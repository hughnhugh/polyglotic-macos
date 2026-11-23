"""Back on every first-run screen after the first (polyglotic-hq 250, the
user's F4: "There should be back buttons for the install flow too"),
keeping what was entered; closing Your data still quits (DECISIONS.md
#88); the yes and the 16+ answer go with Continue only. Offscreen: each
screen is answered by a script (`first_run_script`)."""

from datetime import UTC, datetime
from functools import partial

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore
from tests.ui.first_run_script import (
    BACK,
    Built,
    agree,
    back,
    check,
    closed,
    next_,
    nothing_asked,
    scripted,
)

from polyglotic_desktop.core.shared import papers
from polyglotic_desktop.main import NotAgreed, first_run
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ui.consent import ConsentDialog
from polyglotic_desktop.ui.first_run import Answer, Step, run

AT = datetime(2026, 11, 16, 9, tzinfo=UTC)
AGREED = ConsentChoice(
    "a", AT, False, False, False, Agreement(papers.TESTER_AGREEMENT_VERSION, AT)
)


def never_code(typed: str) -> None:
    raise AssertionError("the code was sent")


# -- the run, as plain Python ------------------------------------------------------------


class Screens:
    """Made-up steps "a", "b" and "c": each notes when it's shown, and
    whether with Back, and answers from its list. `needed`: which are
    needed; `once`: which aren't any more once answered (a level picked)."""

    def __init__(
        self, answers: dict[str, list[Answer]], needed: set[str], once: set[str]
    ) -> None:
        self.answers, self.needed, self.once = answers, needed, once
        self.log: list[str] = []

    def ask(self, name: str, with_back: bool) -> Answer:
        self.log.append(name + ("+back" if with_back else ""))
        if name in self.once:
            self.needed.discard(name)
        return self.answers[name].pop(0)

    def is_needed(self, name: str) -> bool:
        return name in self.needed

    def steps(self) -> list[Step]:
        return [
            Step(name, partial(self.is_needed, name), partial(self.ask, name))
            for name in ("a", "b", "c")
        ]


def test_back_goes_to_the_screen_shown_before_and_the_first_has_none() -> None:
    answers = {
        "a": [Answer.NEXT, Answer.NEXT],
        "b": [],
        "c": [Answer.BACK, Answer.NEXT],
    }
    screens = Screens(answers, {"a", "c"}, set())  # b isn't needed: skipped
    assert run(screens.steps())
    assert screens.log == ["a", "c+back", "a", "c+back"]


def test_a_screen_shown_once_is_shown_again_coming_back_to_it() -> None:
    """Once answered it may not be needed any more (a level picked), but
    the learner walking back and forth sees it where it was."""
    answers = {
        "a": [Answer.NEXT],
        "b": [Answer.NEXT, Answer.NEXT],
        "c": [Answer.BACK, Answer.NEXT],
    }
    screens = Screens(answers, {"a", "b", "c"}, {"b"})
    assert run(screens.steps())
    assert screens.log == ["a", "b+back", "c+back", "b+back", "c+back"]


def test_quitting_stops_the_run() -> None:
    answers = {"a": [Answer.NEXT], "b": [Answer.QUIT], "c": []}
    screens = Screens(answers, {"a", "b", "c"}, set())
    assert not run(screens.steps())
    assert screens.log == ["a", "b+back"]


# -- the first run's screens -------------------------------------------------------------


def test_back_on_every_screen_after_the_first_keeping_what_was_entered(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 1 is Your language (658), then Your data, then Sign in; Back
    keeps what was entered on each screen."""
    store = MemorySettingsStore()
    built = Built()
    script = [
        ("LanguagePicker", next_),  # keeps OS language (en): no restart
        ("ConsentDialog", agree()),
        ("SignInDialog", back),
        (
            "ConsentDialog",
            check(lambda d: d.agree.isChecked() and d.usage.isChecked(), next_),
        ),
        ("SignInDialog", closed),  # signed out: Home says so
    ]
    seen = scripted(monkeypatch, script)
    started = first_run(store, built, None, never_code, windows_languages=["en-AU"])
    assert script == []
    assert [with_back for _, with_back in seen] == [False, True, True, True, True]
    assert store.values.get("learning") is None  # none asked: chosen on Learning
    assert started.tools.is_chinese and started.tools is built.made[False]
    assert started.tools.vocabulary.line is None  # none asked: Home's line asks
    assert built.closed == []  # the one built is the window's
    assert started.first is not None and started.first.choices == (True, False, False)
    assert started.first.agreement is not None
    assert started.code_asked


def test_closing_your_data_still_quits(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemorySettingsStore({"learning": "zh"})
    built = Built()
    script = [
        ("ConsentDialog", agree()),
        ("SignInDialog", back),
        ("ConsentDialog", closed),
    ]
    seen = scripted(monkeypatch, script)
    with pytest.raises(NotAgreed):
        first_run(store, built, None, never_code)
    assert seen[0] == ("ConsentDialog", False)
    assert built.closed == [False]  # no further: its store closed


def test_the_yes_is_given_with_continue_not_with_the_tick(qapp: QApplication) -> None:
    dialog = ConsentDialog(clock=lambda: AT)
    assert dialog.agree is not None
    dialog.agree.setChecked(True)
    assert dialog.ok.isEnabled() and dialog.agreement() is None
    dialog.back.click()
    assert dialog.result() == BACK and dialog.agreement() is None
    dialog.accept()
    assert dialog.agreement() == Agreement(papers.TESTER_AGREEMENT_VERSION, AT)
    dialog.close()


def test_no_level_is_asked(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """polyglotic-hq 293: words are estimated at a middle level until the
    learner sets theirs, so a first run agreed before asks nothing - and
    the code, with no screen before it, is asked over the window."""
    nothing_asked(monkeypatch)
    started = first_run(
        MemorySettingsStore({"learning": "en"}), Built(), AGREED, never_code
    )
    assert not started.tools.is_chinese and started.tools.vocabulary.line is None
    assert started.first is None and not started.code_asked


def test_signed_in_the_code_isnt_asked(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted(monkeypatch, [("LanguagePicker", next_), ("ConsentDialog", agree())])
    started = first_run(MemorySettingsStore(), Built(), None, None)
    assert not started.code_asked
    assert started.new  # nothing saved before: no What's new (345)


def test_a_returning_learner_is_asked_nothing_not_even_the_code(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Signed out at a later start, the code is asked over the window, as
    before - not here, before it."""
    nothing_asked(monkeypatch)
    store = MemorySettingsStore({"learning": "zh"})
    started = first_run(store, Built(level_picked=True), AGREED, never_code)
    assert started.tools.is_chinese and not started.code_asked
    assert not started.new  # an update's start: What's new can show (345)


def test_a_screen_shown_again_doesnt_open_with_the_focus_on_back(
    qapp: QApplication,
) -> None:
    """Back pressed by keyboard keeps the focus on Back; the screen shown
    again opened with it there, so Space - what a keyboard presses on a
    button - went back again (269, by keyboard alone)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QVBoxLayout

    from polyglotic_desktop.ui.first_run import BACK, add_back, asked

    dialog = QDialog()
    column = QVBoxLayout(dialog)
    field = QLineEdit()
    column.addWidget(field)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dialog.accept)
    column.addWidget(buttons)
    back = add_back(dialog, buttons)
    focused: list[object] = []

    def press_back() -> None:
        back.setFocus()
        back.click()  # as Space on it does

    def look_then_go_on() -> None:
        focused.append(QApplication.focusWidget())
        dialog.accept()

    QTimer.singleShot(50, press_back)
    assert asked(dialog, back, True) == BACK
    QTimer.singleShot(50, look_then_go_on)
    assert asked(dialog, back, True) == QDialog.DialogCode.Accepted
    assert focused and focused[0] is not back
    dialog.deleteLater()
