"""Words' bands: the words met by how common they are, or by HSK level, and
where they stand in each (polyglotic-hq project 163, from 155's mock 2).

A row per band - "Top 1,000", "1,001-2,000", ... "Rarer", or "HSK 1" to
"HSK 7-9" - with its counts in words and a bar as long as the band, filled
by status: known (neutral), in your deck (deep yellow, dashes), new (blue,
dots), not heard yet (an outline). The patterns as well as the colours,
so no status is told by colour alone; the two colours are 155's, checked
for colour-blind separation on the dark card. Bars, not a 10,000-cell
grid: a grid says less per pixel and can't be read by a screen reader.
The counting is Learning's (`core.learning.bands`); the bands' sizes come
from the dictionary.
"""

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QLocale, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.bands import (
    FREQUENCY_BANDS,
    Band,
    MetWord,
    by_frequency,
    by_level,
)
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import Flow, Segmented, label

DECK = "#b08c30"
"""In your deck: a deeper step of the app's yellow (#f2c14e is too light
for a fill on the card - 155, 5.2)."""
NEW = "#5a8be6"
"""New: heard, not known."""
_MARK = "#e9ecf1"  # the dashes and dots on the fills

BY_FREQUENCY, BY_LEVEL = "frequency", "level"


def _tr(text: str) -> str:
    return QApplication.translate("Words", text)


def _number(n: int) -> str:
    return QLocale().toString(n)


def band_names(levels: Sequence[int], scheme_levels: Sequence[str]) -> list[str]:
    """The level bands' names: "HSK 1" ... "HSK 7-9" (the scheme's labels)."""
    names = []
    for level in levels:
        tag = scheme_levels[level - 1] if 0 < level <= len(scheme_levels) else level
        names.append(_tr("HSK {level}").format(level=tag))
    return names


def frequency_names() -> list[str]:
    """ "Top 1,000", "1,001-2,000", "2,001-5,000", "5,001-10,000"."""
    names = []
    for first, last in FREQUENCY_BANDS:
        if first == 1:
            names.append(_tr("Top {last}").format(last=_number(last)))
        else:
            names.append(
                _tr("{first}-{last}").format(first=_number(first), last=_number(last))
            )
    return names


def counts_line(band: Band) -> str:
    """A band's counts in words."""
    if band.size is None:
        return _tr("{known} known · {deck} in your deck · {new} new").format(
            known=_number(band.known), deck=_number(band.deck), new=_number(band.new)
        )
    return _tr(
        "{known} known · {deck} in your deck · {new} new · {unheard} not heard yet"
    ).format(
        known=_number(band.known),
        deck=_number(band.deck),
        new=_number(band.new),
        unheard=_number(band.not_heard),
    )


class BandBar(QWidget):
    """A band's bar: as long as the band, filled by status."""

    def __init__(self) -> None:
        super().__init__()
        self.band = Band()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(style.px(12))

    def sizeHint(self) -> QSize:
        return QSize(style.px(200), style.px(12))

    def set_band(self, band: Band) -> None:
        self.band = band
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        band = self.band
        whole = band.size if band.size is not None else band.met
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = style.current()
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(theme["BORDER"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 3, 3)  # not heard yet: the outline
        if whole <= 0:
            painter.end()
            return
        x = rect.left()
        parts = (
            (band.known, QColor(theme["TEXT_DIM"]), None),
            (band.deck, QColor(DECK), Qt.BrushStyle.HorPattern),
            (band.new, QColor(NEW), Qt.BrushStyle.Dense6Pattern),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        for count, colour, pattern in parts:
            width = rect.width() * min(count, whole) / whole
            if width <= 0:
                continue
            part = QRectF(x, rect.top(), width, rect.height())
            painter.fillRect(part, colour)
            if pattern is not None:
                mark = QColor(_MARK)
                mark.setAlpha(150)
                painter.fillRect(part, QBrush(mark, pattern))
            x += width
        painter.end()


class BandRow(QWidget):
    """One band: its name and counts, and its bar beneath."""

    def __init__(self) -> None:
        super().__init__()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        line = QHBoxLayout()
        line.setSpacing(12)
        self.name = label("", "RowTitle")
        self.counts = label("", "Faint", wrap=True)
        self.counts.setAlignment(Qt.AlignmentFlag.AlignRight)
        line.addWidget(self.name)
        line.addWidget(self.counts, 1)
        column.addLayout(line)
        self.bar = BandBar()
        column.addWidget(self.bar)

    def set_band(self, name: str, band: Band) -> None:
        self.name.setText(name)
        counts = counts_line(band)
        self.counts.setText(counts)
        self.bar.set_band(band)
        self.bar.setHidden(band.size is None)  # the rarer words: no length to fill
        self.setAccessibleName(_tr("{band}: {counts}").format(band=name, counts=counts))


class Legend(QWidget):
    """What the bars' fills mean, once under them."""

    def __init__(self) -> None:
        super().__init__()
        row = Flow(self, spacing=16)  # onto more lines where it's narrow (354)
        for band, text in (
            (Band(known=1), _tr("known")),
            (Band(deck=1), _tr("in your deck")),
            (Band(new=1), _tr("new (heard, not known)")),
            (Band(size=1), _tr("not heard yet")),
        ):
            key = QHBoxLayout()
            key.setSpacing(6)
            swatch = BandBar()
            swatch.setFixedSize(style.px(12), style.px(12))
            swatch.set_band(band)
            key.addWidget(swatch)
            key.addWidget(label(text, "Faint"))
            row.add_layout(key)


class WordBands(QWidget):
    """The bands by frequency, or by level (a learner whose scheme has
    levels - HSK - can switch)."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("words.bands")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        head = Flow()  # the switch under the title where it's narrow (354)
        self.title = label("", "SectionLabel", wrap=True)
        head.add_widget(self.title, 1)
        self.view = Segmented(
            [(BY_FREQUENCY, _tr("By frequency")), (BY_LEVEL, _tr("By HSK level"))],
            BY_FREQUENCY,
        )
        self.view.setObjectName("words.bands_view")
        self.view.setAccessibleName(_tr("Show the bands"))
        self.view.changed.connect(lambda _: self._show())
        head.addWidget(self.view)
        column.addLayout(head)
        self.rows_column = QVBoxLayout()
        self.rows_column.setSpacing(10)
        column.addLayout(self.rows_column)
        self.rows: list[BandRow] = []
        column.addWidget(Legend())
        self._met: list[MetWord] = []
        self._sizes: tuple[Sequence[int], Mapping[int, int]] = ((), {})
        self._levels: Sequence[str] = ()

    def set_words(
        self,
        met: list[MetWord],
        sizes: tuple[Sequence[int], Mapping[int, int]],
        scheme_levels: Sequence[str],
    ) -> None:
        """The words met, the bands' sizes (frequency, levels) and the
        level scheme's labels."""
        self._met, self._sizes, self._levels = met, sizes, scheme_levels
        self.view.setVisible(bool(sizes[1]))
        if not sizes[1]:
            self.view.set_value(BY_FREQUENCY)
        self._show()

    def _show(self) -> None:
        frequency, levels = self._sizes
        if self.view.value() == BY_LEVEL and levels:
            found = by_level(self._met, levels)
            names = band_names(list(found), self._levels)
            bands = list(found.values())
            self.title.setText(_tr("Words met, by HSK level").upper())
        else:
            if len(frequency) != len(FREQUENCY_BANDS):
                frequency = [0] * len(FREQUENCY_BANDS)
            ranked, rarer = by_frequency(self._met, frequency)
            names = [*frequency_names(), _tr("Rarer")]
            bands = [*ranked, rarer]
            self.title.setText(_tr("Words met, by frequency").upper())
        while len(self.rows) < len(bands):
            row = BandRow()
            self.rows.append(row)
            self.rows_column.addWidget(row)
        for row, name, band in zip(self.rows, names, bands, strict=False):
            row.set_band(name, band)
        for index, row in enumerate(self.rows):
            row.setHidden(index >= len(bands))
