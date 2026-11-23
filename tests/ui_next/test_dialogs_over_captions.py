"""The caption windows out of the way of the app's own dialogs
(polyglotic-hq 579): always on top, they sat over Save transcript's dialog
- its Name, Save and Cancel on KDE - and would take clicks meant for it.
Offscreen, real windows: a message box, a save dialog (Qt's own here; a
native one is in Qt's list of modal windows the same way), one dialog
over another, the joined window, windows the learner hid, and windows
joined while a dialog is open."""

from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QRect, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget
from tests.ui_next.made_up import SEPARATE, finished_updates

from polyglotic_desktop.core.listening.hidden import Sight
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_windows import DIALOG_CHECK_MS, CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = Rect(0, 0, 1920, 1040)
SECOND_APP = SourceId("app-2")


class Store:
    """The settings port, in memory."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {"targets": ["en"]}

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(Store(), MIC, lambda: [AREA])
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    found.set_captioned([("a", APP)])
    for update in finished_updates(5, APP):
        found.apply(update)
    qapp.processEvents()
    yield found
    found.close()


@pytest.fixture
def owner(qapp: QApplication) -> Iterator[QWidget]:
    """The app's window a dialog opens over."""
    found = QWidget()
    found.show()
    yield found
    found.close()
    found.deleteLater()


def _shown(windows: CaptionWindows) -> list[bool]:
    """Whether each caption window shows - and the joined window, if any."""
    found = [w.isVisible() for w in windows.windows.values() if w.host is None]
    if windows.joined_window is not None:
        found.append(windows.joined_window.isVisible())
    return found


def _places(windows: CaptionWindows) -> dict[str, QRect]:
    return {key: w.geometry() for key, w in windows.windows.items()}


def _while_open(open_it: Callable[[], object], inside: Callable[[], None]) -> None:
    """`open_it` opens a modal dialog and waits for it; `inside` runs once
    it's open (and the windows have had their moment), then it's cancelled."""

    def then() -> None:
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        inside()
        dialog.close()

    QTimer.singleShot(50, then)
    open_it()


def _back(qapp: QApplication) -> None:
    """The windows' next look: the dialog has gone."""
    QTest.qWait(DIALOG_CHECK_MS * 2)


def test_a_message_box_has_the_windows_step_aside_and_back_as_they_were(
    qapp: QApplication, windows: CaptionWindows, owner: QWidget
) -> None:
    places = _places(windows)
    seen: list[list[bool]] = []
    box = QMessageBox(QMessageBox.Icon.Question, "Remove?", "Remove it?", parent=owner)

    came = finished_updates(2, APP, start=5)

    def inside() -> None:
        seen.append(_shown(windows))
        for update in came:  # captions keep coming
            windows.apply(update)

    _while_open(box.exec, inside)
    assert seen == [[False]]  # nothing over the box's buttons
    _back(qapp)
    assert _shown(windows) == [True]
    assert _places(windows) == places
    window = windows.windows["a"]
    assert {u.caption_id for u in came} <= {
        line.caption_id for line in window.view.lines
    }
    # not the learner's Hide: no timer, nothing for Home and the tray
    assert not windows.hidden and windows.sight("a") == (Sight.SHOWN, None)


def test_a_save_dialog_has_them_step_aside(
    qapp: QApplication, windows: CaptionWindows, owner: QWidget
) -> None:
    seen: list[list[bool]] = []
    _while_open(
        lambda: QFileDialog.getSaveFileName(
            owner, "Save transcript", "", "Text (*.txt)"
        ),
        lambda: seen.append(_shown(windows)),
    )
    assert seen == [[False]]
    _back(qapp)
    assert _shown(windows) == [True]


def test_one_dialog_over_another_they_come_back_after_the_last(
    qapp: QApplication, windows: CaptionWindows, owner: QWidget
) -> None:
    seen: list[list[bool]] = []
    outer = QMessageBox(QMessageBox.Icon.Question, "Outer", "Outer", parent=owner)
    inner = QMessageBox(QMessageBox.Icon.Warning, "Inner", "Inner", parent=owner)

    def over_it() -> None:
        _while_open(inner.exec, lambda: seen.append(_shown(windows)))
        QTest.qWait(DIALOG_CHECK_MS * 2)  # the inner one gone, the outer still open
        seen.append(_shown(windows))

    _while_open(outer.exec, over_it)
    assert seen == [[False], [False]]
    _back(qapp)
    assert _shown(windows) == [True]


def test_the_joined_window_steps_aside_too(
    qapp: QApplication, windows: CaptionWindows, owner: QWidget
) -> None:
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.join("a")
    assert windows.joined_window is not None and _shown(windows) == [True]
    seen: list[list[bool]] = []
    box = QMessageBox(QMessageBox.Icon.Question, "Remove?", "Remove it?", parent=owner)
    _while_open(box.exec, lambda: seen.append(_shown(windows)))
    assert seen == [[False]]
    _back(qapp)
    assert _shown(windows) == [True]


def test_windows_joined_while_a_dialog_is_open_come_back_after_it(
    qapp: QApplication, windows: CaptionWindows, owner: QWidget
) -> None:
    """A second app's window joins the first's as it opens (554) - here
    while a dialog is open: the window Qt said was blocked is a column
    now, and the joined window was never shown, so neither hears the
    dialog close. They're back all the same."""
    box = QMessageBox(QMessageBox.Icon.Question, "Remove?", "Remove it?", parent=owner)

    def second_app() -> None:
        windows.set_captioned([("a", APP), ("b", SECOND_APP)])
        windows.join("a")

    _while_open(box.exec, second_app)
    _back(qapp)
    assert windows.joined_window is not None and _shown(windows) == [True]


def test_windows_the_learner_hid_stay_hidden_after_a_dialog(
    qapp: QApplication, windows: CaptionWindows, owner: QWidget
) -> None:
    windows.set_hidden(True)
    box = QMessageBox(QMessageBox.Icon.Question, "Remove?", "Remove it?", parent=owner)
    _while_open(box.exec, lambda: None)
    _back(qapp)
    assert _shown(windows) == [False] and windows.sight("a")[0] is Sight.HIDDEN
    windows.set_hidden(False)
    assert _shown(windows) == [True]
