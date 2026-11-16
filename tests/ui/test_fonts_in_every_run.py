"""Qt draws the UI tests' text in Windows' fonts whichever tests run
(polyglotic-hq 258): `tests/conftest.py` sets the fonts folder before any
test makes the application. Without it, offscreen Qt on Windows has no
fonts: a run of `tests/ui` alone drew boxes, then - once a DesktopApp had
added the theme's heading face - that one Latin face, with no Chinese,
and 249's underline and arrow tests failed (on main, 2026-11-08). A whole
run had the fonts only because it collects the UI lab's tests, whose
`tools.ui_lab.lab` sets the same folder."""

import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


@pytest.mark.windows_only
def test_the_tests_draw_in_windows_fonts(qapp: QApplication) -> None:
    assert "Segoe UI" in QFontDatabase.families(), len(QFontDatabase.families())
    chinese = QFontDatabase.families(QFontDatabase.WritingSystem.SimplifiedChinese)
    assert chinese  # a face to draw the Chinese captions' text in
