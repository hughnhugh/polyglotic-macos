"""The caption font Polyglotic chooses is marked "(Default)" -
"Polyglotic's own" didn't say it was the default (the user's rehearsal
feedback F20, polyglotic-hq 249, 2026-11-08); since 482 each language's
row names its face too, and since 952 Chinese defaults to the platform's
plain CJK UI face."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next import fonts
from polyglotic_desktop.ui_next.face_rows import FaceBox


def test_the_default_font_says_it_is_the_default(qapp: QApplication) -> None:
    box = FaceBox("zh")
    expected = f"{fonts.default_family('zh')} (Default)"
    try:
        assert box.currentText() == expected
        assert box.currentData() == ""
        box.showPopup()  # the PC's fonts listed: still there, same name
        box.hidePopup()
        assert box.currentText() == expected
        windows_own = FaceBox("ko")  # no face of its own yet: Windows' is the default
        assert windows_own.currentText().endswith("(Default)")
        windows_own.deleteLater()
    finally:
        box.deleteLater()
