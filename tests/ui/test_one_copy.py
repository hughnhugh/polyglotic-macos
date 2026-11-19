"""One copy per user and data folder (polyglotic-hq 310, decision 0101): the
asking, on Qt's local socket (`ui/one_copy.py`). The copy that runs is this
test's `SecondStarts`; each start that asks it is a process of its own, as a
second start is - the real mechanism in two processes. `start`'s waiting
and trying again is tested on its own, with a made-up clock."""

import os
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import SIGNAL, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from polyglotic_desktop.ui import one_copy
from polyglotic_desktop.ui.one_copy import SecondStarts, Start, ask_to_show, copy_name
from polyglotic_desktop.ui.os_words import pc_or_mac

ROOT = Path(__file__).resolve().parents[2]
ASK = """
import sys
from polyglotic_desktop.ui.one_copy import ask_to_show
told = []
print(ask_to_show(sys.argv[1], told.append, float(sys.argv[2])), told)
"""
SAY = """
import sys
from PySide6.QtNetwork import QLocalSocket
socket = QLocalSocket()
socket.connectToServer(sys.argv[1])
socket.waitForConnected(2000)
socket.waitForReadyRead(2000)
socket.readLine()
socket.write(sys.argv[2].encode() + b"\\n")
socket.waitForBytesWritten(2000)
print(socket.waitForReadyRead(1500), bytes(socket.readAll().data()))
"""


@pytest.fixture
def name() -> str:
    return f"Polyglotic-test-310-{uuid.uuid4().hex}"


@pytest.fixture
def starts(qapp: QApplication, name: str) -> Iterator[SecondStarts]:
    answering = SecondStarts(name, qapp)
    assert answering.listening
    yield answering
    answering.close()
    answering.deleteLater()


def _in_another_process(qapp: QApplication, script: str, *args: str) -> str:
    """`script` in a Python of its own, with this test's event loop running -
    the copy that runs answers on it - until it ends: what it printed."""
    run = subprocess.Popen(
        [sys.executable, "-c", script, *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    end = time.monotonic() + 60
    while run.poll() is None and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    if run.poll() is None:
        run.kill()
    out, _ = run.communicate()
    qapp.processEvents()
    return out.strip().splitlines()[-1] if out.strip() else ""


def _asked(qapp: QApplication, name: str, wait: float = 5.0) -> str:
    return _in_another_process(qapp, ASK, name, str(wait))


# --- The copy that runs answers a second start ---------------------------------


def test_a_second_start_is_told_this_process_and_the_window_comes_forward(
    qapp: QApplication, starts: SecondStarts, name: str
) -> None:
    """The start lets this process to the front (its ID, as the greeting
    says it) before asking; the window comes forward once."""
    shown: list[str] = []
    starts.show_with(lambda: shown.append("shown"))

    said = _asked(qapp, name)

    assert said == f"True [{os.getpid()}]"
    assert shown == ["shown"]


def test_before_the_window_is_there_it_comes_forward_once_it_is(
    qapp: QApplication, starts: SecondStarts, name: str
) -> None:
    """A copy started in the tray, still building its window when asked: the
    start is answered, and the window shows once it's there."""
    assert _asked(qapp, name).startswith("True")
    shown: list[str] = []

    starts.show_with(lambda: shown.append("shown"))
    starts.show_with(lambda: shown.append("again"))  # once, not each time

    assert shown == ["shown"]


def test_during_the_first_runs_questions_the_question_comes_forward(
    qapp: QApplication, starts: SecondStarts, name: str
) -> None:
    """The first run's questions come before the main window: the question in
    front is restored and brought forward, and the window isn't wanted twice
    after it (it shows when the first run ends anyway)."""
    owner = QWidget()
    question = QDialog(owner)
    question.setWindowModality(Qt.WindowModality.ApplicationModal)
    question.show()
    question.showMinimized()
    qapp.processEvents()
    assert QApplication.activeModalWidget() is question
    try:
        assert _asked(qapp, name).startswith("True")
        assert not question.isMinimized()
        shown: list[str] = []
        starts.show_with(lambda: shown.append("shown"))
        assert shown == []
    finally:
        question.close()
        question.deleteLater()
        owner.deleteLater()
        qapp.processEvents()


def test_a_copy_that_is_quitting_answers_no_more(
    qapp: QApplication, starts: SecondStarts, name: str
) -> None:
    """At Quit it stops answering, so a start waits for it to end and runs
    itself (an update's restart), rather than being answered by a copy on
    its way out. Not answered, a start learns so at once."""
    shown: list[str] = []
    starts.show_with(lambda: shown.append("shown"))
    starts.close()  # as Quit does (`aboutToQuit`), before the copy ends

    began = time.monotonic()
    said = _asked(qapp, name, wait=5.0)

    assert said == "False []"
    assert shown == []
    assert time.monotonic() - began < 4  # not the wait: there's nobody to ask


def test_it_stops_answering_as_the_app_quits(qapp: QApplication, name: str) -> None:
    quitting = SIGNAL("aboutToQuit()")
    before = qapp.receivers(quitting)
    answering = SecondStarts(name, qapp)
    try:
        assert qapp.receivers(quitting) == before + 1
    finally:
        answering.close()
        answering.deleteLater()


def test_anything_but_show_is_turned_away(
    qapp: QApplication, starts: SecondStarts, name: str
) -> None:
    shown: list[str] = []
    starts.show_with(lambda: shown.append("shown"))

    said = _in_another_process(qapp, SAY, name, "open C:/Windows")

    assert said.endswith("b''")  # no answer: the connection was let go
    assert shown == []


# --- A copy that doesn't answer -----------------------------------------------------

HUNG = """
import sys, time
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer
app = QCoreApplication([])
server = QLocalServer()
print(server.listen(sys.argv[1]), flush=True)
time.sleep(float(sys.argv[2]))  # its interface thread stuck: no event loop
"""
NOT_OURS = """
import sys
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtNetwork import QLocalServer
app = QCoreApplication([])
server = QLocalServer()
def greet():
    socket = server.nextPendingConnection()
    socket.write(sys.argv[2].encode())
    socket.flush()
server.newConnection.connect(greet)
print(server.listen(sys.argv[1]), flush=True)
QTimer.singleShot(8000, app.quit)
app.exec()
"""


def _listening(script: str, *args: str) -> subprocess.Popen[str]:
    """A stand-in for the copy that runs, in a process of its own, once it
    listens."""
    run = subprocess.Popen(
        [sys.executable, "-c", script, *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert run.stdout is not None
    assert run.stdout.readline().strip() == "True"
    return run


def test_a_hung_copy_isnt_waited_on_past_the_wait(name: str) -> None:
    """Connected, but never greeted: False once the wait is over, not
    forever (then the start says the copy isn't responding)."""
    hung = _listening(HUNG, name, "20")
    try:
        let: list[int] = []
        began = time.monotonic()
        assert not ask_to_show(name, let.append, 1.5)
        assert 1.2 < time.monotonic() - began < 6
        assert let == []
    finally:
        hung.kill()
        hung.communicate()


@pytest.mark.parametrize("greeting", ["hello\n", "polyglotic me\n", "x" * 200])
def test_a_greeting_that_isnt_ours_is_no_answer(name: str, greeting: str) -> None:
    other = _listening(NOT_OURS, name, greeting)
    try:
        let: list[int] = []
        assert not ask_to_show(name, let.append, 2.0)
        assert let == []  # nobody is let to the front
    finally:
        other.kill()
        other.communicate()


def test_nobody_listening_is_no_answer_at_once(name: str) -> None:
    began = time.monotonic()
    assert not ask_to_show(name, lambda pid: None, 5.0)
    assert time.monotonic() - began < 2


# --- A start: the lock, or the copy that holds it asked ------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _start(
    takes: list[bool],
    answers: list[bool],
    show: bool = True,
    clock: Clock | None = None,
    asking_takes: float = 0.0,
) -> tuple[Start, list[float]]:
    """`start` with a lock taken as `takes` says, try by try (then not), and
    asks answered as `answers` says (then not); each ask costs
    `asking_takes` seconds. What it said, and each ask's seconds left."""
    clock = clock or Clock()
    tries, asks = iter(takes), iter(answers)
    left: list[float] = []

    def ask(seconds: float) -> bool:
        left.append(seconds)
        clock.now += min(asking_takes, seconds)  # never past what's left
        return next(asks, False)

    started = one_copy.start(
        lambda: next(tries, False), ask, show, 8.0, clock, clock.sleep
    )
    return started, left


def test_no_copy_running_this_one_runs_without_asking() -> None:
    assert _start([True], []) == (Start.RUNS, [])


def test_a_copy_running_is_asked_and_this_one_ends() -> None:
    started, left = _start([False], [True])
    assert started is Start.SHOWN
    assert left == [8.0]  # the whole wait is the answer's to use


def test_a_copy_still_starting_is_asked_again_until_it_listens() -> None:
    """Its lock taken, its socket not yet listening: asked every 0.1 s."""
    started, left = _start([False] * 30, [False] * 5 + [True])
    assert started is Start.SHOWN
    assert len(left) == 6
    assert left[0] - left[-1] == pytest.approx(0.5)


def test_a_copy_ending_is_waited_for_then_this_one_runs() -> None:
    """An update's restart, or a start just after Quit: the copy on its way
    out answers no more, and once it has ended the lock is this one's."""
    started, left = _start([False] * 12 + [True], [])
    assert started is Start.RUNS
    assert len(left) == 12


def test_a_copy_that_never_answers_is_said_after_the_wait() -> None:
    clock = Clock()
    started, left = _start([], [], clock=clock, asking_takes=1.0)
    assert started is Start.NO_ANSWER
    assert clock.now - 100.0 == pytest.approx(8.0, abs=0.2)
    assert left[0] == 8.0 and all(0 < s <= 8.0 for s in left)


def test_started_in_the_tray_a_copy_running_is_enough() -> None:
    """Windows starts the app in the tray at sign-in: with a copy running,
    nothing is asked and nothing shows."""
    assert _start([False], [True], show=False) == (Start.ALREADY, [])


# --- The name -------------------------------------------------------------------


def test_one_folder_however_its_written_is_one_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "Polyglotic"
    folder.mkdir()
    monkeypatch.chdir(tmp_path)
    same = [
        folder,
        Path("Polyglotic"),
        tmp_path / "x" / ".." / "Polyglotic",
        Path(str(folder) + os.sep),
    ]
    if sys.platform == "win32":  # Windows' paths ignore case and take /
        same += [Path(str(folder).upper()), Path(str(folder).replace("\\", "/"))]
    assert len({copy_name(f, "learner") for f in same}) == 1


def test_another_folder_or_person_is_another_copy(tmp_path: Path) -> None:
    """A test's folder, a copy from source beside the installed one, QA's on
    private desktops: each runs beside the others; and another person's."""
    names = {
        copy_name(tmp_path / "Polyglotic", "learner"),
        copy_name(tmp_path / "harness", "learner"),
        copy_name(tmp_path / "not-there-yet", "learner"),
        copy_name(tmp_path / "Polyglotic", "another"),
    }
    assert len(names) == 4


def test_the_name_is_one_windows_and_qt_take(tmp_path: Path) -> None:
    """A mutex's name may hold no backslash after its namespace; a pipe's
    is short."""
    name = copy_name(tmp_path / "Polyglotic", "learner")
    assert name.startswith("Polyglotic-") and len(name) == 43
    assert name.replace("-", "").isalnum()


def test_a_user_the_os_wont_name_still_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    def unnamed() -> str:
        raise OSError("no user name")

    monkeypatch.setattr(one_copy.getpass, "getuser", unnamed)
    assert one_copy.user() == ""


def test_the_not_responding_box_says_what_to_do() -> None:
    said = one_copy.not_answering()
    assert "already open" in said
    assert pc_or_mac("Task Manager", "force quit Polyglotic (⌥⌘Esc)") in said
