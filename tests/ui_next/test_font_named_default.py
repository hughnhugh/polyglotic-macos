"""The caption font Polyglotic chooses is marked "(Default)" -
"Polyglotic's own" didn't say it was the default (the user's rehearsal
feedback F20, polyglotic-hq 249, 2026-11-08); since 482 each language's
row names its face too: "Ma Shan Zheng (Default)" (532)."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.face_rows import FaceBox


def test_the_default_font_says_it_is_the_default(qapp: QApplication) -> None:
    box = FaceBox("zh")
    try:
        assert box.currentText() == "Ma Shan Zheng (Default)"
        assert box.currentData() == ""
        box.showPopup()  # the PC's fonts listed: still there, same name
        box.hidePopup()
        assert box.currentText() == "Ma Shan Zheng (Default)"
        windows_own = FaceBox("ko")  # no face of its own yet: Windows' is the default
        assert windows_own.currentText().endswith("(Default)")
        windows_own.deleteLater()
    finally:
        box.deleteLater()
