"""Signing in with an invite code, and signing out.

A tester types the invite code we sent them (`7KQM-X2PD-9VHT-C4RA`), or
a learner the code in the email Plus sent when they bought it on the site
- the same look, the same field (protocol.md, redeeming; polyglotic-hq
185 and 193), so the words here fit both; case, spaces and dashes don't
matter. The dialog runs the
redeem it's given - `main` passes one that calls the connection's
`redeem` and keeps the device token in Credential Manager - on a thread
of its own, so the window never waits on the network, and says plainly
what went wrong: not a code, a code that isn't valid (mistyped, used,
expired or revoked - the server doesn't say which), too many tries, or no
server. The code is never logged or kept.

Signing out forgets the device token on this PC, and asks first. The
same invite code signs this PC in again (polyglotic-hq 288: the server
knows the install it signed in, server decision 0057; the app keeps the
install id, decision 0080) - so after signing out, the dialog says so
(`again`).

`SignInProblem` is this view's own list, as `app.ConnectionState` is
for Home: `main` maps the connection's results onto it. Every string goes
through `tr()`.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QCoreApplication, QDate, QLocale, Signal
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.unreachable import Side, Unreachable, side
from polyglotic_desktop.ui.first_run import add_back
from polyglotic_desktop.ui.os_words import pc_mac_or_linux, pc_or_mac
from polyglotic_desktop.ui.widgets import TextDialog


def _tr(text: str) -> str:
    """The sign-out question's words, beside the sign-in dialog's. Not
    `box.tr`: PySide6 looks that up under "QMessageBox", where our
    translations aren't - the question stayed English in every language
    (polyglotic-hq 184)."""
    return QCoreApplication.translate("SignInDialog", text)


class SignInProblem(StrEnum):
    NOT_A_CODE = "not_a_code"  # not 16 letters and digits; nothing was sent
    NOT_VALID = "not_valid"  # unknown, used, expired or revoked
    SUBSCRIPTION_ENDED = "subscription_ended"  # a Plus email's code, cancelled first
    PLUS_ALREADY = "plus_already"  # a subscription pays already: code not used
    SIGN_IN_AGAIN = "sign_in_again"  # this PC's sign-in isn't taken any more
    SIGN_OUT_FIRST = "sign_out_first"  # signed in, a code for a new account: unused
    TOO_MANY_ATTEMPTS = "too_many_attempts"  # the server's guessing limit
    UNREACHABLE = "unreachable"  # no server, or an answer that couldn't be read


@dataclass(frozen=True)
class SignInFailed:
    problem: SignInProblem
    retry_after: int | None = None  # seconds, for too many attempts
    unreachable: Unreachable | None = None
    """UNREACHABLE: why the server couldn't be reached, if that's known
    (polyglotic-hq 251)."""


Redeem = Callable[[str], SignInFailed | None]
"""Redeems the code as typed; None once signed in. It blocks: the dialog
calls it off the interface's thread."""


class SignInDialog(TextDialog):
    _finished = Signal(object)  # SignInFailed | None, from the redeem thread

    def __init__(
        self, redeem: Redeem, parent: QWidget | None = None, again: bool = False
    ) -> None:
        """`again`: this PC has signed in before (its install id is kept),
        so the code it used then works again."""
        super().__init__(parent)
        self.setObjectName("SignInDialog")
        self.setWindowTitle(self.tr("Sign in"))
        self.set_least_width(440)
        self._redeem = redeem
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        title = QLabel(self.tr("Enter your code"))
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        intro = QLabel(
            self.tr(
                "Your invite code, or the code in your Plus email: 16 letters "
                "and digits. Capitals and dashes don't matter."
            )
        )
        intro.setObjectName("Dim")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.again = QLabel(
            pc_or_mac(
                self.tr(
                    "This PC has signed in before: the invite code you used then "
                    "works again here."
                ),
                self.tr(
                    "This Mac has signed in before: the invite code you used then "
                    "works again here."
                ),
            )
        )
        self.again.setObjectName("sign_in.again")
        self.again.setWordWrap(True)
        self.again.setVisible(again)
        layout.addWidget(self.again)
        self.code = QLineEdit()
        self.code.setObjectName("sign_in.code")
        self.code.setPlaceholderText("7KQM-X2PD-9VHT-C4RA")
        self.code.setAccessibleName(title.text())  # a screen reader's name for it
        self.code.setMaxLength(40)
        self.code.returnPressed.connect(self._sign_in)
        layout.addWidget(self.code)
        self.message = QLabel("")
        self.message.setObjectName("sign_in.message")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText(self.tr("Sign in"))
        buttons.accepted.connect(self._sign_in)
        buttons.rejected.connect(self.reject)
        self.back = add_back(self, buttons)  # at the first run: Your data
        layout.addWidget(buttons)
        self._finished.connect(self._done)
        self.busy = False

    def _sign_in(self) -> None:
        typed = self.code.text().strip()
        if self.busy or not typed:
            return
        self.busy = True
        self.code.setEnabled(False)
        self.ok.setEnabled(False)
        self.back.setEnabled(False)  # not away while the code is out
        self.message.setText(self.tr("Signing in…"))
        threading.Thread(
            target=lambda: self._finished.emit(self._redeem(typed)),
            name="sign-in",
            daemon=True,
        ).start()

    def _done(self, failed: SignInFailed | None) -> None:
        self.busy = False
        self.code.setEnabled(True)
        self.ok.setEnabled(True)
        self.back.setEnabled(True)
        if failed is None:
            self.message.setText(self.tr("Signed in."))
            self.code.clear()
            self.accept()
            return
        self.message.setText(self.explain(failed))
        self.code.setFocus()
        self.code.selectAll()

    def explain(self, failed: SignInFailed) -> str:
        """What went wrong, for the user."""
        if failed.problem is SignInProblem.NOT_A_CODE:
            return self.tr(
                "That isn't one of our codes - they have 16 letters and digits, "
                "like 7KQM-X2PD-9VHT-C4RA."
            )
        if failed.problem is SignInProblem.NOT_VALID:
            return pc_or_mac(
                self.tr(
                    "This code doesn't work: it may be mistyped, used on another PC "
                    "or no longer valid. Check it, or write to us and we'll sort it "
                    "out."
                ),
                self.tr(
                    "This code doesn't work: it may be mistyped, used on another "
                    "computer or no longer valid. Check it, or write to us and we'll "
                    "sort it out."
                ),
            )
        if failed.problem is SignInProblem.SUBSCRIPTION_ENDED:
            # protocol.md's words for it (server #252, polyglotic-hq 256, 258)
            return self.tr(
                "This code's subscription was cancelled before the code was used, "
                "so it gives no Plus. To get Plus, subscribe again on our site - "
                "or write to us if you didn't cancel it."
            )
        if failed.problem is SignInProblem.PLUS_ALREADY:
            return self.tr(
                "This account has Plus by subscription already, so the code "
                "wasn't used. Keep it for later, or give it to someone."
            )
        if failed.problem is SignInProblem.SIGN_IN_AGAIN:
            return pc_or_mac(
                self.tr(
                    "This PC's sign-in has run out. Sign out on Account, then sign "
                    "in with this code."
                ),
                self.tr(
                    "This Mac's sign-in has run out. Sign out on Account, then sign in "
                    "with this code."
                ),
            )
        if failed.problem is SignInProblem.SIGN_OUT_FIRST:
            return self.tr(
                "This code starts a new account - sign out first, then use it."
            )
        if failed.problem is SignInProblem.TOO_MANY_ATTEMPTS:
            minutes = max(1, -(-(failed.retry_after or 600) // 60))
            # English's forms: "... in a minute.", "... in 5 minutes." (137, 156)
            return self.tr(
                "Too many tries from this network. Try again in %n minute(s).",
                "",
                minutes,
            )
        return self._unreachable(failed.unreachable)

    def _unreachable(self, why: Unreachable | None) -> str:
        """The server couldn't be reached: whose side it's on and what to do,
        as Home says it (polyglotic-hq 251) - a first sign-in while our server
        was down said to check the learner's internet."""
        if why is Unreachable.CLOCK:  # wrong for certain (connection.tls, 313)
            today = QLocale().toString(
                QDate.currentDate(), QLocale.FormatType.LongFormat
            )
            return pc_mac_or_linux(
                #: {date}: the date this PC's clock says, in its regional format
                self.tr(
                    "This PC says it's {date}, which can't be right, and a secure "
                    "connection needs the right date. Turn on Set time automatically "
                    "in Windows' Settings, Time & language, Date & time, then choose "
                    "Sync now."
                ),
                #: {date}: the date this Mac's clock says, in its regional format
                self.tr(
                    "This Mac says it's {date}, which can't be right, and a secure "
                    "connection needs the right date. Turn on Set time and date "
                    "automatically in System Settings, General, Date & Time."
                ),
                #: {date}: the date this PC's clock says, in its regional format.
                #: Linux: GNOME's, KDE's and Xfce's settings each have Date & Time
                self.tr(
                    "This PC says it's {date}, which can't be right, and a secure "
                    "connection needs the right date. Turn on automatic date and time "
                    "in your desktop's settings, under Date & Time."
                ),
            ).format(date=today)
        if why is Unreachable.OUT_OF_DATE:  # an out-of-date certificate (313)
            return self.tr(
                "Something on this network is in the way with an out-of-date "
                "certificate - most often an antivirus's HTTPS scanning, or a "
                "VPN. Turn it off for Polyglotic, or try another network."
            )
        if why in (Unreachable.BLOCKED, Unreachable.NOT_SECURE):
            return self.tr(
                "Something on this network is in the way - a Wi-Fi sign-in page, "
                "a firewall, a proxy or an antivirus. Sign in to the Wi-Fi, or try "
                "another network."
            )
        if why is not None and side(why) is Side.OURS:
            return self.tr(
                "Polyglotic's server isn't answering - it's not your internet. "
                "Try again in a few minutes."
            )
        if why is Unreachable.NO_ANSWER:
            return self.tr(
                "Couldn't reach Polyglotic's server. Check your internet; if it's "
                "working, we're probably down - try again in a few minutes."
            )
        return self.tr(
            "Couldn't reach the server. Check your internet connection and try again."
        )


def confirm_sign_out(parent: QWidget | None = None, unsent: bool = False) -> bool:
    """Asks before signing out (`sign_out_question`): True to sign out."""
    return sign_out_question(parent, unsent).exec() == QMessageBox.StandardButton.Yes


def sign_out_question(
    parent: QWidget | None = None, unsent: bool = False
) -> QMessageBox:
    """The question before signing out: signing in again takes the same
    invite code (288); with `unsent`, what hasn't reached the server yet is
    dropped."""
    box = QMessageBox(parent)
    box.setObjectName("SignOutQuestion")
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(_tr("Sign out"))
    box.setText(
        pc_or_mac(
            _tr("Sign out of Polyglotic on this PC?"),
            _tr("Sign out of Polyglotic on this Mac?"),
        )
    )
    text = pc_or_mac(
        _tr(
            "Captions stop until you sign in again. Your saved words and learning data stay, "
            "on this PC and on our server."
        ),
        _tr(
            "Captions stop until you sign in again. Your saved words and learning data stay, on this "
            "Mac and on our server."
        ),
    )
    if unsent:
        text += " " + pc_or_mac(
            _tr(
                "Changes this PC hasn't sent to our server yet are dropped, so"
                " none of them reach whoever signs in next."
            ),
            _tr(
                "Changes this Mac hasn't sent to our server yet are dropped, so none "
                "of them reach whoever signs in next."
            ),
        )
    box.setInformativeText(text)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
    )
    box.button(QMessageBox.StandardButton.Yes).setText(_tr("Sign out"))
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box
