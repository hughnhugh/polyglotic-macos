"""The cohort is known the moment a code signs in (polyglotic-hq 279): the
redeem answer carries it, so an alpha tester's "Report a problem" and
diagnostics don't wait for the first session's `welcome`."""

from datetime import UTC, datetime

from PySide6.QtWidgets import QApplication, QDialog
from tests.ui.fakes import MemorySettingsStore
from tests.ui.test_sign_in_dialog import settle

from polyglotic_desktop.connection.sign_in import (
    InviteNotValid,
    RedeemResult,
    SignedIn,
)
from polyglotic_desktop.main import SignedInCohort, cohort_known
from polyglotic_desktop.ports.consent import ConsentChoice
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui.sign_in import SignInDialog, SignInFailed, SignInProblem


def test_the_cohort_a_code_signs_in_with_reaches_the_interfaces_thread(
    qapp: QApplication,
) -> None:
    """The redeem runs on the dialog's sign-in thread; once the dialog has
    closed, the interface's thread takes the cohort its answer carried."""
    cohort = SignedInCohort()
    answers: list[RedeemResult] = [InviteNotValid(), SignedIn("alpha")]
    dialog = SignInDialog(lambda _typed: cohort.answered(answers.pop(0)))
    dialog.code.setText("7KQM-X2PD-9VHT-C4RA")
    dialog.ok.click()
    settle(qapp, dialog)
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert cohort.take() is None  # a code that didn't sign in says no cohort
    dialog.ok.click()
    settle(qapp, dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert cohort.take() == "alpha"
    assert cohort.take() is None  # taken once
    dialog.deleteLater()


def test_the_dialog_still_shows_what_the_redeem_answered() -> None:
    cohort = SignedInCohort()
    assert cohort.answered(SignedIn("beta")) is None
    assert cohort.answered(InviteNotValid()) == SignInFailed(SignInProblem.NOT_VALID)
    assert cohort.take() == "beta"  # the last code that signed in


class Exchange:
    def __init__(self) -> None:
        self.consent = ConsentChoice(
            id="c1",
            at=datetime(2026, 11, 11, tzinfo=UTC),
            usage=False,
            crashes=False,
            exposures=True,
        )
        self.chosen: list[tuple[bool, bool, bool]] = []

    def choose_consent(self, usage: bool, crashes: bool, exposures: bool) -> None:
        self.chosen.append((usage, crashes, exposures))


def test_an_alpha_cohort_known_at_sign_in_makes_a_tester_at_once() -> None:
    """Kept in settings ("Report a problem" is the tester's window), the
    caption windows' strips report a problem, and diagnostics go on - as a
    `welcome`'s cohort does."""
    store = MemorySettingsStore({})
    settings = Settings(store)
    exchange = Exchange()
    reporting: list[bool] = []
    cohort_known("alpha", settings, exchange, reporting.append)  # type: ignore[arg-type]
    assert settings.value.cohort == "alpha"
    assert store.load()["cohort"] == "alpha"  # for the next start
    assert reporting == [True]
    assert exchange.chosen == [(True, True, True)]  # word counts as chosen


def test_another_cohort_known_at_sign_in_keeps_the_feedback_form() -> None:
    settings = Settings(MemorySettingsStore({"cohort": "alpha"}))  # the last account
    exchange = Exchange()
    reporting: list[bool] = []
    cohort_known("beta", settings, exchange, reporting.append)  # type: ignore[arg-type]
    assert settings.value.cohort == "beta"
    assert reporting == [False]
    assert exchange.chosen == []
