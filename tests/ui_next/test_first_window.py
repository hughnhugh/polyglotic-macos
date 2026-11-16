"""Windows' first-time work for a first window, done ahead of the main
window (`ui_next/first_window.py`, polyglotic-hq 322, decision 0113)."""

from typing import cast

import pytest
import shiboken6
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.ui_next.first_window import made_ahead


def test_offscreen_no_window_is_made_ahead(qapp: QApplication) -> None:
    asked: list[int] = []

    assert QGuiApplication.platformName() == "offscreen"
    assert not made_ahead(asked.append)
    assert asked == []


def test_with_real_windows_a_widget_nobody_sees_gets_its_window_and_goes(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "windows")
    before = set(QApplication.topLevelWidgets())
    seen: list[tuple[QWidget, bool, bool]] = []

    def make(address: int) -> bool:
        widget = cast(QWidget, shiboken6.wrapInstance(address, QWidget))
        seen.append((widget, widget.isVisible(), widget.isWindow()))
        return True

    assert made_ahead(make)

    [(widget, visible, top_level)] = seen
    assert top_level and not visible  # a window of its own, never shown
    assert not shiboken6.isValid(widget)  # and gone: nothing is kept
    assert set(QApplication.topLevelWidgets()) == before


def test_the_widget_goes_even_if_the_call_fails(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "windows")
    before = set(QApplication.topLevelWidgets())

    assert not made_ahead(lambda widget: False)  # the name wasn't found
    assert set(QApplication.topLevelWidgets()) == before


def test_an_os_with_no_such_call_makes_none(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QGuiApplication, "platformName", lambda: "windows")
    assert not made_ahead(None)
