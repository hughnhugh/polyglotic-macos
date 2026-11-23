"""Saving a selection as a sentence (polyglotic-hq 459; the user,
2026-11-14: "a sentence could span across multiple lines, when
highlighting very large lines that span across multiple caption
translation, it will still work"): the selection's rows made into parts -
the side dragged across as selected, the other whole, links kept and
renumbered, each line's speaker - then the card a caption window offers
under it, and the transcript's menu. Real windows, offscreen; made-up
captions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtWidgets import QApplication, QMenu
from tests.ui_next import test_lookup_card as cards
from tests.ui_next.test_copy_from_the_transcript import drag as transcript_drag
from tests.ui_next.test_lookup_card import window
from tests.ui_next.test_select_captions import (
    MEANT,
    SAID,
    drag,
    last_two,
    point,
)
from tests.ui_next.test_transcript_lookup import both, find, listed

from polyglotic_desktop.core.learning.sentences import SentenceLink, SentencePart
from polyglotic_desktop.core.listening.captions import Clause, Language, WordLink
from polyglotic_desktop.core.listening.display import CaptionRow, LinkedWords
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.sentence_card import GAP, placed
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.sentences import (
    Selected,
    selected_sentence,
    sides_aloud,
    worth_saving,
)

windows = cards.windows  # a window of 40 made-up captions
keys = cards.keys
problem = cards.problem
__all__ = ["both", "keys", "problem", "windows"]  # the fixtures, shared

AT = datetime(2026, 11, 17, tzinfo=UTC)


def line(key: int, by_you: bool, *rows: CaptionRow) -> Line:
    return Line(key, SourceId("app"), by_you, rows, False, False, AT)


FIRST = line(
    1,
    False,
    CaptionRow("我今天去超市。", SAID, Language("zh"), 0, True,
               (LinkedWords(4, 6, 0), LinkedWords(0, 1, 1, key=False))),
    CaptionRow("I went to the supermarket today.", MEANT, Language("en"), 0, False,
               (LinkedWords(14, 25, 0), LinkedWords(0, 1, 1, key=False))),
    CaptionRow("买水果", SAID, Language("zh"), 1, True, (LinkedWords(1, 3, 2),)),
    CaptionRow("to buy fruit", MEANT, Language("en"), 1, False, (LinkedWords(7, 12, 2),)),
)  # fmt: skip
SECOND = line(
    2,
    True,
    CaptionRow("好吃吗", SAID, Language("zh"), 0, True),
    CaptionRow("Is it good?", MEANT, Language("en"), 0, False),
)


def speaker(found: Line) -> str:
    return "You" if found.by_you else "Discord"


def test_the_side_dragged_across_as_selected_the_other_whole() -> None:
    # from 去 in the first caption's first clause to 吗's start, said only
    pieces = [
        (FIRST, FIRST.rows[0], 3, 7),
        (FIRST, FIRST.rows[2], 0, 3),
        (SECOND, SECOND.rows[0], 0, 2),
    ]
    found = selected_sentence(pieces, speaker)
    assert found is not None
    assert [p.original for p in found.parts] == ["去超市。", "买水果", "好吃"]
    assert [p.translation for p in found.parts] == [
        "I went to the supermarket today.", "to buy fruit", "Is it good?",
    ]  # fmt: skip
    # 超市 -> supermarket kept, from where the kept text starts; 我 was cut off
    assert found.parts[0].links == (SentenceLink((1, 3), (14, 25)),)
    assert found.parts[1].links == (SentenceLink((1, 3), (7, 12)),)
    assert [p.speaker for p in found.parts] == ["Discord", "Discord", "You"]
    assert found.original == "去超市。买水果好吃"
    assert (
        found.translation == "I went to the supermarket today. to buy fruit Is it good?"
    )
    assert (found.language, found.translation_language) == ("zh", "en")


def test_a_translation_dragged_across_keeps_its_originals_whole() -> None:
    found = selected_sentence([(FIRST, FIRST.rows[1], 7, 25)], speaker)
    assert found is not None
    (part,) = found.parts
    assert (part.original, part.translation) == ("我今天去超市。", "to the supermarket")
    assert part.links == (SentenceLink((4, 6), (7, 18)),)


def test_both_sides_held_and_nothing_but_spaces() -> None:
    both = selected_sentence([(SECOND, SECOND.rows[0], 0, 3), (SECOND, SECOND.rows[1], 0, 11)], speaker)  # fmt: skip
    assert (
        both is not None
        and both.original == "好吃吗"
        and both.translation == "Is it good?"
    )
    spaces = line(3, False, CaptionRow("  ", SAID, Language("zh"), 0, True))
    assert selected_sentence([(spaces, spaces.rows[0], 0, 2)], speaker) is None


def sentence(original: str, parts: int = 1) -> Selected:
    return Selected(
        tuple(SentencePart(original) for _ in range(parts)), original, "", "zh", ""
    )


def test_more_than_a_word_is_worth_saving() -> None:
    assert worth_saving(sentence("我今天去超市"))
    assert not worth_saving(sentence("超市"))
    assert worth_saving(sentence("go home"))
    assert not worth_saving(sentence("home"))
    assert worth_saving(sentence("超市", parts=2))
    assert not worth_saving(None)


def test_the_card_goes_at_the_mouse_or_above_it_and_stays_on_the_screen() -> None:
    """At the mouse, where the drag let go (522: the user, 2026-11-18, "too
    low from selection, should appear on mouse")."""
    area = QRect(0, 0, 1000, 800)
    assert placed(QPoint(100, 100), (200, 40), area) == QPoint(100, 106)
    assert placed(QPoint(100, 780), (200, 40), area) == QPoint(100, 734)
    assert placed(QPoint(900, 100), (200, 40), area) == QPoint(800, 106)


# -- in a caption window ---------------------------------------------------------


def test_a_drag_across_captions_offers_it_and_a_category_saves_it(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    end = point(shown_, second.key, SAID, 2)
    drag(shown_, point(shown_, first.key, SAID, 0), end)
    offered = shown_.sentence_card
    assert offered is not None and offered.isVisible()
    assert not offered.isActiveWindow()  # never takes the keyboard
    # at the mouse, where the drag let go - not under the caption (522)
    let_go = shown_.mapToGlobal(end.toPoint())
    assert offered.geometry().adjusted(-GAP, -GAP, GAP, GAP).contains(let_go)
    vocabulary = cards.tools(windows).vocabulary
    assert vocabulary.sentences == []
    tricky = next(b for b in offered.buttons if b.objectName().endswith("tricky"))
    tricky.click()  # its click doesn't let go of the selection
    (kept,) = vocabulary.sentences
    assert kept.category_id == "tricky"
    assert len(kept.parts) >= 2  # across two captions
    assert kept.original.startswith(first.rows[0].text[:2])
    assert offered.said.text() == "Saved to Tricky"
    assert shown_.held.selection is not None
    offered.hide()


def test_a_single_word_or_a_double_click_offers_nothing(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    _, second = last_two(shown_)
    drag(shown_, point(shown_, second.key, SAID, 0), point(shown_, second.key, SAID, 1))
    assert shown_.sentence_card is None or not shown_.sentence_card.isVisible()


def test_more_than_a_word_in_one_clause_gets_the_card_alone(
    windows: CaptionWindows,
) -> None:
    """A drag within a clause across more than a word: the sentence card,
    and no lookup card over it (522: the user, 2026-11-18, "both modals
    overlapping each other, can't see play sentence"). Three characters
    or fewer still pin their lookup (test_lookup_card)."""
    shown_, shared = window(windows), cards.card(windows)
    _, start = cards.find(shown_, "画")
    _, end = cards.find(shown_, "漂亮")
    drag(shown_, start, QPointF(end.x() + 4, end.y()))  # 画面很漂: four
    offered = shown_.sentence_card
    assert offered is not None and offered.isVisible()
    assert not shared.isVisible()
    assert shown_.held.selection is not None  # held: a right-click copies it
    offered.hide()


def test_a_phrase_in_one_clause_is_looked_up_from_the_card(
    windows: CaptionWindows,
) -> None:
    """The sentence card's "Look it up" (533): a set phrase of four
    characters or more (一石二鳥) gets the sentence card, not a lookup
    (522), so the card looks it up - and goes, the lookup card in its
    place, never both at once."""
    shown_, shared = window(windows), cards.card(windows)
    _, start = cards.find(shown_, "画")
    _, end = cards.find(shown_, "漂亮")
    drag(shown_, start, QPointF(end.x() + 4, end.y()))  # 画面很漂: four
    offered = shown_.sentence_card
    assert offered is not None and offered.isVisible()
    assert offered.look_up.isVisible() and offered.look_up.text() == "Look it up"
    assert not shared.isVisible()
    offered.look_up.click()
    assert not offered.isVisible()
    assert shared.isVisible() and shared.pinned
    assert shared.model.word == "画面很漂"
    assert shown_.held.selection is not None  # still held: a right-click copies it
    shared.close_card()


def test_a_selection_across_captions_has_no_look_it_up(
    windows: CaptionWindows,
) -> None:
    """Across clauses or captions there's no one phrase to look up."""
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 2))
    offered = shown_.sentence_card
    assert offered is not None and offered.isVisible()
    assert not offered.look_up.isVisible()
    offered.hide()


def test_esc_lets_go_of_the_selection_and_the_card(windows: CaptionWindows) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 2))
    assert shown_.sentence_card is not None and shown_.sentence_card.isVisible()
    shown_.held.clear()  # what Esc and a click elsewhere do
    QApplication.processEvents()
    assert not shown_.sentence_card.isVisible()


# -- in a transcript --------------------------------------------------------------


def test_the_transcripts_menu_saves_what_is_selected(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    shown_ = listed(both[1])
    _, start = find(shown_, "电脑")
    _, end = find(shown_, "游戏")
    transcript_drag(shown_, start, end)
    menu = shown_.menu_at(start.y())
    assert menu is not None
    into = cast(QMenu, menu.actions()[-1].menu())
    assert into is not None and menu.actions()[-1].text() == "Save sentence to"
    saved = next(a for a in into.actions() if a.text() == "Saved")
    saved.trigger()
    vocabulary = both[0].learner.vocabulary  # type: ignore[union-attr]
    (kept,) = vocabulary.sentences
    assert kept.category_id == "saved" and "电脑" in kept.original
    assert kept.translation  # each line's translation came with it
    menu.deleteLater()


def test_a_saved_sentence_keeps_the_windows_marks(windows: CaptionWindows) -> None:
    """Saving one marks nothing in the captions: their marks aren't worked
    out again (the marks' cache stays)."""
    shown_ = window(windows)
    assert shown_.marks._kept  # worked out as they were painted
    assert not shown_.marks.learning_changed("sentences")
    assert shown_.marks._kept
    assert shown_.marks.learning_changed("saved_words")


def test_the_captions_own_links_are_kept_even_where_the_window_shows_none() -> None:
    """Word links off, or only those past what the learner knows: the rows
    show none, but the sentence keeps every link its caption had (459's
    first real-caption run saved none)."""
    shown = line(
        5, False,
        CaptionRow("我今天去超市。", SAID, Language("zh"), 0, True),
        CaptionRow("I went to the supermarket today.", MEANT, Language("en"), 0, False,
                   target=Language("en")),
    )  # fmt: skip
    clause = Clause(
        "我今天去超市。",
        {Language("en"): "I went to the supermarket today."},
        {Language("en"): (WordLink((4, 6), (14, 25), True, 0.9),)},
    )
    captions = {5: cast(Caption, SimpleNamespace(clauses=(clause,)))}
    found = selected_sentence([(shown, shown.rows[0], 2, 7)], speaker, captions.get)
    assert found is not None
    assert found.parts[0].links == (SentenceLink((2, 4), (14, 25)),)
    # without the caption: what the rows show - none here
    alone = selected_sentence([(shown, shown.rows[0], 2, 7)], speaker)
    assert alone is not None and alone.parts[0].links == ()


def test_say_it_reads_each_language_from_whichever_row_is_in_it() -> None:
    """The user, 2026-11-18: dragging across a Chinese caption (English
    under it) and an English one (Chinese under it), "Say it in Chinese"
    read the first row of each - Chinese then English. Each side is now a
    language: its row from every clause, said or translated."""
    zh_first = line(
        1,
        False,
        CaptionRow("我今天去超市。", SAID, Language("zh"), 0, True),
        CaptionRow("I went to the supermarket today.", MEANT, Language("en"), 0, False),
    )
    en_first = line(
        2,
        False,
        CaptionRow("What am I doing?", SAID, Language("en"), 0, True),
        CaptionRow("我在干嘛？", MEANT, Language("zh"), 0, False),
    )
    pieces = [(zh_first, zh_first.rows[0], 0, 7), (en_first, en_first.rows[0], 0, 16)]
    sides = sides_aloud(pieces)
    assert [s.language for s in sides] == ["zh", "en"]
    zh, en = sides
    assert [st.text for st in zh.stretches] == ["我今天去超市。", "我在干嘛？"]
    assert [st.text for st in en.stretches] == [
        "I went to the supermarket today.",
        "What am I doing?",
    ]
    assert [w.side for _, w in zh.shown] == [SAID, MEANT]  # each lit where it is
