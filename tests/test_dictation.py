"""Dictation's rules (core.listening.dictation, decision 0073): a hold, its
pieces in order, what's typed and what the sign says."""

import itertools

from polyglotic_desktop.core.listening.australian import australian_spelling
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.dictation import (
    ANSWER_WITHIN_SEC,
    DICTATION_LANGUAGES,
    DICTATION_SOURCE,
    Dictation,
    Said,
    Stage,
    ToType,
    dictated_text,
    quietest_cut,
    without_fillers,
)
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import DICTATION, MIC, SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, SpeechKind
from polyglotic_desktop.ports.capture import SourceCategory

EN = Language("en")
ZH = Language("zh")
WINDOW = 0x1234


def ids() -> Dictation:
    counter = itertools.count(1)
    return Dictation(lambda: CaptionId(f"c{next(counter)}"))


def finished(
    caption_id: str, *originals: str, language: Language = EN
) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption_id),
        DICTATION,
        CaptionKind.FINISHED,
        clauses=tuple(Clause(o) for o in originals),
        language=language,
    )


def withdrawn(caption_id: str) -> CaptionUpdate:
    return CaptionUpdate(CaptionId(caption_id), DICTATION, CaptionKind.WITHDRAWN)


# -- a hold --------------------------------------------------------------------------


def test_a_hold_is_one_finished_piece_from_the_mic_sent_when_let_go() -> None:
    d = ids()
    assert d.stage is Stage.IDLE
    assert d.press(10.0)
    assert d.stage is Stage.LISTENING
    assert d.release(12.5)
    assert d.stage is Stage.WORKING  # the last piece comes after the mic's tail
    request = d.cut(9.9, 12.7, 12.7, WINDOW, last=True)
    assert request.kind is SpeechKind.FINISHED
    assert request.source == DICTATION_SOURCE
    assert request.source.category is SourceCategory.MIC
    assert (request.speech_start, request.speech_end) == (9.9, 12.7)
    assert d.answer(finished("c1", "Hello there.")) == [ToType("Hello there. ", WINDOW)]
    assert d.stage is Stage.IDLE
    assert d.said is Said.TYPED


def test_a_stray_tap_sends_nothing() -> None:
    d = ids()
    d.press(1.0)
    assert not d.release(1.2)
    assert d.said is Said.TOO_SHORT
    assert d.stage is Stage.IDLE


def test_a_long_hold_keeps_listening_once_a_piece_is_cut() -> None:
    d = ids()
    d.press(0.0)
    d.cut(0.0, 30.0, 30.0, WINDOW, last=False)
    assert d.stage is Stage.LISTENING
    assert d.answer(finished("c1", "The first part.")) == [
        ToType("The first part. ", WINDOW)
    ]
    assert d.said is None  # still held: the sign says Listening
    assert d.release(31.0)
    assert d.stage is Stage.WORKING


def test_pieces_are_typed_in_order_whatever_order_their_answers_come_in() -> None:
    d = ids()
    d.press(0.0)
    d.cut(0.0, 28.0, 28.0, WINDOW, last=False)  # c1
    d.release(40.0)
    d.cut(28.0, 40.2, 40.2, WINDOW, last=True)  # c2
    assert d.answer(finished("c2", "the second.")) == []  # waits for c1
    assert d.answer(finished("c1", "The first,")) == [
        ToType("The first, ", WINDOW),
        ToType("the second. ", WINDOW),
    ]
    assert d.said is Said.TYPED


def test_a_new_hold_can_start_while_the_last_is_on_its_way() -> None:
    d = ids()
    d.press(0.0)
    d.release(2.0)
    d.cut(0.0, 2.2, 2.2, WINDOW, last=True)  # c1
    assert d.press(2.5)
    assert d.stage is Stage.LISTENING
    assert d.answer(finished("c1", "One.")) == [ToType("One. ", WINDOW)]
    assert d.said is None  # the new hold's sign is Listening, not "typed"
    d.release(4.0)
    d.cut(2.5, 4.2, 4.2, WINDOW, last=True)  # c2
    assert d.answer(finished("c2", "Two.")) == [ToType("Two. ", WINDOW)]
    assert d.said is Said.TYPED


def test_nothing_worth_typing_says_so() -> None:
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    assert d.answer(withdrawn("c1")) == []
    assert d.said is Said.NOTHING_HEARD
    assert d.stage is Stage.IDLE


def test_a_mic_that_gave_nothing_says_nothing_was_heard() -> None:
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.nothing_cut()
    assert d.said is Said.NOTHING_HEARD
    assert d.stage is Stage.IDLE
    d.press(2.0)
    d.release(3.0)
    d.nothing_cut(mic_failed=True)
    assert d.said is Said.NO_MIC


def test_esc_cancels_the_hold_and_whatever_waits() -> None:
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    assert d.cancel()
    assert d.said is Said.CANCELLED
    assert d.stage is Stage.IDLE
    assert d.answer(finished("c1", "Too late.")) == []  # its answer is ignored
    assert not d.cancel()  # nothing left to cancel


def test_esc_while_held_cancels_too() -> None:
    d = ids()
    d.press(0.0)
    assert d.cancel()
    assert d.stage is Stage.IDLE
    assert not d.release(3.0)  # the key coming up afterwards sends nothing


def test_no_answer_in_time_gives_the_pieces_up() -> None:
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    assert not d.overdue(1.2 + ANSWER_WITHIN_SEC - 0.1)
    assert d.overdue(1.2 + ANSWER_WITHIN_SEC)
    assert d.said is Said.NO_ANSWER
    assert d.stage is Stage.IDLE
    assert d.answer(finished("c1", "Late.")) == []


def test_no_server_gives_everything_up_at_once() -> None:
    """The session can't be answered (the server out of reach): what waits
    is given up now, not after `ANSWER_WITHIN_SEC` (polyglotic-hq 299)."""
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    assert d.no_server()
    assert d.said is Said.NO_SERVER
    assert d.stage is Stage.IDLE
    assert d.answer(finished("c1", "Late.")) == []
    assert not d.no_server()  # nothing left
    d.press(2.0)  # while held, too
    assert d.no_server()
    assert d.stage is Stage.IDLE
    assert not d.release(4.0)


def test_live_updates_and_strangers_are_ignored() -> None:
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    live = CaptionUpdate(CaptionId("c1"), DICTATION, CaptionKind.LIVE, (Clause("Hel"),))
    assert d.answer(live) == []
    assert d.answer(finished("someone-else", "Hi.")) == []
    assert d.stage is Stage.WORKING


def test_a_language_set_is_the_texts_whatever_the_server_labels_it() -> None:
    """Set to English, it's typed as English (Australian spelling too) even
    when the server labels the line otherwise; Detect follows the label."""
    d = ids()
    for _ in range(2):
        d.press(0.0)
        d.release(1.0)
        d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    labelled_chinese = finished("c1", "My favorite color.", language=ZH)
    assert d.answer(labelled_chinese, australian=True, chosen=EN) == [
        ToType("My favourite colour. ", WINDOW)
    ]
    detected = finished("c2", "My favorite color.", language=ZH)
    assert d.answer(detected, australian=True) == [
        ToType("My favorite color. ", WINDOW)
    ]


def test_dictation_can_be_set_to_any_language_the_speech_model_takes() -> None:
    assert len(DICTATION_LANGUAGES) == 30 == len(set(DICTATION_LANGUAGES))
    assert DICTATION_LANGUAGES[:3] == ("en", "zh", "yue")


def test_text_that_couldnt_be_typed_is_said() -> None:
    d = ids()
    d.press(0.0)
    d.release(1.0)
    d.cut(0.0, 1.2, 1.2, WINDOW, last=True)
    d.answer(finished("c1", "Hi."))
    d.not_typed(Said.WINDOW_CHANGED)
    assert d.said is Said.WINDOW_CHANGED


# -- the text ------------------------------------------------------------------------


def test_the_clauses_are_joined_with_a_space_after() -> None:
    assert dictated_text(["So I went home,", "and slept."], EN) == (
        "So I went home, and slept. "
    )


def test_chinese_is_joined_without_spaces_and_none_after() -> None:
    assert dictated_text(["我回家了，", "然后睡觉了。"], ZH) == "我回家了，然后睡觉了。"


def test_nothing_left_types_nothing() -> None:
    assert dictated_text([], EN) == ""
    assert dictated_text(["Um."], EN) == ""


def test_english_fillers_on_their_own_go_and_the_capital_comes_back() -> None:
    assert without_fillers("Um, so I think, uh, we should go.") == (
        "So I think, we should go."
    )
    assert without_fillers("Hmm. Erm, yes.") == "Yes."
    # words that only contain a filler stay
    assert without_fillers("The summer umbrella was under her.") == (
        "The summer umbrella was under her."
    )


def test_fillers_stay_in_other_languages() -> None:
    assert dictated_text(["Um, hola."], Language("es")) == "Um, hola. "


def test_australian_spelling_only_when_asked_and_only_for_english() -> None:
    assert dictated_text(["My favorite color."], EN) == "My favorite color. "
    assert dictated_text(["My favorite color."], EN, australian=True) == (
        "My favourite colour. "
    )
    assert dictated_text(["color"], Language("es"), australian=True) == "color "


# -- Australian spelling -------------------------------------------------------------


def test_australian_spelling_of_the_usual_differences() -> None:
    us = (
        "I realized the organization's center was gray, so we traveled to the"
        " theater and analyzed the catalog for our defense."
    )
    assert australian_spelling(us) == (
        "I realised the organisation's centre was grey, so we travelled to the"
        " theatre and analysed the catalogue for our defence."
    )


def test_our_keeps_its_u_only_where_australian_does() -> None:
    assert australian_spelling("colorful neighborhood favorites") == (
        "colourful neighbourhood favourites"
    )
    # these drop the u in Australia too
    assert australian_spelling("humorous honorary laborious vigorous") == (
        "humorous honorary laborious vigorous"
    )


def test_size_prize_and_seize_are_not_ize_endings() -> None:
    words = (
        "size resized oversized capsize downsizing prize seized maize Belize citizen"
    )
    assert australian_spelling(words) == words
    assert australian_spelling("emphasize apologizing") == "emphasise apologising"


def test_words_whose_spelling_depends_on_meaning_are_left_alone() -> None:
    words = "practice license meter check tire program dialog judgment"
    assert australian_spelling(words) == words


def test_case_is_kept() -> None:
    assert australian_spelling("Color COLOR color") == "Colour COLOUR colour"


# -- cutting a long hold ------------------------------------------------------------


def test_a_long_hold_is_cut_at_its_quietest_moment_near_the_end() -> None:
    step = 0.1
    levels = [0.5] * 300  # 30 s
    levels[100] = 0.0  # quiet, but long before the last 4 s
    levels[280] = 0.05
    levels[290] = 0.05  # as quiet: the later one
    assert quietest_cut(levels, step) == 290
    assert quietest_cut([], step) == 0


# -- dictation's languages on the session -------------------------------------------


def test_dictation_never_makes_the_session_original_only() -> None:
    chosen = ListeningSettings(
        targets=(EN,),
        source_targets={SourceId("app"): (EN,), DICTATION: ()},
    )
    assert not chosen.original_only
    assert chosen.targets_of(DICTATION) == ()
    assert ListeningSettings(source_targets={MIC: (), DICTATION: ()}).original_only
