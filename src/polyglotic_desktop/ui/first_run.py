"""The first run's screens, one after another, with Back (polyglotic-hq
250, the user's F4: "There should be back buttons for the install flow
too").

Every screen after the first has **Back**: the screen before, shown again
with what was entered on it - the same screen, not a new one. Closing a
screen does what it did before Back existed: the level goes on without an
answer, Your data without the yes quits (polyglotic-hq DECISIONS.md #88),
the code goes on signed out. No language is asked (polyglotic-hq 293). A
screen's answer is kept only on its own Next: Back keeps nothing, so the
yes to the tester agreement goes with Continue alone.

`main` gives the steps (`main.first_run`); `run` takes them in order.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPushButton

BACK = 2
"""What a first-run screen's `exec` returns for Back (a dialog's own are 0,
closed, and 1, accepted)."""


class Answer(Enum):
    NEXT = "next"
    """On to the next screen: answered - or closed, where that goes on."""
    BACK = "back"
    """The screen shown before."""
    QUIT = "quit"
    """Closed where that quits: no further."""


@dataclass(frozen=True)
class Step:
    name: str
    needed: Callable[[], bool]
    """Whether to ask it, when the run first comes to it."""
    ask: Callable[[bool], Answer]
    """Shows the screen - with Back if True - and says what was pressed."""


def run(steps: Sequence[Step], start_at: int = 0) -> bool:
    """Each step that's needed, in order; Back goes to the screen shown
    before it, and the first one shown has no Back. A step once shown is
    shown again when the run comes back to it, needed or not - what was
    entered there may change what comes after. False when one quits.

    `start_at`: resume at step index `start_at` (for example after step 1's
    language relaunch), keeping earlier steps in `behind` so Back can still
    reach them."""
    at = max(0, min(start_at, len(steps)))
    behind: list[int] = list(range(at))
    """The steps shown, in order: where Back goes."""
    shown: set[int] = set(behind)
    while at < len(steps):
        step = steps[at]
        if at not in shown and not step.needed():
            at += 1
            continue
        shown.add(at)
        answer = step.ask(bool(behind))
        if answer is Answer.QUIT:
            return False
        if answer is Answer.BACK and behind:
            at = behind.pop()
            continue
        behind.append(at)
        at += 1
    return True


def add_back(dialog: QDialog, buttons: QDialogButtonBox) -> QPushButton:
    """Back, at the left of `buttons` (where Windows puts a reset button),
    hidden until a run shows the screen after another (`asked`): it ends
    the screen with `BACK`. Never the default: Enter goes on."""
    back = buttons.addButton(
        QCoreApplication.translate("FirstRun", "Back"),
        QDialogButtonBox.ButtonRole.ResetRole,
    )
    back.setObjectName("first_run.back")
    back.setAutoDefault(False)
    back.setDefault(False)
    back.clicked.connect(lambda: dialog.done(BACK))
    back.hide()
    return back


def asked(dialog: QDialog, back: QPushButton, with_back: bool) -> int:
    """`dialog` shown until it's answered, with Back if `with_back`: what
    its `exec` returned (`BACK` for Back).

    Shown again after its Back was pressed by the keyboard, it doesn't open
    with the focus still on Back, where Space would go back once more
    (269): Qt then gives it to the screen's first control."""
    back.setVisible(with_back)
    if dialog.focusWidget() is back:
        back.clearFocus()
    return dialog.exec()
