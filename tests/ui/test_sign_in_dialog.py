"""The sign-in dialog (offscreen): the code goes to the redeem it was
given, off the interface's thread; each failure is explained and the
dialog stays open to try again; success closes it."""

import os
import re
import sys
import threading
import time

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox
from tests.stopped_clock import AFTER_MIDNIGHT_IN_MELBOURNE, qt_stopped_at
from tests.ui.test_consent_dialog import SCREENSHOTS

from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ui import sign_in
from polyglotic_desktop.ui.interface_language import ENGLISH, formats, install
from polyglotic_desktop.ui.sign_in import (
    SignInDialog,
    SignInFailed,
    SignInProblem,
    confirm_sign_out,
)
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.os_words import pc_or_mac


def settle(qapp: QApplication, dialog: SignInDialog, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    qapp.processEvents()
    while dialog.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


class Redeem:
    def __init__(self, *answers: SignInFailed | None) -> None:
        self.answers = list(answers)
        self.typed: list[str] = []
        self.threads: list[str] = []

    def __call__(self, code: str) -> SignInFailed | None:
        self.typed.append(code)
        self.threads.append(threading.current_thread().name)
        return self.answers.pop(0)


def test_a_failure_is_explained_then_success_closes(qapp: QApplication) -> None:
    redeem = Redeem(SignInFailed(SignInProblem.NOT_VALID), None)
    dialog = SignInDialog(redeem)
    dialog.code.setText(" 7kqm-x2pd-9vht-c4ra ")
    dialog.ok.click()
    settle(qapp, dialog)
    assert "doesn't work" in dialog.message.text()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.code.isEnabled() and dialog.ok.isEnabled()
    dialog.ok.click()
    settle(qapp, dialog)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert redeem.typed == ["7kqm-x2pd-9vht-c4ra"] * 2  # the connection reads it
    assert redeem.threads == ["sign-in", "sign-in"]  # never the interface's thread
    assert dialog.code.text() == ""


def test_the_screen_asks_for_an_invite_or_a_plus_emails_code(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 185: the code from a Plus email goes in the same field as
    an invite code (193), so the screen names both."""
    dialog = SignInDialog(Redeem())
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "Enter your code" in texts
    assert "Your invite code, or the code in your Plus email" in texts


def test_signed_in_here_before_the_screen_says_the_same_code_works_again(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 288: the screen said "Each code works once", and
    signing out "needs a new invite code from us". The same invite code
    signs this PC in again now (server decision 0057): after signing out,
    the screen says so; a PC that never signed in isn't told."""
    before = SignInDialog(Redeem(), again=True)
    never = SignInDialog(Redeem())
    try:
        assert not before.again.isHidden()
        assert before.again.text() == (
            pc_or_mac("This PC", "This Mac")
            + " has signed in before: the invite code you used then works "
            "again here."
        )
        assert never.again.isHidden()
        for dialog in (before, never):
            texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
            assert "works once" not in texts
    finally:
        before.deleteLater()
        never.deleteLater()


def test_nothing_typed_sends_nothing(qapp: QApplication) -> None:
    redeem = Redeem()
    dialog = SignInDialog(redeem)
    dialog.ok.click()
    assert not dialog.busy and redeem.typed == []


def test_every_problem_has_a_plain_explanation(qapp: QApplication) -> None:
    dialog = SignInDialog(Redeem())
    texts = {
        problem: dialog.explain(SignInFailed(problem, 420)) for problem in SignInProblem
    }
    assert "16 letters and digits" in texts[SignInProblem.NOT_A_CODE]
    assert (
        "used on another " + pc_or_mac("PC", "computer")
        in texts[SignInProblem.NOT_VALID]
    )
    assert "7 minutes" in texts[SignInProblem.TOO_MANY_ATTEMPTS]
    assert "internet connection" in texts[SignInProblem.UNREACHABLE]
    assert texts[SignInProblem.SIGN_OUT_FIRST] == (
        "This code starts a new account - sign out first, then use it."
    )
    # protocol.md's words for a code whose subscription ended (258)
    assert texts[SignInProblem.SUBSCRIPTION_ENDED] == (
        "This code's subscription was cancelled before the code was used, so it "
        "gives no Plus. To get Plus, subscribe again on our site - or write to us "
        "if you didn't cancel it."
    )
    assert len(set(texts.values())) == len(SignInProblem)
    # an invite code and a Plus email's code alike (polyglotic-hq 185, 193):
    # nothing says "invite" alone, nor that a code expires - a Plus code doesn't
    for text in texts.values():
        assert "invite code" not in text and "expired" not in text
    soon = dialog.explain(SignInFailed(SignInProblem.TOO_MANY_ATTEMPTS, 45))
    assert soon.endswith("Try again in a minute.")  # not "1 minutes" (137)


def test_the_server_unreachable_says_whose_side(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first sign-in while our server was down said "Check your internet
    connection" (polyglotic-hq 251): now whose side it's on, as Home says."""
    dialog = SignInDialog(Redeem())

    def said(why: Unreachable | None) -> str:
        return dialog.explain(SignInFailed(SignInProblem.UNREACHABLE, unreachable=why))

    assert said(Unreachable.DOWN).startswith("Polyglotic's server isn't answering")
    assert "not your internet" in said(Unreachable.SERVER_ERROR)
    assert "we're probably down" in said(Unreachable.NO_ANSWER)
    assert "internet connection" in said(Unreachable.OFFLINE)
    assert said(None) == said(Unreachable.OFFLINE)  # not known: as before
    assert "another network" in said(Unreachable.BLOCKED)
    # 313: wrong for certain - the date it says, and where to set it; the
    # app's date and the test's read once (polyglotic-hq 344: midnight)
    stopped_date, _ = qt_stopped_at(AFTER_MIDNIGHT_IN_MELBOURNE)
    monkeypatch.setattr(sign_in, "QDate", stopped_date)
    today = QLocale().toString(
        stopped_date.currentDate(), QLocale.FormatType.LongFormat
    )
    this = pc_or_mac("This PC", "This Mac")
    assert said(Unreachable.CLOCK).startswith(f"{this} says it's {today}")
    assert pc_or_mac(
        "Set time automatically", "Set time and date automatically"
    ) in said(Unreachable.CLOCK)
    # a certificate out of date, the clock right: an antivirus or a VPN first
    assert "antivirus's HTTPS scanning, or a VPN" in said(Unreachable.OUT_OF_DATE)


def test_a_screenshot_when_asked(qapp: QApplication) -> None:
    """With POLYGLOTIC_SCREENSHOTS set (and QT_QPA_FONTDIR for glyphs)."""
    if not os.environ.get("POLYGLOTIC_SCREENSHOTS"):
        return
    dialog = SignInDialog(Redeem(SignInFailed(SignInProblem.NOT_VALID)))
    dialog.setStyleSheet(style.stylesheet(window_theme()))  # as shown
    dialog.code.setText("7KQM-X2PD-9VHT-C4RB")
    dialog.show()
    dialog.ok.click()
    settle(qapp, dialog)
    dialog.adjustSize()
    qapp.processEvents()
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    dialog.grab().save(str(SCREENSHOTS / "sign-in.png"))
    dialog.close()


def test_signing_out_says_unsent_changes_are_dropped_only_when_there_are_some(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project 042, Low 12: what hasn't reached the server is dropped at
    sign-out, and the question says so - when there's something to drop.
    Answered without showing it."""
    asked: list[str] = []

    def answer(box: QMessageBox) -> int:
        asked.append(box.informativeText())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", answer)
    assert confirm_sign_out(None, unsent=True)
    assert confirm_sign_out(None, unsent=False)
    with_unsent, without = asked
    assert "hasn't sent to our server yet are dropped" in with_unsent
    assert "dropped" not in without
    # the same code signs in again (288): no "new invite code from us"
    assert (
        "with the same invite code: it works again on this " + pc_or_mac("PC", "Mac")
        in without
    )
    assert "new invite code" not in without


def test_the_sign_out_question_is_in_the_interfaces_language(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 184: in a Chinese interface the question, its button
    and its explanation stayed English - `box.tr` looks the words up under
    "QMessageBox", where our translations aren't. Answered without showing it."""
    shown: list[str] = []

    def answer(box: QMessageBox) -> int:
        yes = box.button(QMessageBox.StandardButton.Yes)
        shown.extend([box.windowTitle(), box.text(), box.informativeText(), yes.text()])
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", answer)
    installed = install(qapp, "zh_CN")
    try:
        assert not confirm_sign_out(None, unsent=True)
    finally:
        for translator in installed:
            qapp.removeTranslator(translator)
        QLocale.setDefault(formats(ENGLISH, QLocale.system()))
    title, question, why, button = shown
    # Qt drops a message box's title on a Mac, as macOS' own alerts have none
    # (polyglotic-hq 420: the first Mac run of the suite)
    assert title == ("" if sys.platform == "darwin" else "退出登录")
    assert button == "退出登录"
    assert question == "要在这台电脑上退出 Polyglotic 的登录吗？"
    assert "邀请码" in why and "丢弃" in why
    assert not re.search(r"[A-Za-z]{3,}", why)


def test_a_long_answer_is_shown_whole(qapp: QApplication) -> None:
    """An answer longer than two lines - the ended Plus code's three -
    grows the screen to show it whole: shown after the screen was sized,
    its third line was cut off (269: "...subscribe again on our site -
    or", then nothing)."""
    dialog = SignInDialog(Redeem(SignInFailed(SignInProblem.SUBSCRIPTION_ENDED)))
    dialog.setStyleSheet(style.stylesheet(window_theme()))  # as shown
    dialog.show()
    qapp.processEvents()
    before = dialog.height()
    dialog.code.setText("7KQM-X2PD-9VHT-C4RA")
    dialog.ok.click()
    settle(qapp, dialog)
    qapp.processEvents()
    message = dialog.message
    needed = message.heightForWidth(message.width())
    assert message.height() >= needed, (message.height(), needed)
    assert dialog.height() > before  # grown for it
    dialog.close()
    dialog.deleteLater()
