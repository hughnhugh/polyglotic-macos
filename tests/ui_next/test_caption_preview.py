"""The live preview at the top of Settings > Captions > Look (polyglotic-hq
248's section 2.1; 261): two made-up captions over the app's own still,
drawn by the caption windows' engine in the look now, redrawn as it
changes - the thing the "Look..." window never had."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.ui_next.caption_preview import CaptionPreview
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView

MADE: list[QWidget] = []
"""What a test made, deleted at its end (`deleted`)."""


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each preview and panel deleted when its test ends, not at the
    interpreter's exit, where one still bound to its view can crash the run
    (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def shown(qapp: QApplication, view: LookView) -> CaptionPreview:
    preview = CaptionPreview(view)
    MADE.append(preview)
    preview.resize(640, 230)
    preview.show()
    qapp.processEvents()
    return preview


def test_it_follows_a_preset_a_colour_and_the_panel(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    preview = shown(qapp, view)
    view.set_preset("ember")
    ink = preview.surface.ink
    assert ink.original == QColor("#dcecff") and ink.translation == QColor("#ffa64d")
    view.set_colour("translation", "#7fe3ff")
    assert preview.surface.ink.translation == QColor("#7fe3ff")
    image = preview.grab().toImage()
    panel = preview.panel_rect()
    inside = image.pixelColor(int(panel.left()) + 4, int(panel.center().y()))
    outside = image.pixelColor(int(panel.left()) - 6, int(panel.center().y()))
    assert inside != outside  # the panel is drawn over the still
    preview.close()


def test_it_shows_what_the_look_shows(qapp: QApplication) -> None:
    view = LookView(CaptionLook(show_original=True))
    preview = shown(qapp, view)
    kinds = {row.kind for line in preview.lines.lines for row in line.rows}
    assert kinds == {RowKind.ORIGINAL, RowKind.TRANSLATION}
    tall = preview.panel_rect().height()
    view.set_show_original(False)
    kinds = {row.kind for line in preview.lines.lines for row in line.rows}
    assert kinds == {RowKind.TRANSLATION}
    assert preview.panel_rect().height() < tall  # the panel fits its captions
    view.set_font("Segoe UI")
    assert preview.surface.engine.style.family == "Segoe UI"
    view.set_word_links(WordLinks.ARROWS)
    view.set_show_original(True)
    assert preview.surface.engine.style.arrows  # room for the curves
    preview.close()


def test_it_is_at_the_top_of_settings_look_only(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    settings, rail = LookPanel(view, notes=True, preview=True), LookPanel(view)
    MADE.extend((settings, rail))
    assert settings.preview is not None and rail.preview is None
    preset_row = settings.presets.parentWidget()
    assert preset_row is not None
    column = settings.column
    assert column.indexOf(settings.preview) < column.indexOf(preset_row)


def test_a_preview_that_goes_is_no_longer_told(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    preview = CaptionPreview(view)
    preview.deleteLater()
    qapp.processEvents()
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    view.set_preset("paper")  # nothing left to tell: no error
