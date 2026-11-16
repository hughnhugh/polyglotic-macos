"""Windows' first-time work for a process's first window, done ahead of
the main window, while the start waits for something else (polyglotic-hq
322, decision 0113).

The first top-level window a process shows costs about 0.1 s more than any
after it: Windows loads what a window that takes drops needs (Qt registers
every top-level window for drag and drop) - its data-exchange and
certificate libraries. That was inside the main window's first show, on the
interface thread, holding the interpreter.

`made_ahead` has a widget nobody sees given its window of Windows' and
taken away again, through the OS adapters' call that doesn't hold the
interpreter (`make_native_window`). `main` does it while it waits for
Windows' fonts (`fonts_ahead`): the same 0.1 s, in time the interface
thread had nothing to do with, and the imports' thread runs through it.

Only on Qt's `windows` platform: offscreen there is no such window.
"""

from collections.abc import Callable

import shiboken6
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget


def made_ahead(make: Callable[[int], object] | None) -> bool:
    """Whether a first window was made and taken away just now, by `make`
    (None: this OS has no such call). Call it on the interface thread, once
    the QApplication exists; nothing is shown."""
    if make is None or QGuiApplication.platformName() != "windows":
        return False
    widget = QWidget()
    try:
        return bool(make(shiboken6.getCppPointer(widget)[0]))
    finally:
        shiboken6.delete(widget)
