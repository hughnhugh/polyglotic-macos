"""Words' "What you've heard": what the learner heard, counted on this PC
(polyglotic-hq project 163, from 155's design: section 5, mock 1).

- **Coverage, last 7 days:** of the words heard in finished captions, the
  share the learner knew as they heard them (`core.learning.coverage`),
  with the research's reference lines in its own words - 95 % "can
  follow, with effort", 98 % "comfortable, guess the rest". Never called
  comprehension: the research doesn't let us claim it (155, 3.3). Under
  200 words heard in the 7 days there's no number - one short session
  swings it.
- **Listening:** the time captions were on, in all and in the last 7
  days (`core.learning.listening_time`), as "12 h 40 min".
- **Words met:** words heard in at least one finished caption, how many
  of them were new in the last 7 days (`first_heard`), and the bands (`word_bands`): by frequency or HSK level, known / in the deck /
  new / not heard yet.

Words' summary line, under its title, says the three in one line:
"1,243 met · coverage 91% · 12 h 40 min" (`summary_line`).

Each number is a tile: a section label, the number, one line of what it
means and one faint line of where it comes from. The tiles sit side by
side when there's room and one above the other below that. Nothing here
leaves the PC.
"""

import math

from PySide6.QtCore import QLocale
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QApplication, QBoxLayout, QLayout, QVBoxLayout, QWidget

from polyglotic_desktop.core.learning.coverage import (
    CAN_FOLLOW,
    COMFORTABLE,
    MIN_TOKENS,
    RECENT_DAYS,
    Coverage,
)
from polyglotic_desktop.core.lexicon.entries import SCHEMES
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import Card, label
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.words import WordsLearner
from polyglotic_desktop.ui_next.word_bands import WordBands

TILES_SIDE_BY_SIDE = 600
"""The tiles sit side by side from this width (px at 100 % text), else
one above the other."""


def _tr(text: str) -> str:
    return QApplication.translate("Words", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("Words", text, None, n)


def percent(share: float) -> str:
    """A share as a whole percent, rounded down - 94.9 % is not yet 95 %
    ("91%"; the language places the sign: translations/README.md)."""
    whole = math.floor(share * 100 + 1e-9)
    return _tr("{percent}%").format(percent=QLocale().toString(whole))


def coverage_lines(coverage: Coverage) -> tuple[str, str, str]:
    """The coverage tile's number, its meaning and its faint line."""
    share = coverage.share
    if share is None:
        return (
            "",
            _tr("Not enough heard yet"),
            _trn(
                "Shows once you've heard %Ln word(s) in 7 days, so one short "
                "session doesn't swing it.",
                MIN_TOKENS,
            ),
        )
    one_in = coverage.one_new_in
    if one_in is None:
        new = _tr("Every word you heard, you knew.")
    elif coverage.known == 0:
        new = _tr("Every word you heard was new to you.")
    elif one_in < 2:  # more than half new: "1 in 1" would say nothing
        new = _tr("Most words you heard were new to you.")
    else:
        #: "1 word in 11 was new to you": the share of words not known, as one in so many
        new = _trn("%Ln word(s) in {total} was new to you.", 1).format(
            total=QLocale().toString(one_in)
        )
    reference = _tr(
        '{follow} is "can follow, with effort"; {comfortable} "comfortable, '
        'guess the rest".'
    ).format(follow=percent(CAN_FOLLOW), comfortable=percent(COMFORTABLE))
    return (
        percent(share),
        _tr("of the words you heard, you knew"),
        f"{new} {reference}",
    )


def duration(seconds: float) -> str:
    """A time in hours and whole minutes: "12 h 40 min", "3 h", "52 min",
    "0 min" (the units' words are the language's)."""
    hours, minutes = divmod(int(seconds // 60), 60)
    number = QLocale().toString
    if not hours:
        return _tr("{minutes} min").format(minutes=number(minutes))
    if not minutes:
        return _tr("{hours} h").format(hours=number(hours))
    return _tr("{hours} h {minutes} min").format(
        hours=number(hours), minutes=number(minutes)
    )


def listening_lines(seconds: float, recent: float) -> tuple[str, str, str]:
    """The listening tile's number, its meaning and its faint line."""
    return (
        duration(seconds),
        _tr("{time} in the last 7 days").format(time=duration(recent)),
        pc_or_mac(
            _tr("Time captions were on, counted on this PC."),
            _tr("Time captions were on, counted on this Mac."),
        ),
    )


def met_lines(met: int, new: int) -> tuple[str, str, str]:
    """The words-met tile's number, its meaning - how many were new in the
    last 7 days - and its faint line."""
    return (
        QLocale().toString(met),
        _trn("+%Ln new in the last 7 days", new),
        _tr(
            "Heard in a finished caption at least once; names and your own "
            "speech don't count."
        ),
    )


def summary_line(met: int, coverage: Coverage, seconds: float) -> str:
    """Words' line under its title: "1,243 met · coverage 91% · 12 h 40
    min" - each part only once there's something to say; "" for none."""
    parts = []
    if met:
        parts.append(_tr("{met} met").format(met=QLocale().toString(met)))
    if coverage.share is not None:
        parts.append(_tr("coverage {percent}").format(percent=percent(coverage.share)))
    if seconds >= 60:
        parts.append(duration(seconds))
    return " · ".join(parts)


class Tile(QWidget):
    """One number: its section label, the number, what it means, and a
    faint line of where it comes from."""

    def __init__(self, name: str, title: str) -> None:
        super().__init__()
        self.setObjectName(name)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.title = label(title.upper(), "SectionLabel", wrap=True)  # 354
        self.number = label("", "Stat")
        self.meaning = label("", "Dim", wrap=True)
        self.note = label("", "Faint", wrap=True)
        for part in (self.title, self.number, self.meaning, self.note):
            column.addWidget(part)
        column.addStretch(1)

    def show_lines(self, number: str, meaning: str, note: str) -> None:
        self.number.setText(number)
        self.number.setHidden(not number)
        self.meaning.setText(meaning)
        self.note.setText(note)
        self.setAccessibleName(" ".join(t for t in (number, meaning) if t))


class Tiles(QWidget):
    """Tiles side by side from `TILES_SIDE_BY_SIDE` wide, else stacked."""

    def __init__(self, tiles: list[Tile]) -> None:
        super().__init__()
        self.box = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self.box.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(16)
        for tile in tiles:
            self.box.addWidget(tile, 1)

    @property
    def side_by_side(self) -> bool:
        return self.box.direction() is QBoxLayout.Direction.LeftToRight

    def resizeEvent(self, event: QResizeEvent) -> None:
        wide = event.size().width() >= style.px(TILES_SIDE_BY_SIDE)
        if wide != self.side_by_side:
            self.box.setDirection(
                QBoxLayout.Direction.LeftToRight
                if wide
                else QBoxLayout.Direction.TopToBottom
            )
        super().resizeEvent(event)


class HeardCard(Card):
    """What you've heard: words met, coverage of the last 7 days, listening,
    and the bands."""

    def __init__(self) -> None:
        super().__init__(
            _tr("What you've heard"),
            pc_or_mac(
                _tr("Counted on this PC from finished captions, and kept here."),
                _tr("Counted on this Mac from finished captions, and kept here."),
            ),
        )
        self.met = Tile("words.met", _tr("Words met"))
        self.coverage = Tile("words.coverage", _tr("Coverage, last 7 days"))
        self.listening = Tile("words.listening", _tr("Listening"))
        self.tiles = Tiles([self.met, self.coverage, self.listening])
        self.add(self.tiles)
        self.bands = WordBands()
        self.add(self.bands)
        self.summary = ""
        """Words' summary line, as last refreshed."""
        self.words_met = 0
        """How many words met, as last refreshed: the language's heading."""

    def refresh(self, learner: WordsLearner) -> None:
        vocabulary = learner.vocabulary
        met = vocabulary.met_words()
        coverage = vocabulary.coverage()
        seconds = vocabulary.listening()
        self.met.show_lines(*met_lines(len(met), vocabulary.new_words()))
        self.coverage.show_lines(*coverage_lines(coverage))
        self.listening.show_lines(
            *listening_lines(seconds, vocabulary.listening(RECENT_DAYS))
        )
        scheme = SCHEMES.get(vocabulary.scheme)
        self.bands.set_words(met, learner.band_sizes(), scheme.levels if scheme else ())
        self.summary = summary_line(len(met), coverage, seconds)
        self.words_met = len(met)
