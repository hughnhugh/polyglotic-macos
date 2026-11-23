"""One copy of the app per user and data folder (polyglotic-hq 310, decision
0101): a second start brings the first copy's main window forward and ends,
before it opens the settings, the outbox, the log or a window.

Two copies would share one settings file, one outbox and one learning file,
take the hotkeys twice and both talk to the server. The copy that runs
holds the data folder's `CopyLock` (`ports.one_copy`, a named mutex on
Windows) and answers on a local socket of the same name (Qt's: a named
pipe on Windows), a line each way:
- the copy that runs, when a start connects: `polyglotic <its process ID>`;
- the start, having let that process to the front: `show`;
- the copy that runs: `shown` - and its main window comes forward, as the
  tray's Open brings it (restored if minimised, shown if in the tray).

A start with `--lock`, `--pause` or `--hide` (polyglotic-hq 570) asks
instead for what that hotkey does - `lock`, `pause` or `hide` - and is
answered `done`, or `not yet` while the copy is still asking its first
run's questions; it then ends, whatever the answer, without running
(`tell`). A shortcut the learner made in their desktop's own settings runs
`polyglotic --lock` where the desktop gives an app no hotkey of its own
(GNOME's Wayland session). With no copy running it ends at once.

The name comes from the user and the data folder, so a copy with a folder
of its own - a test's, a copy from source beside the installed one, QA's -
runs beside the others. The socket alone can't be the lock: on Windows two
servers can listen under one name.
"""

from __future__ import annotations

import getpass
import hashlib
import logging
import os
import time
from collections.abc import Callable
from enum import Enum
from functools import partial
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ports.one_copy import LetToFront
from polyglotic_desktop.ui.os_words import pc_mac_or_linux

log = logging.getLogger(__name__)

WAIT_SEC = 8.0
"""How long a second start waits for the copy that runs: its window is
usually up within 1-3 s of its start, and it answers from then on. A copy
not answering in this long is stuck, or ending - then this start runs."""
RETRY_SEC = 0.1  # between tries while the copy that runs isn't listening yet
CONNECT_MS = 200
ANSWER_MS = 5_000  # a start that connects and says nothing is let go
GREETING = b"polyglotic"
SHOW, SHOWN = b"show", b"shown"
COMMANDS = ("lock", "pause", "hide")
"""What a start can ask the copy that runs to do, as its hotkey does (570):
each the hotkey's name (`core.listening.hotkeys.Hotkey`)."""
DONE, NOT_YET = b"done", b"not yet"
TELL_SEC = 2.0
"""How long a start with a command waits for the copy that runs to answer."""
LONGEST_LINE = 64


def _tr(text: str) -> str:
    return QApplication.translate("OneCopy", text)


def user() -> str:
    """Who is signed in to the OS, by name - blank where it won't say: a
    start never fails on it."""
    try:
        return getpass.getuser()
    except (ImportError, KeyError, OSError):
        return ""


def copy_name(data: Path, user: str) -> str:
    """The name the copy for `user` and the data folder `data` holds its lock
    and listens under: the same for any spelling of the same folder."""
    try:
        folder = data.resolve()
    except OSError:  # not there, or unreadable: as given, made whole
        folder = data.absolute()
    key = f"{user.casefold()}\n{os.path.normcase(str(folder))}"
    return "Polyglotic-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class Start(Enum):
    """How a start went."""

    RUNS = "runs"
    """This copy holds the lock: it runs."""
    SHOWN = "shown"
    """The copy that runs brought its main window forward: this one ends."""
    ALREADY = "already running"
    """Started in the tray (as Windows starts it) while a copy runs: this
    one ends, nothing shown."""
    NO_ANSWER = "no answer"
    """A copy holds the lock but didn't answer in `WAIT_SEC`: this one ends,
    and says so."""


def start(
    take: Callable[[], bool],
    ask: Callable[[float], bool],
    show: bool,
    wait_sec: float = WAIT_SEC,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Start:
    """Takes the lock (`take`), or asks the copy that holds it to show its
    window (`ask`, given the seconds left) until it says it has - trying the
    lock again between asks, as that copy may be ending (an update's
    restart, a Quit a moment ago). `show` False (started in the tray): a
    copy holding it is enough."""
    end = clock() + wait_sec
    while True:
        if take():
            return Start.RUNS
        if not show:
            return Start.ALREADY
        left = end - clock()
        if left <= 0:
            return Start.NO_ANSWER
        if ask(left):
            return Start.SHOWN
        sleep(max(0.0, min(RETRY_SEC, end - clock())))


def ask_to_show(name: str, let_to_front: LetToFront, wait_sec: float) -> bool:
    """Asks the copy listening under `name` to bring its main window forward:
    True once it says it has. False at once if none listens (not yet, or no
    longer), or if it doesn't answer within `wait_sec`."""
    end = time.monotonic() + wait_sec
    socket = QLocalSocket()
    socket.connectToServer(name)
    try:
        if not socket.waitForConnected(CONNECT_MS):
            return False
        greeting = _line(socket, end)
        if greeting is None:
            return False
        said, _, pid = greeting.partition(b" ")
        if said != GREETING or not pid.isdigit():
            return False
        let_to_front(int(pid))  # before it asks Windows to bring it forward
        socket.write(SHOW + b"\n")
        socket.flush()  # its answer is what counts: none comes if this didn't go
        return _line(socket, end) == SHOWN
    finally:
        socket.abort()


class Told(Enum):
    """What the copy that runs said to a command (`tell`)."""

    DONE = "done"
    NOT_YET = "not yet"
    """Still asking its first run's questions: nothing done."""
    NO_COPY = "no copy running"
    """None listens, or none answered in time."""


def tell(name: str, command: str, wait_sec: float = TELL_SEC) -> Told:
    """Asks the copy listening under `name` to do `command` (one of
    `COMMANDS`), as its hotkey does."""
    if command not in COMMANDS:
        raise ValueError(f"not a command: {command!r}")
    end = time.monotonic() + wait_sec
    socket = QLocalSocket()
    socket.connectToServer(name)
    try:
        if not socket.waitForConnected(CONNECT_MS):
            return Told.NO_COPY
        greeting = _line(socket, end)
        if greeting is None or not greeting.startswith(GREETING + b" "):
            return Told.NO_COPY
        socket.write(command.encode("ascii") + b"\n")
        socket.flush()
        said = _line(socket, end)
        if said == DONE:
            return Told.DONE
        return Told.NOT_YET if said == NOT_YET else Told.NO_COPY
    finally:
        socket.abort()


def _ms_left(end: float) -> int:
    return max(0, int((end - time.monotonic()) * 1000))


def _line(socket: QLocalSocket, end: float) -> bytes | None:
    """The next line from `socket`, or None if none comes before `end`."""
    while not socket.canReadLine():
        if socket.bytesAvailable() > LONGEST_LINE:
            return None
        left = _ms_left(end)
        if left <= 0 or not socket.waitForReadyRead(left):
            return None
    return bytes(socket.readLine(LONGEST_LINE).data()).strip()


def not_answering() -> str:
    """What a start says when the copy that runs doesn't answer."""
    return pc_mac_or_linux(
        _tr(
            "Polyglotic is already open, but it isn't responding. Wait a moment,"
            " then open it again. If it still doesn't come up, end Polyglotic in"
            " Task Manager, then open it again."
        ),
        _tr(
            "Polyglotic is already open, but it isn't responding. Wait a moment, then "
            "open it again. If it still doesn't come up, force quit Polyglotic (⌥⌘Esc),"
            " then open it again."
        ),
        # Linux: GNOME's and KDE's are both called System Monitor (571)
        _tr(
            "Polyglotic is already open, but it isn't responding. Wait a moment, then "
            "open it again. If it still doesn't come up, end Polyglotic in System "
            "Monitor, then open it again."
        ),
    )


class SecondStarts(QObject):
    """The copy that runs: listens under its name and answers each start that
    finds it, bringing its main window forward (`show_with`). Before the
    main window is there - the first run's questions - the question in
    front comes forward instead, and the window is shown once it's there
    (a copy that started in the tray and hasn't shown it yet). Stops
    answering as `app` quits."""

    def __init__(self, name: str, app: QCoreApplication) -> None:
        super().__init__(app)
        self._show: Callable[[], None] | None = None
        self._do: Callable[[str], None] | None = None
        self._wanted = False
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._connected)
        QLocalServer.removeServer(name)  # a socket file a crash left (not Windows)
        if not self._server.listen(name):
            log.warning(
                "one copy: a second start can't reach this copy (%s)",
                self._server.serverError().name,
            )
        app.aboutToQuit.connect(self.close)

    @property
    def listening(self) -> bool:
        return self._server.isListening()

    def show_with(self, show: Callable[[], None]) -> None:
        """`show` brings the main window forward from now on - at once if a
        start asked before it was there."""
        self._show = show
        if self._wanted:
            self._wanted = False
            show()

    def do_with(self, do: Callable[[str], None]) -> None:
        """`do` carries out a start's command (one of `COMMANDS`) from now
        on; before, such a start is told `not yet`."""
        self._do = do

    def close(self) -> None:
        """At quit: a start from now on waits for this copy to end, then
        runs, rather than being answered by a copy on its way out."""
        self._server.close()

    def _connected(self) -> None:
        while (socket := self._server.nextPendingConnection()) is not None:
            socket.readyRead.connect(partial(self._read, socket))
            socket.disconnected.connect(socket.deleteLater)
            QTimer.singleShot(ANSWER_MS, socket, socket.abort)
            socket.write(GREETING + f" {os.getpid()}\n".encode("ascii"))

    def _read(self, socket: QLocalSocket) -> None:
        if not socket.canReadLine():
            if socket.bytesAvailable() > LONGEST_LINE:
                socket.abort()
            return
        line = bytes(socket.readLine(LONGEST_LINE).data()).strip()
        command = line.decode("ascii", "replace")
        if command in COMMANDS:
            self._command(socket, command)
            return
        if line != SHOW:
            socket.abort()
            return
        socket.write(SHOWN + b"\n")
        socket.disconnectFromServer()  # once what's written has gone
        log.info("a second start: the main window brought forward")
        self._bring_forward()

    def _command(self, socket: QLocalSocket, command: str) -> None:
        do = self._do
        socket.write((DONE if do is not None else NOT_YET) + b"\n")
        socket.disconnectFromServer()  # once what's written has gone
        if do is not None:
            log.info("a start asked: %s", command)
            do(command)

    def _bring_forward(self) -> None:
        if self._show is not None:
            self._show()
            return
        question = QApplication.activeModalWidget()
        if question is None:
            self._wanted = True
            return
        question.setWindowState(
            question.windowState() & ~Qt.WindowState.WindowMinimized
        )
        question.raise_()
        question.activateWindow()
