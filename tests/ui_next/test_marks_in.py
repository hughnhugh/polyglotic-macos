"""The learner's words are marked in the line that is in the language
being learned (polyglotic-hq 526; the user, 2026-11-19: with English
learned too, an English translation of Mandarin speech had its words
highlighted) - with an option for both lines, or what was said only."""

from dataclasses import replace

from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.views.caption_window import (
    CaptionLook,
    MarksIn,
    rows_marked,
)
from polyglotic_desktop.ui_next.views.panels import LookView

# a caption's rows: (clause, is what was said, its language is learned)
BOTH_LEARNED = [(0, True, True), (0, False, True), (1, True, True), (1, False, True)]
TRANSLATION_LEARNED = [(0, True, False), (0, False, True)]
MIXED = [(0, True, True), (0, False, True), (1, True, False), (1, False, True)]


def test_by_default_only_the_line_in_the_language_being_learned_is_marked() -> None:
    assert MarksIn.LEARNED is CaptionLook().marks_in
    # Mandarin speech, English translation, both learned: what was said
    assert rows_marked(BOTH_LEARNED, MarksIn.LEARNED) == {0, 2}
    # speech in a language not learned, translated into one that is
    assert rows_marked(TRANSLATION_LEARNED, MarksIn.LEARNED) == {1}
    # clause by clause: a clause said in another language is marked in its translation
    assert rows_marked(MIXED, MarksIn.LEARNED) == {0, 3}


def test_both_lines_and_what_was_said_only_are_choices() -> None:
    assert rows_marked(BOTH_LEARNED, MarksIn.BOTH) == {0, 1, 2, 3}  # as before 526
    assert rows_marked(MIXED, MarksIn.BOTH) == {0, 1, 3}
    assert rows_marked(BOTH_LEARNED, MarksIn.SAID) == {0, 2}
    assert rows_marked(TRANSLATION_LEARNED, MarksIn.SAID) == set()


def test_a_row_in_a_language_not_learned_is_never_marked() -> None:
    nothing = [(0, True, False), (0, False, False)]
    for where in MarksIn:
        assert rows_marked(nothing, where) == set()


def test_the_choice_is_kept_and_read_leniently() -> None:
    assert AppSettings().marks_in == "learned"
    kept = AppSettings.from_stored(replace(AppSettings(), marks_in="both").to_stored())
    assert kept.marks_in == "both"
    assert AppSettings.from_stored({"marks_in": "everywhere"}).marks_in == "learned"


def test_look_changes_it() -> None:
    view = LookView(CaptionLook())
    view.set_marks_in(MarksIn.SAID)
    assert view.value.marks_in is MarksIn.SAID
