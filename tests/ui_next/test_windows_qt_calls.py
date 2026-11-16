"""Calls into Qt's own library that don't hold the interpreter
(`platform/windows/qt_calls.py`, polyglotic-hq 322, decision 0112)."""

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF
from PySide6.QtWidgets import QApplication, QWidget

pytestmark = pytest.mark.windows_only  # Qt's library as Windows names its functions


def test_this_qt_has_the_function_the_fonts_are_read_by(qapp: QApplication) -> None:
    """A Qt update that loses the name is seen here, before it ships: the
    fonts would be read on the interface thread again, 0.3 s of the start."""
    from polyglotic_desktop.platform.windows import qt_calls

    assert qt_calls.exported(qt_calls.GUI_LIBRARY, qt_calls.EVERY_FAMILY_READ)
    assert (
        qt_calls.exported(qt_calls.GUI_LIBRARY, "?no_such@QFontDatabase@@SAXXZ") is None
    )
    assert qt_calls.exported("NotLoadedHere.dll", qt_calls.EVERY_FAMILY_READ) is None


def test_the_fonts_are_read_and_qt_goes_on_as_before(qapp: QApplication) -> None:
    from polyglotic_desktop.platform.windows import qt_calls

    assert qt_calls.read_fonts()
    assert qt_calls.read_fonts()  # again: nothing left to read, no harm

    assert QFontDatabase.families()
    assert QFontMetricsF(QFont()).horizontalAdvance("Home 设置") > 0


def test_the_call_is_one_that_lets_the_interpreter_go(qapp: QApplication) -> None:
    """The point of calling Qt this way: for the call's length another
    thread's Python runs. ctypes lets the interpreter go for every function
    of a `CDLL` - not for one flagged as Python's own API (`PyDLL`)."""
    import ctypes

    from polyglotic_desktop.platform.windows import qt_calls

    read = qt_calls.exported(qt_calls.GUI_LIBRARY, qt_calls.EVERY_FAMILY_READ)

    assert read is not None
    assert not read._flags_ & ctypes._FUNCFLAG_PYTHONAPI  # type: ignore[attr-defined]


def test_this_qt_has_the_function_a_window_is_made_by(qapp: QApplication) -> None:
    """Decision 0113: lost, the first window's 0.1 s is the main window's
    again."""
    from polyglotic_desktop.platform.windows import qt_calls

    assert qt_calls.exported(qt_calls.WIDGETS_LIBRARY, qt_calls.NATIVE_WINDOW)


def test_a_widget_is_given_its_window_and_qt_goes_on_as_before(
    qapp: QApplication,
) -> None:
    import ctypes

    from polyglotic_desktop.platform.windows import qt_calls

    widget = QWidget()
    try:
        assert not widget.testAttribute(Qt.WidgetAttribute.WA_WState_Created)
        assert qt_calls.make_native_window(shiboken6.getCppPointer(widget)[0])
        assert widget.testAttribute(Qt.WidgetAttribute.WA_WState_Created)
        assert widget.winId()  # the same window, asked of PySide
        assert not widget.isVisible()  # made, never shown
    finally:
        shiboken6.delete(widget)
    make = qt_calls.exported(qt_calls.WIDGETS_LIBRARY, qt_calls.NATIVE_WINDOW)
    assert make is not None
    assert not make._flags_ & ctypes._FUNCFLAG_PYTHONAPI  # type: ignore[attr-defined]
