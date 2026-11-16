"""The Mac's offer to move Polyglotic to Applications (polyglotic-hq 433,
decision 0205): asked at the start when macOS runs the app from a temporary
copy (`ports.system.Translocation`), where it can't update itself.

`offer` asks once - **Move to Applications** or **Not now** - and says how to
do it by hand in the same box, so Not now still leaves the learner knowing
what to do. If the move fails, a second box says the same plainly. It
returns where the app was moved to, for `main` to open it there and end
this copy.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from polyglotic_desktop.ports.system import Translocation

log = logging.getLogger(__name__)


def _tr(text: str) -> str:
    return QApplication.translate("MoveToApplications", text)


def title() -> str:
    return _tr("Move Polyglotic to Applications?")


def question() -> str:
    return _tr(
        "Polyglotic was opened outside your Applications folder, from Downloads"
        " perhaps, so your Mac runs it from a temporary copy. From there it"
        " can't update itself."
    )


def by_hand() -> str:
    return _tr(
        "To do it yourself: quit Polyglotic, drag it into Applications in"
        " Finder, and open it there."
    )


def move_button() -> str:
    return _tr("Move to Applications")


def not_now_button() -> str:
    return _tr("Not now")


def not_moved() -> str:
    return _tr("Polyglotic couldn't move itself to Applications.")


def ask(parent: QWidget | None) -> bool:
    """The question; True for Move to Applications."""
    box = QMessageBox(QMessageBox.Icon.Question, title(), question(), parent=parent)
    box.setInformativeText(
        _tr("Move it, and Polyglotic opens again from Applications.")
        + "\n\n"
        + by_hand()
    )
    move = box.addButton(move_button(), QMessageBox.ButtonRole.AcceptRole)
    later = box.addButton(not_now_button(), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(move)
    box.setEscapeButton(later)
    box.exec()
    chosen = box.clickedButton() is move
    box.deleteLater()
    return chosen


def tell(parent: QWidget | None) -> None:
    """The move failed: what to do by hand."""
    box = QMessageBox(QMessageBox.Icon.Warning, title(), not_moved(), parent=parent)
    box.setInformativeText(by_hand())
    box.exec()
    box.deleteLater()


def offer(
    place: Translocation,
    parent: QWidget | None = None,
    asking: Callable[[QWidget | None], bool] = ask,
    telling: Callable[[QWidget | None], None] = tell,
) -> Path | None:
    """Asks to move the app; where it is now if it moved, else None."""
    if not asking(parent):
        log.info("not moved to Applications: Not now")
        return None
    try:
        return place.move()
    except OSError as problem:
        log.warning("couldn't move the app to Applications: %s", problem)
        telling(parent)
        return None
