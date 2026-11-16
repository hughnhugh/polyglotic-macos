"""A button whose face is one of the interface's own drawn icons - Home's
"show my speech in this window" was the 🎤 emoji as text (polyglotic-hq 403)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

import polyglotic_desktop.ui_next as package
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import GlyphButton
from polyglotic_desktop.ui_next.glyphs import Glyph


@pytest.fixture
def button(qapp: QApplication) -> Iterator[GlyphButton]:
    window = QWidget()
    window.setStyleSheet(style.stylesheet(style.current()))
    row = QHBoxLayout(window)
    button = GlyphButton(Glyph.MIC)
    button.setProperty("mark", True)
    button.setCheckable(True)
    row.addWidget(button)
    window.show()
    QApplication.processEvents()
    yield button
    window.close()
    window.deleteLater()
    QApplication.processEvents()


def _closest(button: GlyphButton, token: str) -> int:
    """How near the button's nearest pixel comes to the theme's `token`."""
    want = QColor(style.current()[token])
    picture = button.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    best = 255 * 3
    for x in range(picture.width()):
        for y in range(picture.height()):
            pixel = picture.pixelColor(x, y)
            best = min(
                best,
                abs(pixel.red() - want.red())
                + abs(pixel.green() - want.green())
                + abs(pixel.blue() - want.blue()),
            )
    return best


def test_it_has_no_text_and_a_size(button: GlyphButton) -> None:
    assert button.text() == ""
    assert button.width() >= style.px(GlyphButton.GLYPH) + 12
    assert button.height() >= 24  # a target (WCAG 2.5.8)


def test_a_smaller_font_keeps_a_target_s_height(button: GlyphButton) -> None:
    """A Mac's font made it 23 px tall (polyglotic-hq 421's Mac run)."""
    button.setStyleSheet("font-size: 10px")
    QApplication.processEvents()
    assert button.sizeHint().height() >= GlyphButton.TARGET == 24


def test_the_icon_is_dim_then_the_accent_while_checked(button: GlyphButton) -> None:
    assert _closest(button, "TEXT_DIM") < 30
    button.setChecked(True)
    QApplication.processEvents()
    assert _closest(button, "ACCENT") < 30


def test_no_emoji_stands_in_for_an_icon() -> None:
    """Impeccable's ban, and DESIGN.md's: icons are drawn, not emoji."""
    for source in Path(package.__file__).parent.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        emoji = [c for c in text if 0x1F300 <= ord(c) <= 0x1FAFF]
        if source.name == "controls.py":  # says which emoji it replaced
            assert len(emoji) <= 1
        else:
            assert not emoji, (source.name, emoji)
