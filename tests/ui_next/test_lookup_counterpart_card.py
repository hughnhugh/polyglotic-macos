"""The card's "Here:" line drawn (polyglotic-hq 328): from a caption
window and from a transcript, the label faint and the words in the card's
text colour, none for a word with no link, larger where the row has no
dictionary, and a hover card wide enough for it. Offscreen, made-up
captions, the sample dictionary."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_lookup_card import (
    card,
    click,
    find,
    keys,
    problem,
    window,
    windows,
)
from tests.ui_next.test_lookup_view import learner
from tests.ui_next.test_transcript_lookup import both, click_list, listed
from tests.ui_next.test_transcript_lookup import find as find_in_transcript

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.listening.captions import CaptionKind
from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.ui.recorded_captions import clause, finished, live
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.lookup_card import (
    FAINT,
    HOVER_WIDTHS,
    TEXT,
    WIDTH,
    LookupCard,
    _Painted,
    here,
)
from polyglotic_desktop.ui_next.transcripts import Transcripts

__all__ = ["both", "keys", "problem", "windows"]  # fixtures, from the cards' tests


def _here(painted: _Painted) -> list[str]:
    return [
        b.layout.text() for b in painted.blocks if b.layout.text().startswith("Here")
    ]


@pytest.fixture
def shown_card(qapp: QApplication) -> Iterator[LookupCard]:
    found = LookupCard(learner())
    yield found
    found.close()
    found.deleteLater()


def test_a_word_clicked_in_a_caption_window_says_its_counterpart(
    windows: CaptionWindows,
) -> None:
    """With word links off (the Look's default) nothing is drawn, and the
    card still says it: what's drawn never decides (323 thins it)."""
    shown, shared = window(windows), card(windows)
    assert shown.look.word_links is WordLinks.OFF
    _, point = find(shown, "电脑")
    click(shown, point)
    assert shared.request is not None
    assert shared.request.context.counterpart == "computer"
    assert shared.request.context.counterpart_language == "en"
    assert _here(shared._painted) == ["Here: computer"]
    block = next(
        b for b in shared._painted.blocks if b.layout.text().startswith("Here")
    )
    assert block.color == QColor(TEXT)
    faint = [(f.start, f.length) for f in block.formats]
    assert faint == [(0, len("Here: "))]
    assert block.formats[0].format.foreground().color() == QColor(FAINT)


def test_a_word_with_no_link_has_no_line(windows: CaptionWindows) -> None:
    """这个 has no link in the made-up line: no "Here:", never an empty one."""
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "这个")
    click(shown, point)
    assert shared.request is not None and shared.request.context.counterpart == ""
    assert _here(shared._painted) == []


def test_a_word_looked_up_in_a_transcript_says_it_too(
    both: tuple[CaptionWindows, Transcripts],
) -> None:
    """The transcript's lines keep their word links: the same line."""
    windows, transcripts = both
    shown, shared = listed(transcripts), card(windows)
    _, point = find_in_transcript(shown, "游戏")
    click_list(shown, point)  # a click: looked up on the release (343)
    assert shared.request is not None
    assert shared.request.context.counterpart == "game"
    assert _here(shared._painted) == ["Here: game"]


def test_where_the_row_has_no_dictionary_it_is_the_cards_main_content(
    shown_card: LookupCard,
) -> None:
    bank = LookupContext("은행에 가요", "I'm going to the bank", "the bank", "en")
    shown_card.model.show("은행", bank, pinned=True, language="ko")
    no_dictionary = shown_card._lay_out(shown_card.model.card(), style.px(WIDTH))
    (block,) = (b for b in no_dictionary.blocks if "the bank" in b.layout.text())
    assert block.layout.font().pixelSize() == style.px(16)
    computer = LookupContext("我的电脑", "My computer", "computer", "en")
    shown_card.model.show("电脑", computer, pinned=True, at=(2, 4))
    entry = shown_card._lay_out(shown_card.model.card(), style.px(WIDTH))
    (block,) = (b for b in entry.blocks if b.layout.text() == "Here: computer")
    assert block.layout.font().pixelSize() == style.px(14)


def test_it_comes_first_under_the_word(shown_card: LookupCard) -> None:
    """Above the dictionary's meanings (326's order): what it means here,
    then what the dictionary says."""
    context = LookupContext("我的电脑", "My computer", "computer", "en")
    shown_card.model.show("电脑", context, pinned=True, at=(2, 4))
    painted = shown_card._lay_out(shown_card.model.card(), style.px(WIDTH))
    texts = [b.layout.text() for b in painted.blocks]
    meaning = next(i for i, t in enumerate(texts) if t.startswith("1. "))
    assert texts.index("Here: computer") < meaning


def test_a_hover_card_is_wide_enough_for_it_up_to_its_widest(
    shown_card: LookupCard,
) -> None:
    short = LookupContext("我的电脑", "My computer", "PC", "en")
    shown_card.model.show("电脑", short, pinned=False, at=(2, 4))
    narrow = shown_card._width(shown_card.model.card())
    long = LookupContext("我的电脑", "", "a computer that I use for games", "en")
    shown_card.model.show("电脑", long, pinned=False, at=(2, 4))
    wide = shown_card._width(shown_card.model.card())
    assert narrow < wide <= style.px(HOVER_WIDTHS[1])


def test_the_words_sit_where_the_label_says() -> None:
    text, (start, end) = here("ngân hàng")
    assert text[start:end] == "ngân hàng" and text == "Here: ngân hàng"


def test_a_word_on_a_line_still_being_spoken_has_none_until_it_finishes(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    """A live caption can change under an open card: no "Here:" until its
    finished caption (the marks' rule)."""
    said = clause("我的电脑坏了", "My computer broke", (("电脑", "computer"),))
    shown = window(windows)
    for update in (live("live-328", said), finished("live-328", said)):
        windows.apply(update)
        qapp.processEvents()
        shown.canvas.repaint()
        marked, _ = find(shown, "电脑坏")
        request = shown.word_at(replace(marked, end=marked.start + 2))
        assert request is not None and request.word == "电脑"
        expected = "" if update.kind is CaptionKind.LIVE else "computer"
        assert request.context.counterpart == expected
