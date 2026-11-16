"""Qt for the view tests: one application, offscreen, so no window
appears (locally or in CI)."""

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui.interface_language import install


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    if not app.property("interface_language"):  # as the app starts (decision 0034):
        app.setProperty("interface_language", "en")  # English's counts, numbers
        install(app, "en")
    yield app
