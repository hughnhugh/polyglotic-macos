"""Learning's map of the language (polyglotic-hq 489, after 474's design;
the user, 2026-11-18: "the display should show your relative knowledge of
the language in relation to the entire language. You will see the
language completely in one colour if you are a native level speaker"):

- **the map**: the language in use's 20,000 most common words, one square
  each, commonest first, in rows of 200 - each in the colour of how well
  the learner knows it (`views.known_colours`, the palette Learning load
  uses), a name or an ignored word in the card's own faint grey;
- **progress, as the user defined it**: how many words are red, between
  and green, the share of what's heard that's green, and how each moved
  in the last 7 days;
- **pointing at a square** says its word, its place, how sure the app is
  that the learner knows it, and why.

It shows what it is given (`views.known_map.KnownMapView`); `main` reads
the words off the interface thread and works the chances out.
"""

import threading
from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    QCoreApplication,
    QLocale,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from polyglotic_desktop.core.learning.known_chance import Chance, Moved, Start
from polyglotic_desktop.core.learning.known_map import MAP_WORDS, Tally
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import Card, label
from polyglotic_desktop.ui_next.heard_card import percent
from polyglotic_desktop.ui_next.views.known_colours import known_colour
from polyglotic_desktop.ui_next.views.known_map import ROW, KnownMapView
from polyglotic_desktop.ui_next.views.lab import Palette
from polyglotic_desktop.ui_next.views.presets import _mix

SQUARE = 3
"""A word's square, in pixels, where the card has the room: 200 of them
make a 600 px row. Narrower, 2 px or 1 px: the page never scrolls
sideways (the UI lab's floor)."""

Describe = Callable[[EntryId], str]
"""A word's text for the hover (its headword and reading): "" if unknown."""


def _tr(text: str) -> str:
    return QCoreApplication.translate("KnownMap", text)


def _trn(text: str, n: int) -> str:
    return QCoreApplication.translate("KnownMap", text, None, n)


def _signed(n: int) -> str:
    text = QLocale().toString(abs(n))
    return f"+{text}" if n > 0 else f"−{text}" if n < 0 else text


def week_text(now: Tally, then: Tally) -> str:
    """How the green and red words moved in the last 7 days."""
    green, red = now.mastered - then.mastered, now.unknown - then.unknown
    if green == 0 and red == 0:
        return _tr("No change in the last 7 days.")
    return _tr("In the last 7 days: {green} green, {red} red.").format(
        green=_signed(green), red=_signed(red)
    )


def why(found: Chance, line: int | None, line_set: bool) -> list[str]:
    """Why a word is the colour it is: where it started, then what moved
    it - each a line a learner could be told."""
    words = QLocale().toString(line or 0)
    start = found.start
    if start in (Start.LINE, Start.STARTING_LINE):
        if found.place is not None and line and found.place <= line:
            lines = [
                _tr("Within the about {words} words you know.").format(words=words)
            ]
        else:
            lines = [_tr("Past the about {words} words you know.").format(words=words)]
        if not line_set:
            lines.append(_tr("Your level isn't set yet, so that's a guess."))
    else:
        lines = [
            {
                Start.SAID_KNOWN: _tr("You said you know it."),
                Start.IMPORTED_KNOWN: _tr("Known from what you imported."),
                Start.NUMBER: _tr("A number written in numerals you know."),
                Start.BY_PARTS: _tr("You know the words it's made of."),
                Start.NOT_BY_PARTS: _tr("Not all the words it's made of are known."),
                Start.LEARNING: _tr("In your deck."),
                Start.LOOKED_UP: _tr("Looked up twice, so new to you for now."),
                Start.SAID_NEW: _tr("You said it's new to you."),
                Start.NOT_PLACED: _tr("Nothing says how common it is."),
            }[start]
        ]
    for moved, _ in found.moved:
        if moved is Moved.HEARD:
            lines.append(_trn("Heard on %n day(s).", found.days_heard))
        else:
            lines.append(
                {
                    Moved.SAVED: _tr("Saved."),
                    Moved.NOT_AGAIN: _tr(
                        "Looked up, then heard again without a lookup."
                    ),
                    Moved.FRESH_LOOKUP: _tr("Looked up in the last 3 days."),
                    Moved.SINCE_KNOWN: _tr(
                        "Looked up twice since you said you know it."
                    ),
                }[moved]
            )
    return lines


MapWords = Sequence[tuple[int, EntryFacts]]


class WordsReader(QObject):
    """Reads a language's map words off the interface thread - 20,000 of
    the dictionary's entries, a second or so - and says when they're back
    (`read`: the key it was asked for, and the words; none if the read
    failed). One read at a time; asked again while reading, nothing."""

    read = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.reading: object | None = None
        self._thread: threading.Thread | None = None

    def start(self, key: object, read: Callable[[], MapWords]) -> None:
        if self.reading is not None:
            return
        self.reading = key

        def run() -> None:
            words: MapWords = ()
            try:
                words = list(read())[:MAP_WORDS]
            finally:
                self.read.emit((key, words))

        self._thread = threading.Thread(target=run, name="known-map", daemon=True)
        self._thread.start()

    def done(self) -> None:
        self.reading = None

    def wait(self, timeout: float = 10.0) -> None:
        """For a test, and for closing: the read finished."""
        if self._thread is not None:
            self._thread.join(timeout)


class MapPicture(QWidget):
    """The squares, one a word, and what pointing at one says."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("learning.known_map.picture")
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(ROW)
        self.square = SQUARE
        self.view: KnownMapView | None = None
        self.describe: Describe = lambda _: ""
        self._image: QImage | None = None

    def show_view(self, view: KnownMapView | None, describe: Describe) -> None:
        self.view, self.describe = view, describe
        self._image = None if view is None else self._drawn(view)
        self.fit()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(ROW * SQUARE, self.height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fit()

    def fit(self) -> None:
        """Squares as big as the width allows, up to `SQUARE`; the height
        follows."""
        self.square = max(1, min(SQUARE, self.width() // ROW))
        rows = self.view.rows if self.view is not None else 0
        self.setFixedHeight(rows * self.square)

    def _drawn(self, view: KnownMapView) -> QImage:
        """One pixel a word, scaled up when painted: 20,000 squares cost
        one image, not 20,000 rectangles."""
        image = QImage(ROW, view.rows, QImage.Format.Format_RGB32)
        panel = style.current()["SURFACE"]
        image.fill(QColor(panel))
        # a name or an ignored word: the theme's faint text, half over the
        # card - grey, never a hole in the map, never one of the colours
        neutral = QColor(_mix(panel, style.current()["TEXT_FAINT"], 0.5))
        palette = view.palette
        shades: dict[int, int] = {}
        for index, found in enumerate(view.chances):
            if found is None:
                rgb = neutral.rgb()
            else:
                step = round(found.chance * 20)
                rgb = shades.get(step, -1)
                if rgb == -1:
                    rgb = shades[step] = QColor(
                        known_colour(step / 20, palette, panel)
                    ).rgb()
            image.setPixel(index % ROW, index // ROW, rgb)
        return image

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._image is None:
            return
        painter = QPainter(self)
        side = self.square
        painter.drawImage(QRect(0, 0, ROW * side, self.height()), self._image)
        painter.end()

    def index_at(self, at: QPoint) -> int | None:
        if at.x() < 0 or at.y() < 0:
            return None
        column, row = at.x() // self.square, at.y() // self.square
        if column >= ROW:
            return None
        return row * ROW + column

    def text_at(self, index: int) -> str | None:
        """What pointing at square `index` says."""
        view = self.view
        found = view.at(index) if view is not None else None
        if view is None or found is None:
            return None
        place, entry_id, chance = found
        word = self.describe(entry_id) or "?"
        head = _tr("{word} · No. {place}").format(
            word=word, place=QLocale().toString(place)
        )
        if chance is None:
            return head + "\n" + _tr("A name, or a word you ignore: not coloured.")
        sure = _tr("About {percent} likely you know it.").format(
            percent=percent(chance.chance)
        )
        return "\n".join([head, sure, *why(chance, view.line, view.line_set)])

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self.index_at(event.position().toPoint())
        text = self.text_at(index) if index is not None else None
        if text:
            QToolTip.showText(event.globalPosition().toPoint(), text, self)
        else:
            QToolTip.hideText()


class KnownMapCard(Card):
    """Learning's card for the map of the language in use."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(_tr("How well you know the language"), parent=parent)
        # its object name stays "Card": the stylesheet draws cards by it
        self.setAccessibleName(_tr("How well you know the language"))
        self.about = label("", "Dim", wrap=True)
        self.add(self.about)
        self.counts = label("", "", wrap=True)
        self.counts.setObjectName("learning.known_map.counts")
        self.add(self.counts)
        self.heard = label("", "Dim", wrap=True)
        self.add(self.heard)
        self.week = label("", "Dim", wrap=True)
        self.add(self.week)
        self.picture = MapPicture(self)
        self.add(self.picture)
        self.legend = label("", "Faint", wrap=True)
        self.add(self.legend)

    def show_reading(self, language: str) -> None:
        """The words are being read: the card says so, with no map yet."""
        self._title(language)
        self.about.setText(_tr("Reading the language's words…"))
        for part in (self.counts, self.heard, self.week, self.legend):
            part.setText("")
        self.picture.show_view(None, lambda _: "")

    def show_map(self, view: KnownMapView | None, describe: Describe) -> None:
        """The map as it is now; None: this language has no ranks."""
        if view is None:
            self.about.setText(
                _tr("This language's dictionary doesn't say how common its words are.")
            )
            for part in (self.counts, self.heard, self.week, self.legend):
                part.setText("")
            self.picture.show_view(None, describe)
            return
        self._title(view.language)
        now = view.now
        self.about.setText(
            _tr(
                "Its {count} most common words, one square each, commonest first. "
                "Point at a square to see its word and why it's that colour."
            ).format(count=QLocale().toString(MAP_WORDS))
        )
        self.counts.setText(
            " · ".join(
                [
                    _coloured(
                        _trn("%Ln word(s) green", now.mastered), 1.0, view.palette
                    ),
                    _coloured(
                        _trn("%Ln word(s) between", now.partial), 0.5, view.palette
                    ),
                    _coloured(_trn("%Ln word(s) red", now.unknown), 0.0, view.palette),
                ]
            )
        )
        self.counts.setTextFormat(Qt.TextFormat.RichText)
        self.heard.setText(
            _tr(
                "{share} of what you hear is green, by how often each word is said."
            ).format(share=percent(now.heard_mastered))
        )
        self.week.setText(week_text(now, view.week_ago))
        self.legend.setText(
            _tr(
                "Red: never met, or far past what you know. The colours between: "
                "words you've heard or partly know. Green: mastered. A native "
                "speaker's map is all green."
            )
        )
        self.picture.show_view(view, describe)

    def _title(self, language: str) -> None:
        if self.title is not None:
            self.title.setText(
                _tr("How well you know {language}").format(language=language)
                if language
                else _tr("How well you know the language")
            )


def _coloured(text: str, chance: float, palette: Palette) -> str:
    colour = known_colour(chance, palette, style.current()["SURFACE"])
    return f"<span style='color:{colour}'>■</span> {text}"
