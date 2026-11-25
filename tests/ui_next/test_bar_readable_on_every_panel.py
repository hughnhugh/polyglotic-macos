"""A caption window's top bar - its icons, its label and note, the hover
behind its buttons - and its other chrome follow the panel's colour, so
they're readable on every preset and any colour the learner picks (the
user's live testing, polyglotic-hq 272: "Some themes make it so the top
bar icon contrast is impossible to see, white on paper background")."""

from dataclasses import replace

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_joined_window import THREE, areas, joined

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import BAR_CONTRAST, bar_ink
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.presets import PRESETS, contrast

ICON_CONTRAST = 3.0
"""WCAG 2.2's 1.4.11 for an icon against what's behind it."""
PICKED = ("#ffffff", "#f6f1e6", "#808080", "#ffd76e", "#000000")
"""Backgrounds a learner might pick: white, Paper's, mid-grey, yellow, black."""


def ink_of(icon: QIcon, side: int = 64) -> str:
    """The colour an icon is drawn in: its most opaque pixel's."""
    image = icon.pixmap(side, side).toImage()
    best, alpha = "#000000", -1
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > alpha:
                best, alpha = pixel.name(), pixel.alpha()
    assert alpha > 150, "the icon drew nothing solid"
    return best


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_every_presets_top_bar_is_readable(qapp: QApplication, preset: object) -> None:
    background = preset.background  # type: ignore[attr-defined]
    look = replace(CaptionLook(), background=background)
    window = window_of(qapp, captions=1, look=look)
    try:
        for name in ("links", "lock", "settings", "stop"):
            drawn = ink_of(window.controls[name].icon())
            assert contrast(drawn, background) >= ICON_CONTRAST, name
        assert contrast(window.tag.ink.text, background) >= BAR_CONTRAST
        assert contrast(window.tag.ink.dim, background) >= BAR_CONTRAST
        assert window.band.styleSheet().count(window.bar.text) >= 1
    finally:
        window.close()


@pytest.mark.parametrize("background", PICKED)
def test_any_picked_colour_gets_readable_chrome(background: str) -> None:
    ink = bar_ink(background)
    assert contrast(ink.text, background) >= BAR_CONTRAST
    assert contrast(ink.dim, background) >= BAR_CONTRAST
    assert contrast(ink.disabled, background) >= ICON_CONTRAST
    assert contrast(ink.accent, background) >= ICON_CONTRAST


def test_a_changed_panel_redraws_the_icons(qapp: QApplication) -> None:
    window = window_of(qapp, captions=1)
    try:
        dark = ink_of(window.controls["settings"].icon())
        window.set_look(replace(window.look, background="#f6f1e6"))  # Paper's
        light = ink_of(window.controls["settings"].icon())
        assert dark != light and contrast(light, "#f6f1e6") >= ICON_CONTRAST
    finally:
        window.close()


def test_a_joined_windows_controls_follow_its_columns_panel(
    qapp: QApplication,
) -> None:
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
        windows.set_captioned(THREE)
        windows.join()
        windows.set_look(replace(CaptionLook(), background="#f6f1e6"))
        window = joined(windows)
        for name in ("lock", "settings"):
            drawn = ink_of(window.controls[name].icon())
            assert contrast(drawn, "#f6f1e6") >= ICON_CONTRAST, name
    finally:
        windows.close()


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
@pytest.mark.parametrize("video", ("#f3f5f7", "#000000"))
def test_the_top_bars_words_and_icons_read_over_a_light_or_dark_video(
    preset: object, video: str
) -> None:
    """The bar as it's seen (polyglotic-hq 284): its band over the panel at
    zero opacity over the video, where the controls have the least protection."""
    from polyglotic_desktop.ui_next.caption_window import band_alpha
    from polyglotic_desktop.ui_next.views.presets import _mix

    background = preset.background  # type: ignore[attr-defined]
    band = _mix(video, background, band_alpha(background, 0.0))
    ink = bar_ink(background)
    assert contrast(ink.text, band) >= BAR_CONTRAST
    assert contrast(ink.accent, band) >= ICON_CONTRAST


def test_a_hovered_word_shows_on_a_light_panel(qapp: QApplication) -> None:
    """The soft highlight behind the word under the mouse, the hovered
    window's edge and a joined window's dividers: black on Paper's cream,
    where white was invisible (polyglotic-hq 284)."""
    from polyglotic_desktop.ui_next.caption_window import shade

    paper = bar_ink("#f6f1e6")
    dark = bar_ink(CaptionLook().background)
    assert shade(paper, 46).name() == "#000000"
    assert shade(dark, 46).name() == "#ffffff" and shade(dark, 46).alpha() == 46
