"""Email sign-in and the worker used by the open-beta account screens."""

import logging
import threading
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from http import HTTPStatus
from typing import cast

from PySide6.QtCore import QEventLoop, QLocale, QObject, Qt, QTimer, QTimeZone, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.shared.open_beta import CHANGE_CONFIRMATION_HOLD, Account
from polyglotic_desktop.core.shared.papers import MAINLAND_PRIVACY_NOTICE
from polyglotic_desktop.ports.open_beta import AccountError, Region
from polyglotic_desktop.ui.first_run import add_back
from polyglotic_desktop.ui.sign_in import Redeem, SignInDialog
from polyglotic_desktop.ui.widgets import TextDialog, page_button

SIGN_IN_WIDTH = 460  # logical px; room for consent text at default text size
EMAIL_LENGTH = 254  # SMTP mailbox limit, in bytes at the server
log = logging.getLogger(__name__)

PIPL_NOTICE = (
    "为提供实时字幕、翻译和账户服务，Polyglotic 在澳大利亚处理您的音频和账户数据。"
    "音频仅用于生成字幕和翻译，处理后不保存；账户信息在提供服务所需期间保存。"
    "您可通过简体中文隐私声明中的联系方式联系 Polyglotic、撤回同意或行使个人信息权利。"
)
PIPL_CONSENT = "我单独同意上述跨境处理。"


def _tr(text: str) -> str:
    return QApplication.translate("OpenBeta", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("OpenBeta", text, None, n)


def system_time_zone() -> str:
    return bytes(QTimeZone.systemTimeZoneId().data()).decode("ascii") or "UTC"


def account_error(error: AccountError) -> str:
    if error.code == "malformed_code":
        return _tr("That code isn't valid - check it and try again.")
    if error.code == "code_not_valid":
        return _tr("Check the code in your email, or request a new one.")
    if error.code == "email_not_allowed":
        return _tr("Use a permanent email address.")
    if error.code in {"too_many_attempts", "rate_limited"}:
        seconds = error.retry_after
        if seconds is not None and 0 <= seconds <= 2_147_483_647:  # Qt's signed int
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            parts = []
            if hours:
                parts.append(_trn("%n hour(s)", hours))
            if minutes:
                parts.append(_trn("%n minute(s)", minutes))
            if seconds or not parts:
                parts.append(_trn("%n second(s)", seconds))
            return _tr("Too many attempts. Try again in {time}.").format(
                time=QLocale().createSeparatedList(parts)
            )
        return _tr("Too many attempts. Try again later.")
    if error.code in {"token_not_valid", "sign_in_required", "registration_required"}:
        return _tr("Sign in with your email to continue.")
    if error.code == "offer_not_available":
        return _tr("That code isn’t available. Check it and try again.")
    if error.code == "plan_offer_not_available":
        return _tr("This plan is unavailable for your account.")
    if error.code == "offer_already_redeemed":
        return _tr("This account already has an offer from another code.")
    if error.code == "change_preview_required":
        return _tr("The price has changed. Review the change again.")
    if error.code in {"offer_checkout_pending", "change_pending"}:
        return _trn(
            "A payment on this account is still being confirmed. Finish paying in the "
            "open checkout, or try again in about %n minute(s).",
            CHANGE_CONFIRMATION_HOLD.value,
        )
    if error.code == "market_not_available":
        return _tr("The open beta is not available in your region yet.")
    return _tr("Polyglotic couldn’t complete that request. Please try again.")


def _cross_border_fields(layout: QVBoxLayout) -> tuple[QWidget, QCheckBox]:
    notice = QWidget()
    column = QVBoxLayout(notice)
    column.setContentsMargins(0, 0, 0, 0)
    text = QLabel(PIPL_NOTICE)
    text.setWordWrap(True)
    column.addWidget(text)
    column.addWidget(
        page_button(
            "简体中文隐私声明", MAINLAND_PRIVACY_NOTICE, "mainland.privacy_notice"
        ),
        alignment=Qt.AlignmentFlag.AlignLeft,
    )
    layout.addWidget(notice)
    consent = QCheckBox(PIPL_CONSENT)
    consent.setObjectName("pipl_cross_border")
    layout.addWidget(consent)
    return notice, consent


class AccountWork(QObject):
    """Run one blocking account request and deliver its result to Qt."""

    _finished = Signal(object)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._receive: Callable[[object], None] | None = None
        self._finished.connect(self._done)

    @property
    def busy(self) -> bool:
        return self._receive is not None

    def run[T](
        self, call: Callable[[], T], receive: Callable[[T | AccountError], None]
    ) -> None:
        if self.busy:
            raise RuntimeError("an account request is already running")
        self._receive = cast(Callable[[object], None], receive)

        def work() -> None:
            try:
                answer: T | AccountError = call()
            except AccountError as failed:
                answer = failed
            except (OSError, ValueError):
                answer = AccountError("unavailable")
            with suppress(
                RuntimeError
            ):  # The app quit while the request was in flight.
                self._finished.emit(answer)

        threading.Thread(target=work, name="account-request", daemon=True).start()

    def _done(self, result: object) -> None:
        receive, self._receive = self._receive, None
        if receive is not None:
            receive(result)


def sign_in_region(
    read: Callable[[], Region], parent: QObject, *, beta_confirmed: bool = False
) -> Region | AccountError | None:
    """Read the email sign-in region. None means a legacy invite-code server.

    A failed probe keeps email sign-in available so the dialog can retry
    the region check before it sends a code.
    """
    loop = QEventLoop()
    work = AccountWork(parent)
    result: Region | AccountError = AccountError("unavailable")

    def received(answer: Region | AccountError) -> None:
        nonlocal result
        result = answer
        loop.quit()

    work.run(read, received)
    loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    work.deleteLater()
    if isinstance(result, AccountError):
        if result.status == HTTPStatus.NOT_FOUND and not beta_confirmed:
            log.info(
                "email sign-in region probe returned HTTP 404, using invite-code sign-in"
            )
            return None
        if result.status is not None:
            reason = f"HTTP {result.status}"
        elif result.code == "request_timed_out":
            reason = "request_timed_out"
        else:
            reason = result.diagnostic or "unavailable"
        log.warning(
            "email sign-in region probe failed, keeping email sign-in (%s)", reason
        )
    return result


class EmailSignIn(TextDialog):
    """A single dialog for email registration, sign-in and purchase restore."""

    def __init__(
        self,
        region: Callable[[], Region],
        start: Callable[[str, bool, bool, str], str],
        verify: Callable[[str, str], Account],
        redeem: Redeem | None,
        parent: QWidget | None = None,
        *,
        restoring: bool = False,
        again: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmailSignIn")
        self.set_least_width(SIGN_IN_WIDTH)
        self.setWindowTitle(_tr("Restore purchase") if restoring else _tr("Sign in"))
        self._region = region
        self._region_ready = False
        self._needs_consent = False
        self._start = start
        self._verify = verify
        self._redeem = redeem
        self._again = again
        self.account: Account | None = None
        self._challenge: str | None = None
        self._work = AccountWork(self)

        layout = QVBoxLayout(self)
        title = QLabel(self.windowTitle())
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.intro = QLabel(
            _tr("Use the email address you bought Polyglotic with.")
            if restoring
            else _tr("Enter your email to create an account or sign in.")
        )
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)
        self.email = QLineEdit()
        self.email.setObjectName("email_sign_in.email")
        self.email.setAccessibleName(_tr("Email address"))
        self.email.setPlaceholderText(_tr("Email address"))
        self.email.setMaxLength(EMAIL_LENGTH)
        self.email.returnPressed.connect(self._submit)
        layout.addWidget(self.email)

        self.code = QLineEdit()
        self.code.setObjectName("email_sign_in.code")
        self.code.setAccessibleName(_tr("Six-digit email code"))
        self.code.setPlaceholderText(_tr("Six-digit email code"))
        self.code.returnPressed.connect(self._submit)
        self.code.hide()
        layout.addWidget(self.code)

        self.marketing = QCheckBox(
            _tr("Send me learning tips and Polyglotic news. Unsubscribe any time.")
        )
        self.marketing.setVisible(not restoring)
        layout.addWidget(self.marketing)
        self.notice, self.consent = _cross_border_fields(layout)
        self.notice.hide()
        self.consent.hide()
        self.consent.toggled.connect(self._buttons)

        self.invite = QPushButton(_tr("Have an invite code? Sign in with it instead"))
        self.invite.setObjectName("email_sign_in.invite")
        self.invite.setProperty("kind", "ghost")
        self.invite.setAutoDefault(False)
        self.invite.setVisible(redeem is not None)
        self.invite.clicked.connect(self._use_invite)
        layout.addWidget(self.invite)
        self.change_email = QPushButton(_tr("Change email or resend code"))
        self.change_email.setAutoDefault(False)
        self.change_email.setProperty("kind", "ghost")
        self.change_email.clicked.connect(self._reset_code)
        self.change_email.hide()
        layout.addWidget(self.change_email)

        self.message = QLabel()
        self.message.setObjectName("email_sign_in.message")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText(_tr("Email me a code"))
        self.back = add_back(self, buttons)
        self.cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._restoring = restoring
        self._buttons()
        QTimer.singleShot(0, self, self._read_region)

    def reject(self) -> None:
        if not self._work.busy:
            super().reject()

    def _buttons(self) -> None:
        idle = not self._work.busy
        self.ok.setEnabled(
            idle and (not self._needs_consent or self.consent.isChecked())
        )
        self.invite.setEnabled(idle)
        self.back.setEnabled(idle)
        self.cancel.setEnabled(idle)
        self.email.setEnabled(idle and self._challenge is None)
        self.code.setEnabled(idle)
        self.change_email.setEnabled(idle)
        self.consent.setEnabled(idle)
        self.marketing.setEnabled(idle)

    def _read_region(self) -> None:
        self._work.run(self._region, self._region_received)
        self._buttons()

    def _region_received(self, result: Region | AccountError) -> None:
        if isinstance(result, AccountError):
            self.message.setText(account_error(result))
        else:
            self._region_ready = True
            self._consent_needed(result.needs_consent)
        self._buttons()

    def _consent_needed(self, needed: bool) -> None:
        self._needs_consent = needed
        self.marketing.setVisible(not needed and not self._restoring)
        if needed:
            self.marketing.setChecked(False)
        self.notice.setVisible(needed)
        self.consent.setVisible(needed)

    def _submit(self) -> None:
        if self._work.busy or (self._needs_consent and not self.consent.isChecked()):
            return
        self.message.clear()
        if self._challenge is not None:
            code = self.code.text().strip()
            self._work.run(partial(self._verify, self._challenge, code), self._verified)
        elif not self._region_ready:
            self._read_region()
            return
        else:
            email = self.email.text().strip()
            if "@" not in email:
                self.message.setText(_tr("Enter your email address."))
                return
            self._work.run(
                partial(
                    self._start,
                    email,
                    self.marketing.isChecked(),
                    self.consent.isChecked(),
                    system_time_zone(),
                ),
                self._code_sent,
            )
        self._buttons()

    def _code_sent(self, result: str | AccountError) -> None:
        if isinstance(result, AccountError):
            if result.code in {
                "pipl_cross_border_required",
                "cross_border_consent_required",
            }:
                self._consent_needed(True)
            else:
                self.message.setText(account_error(result))
        else:
            self._challenge = result
            self.code.show()
            self.change_email.show()
            self.invite.hide()
            self.ok.setText(_tr("Verify email"))
            self.message.setText(_tr("Check your inbox for a six-digit code."))
        self._buttons()
        if self._challenge is not None:
            self.code.setFocus()

    def _reset_code(self) -> None:
        self._challenge = None
        self.code.clear()
        self.code.hide()
        self.change_email.hide()
        self.invite.setVisible(self._redeem is not None)
        self.ok.setText(_tr("Email me a code"))
        self.message.clear()
        self._buttons()
        self.email.setFocus()

    def _verified(self, result: Account | AccountError) -> None:
        self._buttons()
        if isinstance(result, AccountError):
            if result.code == "cross_border_consent_required":
                self._reset_code()
                self._consent_needed(True)
                self._buttons()
                return
            self.message.setText(account_error(result))
            self.code.selectAll()
            self.code.setFocus()
        else:
            self.account = result
            self.code.clear()
            self.accept()

    def _use_invite(self) -> None:
        if self._redeem is None:
            return
        dialog = SignInDialog(self._redeem, self, again=self._again)
        if dialog.exec():
            self.accept()
        dialog.deleteLater()


class CrossBorderConsent(TextDialog):
    """Review the same mainland notice when the server needs consent again."""

    def __init__(
        self,
        allow: Callable[[], Account],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("跨境处理同意")
        self.set_least_width(SIGN_IN_WIDTH)
        self.account: Account | None = None
        self._work = AccountWork(self)
        layout = QVBoxLayout(self)
        _, self.consent = _cross_border_fields(layout)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("继续")
        self.ok.setEnabled(False)
        self.consent.toggled.connect(self.ok.setEnabled)
        buttons.rejected.connect(self.reject)
        self._allow = allow
        buttons.accepted.connect(self._submit)
        layout.addWidget(buttons)

    def reject(self) -> None:
        if not self._work.busy:
            super().reject()

    def _submit(self) -> None:
        if self._work.busy or not self.consent.isChecked():
            return
        self.ok.setEnabled(False)
        self.consent.setEnabled(False)
        self._work.run(self._allow, self._received)

    def _received(self, result: Account | AccountError) -> None:
        if isinstance(result, AccountError):
            self.message.setText(account_error(result))
            self.ok.setEnabled(True)
            self.consent.setEnabled(True)
        else:
            self.account = result
            self.accept()
