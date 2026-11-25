"""Closing the main window where the desktop has no tray (polyglotic-hq 571):
GNOME without its AppIndicator extension - Fedora's, by default - or any
desktop whose tray isn't running.

The app runs on as it does with a tray: the caption windows stay up and
keep captioning, and the window comes back from the desktop's own app
launcher or menu entry (a second start shows it: `ui/one_copy.py`). Quit is
at the foot of the window's sidebar. The first time, before the window
goes, a box says so and offers Quit at once (`keep_running`): without a
tray nothing else on screen would show that the app still runs.
"""

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QMessageBox, QWidget


def _tr(text: str) -> str:
    return QCoreApplication.translate("NoTray", text)


def still_running_box(parent: QWidget | None) -> QMessageBox:
    """The question, made - not shown (`keep_running` shows it): Keep
    running (the default, and Esc) or Quit."""
    box = QMessageBox(parent)
    box.setObjectName("no_tray.still_running")
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("Polyglotic")
    box.setText(_tr("Keep Polyglotic running?"))
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.setInformativeText(
        _tr(
            "Caption windows stay open. To reopen this window, launch Polyglotic "
            "again. You can quit from the sidebar."
        )
    )
    keep = box.addButton(_tr("Keep running"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(_tr("Quit"), QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(keep)
    box.setEscapeButton(keep)
    return box


def keep_running(parent: QWidget | None) -> bool:
    """Asks; True unless the learner chose Quit."""
    box = still_running_box(parent)
    box.exec()
    clicked = box.clickedButton()
    quit_chosen = (
        clicked is not None
        and box.buttonRole(clicked) is QMessageBox.ButtonRole.DestructiveRole
    )
    box.deleteLater()
    return not quit_chosen


__all__ = ["keep_running", "still_running_box"]
