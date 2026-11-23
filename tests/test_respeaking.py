"""Re-speaking (core.listening.respeaking; polyglotic-hq 567, decision 0274):
which hold is which on one key, whose a hold is, and a hold's pieces sent
and answered as that source's captions - with the mark carried to the
caption's history, its label and the transcript's saved files."""

import csv
import io
from dataclasses import replace
from datetime import UTC, datetime

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.dictation import ANSWER_WITHIN_SEC, Stage
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.respeaking import (
    TAP_GAP_SEC,
    KeyGesture,
    Respeaking,
    Said,
    Use,
    respoken_for,
)
from polyglotic_desktop.core.listening.sources import (
    DICTATION,
    MIC,
    SAMPLE,
    SourceId,
    SourceLabel,
)
from polyglotic_desktop.core.listening.sources import Source as Heard
from polyglotic_desktop.core.listening.timing import CaptionId, SpeechKind
from polyglotic_desktop.core.listening.transcript import as_csv, as_text
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ui_next.views.captions import Labels

DISCORD = SourceId("app-1")
VIDEO = SourceId("app-2")


# -- one key for both ----------------------------------------------------------------


def test_a_hold_dictates_as_before_and_a_tap_then_a_hold_re_speaks() -> None:
    key = KeyGesture()
    assert key.down(10.0, dictation=True, respeaking=True) is Use.DICTATE
    assert key.up(12.0) == (Use.DICTATE, False)
    assert key.down(13.0, True, True) is Use.DICTATE  # a tap...
    assert key.up(13.1) == (Use.DICTATE, True)
    assert key.down(13.1 + TAP_GAP_SEC - 0.05, True, True) is Use.RESPEAK  # a hold
    assert key.up(16.0) == (Use.RESPEAK, False)
    assert key.down(16.1, True, True) is Use.DICTATE  # a hold after it: dictation


def test_a_hold_too_long_after_a_tap_dictates() -> None:
    key = KeyGesture()
    key.down(1.0, True, True)
    key.up(1.1)
    assert key.down(1.1 + TAP_GAP_SEC + 0.05, True, True) is Use.DICTATE


def test_repeated_key_down_while_held_is_ignored() -> None:
    """Auto-repeat down events while held must not restart or switch the hold (651)."""
    key = KeyGesture()
    key.down(1.0, True, True)
    key.up(1.1)  # tap
    assert key.down(1.2, True, True) is Use.RESPEAK
    assert key.down(1.5, True, True) is None
    assert key.down(2.0, True, True) is None
    assert key.up(2.1) == (Use.RESPEAK, False)


def test_with_one_of_them_off_every_hold_is_the_other_s() -> None:
    key = KeyGesture()
    assert key.down(1.0, dictation=False, respeaking=True) is Use.RESPEAK
    key.up(2.0)
    key.down(3.0, dictation=True, respeaking=False)
    key.up(3.1)  # a tap
    assert key.down(3.2, dictation=True, respeaking=False) is Use.DICTATE
    key.up(4.0)
    assert key.down(5.0, dictation=False, respeaking=False) is None
    assert key.up(6.0) == (None, False)


# -- whose ---------------------------------------------------------------------------


def test_it_is_for_the_watched_captured_source_never_the_mic() -> None:
    captured = (MIC, DISCORD, VIDEO)
    assert respoken_for(captured, [MIC, VIDEO, DISCORD]) == VIDEO
    assert respoken_for(captured, [DISCORD, VIDEO]) == DISCORD
    assert respoken_for(captured, []) == DISCORD  # nobody yet: the first
    assert respoken_for((MIC, SAMPLE), [MIC]) == SAMPLE  # Home's sample counts
    gone = SourceId("app-9")
    assert respoken_for(captured, [gone]) == DISCORD  # gone now


def test_with_nothing_else_captioned_it_s_for_no_one() -> None:
    assert respoken_for((MIC, DICTATION), [MIC]) is None
    assert respoken_for((), []) is None


# -- a hold --------------------------------------------------------------------------

CALL = Heard(DISCORD, SourceCategory.CALL)


def ids() -> Respeaking:
    count = iter(range(1, 100))
    return Respeaking(new_id=lambda: f"r{next(count)}")


def finished(caption_id: str, text: str = "我们明天见") -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption_id),
        DISCORD,
        CaptionKind.FINISHED,
        (Clause(text, {Language("en"): "See you tomorrow"}),),
        Language("zh"),
    )


def test_a_hold_is_sent_as_a_finished_caption_of_the_source_it_s_for() -> None:
    """As theirs on the wire: their id and category, so the server hears it
    in their language, translates it into their targets and doesn't drop
    it as mic bleed."""
    holds = ids()
    assert holds.press(10.0, CALL)
    assert holds.stage is Stage.LISTENING
    assert holds.release(12.0)
    request = holds.cut(10.0, 12.2, 12.3, last=True)
    assert request.source == CALL
    assert request.kind is SpeechKind.FINISHED
    assert (request.speech_start, request.speech_end) == (10.0, 12.2)
    assert holds.is_respoken(request.caption_id)
    assert not holds.is_respoken(CaptionId("theirs"))
    assert holds.stage is Stage.WORKING
    assert holds.answer(finished("r1"))
    assert holds.stage is Stage.IDLE and holds.said is Said.RESPOKEN
    assert holds.is_respoken(CaptionId("r1"))  # still marked once answered


def test_with_no_one_to_re_speak_for_the_mic_stays_closed() -> None:
    holds = ids()
    assert not holds.press(1.0, None)
    assert holds.said is Said.NO_SOURCE and holds.stage is Stage.IDLE


def test_a_tap_sends_nothing() -> None:
    holds = ids()
    holds.press(1.0, CALL)
    assert not holds.release(1.1)
    assert holds.said is Said.TOO_SHORT


def test_nothing_heard_is_said() -> None:
    holds = ids()
    holds.press(1.0, CALL)
    holds.release(3.0)
    holds.cut(1.0, 3.0, 3.1, last=True)
    holds.answer(CaptionUpdate(CaptionId("r1"), DISCORD, CaptionKind.WITHDRAWN))
    assert holds.said is Said.NOTHING_HEARD
    holds.press(4.0, CALL)
    holds.release(6.0)
    holds.nothing_cut(last=True, mic_failed=True)
    assert holds.said is Said.NO_MIC


def test_a_finished_answer_with_a_blank_clause_is_still_a_recognition_miss() -> None:
    holds = ids()
    holds.press(0.0, CALL)
    holds.release(2.0)
    holds.cut(0.0, 2.0, 2.0, last=True)
    assert holds.answer(finished("r1", "  "))
    assert holds.said is Said.NOTHING_HEARD


def test_a_long_hold_s_pieces_all_answer_before_it_s_over() -> None:
    holds = ids()
    holds.press(0.0, CALL)
    holds.cut(0.0, 30.0, 30.0, last=False)  # cut while held
    holds.release(40.0)
    holds.answer(finished("r1"))
    assert holds.stage is Stage.WORKING  # its last piece isn't in yet
    holds.cut(30.0, 40.2, 40.3, last=True)
    holds.answer(finished("r2"))
    assert holds.said is Said.RESPOKEN


def test_esc_no_answer_and_no_server_give_it_up() -> None:
    holds = ids()
    holds.press(0.0, CALL)
    assert holds.cancel()
    assert holds.said is Said.CANCELLED
    holds.press(1.0, CALL)
    holds.release(3.0)
    holds.cut(1.0, 3.0, 3.0, last=True)
    assert not holds.overdue(3.0 + ANSWER_WITHIN_SEC - 1)
    assert holds.overdue(3.0 + ANSWER_WITHIN_SEC + 0.1)
    assert holds.said is Said.NO_ANSWER
    holds.press(20.0, CALL)
    assert holds.cancel(Said.NO_SERVER) and holds.said is Said.NO_SERVER
    assert not holds.cancel()  # nothing under way


def test_its_answers_only_and_live_updates_aside() -> None:
    holds = ids()
    holds.press(0.0, CALL)
    holds.release(2.0)
    holds.cut(0.0, 2.0, 2.0, last=True)
    assert not holds.answer(finished("theirs"))
    live = CaptionUpdate(CaptionId("r1"), DISCORD, CaptionKind.LIVE, (Clause("我"),))
    assert not holds.answer(live)
    assert holds.stage is Stage.WORKING


# -- marked as theirs, re-spoken -------------------------------------------------------

AT = datetime(2026, 11, 20, 11, 0, tzinfo=UTC)


def history_with(respoken: bool) -> CaptionHistory:
    history = CaptionHistory(clock=lambda: AT)

    history.apply(replace(finished("r1"), respoken=respoken))
    return history


def test_the_mark_is_kept_in_the_history_as_theirs() -> None:
    (caption,) = history_with(True).captions
    assert caption.respoken and not caption.by_you and caption.source_id == DISCORD
    (plain,) = history_with(False).captions
    assert not plain.respoken


def test_its_label_names_whose_and_that_it_was_re_spoken() -> None:
    """Even with each caption's source hidden: whose it is shows."""
    (caption,) = history_with(True).captions
    labels = Labels({DISCORD: SourceLabel("Discord", "#4dd0e1")}, respoken="re-spoken")
    assert labels.of(caption) == ("Discord  re-spoken", "#4dd0e1")
    (plain,) = history_with(False).captions
    assert labels.of(plain) == ("", "")


def test_the_transcript_saves_it_as_theirs_marked_re_spoken() -> None:
    (caption,) = history_with(True).captions
    names = {DISCORD: "Discord"}
    text = as_text([caption], [Language("en")], sources=names)
    assert text.startswith("[11:00:00] Discord (re-spoken): 我们明天见")
    assert as_text([caption], [Language("en")]).startswith(
        "[11:00:00] (re-spoken): 我们明天见"
    )
    rows = list(csv.reader(io.StringIO(as_csv([caption], [Language("en")]))))
    assert rows[0][:4] == ["time", "you", "source", "respoken"]
    assert rows[1][1] == "no" and rows[1][3] == "yes"
