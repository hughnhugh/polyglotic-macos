"""Windows' fonts read ahead of the first window, beside the start's other
work (polyglotic-hq 322, decision 0112).

Qt reads Windows' fonts on whichever thread first asks: the list of
families at the first font used (about 0.1 s), and every family's faces at
the first font list that needs a fallback (about 0.2 s) - the interface's
own list does, at Home's first label. Both were the interface thread's, and
held the interpreter: 0.3 s of the start in which nothing else ran.

`FontsAhead` has them read on a thread of their own from the moment the
QApplication exists, by a call that doesn't hold the interpreter (the OS
adapters' `read_fonts`), while the interface thread reads the learner's
data. `wait` comes before the first font is used: by then the fonts are
read, or nearly, and what's left of the wait is the other threads' to use.

Only on Qt's `windows` platform: offscreen (the tests, the start gate,
`--check-install`) Qt reads its fonts another way, at once.
"""

import threading
from collections.abc import Callable

from PySide6.QtGui import QGuiApplication

THREAD = "fonts-ahead"
"""The reading thread's name. Not a daemon: it is inside Qt, and Qt must
not be taken down under it - an app that quits at once waits for it."""


class FontsAhead:
    """Windows' fonts, read on a thread of their own by `read` (None: this
    OS has no such call; they're read when first needed, as before)."""

    def __init__(self, read: Callable[[], object] | None) -> None:
        self._read = read
        self._thread: threading.Thread | None = None

    def begin(self) -> bool:
        """The read begins, if it can be made here and hasn't begun. Call it
        once the QGuiApplication exists, before any font is used."""
        if (
            self._read is None
            or self._thread is not None
            or QGuiApplication.platformName() != "windows"
        ):
            return False
        self._thread = threading.Thread(target=self._read, name=THREAD)
        self._thread.start()
        return True

    def wait(self) -> None:
        """Until the fonts are read - at once if the read never began or is
        over. The interpreter is let go meanwhile."""
        if self._thread is not None:
            self._thread.join()
