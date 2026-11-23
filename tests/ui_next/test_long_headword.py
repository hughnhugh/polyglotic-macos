"""A long headword never runs under the lookup card's Say it and Close
(polyglotic-hq 522's picture of a long selection's card, 533): it shrinks,
then wraps, clear of the buttons - at any text size. A stand-in speaker:
nothing is played."""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_say_it import hushed, opened, pin, shown, speaker

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.lookup_card import PAD, LookupCard

__all__ = ["hushed", "opened", "shown", "speaker"]  # the fixtures, shared

LONG = (
    "中华人民共和国全国人民代表大会常务委员会",  # a whole clause, dragged across
    "Donaudampfschifffahrtsgesellschaftskapitän",  # one German word, no spaces
    "cộng hòa xã hội chủ nghĩa Việt Nam",  # Vietnamese, by syllables
)


@pytest.fixture
def text_size(qapp: QApplication) -> Iterator[None]:
    yield
    style.use_text_scale(1.0)


def headword_right(card: LookupCard, word: str) -> float:
    """Where the drawn headword ends, on the card: a line's run, or a
    wrapped block's widest line."""
    painted = card._painted
    ends = [
        run.at.x() + QFontMetricsF(run.font).horizontalAdvance(run.text)
        for run in painted.runs
        if run.text == word
    ]
    for block in painted.blocks:
        if block.layout.text() == word:
            layout = block.layout
            widest = max(
                layout.lineAt(n).naturalTextWidth() for n in range(layout.lineCount())
            )
            ends.append(block.at.x() + widest)
    assert ends, f"{word} isn't drawn"
    return max(ends)


def text_right(card: LookupCard) -> float:
    """Where the card's rightmost text ends: every run and wrapped block."""
    painted = card._painted
    ends = [
        run.at.x() + QFontMetricsF(run.font).horizontalAdvance(run.text)
        for run in painted.runs
    ]
    for block in painted.blocks:
        layout = block.layout
        ends += [
            block.at.x() + layout.lineAt(n).naturalTextWidth()
            for n in range(layout.lineCount())
        ]
    return max(ends)


def buttons_left(card: LookupCard) -> float:
    hits = [b.rect.left() for b in card._painted.boxes if b.hit in ("say", "close")]
    assert len(hits) == 2  # Say it and Close
    return min(hits)


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_a_long_headword_stays_clear_of_say_it_and_close(
    shown: LookupCard, text_size: None, scale: float
) -> None:
    style.use_text_scale(scale)
    for word in LONG:
        pin(shown, word)
        assert headword_right(shown, word) <= buttons_left(shown), (word, scale)
        # nor its reading, or anything else, off the card's edge
        assert text_right(shown) <= shown._painted.width - PAD + 0.5, (word, scale)


def test_a_short_headword_keeps_its_size_and_its_line(shown: LookupCard) -> None:
    pin(shown, "电脑")
    (run,) = [r for r in shown._painted.runs if r.text == "电脑"]
    assert run.font.pixelSize() == style.px(26)
    assert not [b for b in shown._painted.blocks if b.layout.text() == "电脑"]


def test_a_word_a_little_too_long_shrinks_a_far_longer_one_wraps(
    shown: LookupCard,
) -> None:
    pin(shown, "中华人民共和国宪法修正案")  # twelve characters: a little too long
    (run,) = [r for r in shown._painted.runs if r.text == "中华人民共和国宪法修正案"]
    assert style.px(26) * 0.7 <= run.font.pixelSize() < style.px(26)
    pin(shown, LONG[1])  # far too long: wrapped, within the card
    (block,) = [b for b in shown._painted.blocks if b.layout.text() == LONG[1]]
    assert block.layout.lineCount() >= 2
    assert block.layout.font().pixelSize() == style.px(24)  # at its own size
    assert headword_right(shown, LONG[1]) <= shown._painted.width - PAD
