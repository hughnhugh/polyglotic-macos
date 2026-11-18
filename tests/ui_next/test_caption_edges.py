"""Visibility: what's drawn around captions' letters (polyglotic-hq 481; the
user, 2026-11-18: "there should be different font thickness, visibility,
contrast, brightness customisations") - nothing (today's), a soft shadow or
an outline, black around light text and white around dark, in Settings >
Look's caption text. No Brightness slider: on a panel it's Contrast.
Offscreen, a made-up caption."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.made_up import EN, finished_updates

from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, Ink
from polyglotic_desktop.ui_next.caption_window import look_ink
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, TextEdge
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import BY_KEY, PRESETS
from polyglotic_desktop.ui_next.views.tone import edge_colour

MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            shiboken6.delete(made)


def test_the_edge_stands_furthest_from_the_text() -> None:
    for preset in PRESETS:
        for text in (preset.original, preset.translation):
            dark = preset.key == "paper"
            assert edge_colour(text) == ("#ffffff" if dark else "#000000"), (
                preset.key,
                text,
            )


def test_nothing_is_drawn_around_the_letters_until_chosen() -> None:
    assert CaptionLook().edge is TextEdge.NONE
    assert look_ink(Ink(), CaptionLook()).edge is TextEdge.NONE
    for edge in (TextEdge.SHADOW, TextEdge.OUTLINE):
        assert look_ink(Ink(), CaptionLook(edge=edge)).edge is edge
        assert look_ink(Ink(), CaptionLook(edge=edge, quiet=True)).edge is edge


def test_the_edge_is_kept_and_read_leniently() -> None:
    look = replace(CaptionLook(), edge=TextEdge.OUTLINE)
    stored = AppSettings().to_stored() | look_settings(look)
    assert caption_look(AppSettings.from_stored(stored)).edge is TextEdge.OUTLINE
    assert caption_look(AppSettings()).edge is TextEdge.NONE
    for wrong in ("glow", 1, None, True):
        assert AppSettings.from_stored({"caption_edge": wrong}).caption_edge == "none"


def _line() -> Line:
    view = CaptionLines((APP,), EN, keep=10, yours=(MIC,))
    view.apply(finished_updates(1, APP)[0])
    return view.lines[0]


def _painted(edge: TextEdge, panel: str, text: str) -> QImage:
    line = _line()
    engine = CaptionLayout()
    laid = engine.laid(line, 600, 1.0)
    image = QImage(640, int(laid.height) + 40, QImage.Format.Format_ARGB32)
    image.fill(QColor(panel))
    painter = QPainter(image)
    ink = Ink(QColor(text), QColor(text), panel=panel, edge=edge)
    engine.paint(painter, line, laid, QPointF(20, 20), ink)
    painter.end()
    return image


def _count(image: QImage, halo: str) -> int:
    """Pixels moved well towards `halo` from the mid grey under them: the
    text itself moves the other way."""
    darker = QColor(halo).lightness() < 128
    return sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if (image.pixelColor(x, y).lightness() < 98) == darker
        and abs(image.pixelColor(x, y).lightness() - 128) > 30
    )


@pytest.mark.parametrize("edge", [TextEdge.SHADOW, TextEdge.OUTLINE])
@pytest.mark.parametrize("key", ["classic", "paper"])
def test_an_edge_draws_round_the_letters_on_a_dark_panel_and_a_light_one(
    qapp: QApplication, edge: TextEdge, key: str
) -> None:
    """Over a mid grey (a video seen through the panel): an edge in black
    around light text (Classic's), white around dark (Paper's); an outline
    more of it than a shadow."""
    preset = BY_KEY[key]
    grey, text = "#808080", preset.original
    halo = edge_colour(text)
    plain = _count(_painted(TextEdge.NONE, grey, text), halo)
    edged = _count(_painted(edge, grey, text), halo)
    assert edged > plain + 200, (plain, edged)
    if edge is TextEdge.OUTLINE:
        shadow = _count(_painted(TextEdge.SHADOW, grey, text), halo)
        assert edged > shadow


def test_visibility_sits_with_the_caption_text_and_points_to_the_panel(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    MADE.append(panel)
    edge = panel.text.edge
    assert edge.objectName() == "look.edge" and edge.value() == "none"
    assert "panel" in edge.toolTip()  # how solid the panel is: Look's own slider
    edge.choose("outline")
    assert view.value.edge is TextEdge.OUTLINE
    view.reset()
    panel.refresh()
    assert edge.value() == "none"


def test_the_caption_text_fits_a_transcripts_rail_in_every_language(
    qapp: QApplication,
) -> None:
    """503: the caption text's names over its sliders, and the ends' columns
    as wide as their longest, leave Look no wider than a transcript's rail
    in any interface language. Train B's UI lab run found Filipino's needing
    376 px of the rail card's 314: the rail's column grew past its view, and
    every line in it was cut off at the right."""
    from PySide6.QtCore import QLocale

    from polyglotic_desktop.ui import interface_language
    from polyglotic_desktop.ui.interface_language import ENGLISH, formats, install
    from polyglotic_desktop.ui_next import style
    from polyglotic_desktop.ui_next.transcript_window import SettingsRail
    from polyglotic_desktop.ui_next.views.transcript import RAIL_WIDTH

    too_wide = {}
    try:
        for code in interface_language.OFFERED:
            installed = install(qapp, code)
            style.use_interface_language(code)
            rail = SettingsRail()
            MADE.append(rail)
            rail.setStyleSheet(style.stylesheet(style.current()))
            rail.add_panel(LookPanel(LookView(CaptionLook())))
            rail.setFixedSize(style.px(RAIL_WIDTH), style.px(900))
            rail.show()
            qapp.processEvents()
            column = rail.widget()
            assert column is not None
            needs = column.minimumSizeHint().width()
            if needs > rail.viewport().width():
                too_wide[code] = (needs, rail.viewport().width())
            for translator in installed:
                qapp.removeTranslator(translator)
    finally:
        style.use_interface_language(ENGLISH)
        QLocale.setDefault(formats(ENGLISH, QLocale.system()))
    assert too_wide == {}
