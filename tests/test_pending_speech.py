"""Speech waiting to be sent, latest wins (core.listening.pending).

Ported from the proof of concept's test_segment_executor.py
(`master-polyglotic`): finished captions first, only the newest live update
per caption section, and none overtaken by its caption's finished speech.
"""

from polyglotic_desktop.core.listening.pending import PendingSpeech
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    SpeechKind,
    TranscriptionRequest,
    WithdrawalReason,
    WithdrawCaption,
)
from polyglotic_desktop.ports.capture import SourceCategory

APP = Source(SourceId("source-1"), SourceCategory.VIDEO)


def live(caption: str, section: int = 0) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(caption), SpeechKind.LIVE, APP, 0.0, 1.0, section=section
    )


def finished(caption: str, replaces: tuple[str, ...] = ()) -> TranscriptionRequest:
    ids = tuple(CaptionId(c) for c in replaces)
    return TranscriptionRequest(
        CaptionId(caption), SpeechKind.FINISHED, APP, 0.0, 1.0, replaces=ids
    )


def drain(pending: PendingSpeech[str]) -> list[str]:
    out = []
    while (item := pending.take()) is not None:
        out.append(item[1])
    return out


def test_finished_first_then_only_the_newest_live_update() -> None:
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(live("g1"), "g1 v1")
    pending.put(live("g1"), "g1 v2")
    pending.put(live("g2"), "g2 live")
    pending.put(finished("g2"), "g2 finished")
    pending.put(finished("other"), "other")
    assert len(pending) == 3
    assert drain(pending) == ["g2 finished", "other", "g1 v2"]


def test_each_live_section_waits_separately() -> None:
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(live("g1", 0), "section 0")
    pending.put(live("g1", 1), "section 1")
    assert drain(pending) == ["section 0", "section 1"]


def test_a_newer_live_update_takes_its_turn_at_the_back() -> None:
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(live("g1"), "g1 v1")
    pending.put(live("g2"), "g2 v1")
    pending.put(live("g1"), "g1 v2")
    assert drain(pending) == ["g2 v1", "g1 v2"]


def test_a_joined_caption_cancels_the_live_updates_it_replaces() -> None:
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(live("g2"), "g2 live")
    pending.put(live("g3"), "g3 live")
    pending.put(finished("g1", replaces=("g2",)), "g1 joined")
    assert drain(pending) == ["g1 joined", "g3 live"]


def test_a_withdrawal_cancels_its_live_updates_and_goes_in_order() -> None:
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(live("g1"), "g1 live")
    pending.put(finished("g0"), "g0 finished")
    pending.put(
        WithdrawCaption(CaptionId("g1"), APP, WithdrawalReason.MIC_BLEED),
        "g1 withdrawn",
    )
    assert drain(pending) == ["g0 finished", "g1 withdrawn"]
    assert pending.take() is None


def ended_at(caption: str, end: float) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(caption), SpeechKind.FINISHED, APP, end - 2.0, end
    )


def test_finished_speech_waiting_behind_two_minutes_of_newer_speech_is_dropped() -> (
    None
):
    """A long outage (polyglotic-hq 165): what waited longer than the server
    keeps a lost session isn't sent minutes late; the rest goes in order."""
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(ended_at("old", 100.0), "old")
    pending.put(ended_at("edge", 130.0), "edge")
    pending.put(ended_at("new", 250.0), "new")  # 150s after "old", 120 after "edge"
    assert drain(pending) == ["edge", "new"]
    assert pending.dropped == 1
    # its finished caption won't come: its live caption ends (557)
    assert pending.take_dropped() == ["old"] and pending.take_dropped() == []


def test_a_short_outage_keeps_every_finished_caption() -> None:
    pending: PendingSpeech[str] = PendingSpeech()
    for i in range(12):  # two minutes' speech, a caption every 10s
        pending.put(ended_at(f"c{i}", 100.0 + 10 * i), f"c{i}")
    pending.put(WithdrawCaption(CaptionId("w"), APP, WithdrawalReason.MIC_BLEED), "w")
    assert drain(pending) == [f"c{i}" for i in range(12)] + ["w"]
    assert pending.dropped == 0


def test_a_long_outage_never_holds_more_than_two_minutes_of_finished_speech() -> None:
    """Nothing is taken while the connection is down: what waits is bounded
    as it comes, not only once it's taken (polyglotic-hq 165)."""
    pending: PendingSpeech[str] = PendingSpeech()
    for i in range(180):  # half an hour of speech, a caption every 10s
        pending.put(ended_at(f"c{i}", 100.0 + 10 * i), f"c{i}")
    assert len(pending) == 13  # the newest 120s: 12 intervals, 13 captions
    assert pending.dropped == 167


def test_cleared_nothing_waits() -> None:
    """Dictation gave its pieces up (polyglotic-hq 299): none is sent."""
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(finished("d1"), "d1")
    pending.put(live("g1"), "g1")
    pending.clear()
    assert len(pending) == 0 and drain(pending) == []


def test_nothing_is_held_through_a_planned_maintenance_window() -> None:
    """polyglotic-hq 319: what waits is dropped as the window's wait begins,
    and so is what comes during it - counted - then holding resumes, in
    order, with what's said after."""
    pending: PendingSpeech[str] = PendingSpeech()
    pending.put(finished("f1"), "f1")
    pending.put(live("g1"), "g1")
    pending.hold(False)
    assert len(pending) == 0 and pending.dropped == 1
    pending.put(finished("f2"), "f2")
    pending.put(live("g2"), "g2")
    assert len(pending) == 0 and pending.dropped == 2  # live updates aren't counted
    assert pending.take_dropped() == ["f1", "f2"]  # their live captions end (557)
    pending.hold(True)
    pending.put(finished("f3"), "f3")
    pending.put(finished("f4"), "f4")
    assert drain(pending) == ["f3", "f4"]
