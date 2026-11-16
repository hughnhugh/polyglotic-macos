"""A listening session's summary (core.listening.summary), and its event.

Caption delay as seen, minutes, captions and the main source category;
rewrite and erasure rates from live updates against finished captions
(by character for Chinese, by word otherwise); dropped captions - late,
failed, or never answered; reconnects; and the tracking plan's
`listening_session_ended` properties, exactly the server's example's.
"""

import pytest
from tests.test_protocol import example

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.summary import (
    ListeningSessionEnded,
    SessionSummary,
    words,
)
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    CaptionMode,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.ports.capture import SourceCategory

VIDEO = Source(SourceId("app"), SourceCategory.VIDEO)
MIC = Source(SourceId("mic"), SourceCategory.MIC)
EN = Language("en")


def finished(
    caption: str,
    start: float,
    end: float,
    source: Source = VIDEO,
    replaces: tuple[str, ...] = (),
) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(caption),
        SpeechKind.FINISHED,
        source,
        start,
        end,
        replaces=tuple(CaptionId(r) for r in replaces),
    )


def update(
    caption: str,
    kind: CaptionKind,
    text: str = "",
    translation: str = "",
    replaces: tuple[str, ...] = (),
) -> CaptionUpdate:
    clauses = (Clause(text, {EN: translation}),) if text else ()
    return CaptionUpdate(
        CaptionId(caption),
        SourceId("app"),
        kind,
        clauses,
        replaces=tuple(CaptionId(r) for r in replaces),
    )


def test_words_count_chinese_by_character() -> None:
    assert words("你好，今天天气") == {"你": 1, "好": 1, "今": 1, "天": 2, "气": 1}
    assert words("Hello, today's weather") == {
        "hello": 1,
        "today": 1,
        "s": 1,
        "weather": 1,
    }


def test_delay_minutes_captions_and_the_main_source() -> None:
    summary = SessionSummary(live_interval=1.5, target=EN)
    for n, (end, back, source) in enumerate(
        [
            (10.0, 11.2, VIDEO),
            (20.0, 21.0, VIDEO),
            (30.0, 32.0, MIC),
            (40.0, 41.1, VIDEO),
        ]
    ):
        caption = f"c{n}"
        summary.speech_sent(finished(caption, end - 6.0, end, source), at=end + 0.8)
        summary.caption_updated(update(caption, CaptionKind.FINISHED, "好"), at=back)
    ended = summary.ended(at=50.0)
    assert (ended.captions, ended.speech_minutes) == (4, 0.4)
    assert ended.source_category is SourceCategory.VIDEO
    assert (ended.delay_p50_ms, ended.delay_p95_ms) == (1100, 2000)
    assert (ended.dropped, ended.reconnects, ended.live_interval_seconds) == (0, 0, 1.5)
    assert ended.caption_mode == "live"


def test_the_caption_mode_is_steady_when_live_updates_are_off() -> None:
    """Without a mode given: with live updates off, only finished
    captions are shown - steady (059, Low 8). Whether anything was
    captioned or not."""
    assert SessionSummary(live_interval=None).ended(5.0).caption_mode == "steady"
    assert SessionSummary(live_interval=1.5).ended(5.0).caption_mode == "live"
    summary = SessionSummary(live_interval=None, target=EN)
    summary.speech_sent(finished("c1", 0.0, 3.0), at=3.8)
    summary.caption_updated(update("c1", CaptionKind.FINISHED, "好"), at=4.5)
    ended = summary.ended(at=10.0)
    assert (ended.captions, ended.caption_mode) == (1, "steady")
    assert listening.session_ended(ended)["caption_mode"] == "steady"


@pytest.mark.parametrize("mode", list(CaptionMode))
def test_the_caption_mode_is_the_learners(mode: CaptionMode) -> None:
    """The tracking plan's `caption_mode` is the mode the session started
    in - `steady`, `preview` or `live` (project 064) - with or without
    anything captioned."""
    interval = mode.live_update_interval(2.0)
    assert SessionSummary(interval, mode=mode).ended(5.0).caption_mode == mode.value
    summary = SessionSummary(interval, target=EN, mode=mode)
    summary.speech_sent(finished("c1", 0.0, 3.0), at=3.6)
    summary.caption_updated(update("c1", CaptionKind.FINISHED, "好"), at=4.5)
    ended = summary.ended(at=10.0)
    assert (ended.captions, ended.caption_mode) == (1, mode.value)
    assert ended.live_interval_seconds == interval
    assert listening.session_ended(ended)["caption_mode"] == mode.value


def test_rewrites_count_words_shown_live_that_didnt_survive() -> None:
    summary = SessionSummary(live_interval=1.5, target=EN)
    summary.speech_sent(finished("c1", 0.0, 3.0), at=3.8)
    summary.caption_updated(update("c1", CaptionKind.LIVE, "今天天", "Today day"), 1.0)
    summary.caption_updated(
        update("c1", CaptionKind.LIVE, "今天田七", "Today field"), 2.0
    )
    summary.caption_updated(
        update("c1", CaptionKind.FINISHED, "今天天气", "Today's weather"), 4.5
    )
    ended = summary.ended(at=5.0)
    # live: 今天天 (all kept), 今天田七 (田 and 七 not kept); finished has 4 characters
    assert ended.rewrite_ratio == 0.5
    # live: "today day" (day gone), "today field" (field gone); finished: today, s, weather
    assert ended.erasure_ratio == round(2 / 3, 3)


def test_a_join_takes_in_the_live_caption_it_replaces() -> None:
    summary = SessionSummary(live_interval=1.5, target=EN)
    summary.speech_sent(finished("a", 0.0, 2.0), at=2.8)
    summary.caption_updated(update("a", CaptionKind.FINISHED, "你好"), at=3.5)
    summary.caption_updated(update("b", CaptionKind.LIVE, "朋有"), at=4.5)
    summary.speech_sent(finished("a", 0.0, 5.0, replaces=("b",)), at=5.8)
    summary.caption_updated(
        update("a", CaptionKind.FINISHED, "你好朋友", replaces=("b",)), at=6.5
    )
    ended = summary.ended(at=10.0)
    assert ended.captions == 1 and ended.speech_minutes == round(5 / 60, 2)
    assert ended.rewrite_ratio == 0.25  # 有 of 4 characters


def test_withdrawn_captions_dont_count() -> None:
    summary = SessionSummary(live_interval=None)
    summary.speech_sent(finished("a", 0.0, 2.0), at=2.8)
    summary.caption_updated(update("a", CaptionKind.WITHDRAWN), at=3.0)
    ended = summary.ended(at=4.0)
    assert (ended.captions, ended.source_category, ended.speech_minutes) == (
        0,
        None,
        0.0,
    )


def test_a_session_with_nothing_captioned_is_summarised_too() -> None:
    """project 034: the tracking plan takes it (S2b) - its dropped captions
    and reconnects are what such a session has to say. Before, nothing was
    sent."""
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("lost", 0.0, 2.0), at=2.8)
    summary.reconnected()
    ended = summary.ended(at=20.0)
    assert (ended.captions, ended.dropped, ended.reconnects) == (0, 1, 1)
    assert ended.delay_p50_ms is None and ended.delay_p95_ms is None
    props = listening.session_ended(ended)
    assert props == {
        "speech_minutes": 0.0,
        "captions": 0,
        "source_category": "none",
        "caption_mode": "live",
        "rewrite_ratio": 0.0,
        "erasure_ratio": 0.0,
        "dropped": 1,
        "reconnects": 1,
        "live_interval_seconds": 1.5,
        "lookups": 0,
        "saves": 0,
        **NOTHING_DONE,
    }  # no delays: optional in the tracking plan since S2b; no capture: not told


def test_dropped_late_failed_or_never_answered() -> None:
    summary = SessionSummary(live_interval=1.5)
    summary.speech_sent(finished("ok", 0.0, 1.0), at=1.8)
    summary.caption_updated(update("ok", CaptionKind.FINISHED, "ok"), at=2.5)
    summary.speech_sent(finished("late", 2.0, 3.0), at=3.8)
    summary.caption_updated(update("late", CaptionKind.FINISHED, "late"), at=14.0)
    summary.speech_sent(finished("failed", 4.0, 5.0), at=5.8)
    summary.failed(CaptionId("failed"))
    summary.speech_sent(finished("lost", 6.0, 7.0), at=7.8)
    summary.speech_sent(finished("waiting", 8.0, 9.0), at=29.0)
    summary.reconnected()
    ended = summary.ended(at=30.0)
    assert ended.dropped == 3  # late, failed, lost - not the one just sent
    assert ended.reconnects == 1 and ended.captions == 2


NOTHING_DONE = {
    "transcripts_opened": 0,
    "lines_flagged": 0,
    "original_only": False,
    "joined_window": False,
}
"""What the learner did (project 134): always in the summary, 0 or no if nothing."""


def test_the_event_has_exactly_the_tracking_plans_properties() -> None:
    summary = ListeningSessionEnded(
        speech_minutes=18.5,
        captions=212,
        source_category=SourceCategory.VIDEO,
        caption_mode="live",
        delay_p50_ms=1180,
        delay_p95_ms=1720,
        rewrite_ratio=0.21,
        erasure_ratio=0.14,
        dropped=1,
        reconnects=0,
        live_interval_seconds=1.5,
        lookups=6,
        saves=2,
    )
    (_first, expected) = example("usage")["events"]
    assert expected["name"] == listening.SESSION_ENDED
    # the copy from before the server's example counted lookups and saves
    # (polyglotic-server, 051) lacks them; the refreshed copy has these
    counts = {"lookups": 6, "saves": 2}
    assert listening.session_ended(summary) == expected["props"] | counts | NOTHING_DONE
    off = ListeningSessionEnded(**{**summary.__dict__, "live_interval_seconds": None})
    assert "live_interval_seconds" not in listening.session_ended(off)  # optional


def test_lookups_and_saves_are_counted_per_session() -> None:
    """polyglotic-hq DECISIONS.md #20: lookups shown and words saved during
    the session are counts in its summary - the only usage statistics
    about them. Nothing captioned still counts them."""
    summary = SessionSummary(1.5, EN)
    for _ in range(3):
        summary.looked_up()
    summary.saved()
    ended = summary.ended(20.0)
    assert (ended.lookups, ended.saves) == (3, 1)
    props = listening.session_ended(ended)
    assert (props["lookups"], props["saves"]) == (3, 1)
    assert SessionSummary(None).ended(1.0).lookups == 0


def test_the_summary_names_the_platform_and_nothing_more_about_the_pc() -> None:
    """polyglotic-server's tracking plan (051): `platform` - windows, macos,
    linux, android or ios - so the summaries of a later phone app can be
    told apart. Never the OS version."""
    ended = SessionSummary(1.5, EN).ended(5.0)
    assert "platform" not in listening.session_ended(ended)
    props = listening.session_ended(ended, platform="windows")
    assert props["platform"] == "windows"


def test_the_known_app_heard_most_is_named_and_no_other_app() -> None:
    """Known app names (polyglotic-hq DECISIONS.md #30, the user,
    2026-11-05): the summary names the well-known app most of the speech
    came from, by its public name - an app not on the list never, even when
    it was heard most; nothing known, no name."""
    discord = Source(SourceId("app-1"), SourceCategory.CALL, "discord")
    chrome = Source(SourceId("app-2"), SourceCategory.BROWSER, "google-chrome")
    private = Source(SourceId("app-3"), SourceCategory.GAME)  # not on the list
    summary = SessionSummary(live_interval=None)
    for n, (source, seconds) in enumerate(
        [(discord, 4.0), (chrome, 6.0), (private, 20.0), (discord, 3.0)]
    ):
        caption = f"c{n}"
        summary.speech_sent(finished(caption, 0.0, seconds, source), at=seconds)
        summary.caption_updated(update(caption, CaptionKind.FINISHED, "好"), at=seconds)
    ended = summary.ended(at=60.0)
    assert ended.source_category is SourceCategory.GAME  # the most speech
    assert ended.known_app == "discord"  # the known app heard most: 7s
    props = listening.session_ended(ended)
    assert props["known_app"] == "discord"
    assert "Game" not in str(props) and "app-3" not in str(props)

    only_private = SessionSummary(live_interval=None)
    only_private.speech_sent(finished("p", 0.0, 5.0, private), at=5.0)
    only_private.caption_updated(update("p", CaptionKind.FINISHED, "好"), at=5.5)
    unnamed = only_private.ended(at=60.0)
    assert unnamed.known_app is None
    assert "known_app" not in listening.session_ended(unnamed)  # left out


def test_a_known_apps_name_never_goes_with_its_speech() -> None:
    """The speech frame carries the source's id and category only (and its
    own languages, when it has them)."""
    discord = Source(SourceId("app-1"), SourceCategory.CALL, "discord")
    header = listening.speech_header(finished("c1", 0.0, 2.0, discord))
    assert "discord" not in header.model_dump_json()
    assert protocol.dump(header)["source"] == {"id": "app-1", "category": "call"}
