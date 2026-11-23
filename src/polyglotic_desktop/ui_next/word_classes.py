"""The word classes shown on caption links, in the legend and on lookup."""

from functools import lru_cache
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from polyglotic_desktop.core.listening.captions import WordClass
from polyglotic_desktop.ui_next.copying import Text
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.presets import (
    _mix,
    ciede2000,
    contrast,
    luminance,
)
from polyglotic_desktop.ui_next.views.tone import caption_text_colour

CLASS_COLOURS = {
    WordClass.NOUN: "#77aadd",
    WordClass.VERB: "#ee8866",
    WordClass.ADJECTIVE: "#44bb99",
    WordClass.ADVERB: "#eedd88",
    WordClass.PRONOUN: "#ff80b2",
    WordClass.PARTICLE: "#aaaa00",
    WordClass.NUMBER: "#d6a4ff",
    None: "#a0a0a0",
}
"""Primary #RRGGBB sRGB swatches for dark panels. Project 734 separates
Number from Noun and strengthens Pronoun's pink beside the neutral grey."""

CLASS_ALTERNATES = {
    WordClass.NOUN: ("#4f87ff", "#245da8", "#005b8a"),
    WordClass.VERB: ("#ff716f", "#af3529", "#b32047"),
    WordClass.ADJECTIVE: ("#00c5c9", "#167360", "#006e82"),
    WordClass.ADVERB: ("#4be4f9", "#8b6900", "#5b6740"),
    WordClass.PRONOUN: ("#f964ce", "#a42a66", "#93218c"),
    WordClass.PARTICLE: ("#6ed44d", "#4e6911", "#356524"),
    WordClass.NUMBER: ("#bc68ee", "#7534b3", "#4c2490"),
    None: ("#909090", "#666666", "#808080"),
}
"""Ordered sRGB alternatives, one for dark panels and two for light ones.
Project 734 uses cyan when the adverb's yellow meets a gold line and
keeps an achromatic swatch when the class is unavailable."""

CLASS_CONTRAST = 3.0
"""Minimum contrast ratio (1–21) for class marks, WCAG 2.2 non-text contrast."""

APART_FROM_TEXT = 22.0
"""Minimum CIEDE2000 distance from the row's ink. Project 554 chose 22
after Classic's gold clashed with orange and olive (18.8 and 18.0)."""


def _tr(text: str) -> str:
    return QApplication.translate("WordClasses", text)


def class_name(pos: str | None) -> str:
    names: dict[str | None, str] = {
        WordClass.NOUN: _tr("Noun"),
        WordClass.VERB: _tr("Verb"),
        WordClass.ADJECTIVE: _tr("Adjective"),
        WordClass.ADVERB: _tr("Adverb"),
        WordClass.PRONOUN: _tr("Pronoun or determiner"),
        WordClass.PARTICLE: _tr("Particle, connector or interjection"),
        WordClass.NUMBER: _tr("Number"),
        None: _tr("Class unavailable"),
    }
    return names.get(pos, names[None])


@lru_cache(maxsize=1024)
def class_backing(colour: str, background: str, opacity: float) -> str | None:
    """A contrasting edge when a scene can come too close to the mark."""
    dark = _mix("#000000", background, opacity)
    light = _mix("#ffffff", background, opacity)
    between = luminance(dark) <= luminance(colour) <= luminance(light)
    if (
        not between
        and min(contrast(colour, dark), contrast(colour, light)) >= CLASS_CONTRAST
    ):
        return None
    return max(("#000000", "#ffffff"), key=lambda ink: contrast(colour, ink))


@lru_cache(maxsize=1024)
def class_colour(
    pos: WordClass | None, background: str, opacity: float, text: str
) -> str:
    """Pick this class's swatch apart from its row, preferring bare marks."""
    primary = CLASS_COLOURS[pos]
    swatches = (primary, *CLASS_ALTERNATES[pos])
    apart = [
        colour for colour in swatches if ciede2000(colour, text) >= APART_FROM_TEXT
    ]
    for colour in apart:
        if class_backing(colour, background, opacity) is None:
            return colour
    for colour in apart:
        if contrast(colour, background) >= CLASS_CONTRAST:
            return colour
    if apart:
        return apart[0]

    # A custom row can be too close to every set swatch. Shade the
    # class's own ink in the 5% steps used by presets.readable_on.
    for step in range(1, 21):
        for end in ("#000000", "#ffffff"):
            colour = _mix(primary, end, step / 20)
            if ciede2000(colour, text) >= APART_FROM_TEXT:
                return colour
    return max(("#000000", "#ffffff"), key=lambda ink: ciede2000(ink, text))


def legend_html(look: CaptionLook, intro: str = "") -> str:
    text_colours = tuple(
        caption_text_colour(colour, look.background, look.vibrance)
        for colour in (look.original, look.translation)
    )

    def swatch(colour: str) -> str:
        backing = (
            class_backing(colour, look.background, look.opacity) or look.background
        )
        return f'<span style="background-color:{backing};color:{colour}">&nbsp;●&nbsp;</span>'

    rows = []
    for pos in CLASS_COLOURS:
        colours = dict.fromkeys(
            class_colour(pos, look.background, look.opacity, text)
            for text in text_colours
        )
        dots = " ".join(swatch(colour) for colour in colours)
        rows.append(f"{dots} {escape(class_name(pos))}")
    return "<br>".join([escape(intro), *rows] if intro else rows)


class WordClassLegend(QWidget):
    """A keyboard-operable disclosure for Settings and the bar controls."""

    expanded = Signal()

    def __init__(self, parent: QWidget | None = None, *, copyable: bool = True) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton(_tr("Word class legend"), self)
        self.button.setObjectName("word_class_legend.button")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setCheckable(True)
        self.button.setAccessibleDescription(
            "\n".join(class_name(pos) for pos in CLASS_COLOURS)
        )
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignLeft)
        self.labels = Text(self) if copyable else QLabel(self)
        self.labels.setObjectName("word_class_legend.labels")
        self.labels.setWordWrap(True)
        self.labels.hide()
        layout.addWidget(self.labels)
        self.button.toggled.connect(self._show)

    def set_look(self, look: CaptionLook) -> None:
        self.labels.setText(legend_html(look))

    def _show(self, on: bool) -> None:
        self.labels.setVisible(on)
        self.expanded.emit()
