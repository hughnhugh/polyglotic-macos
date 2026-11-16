"""The caption font Polyglotic chooses is called "Polyglotic (Default)" -
"Polyglotic's own" didn't say it was the default (the user's rehearsal
feedback F20, polyglotic-hq 249, 2026-11-08)."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView


def test_the_default_font_says_it_is_the_default(qapp: QApplication) -> None:
    panel = LookPanel(LookView(CaptionLook()))
    assert panel.font_box.currentText() == "Polyglotic (Default)"
    assert panel.font_box.currentData() is None
    panel.font_box.showPopup()  # the PC's fonts listed: still first, same name
    panel.font_box.hidePopup()
    assert panel.font_box.itemText(0) == "Polyglotic (Default)"
    assert panel.font_box.itemData(0) is None
