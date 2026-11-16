"""The caption windows' icons are drawn (`ui_next.glyphs`), not Windows' icon
font, whose characters are empty boxes on macOS and Linux (polyglotic-hq
171, 179); and the font lists end with each OS's own fonts (`ui_next.fonts`)
while Windows' stay as they were."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_joined_window import THREE, Store, areas

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import MIC
from polyglotic_desktop.ui_next import caption_layout, fonts, style
from polyglotic_desktop.ui_next.caption_window import GLYPH_PX
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.glyphs import Glyph, icon, paint, text_width

SOURCE = Path(__file__).resolve().parents[2] / "src" / "polyglotic_desktop"
PRIVATE_USE = range(0xE000, 0xF900)
"""Unicode's private-use area: where icon fonts keep their glyphs."""


def drawn(glyph: Glyph, size: int) -> QImage:
    image = QImage(size + 4, size + 4, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint(painter, glyph, QRectF(2, 2, size, size), QColor("#e9ecf2"))
    painter.end()
    return image


@pytest.mark.parametrize("glyph", list(Glyph))
@pytest.mark.parametrize("size", [11, 22])
def test_each_glyph_is_drawn_inside_its_square(
    qapp: QApplication, glyph: Glyph, size: int
) -> None:
    image = drawn(glyph, size)
    inked = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    ]
    assert len(inked) > size  # something there
    assert all(1 <= x <= size + 2 and 1 <= y <= size + 2 for x, y in inked)


def test_a_glyph_takes_the_room_windows_icon_font_gave_it(qapp: QApplication) -> None:
    """An em and a space either side: 12 + 4 + 4 at 12 px with Windows'
    icon fonts (measured on 2026-11-08: the band's buttons were 37 px wide
    at 100 %, 40 at 125 %, 45 at 150 %); a third of an em without them."""
    assert text_width(12) == 20
    assert text_width(24) == 24 + 2 * 7 or text_width(24) == 24 + 2 * 8


def test_an_icon_is_sharp_at_twice_the_size(qapp: QApplication) -> None:
    pixmap = icon(Glyph.LOCK, "#e9ecf2", 11).pixmap(QSize(11, 11), 2.0)
    assert (pixmap.width(), pixmap.height()) == (22, 22)


def test_no_icon_font_character_is_left_in_the_code() -> None:
    """Segoe Fluent Icons' characters (the lock, the gear, the cross, More,
    the mic) were in `caption_window` and `joined_window`."""
    found = [
        f"{path.relative_to(SOURCE)}: U+{ord(char):04X}"
        for path in SOURCE.rglob("*.py")
        for char in path.read_text(encoding="utf-8")
        if ord(char) in PRIVATE_USE
    ]
    assert found == []


def test_the_band_buttons_are_drawn_icons(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        for name in ("lock", "settings", "stop"):
            assert not window.controls[name].icon().isNull(), name
            side = style.px(GLYPH_PX)
            assert window.buttons[name].iconSize() == QSize(side, side)
            assert window.buttons[name].accessibleName()  # its words, said
        assert window.controls["bigger"].icon().isNull()  # "A+": words
    finally:
        window.close()


def test_the_joined_windows_buttons_are_drawn_icons(qapp: QApplication) -> None:
    windows = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    windows.set_labels(
        {source: SourceLabel(name, "#4dd0e1") for name, source in THREE}, "You"
    )
    windows.set_captioned(THREE)
    try:
        windows.join("b")
        joined = windows.joined_window
        assert joined is not None
        for name in ("lock", "settings"):
            assert not joined.controls[name].icon().isNull(), name
    finally:
        windows.close()


def test_on_windows_the_font_lists_are_as_they_were() -> None:
    assert fonts.also("latin", "win32") == fonts.also("zh", "win32") == ()
    if sys.platform != "win32":
        return
    assert caption_layout.LATIN_FAMILIES == ("Segoe UI Variable Display", "Segoe UI")
    assert caption_layout.CJK_FAMILIES["zh"] == (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
    )
    assert style.UI_FAMILIES == [
        "Segoe UI Variable Text",
        "Segoe UI",
        "Microsoft YaHei UI",
        "Microsoft JhengHei UI",
    ]


@pytest.mark.parametrize("system", ["darwin", "linux"])
def test_another_os_has_its_own_font_for_every_script(system: str) -> None:
    for script in ("latin", *caption_layout.CJK_FAMILIES):
        assert fonts.also(script, system), (system, script)
