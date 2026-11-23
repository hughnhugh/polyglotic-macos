"""Account, in the new main window (polyglotic-hq project 109's structure,
section 7): today's Account page (project 028), unchanged in what it
does.

- **This PC** - signed in or not; Sign in (an invite code) or Sign out;
  signed in, "I have a code" - the code from a Plus email, onto this
  account (polyglotic-hq 185);
  once a session has opened, the start of the account ID, for the
  learner to quote when they write to us about their data (041);
- **Plus** - the plan as the server states it, in one line with its date
  (`views.plan`), and "Get Plus" - the site's Plus page, in the browser -
  when Plus ends with nothing after it (polyglotic-hq 185); hidden until a
  session brings the plan;
- **Your data** - the consent screen again, to change what's shared;
- **Your learning data** - delete it from our server, and from this PC
  too if the learner ticks that;
- **The privacy notice and the tester agreement** - each a button that
  opens our website's page in the browser (polyglotic-hq 185);
- **Feedback** - report a problem or suggest something (053; `main`
  hands over the commands it shares with the tray and Home).

Each is a named command (`QAction`) the page only shows; `main` connects
them to today's dialogs and the connection, and tells the page whether
this PC is signed in - the same names as today's page, so either page
can be wired.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton

from polyglotic_desktop.core.shared.open_beta import Account
from polyglotic_desktop.core.shared.papers import (
    PLUS,
    PRIVACY_NOTICE,
    TESTER_AGREEMENT,
)
from polyglotic_desktop.ui_next.controls import (
    Card,
    Flow,
    label,
    page_button,
    right_row,
)
from polyglotic_desktop.ui_next.home import Page, sign_in_needed
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.plan import get_plus_text, plan_text
from polyglotic_desktop.ui_next.upgrade import billing_line
from polyglotic_desktop.ui_next.views.plan import PlanLine

SHORT_ID = 8
"""Characters of the account ID shown: plenty to tell testers apart."""


def _tr(text: str) -> str:
    return QApplication.translate("Account", text)


def _button(action: QAction) -> QPushButton:
    """A button showing `action`: its text, and whether it shows and works."""
    button = QPushButton(action.text())
    button.setObjectName(action.objectName())
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(action.trigger)

    def follow() -> None:
        button.setText(action.text())
        button.setVisible(action.isVisible())
        button.setEnabled(action.isEnabled())

    action.changed.connect(follow)
    return button


class AccountPage(Page):
    """Signing in and out, what's shared, deleting learning data, feedback."""

    def __init__(self, plus: str = PLUS) -> None:
        """`plus`: the site's Plus page that "Get Plus" opens (with the
        install's `?ref=`, once it has one: `views.plan.plus_page`)."""
        super().__init__(_tr("Account"))
        self.sign_in = self._action("account.sign_in", _tr("Sign in"))
        self.sign_out = self._action("account.sign_out", _tr("Sign out"))
        self.have_code = self._action("account.have_code", _tr("Redeem a code"))
        self.add_email = self._action("account.add_email", _tr("Add an email"))
        self.upgrade = self._action("account.upgrade", _tr("Upgrade"))
        self.restore_purchase = self._action(
            "account.restore_purchase", _tr("Restore purchase")
        )
        self.your_data = self._action("account.your_data", _tr("Choose what to share"))
        self.delete_learning = self._action(
            "account.delete_learning", _tr("Delete learning data…")
        )

        this_pc = Card(pc_or_mac(_tr("This PC"), _tr("This Mac")))
        row = Flow()
        self.state = label("", wrap=True)
        self.state.setObjectName("account.state")
        row.add_widget(self.state, stretch=1)
        self.sign_in_button = _button(self.sign_in)
        self.sign_out_button = _button(self.sign_out)
        self.have_code_button = _button(self.have_code)
        self.add_email_button = _button(self.add_email)
        row.addWidget(self.sign_in_button)
        row.addWidget(self.have_code_button)
        row.addWidget(self.add_email_button)
        row.addWidget(self.sign_out_button)
        this_pc.add(row)
        self.account_id = label("", "Dim", wrap=True)
        this_pc.add(self.account_id)
        this_pc.add(right_row(_button(self.restore_purchase)))
        self.content.addWidget(this_pc)

        self.plan_card = Card(_tr("Plus"))
        plan_row = QHBoxLayout()
        plan_row.setSpacing(8)
        self.plan = label("", wrap=True)
        self.plan.setObjectName("account.plan")
        plan_row.addWidget(self.plan, 1)
        self.get_plus = page_button(get_plus_text(), plus, "account.get_plus")
        plan_row.addWidget(self.get_plus)
        self.plan_card.add(plan_row)
        self.plan_card.hide()  # until a session brings the plan
        self.content.addWidget(self.plan_card)

        self.beta_card = Card(_tr("Your plan"))
        self.beta_plan = label("", wrap=True)
        self.beta_card.add(self.beta_plan)
        self.beta_card.add(right_row(_button(self.upgrade)))
        self.beta_card.hide()
        self.content.addWidget(self.beta_card)

        shared = Card(
            _tr("Your data"),
            _tr(
                "What Polyglotic sends to run the service, and what you choose to "
                "share: usage statistics, crash reports, how often you hear words."
            ),
        )
        shared.add(right_row(_button(self.your_data)))
        self.content.addWidget(shared)

        learning = Card(
            _tr("Your learning data"),
            pc_or_mac(
                _tr(
                    "The words you look up, save and mark are kept on our server as "
                    "dictionary words and times: saved words and statuses follow you "
                    "to another PC, and lookups show us how people learn. You can "
                    "delete them there, in every language you learn - and on this PC "
                    "too, if you choose."
                ),
                _tr(
                    "The words you look up, save and mark are kept on our server as "
                    "dictionary words and times: saved words and statuses follow you "
                    "to another computer, and lookups show us how people learn. You "
                    "can delete them there, in every language you learn - and on this "
                    "Mac too, if you choose."
                ),
            ),
        )
        learning.add(right_row(_button(self.delete_learning)))
        self.content.addWidget(learning)

        papers = Card(
            _tr("Privacy and the tester agreement"),
            _tr("What we keep and why, and what you agreed to as a tester."),
        )
        papers.add(
            right_row(
                page_button(
                    _tr("Privacy notice"), PRIVACY_NOTICE, "account.privacy_notice"
                ),
                page_button(
                    _tr("Tester agreement"),
                    TESTER_AGREEMENT,
                    "account.tester_agreement",
                ),
            )
        )
        self.content.addWidget(papers)
        self.content.addStretch(1)
        self._email_sign_in = True
        self.set_signed_in(False)

    def _action(self, name: str, text: str) -> QAction:
        action = QAction(text, self)
        action.setObjectName(name)
        self.addAction(action)
        return action

    def add_feedback(self, *actions: QAction) -> None:
        """The feedback card (today's commands), above the page's foot."""
        card = Card(
            _tr("Feedback"),
            _tr(
                "Tell us what went wrong or what would help - with the app's log "
                "if you like. You see everything before it's sent."
            ),
        )
        buttons = []
        for action in actions:
            button = QPushButton(action.text().replace("&", ""))
            button.setObjectName(action.objectName() or "account.feedback")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(action.trigger)
            buttons.append(button)
        card.add(right_row(*buttons))
        self.content.insertWidget(self.content.count() - 1, card)

    def use_email_sign_in(self, available: bool) -> None:
        self._email_sign_in = available
        self.restore_purchase.setVisible(available)
        if self.sign_in.isVisible():
            self.set_signed_in(False)

    def set_signed_in(self, signed_in: bool) -> None:
        self.state.setText(
            pc_or_mac(_tr("Signed in on this PC."), _tr("Signed in on this Mac."))
            if signed_in
            else _tr("Not signed in - {needed}.").format(
                needed=sign_in_needed(self._email_sign_in)
            )
        )
        self.sign_in.setVisible(not signed_in)
        self.sign_out.setVisible(signed_in)
        self.have_code.setVisible(signed_in)
        self.add_email.setVisible(False)
        self.delete_learning.setEnabled(signed_in)
        # the buttons follow their actions; set here too for the first show
        self.sign_in_button.setHidden(signed_in)
        self.sign_out_button.setHidden(not signed_in)
        self.have_code_button.setHidden(not signed_in)
        self.add_email_button.hide()
        if not signed_in:
            self.account_id.clear()
            self.account_id.setHidden(True)
            self.show_plan(None)
            self.show_beta_account(None)

    def show_beta_account(self, account: Account | None) -> None:
        show_plan = (
            account is not None and account.registered and account.plan != "alpha"
        )
        self.beta_card.setVisible(show_plan)
        self.upgrade.setVisible(
            account is not None and account.registered and account.plan != "alpha"
        )
        if account is not None:
            self.plan_card.hide()
            if show_plan:
                self.beta_plan.setText(billing_line(account))
            if account.email is not None:
                self.state.setText(account.email)
            elif not account.registered:
                self.state.setText(_tr("Signed in with an invite code"))
            self.add_email.setVisible(not account.registered)
            self.add_email_button.setVisible(not account.registered)
            self.show_account(account.id)

    def show_plan(self, line: PlanLine | None) -> None:
        """The account's plan in one line, and "Get Plus" when it ends with
        nothing after it (None: no plan heard - signed out, say)."""
        self.plan_card.setVisible(line is not None)
        if line is None:
            return
        self.plan.setText(plan_text(line))
        self.get_plus.setVisible(line.get_plus)

    def show_account(self, account_id: str) -> None:
        """The account the server says this PC is signed in to (`welcome`),
        shortened: what the learner quotes to see, export or delete their
        data."""
        self.account_id.setText(
            _tr(
                "Your account ID: {id}. Quote it if you write to us about your data."
            ).format(id=account_id[:SHORT_ID])
        )
        self.account_id.setHidden(False)
