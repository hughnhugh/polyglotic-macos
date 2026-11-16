"""A field's hint (its placeholder) reads on the field in the main window,
in every theme, light and dark: the theme's dim text, not Qt's fainter
one. Settings > Speech's Names and slang ("e.g. rizz, no cap, yyds...")
was 4.36:1 on Margin's dark field, under WCAG's 4.5:1 for text - the UI
lab's contrast check found it once Speech had a section of its own
(polyglotic-hq 304)."""

from dataclasses import asdict

import pytest
import shiboken6
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from polyglotic_desktop.ui import theme as todays_theme
from polyglotic_desktop.ui_next import style


def luminance(colour: QColor) -> float:
    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in (colour.redF(), colour.greenF(), colour.blueF()))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one: QColor, other: QColor) -> float:
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("mode", ["dark", "light"])
@pytest.mark.parametrize("name", sorted(todays_theme.THEMES))
def test_a_fields_hint_reads_on_it(qapp: QApplication, name: str, mode: str) -> None:
    palette = todays_theme.palette(mode, name)
    theme = style.Theme(asdict(palette), dark=mode == "dark")
    window = QWidget()
    window.setStyleSheet(style.stylesheet(theme))
    field = QLineEdit()
    field.setPlaceholderText("e.g. rizz, no cap, yyds")
    QVBoxLayout(window).addWidget(field)
    try:
        window.show()
        qapp.processEvents()
        hint = field.palette().color(QPalette.ColorRole.PlaceholderText)
        assert hint.name() == QColor(theme["TEXT_DIM"]).name()
        assert contrast(hint, QColor(theme["SURFACE_2"])) >= 4.5
    finally:
        window.close()
        shiboken6.delete(window)
