"""The apps with sound, found off the interface thread.

Listing them asks Windows for every audio session (COM): 7-33 ms each time
(polyglotic-hq projects 108 and 110), and it was asked on the interface
thread every 3 seconds while the Audio page showed and every 5 seconds
for a chosen app not yet open. `AppsWithSound` asks on a thread of its
own (`look`) and says what it found on the interface thread (`found`);
`playing_apps` answers at once with what was found last - none before
the first look has answered (polyglotic-hq 291: asked there and then on
the interface thread, as before, it held the interface 1.2s on a tester's
Windows 10 PC with four output devices - Windows' audio devices, the
first time they're asked). Whoever needs the list follows `found` (the
hub, the sources). The first look comes when `look` is first asked for -
`main` asks right after the window's first paint - or `FIRST_LOOK_MS`
after the first ask, whichever is sooner: a look on its thread while the
window was still being built slowed the start ~15 ms (the threads share
Python's lock).

One thread for every look, kept until `stop` (the app closing): it joins
Windows' COM apartment once, not every few seconds (polyglotic-hq project
117, Low 12).

The app picker (`AudioPage`) and `main`'s sources share one; it's the
`AppList` port they both read. An app's name stays on this PC.
"""

import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from polyglotic_desktop.ports.capture import AppList, PlayingApp

log = logging.getLogger(__name__)

FIRST_LOOK_MS = 500
"""The first look starts this long after the first ask, unless `look` is
asked for sooner."""


class AppsWithSound(QObject):
    found = Signal()  # a look finished: `playing_apps` has its answer
    _looked = Signal(object)  # from the looking thread: a list of PlayingApp

    def __init__(self, apps: AppList, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._apps = apps
        self._last: list[PlayingApp] | None = None
        self._looking = False
        self._looked.connect(self._take, Qt.ConnectionType.QueuedConnection)
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="apps-with-sound")
        self._first = QTimer(self, singleShot=True, interval=FIRST_LOOK_MS)
        self._first.timeout.connect(self.look)

    def playing_apps(self) -> list[PlayingApp]:
        """The apps found last; none until the first look answers - which
        starts `FIRST_LOOK_MS` after the first ask at the latest (`found`
        when done)."""
        if self._last is None:
            if not self._looking and not self._first.isActive():
                self._first.start()
            return []
        return list(self._last)

    def look(self) -> None:
        """Looks again, on its thread; `found` when done. A look already
        under way answers this one too; after `stop`, nothing."""
        self._first.stop()
        if self._looking:
            return
        try:
            self._worker.submit(self._look)
        except RuntimeError:  # stopped: the app is closing
            return
        self._looking = True

    def stop(self) -> None:
        """No more looks; the thread ends once a look under way is done
        (tens of milliseconds at most)."""
        self._worker.shutdown(wait=True, cancel_futures=True)

    def _look(self) -> None:
        try:
            apps = self._apps.playing_apps()
        except Exception:
            log.exception("couldn't list the apps with sound")
            apps = None
        with contextlib.suppress(RuntimeError):  # this went (the app closing)
            self._looked.emit(apps)

    @Slot(object)
    def _take(self, apps: list[PlayingApp] | None) -> None:
        self._looking = False
        if apps is not None:
            self._last = apps
        self.found.emit()
