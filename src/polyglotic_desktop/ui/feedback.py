"""The feedback form: report a problem, suggest something, ask a question, offer to work with us.

MVP.md's "Send feedback", project 053. A short form:
- **what kind** - a problem, a suggestion, a question, or "I'd like to
  work on Polyglotic";
- **the text** (at most 5,000 characters, protocol.md);
- **how to reply** - an email address or a Discord name: optional, but
  needed to work with us, or we couldn't answer;
- **the app's log**, attached only if ticked (ticked for a problem), and
  then **shown in full before it's sent** - what's shown is what goes;
- Help's "no captions?" check, if the form was opened from there: its
  result (ticks and crosses, no content), shown, and added to the text;
- a line saying what else goes (the app and Windows versions, the
  session ID), and that there's no screenshot: captions on screen can be
  other people's words.

The form only asks: `report()` is what the user chose. `main` adds the
versions and the session ID, keeps the report and sends it. Every string
goes through `tr()`.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ports.feedback import ReportKind
from polyglotic_desktop.ui.os_words import pc_or_mac

MAX_TEXT = 5000  # protocol.md's limit
MAX_REPLY = 254  # an email address's limit, and the protocol's
KINDS: tuple[ReportKind, ...] = ("problem", "suggestion", "question", "work_with_us")


def can_send(kind: ReportKind, text: str, reply_to: str) -> bool:
    """Something written, within the limit, and a way to reply for someone
    who'd like to work with us (one line)."""
    reply = reply_to.strip()
    return (
        bool(text.strip())
        and len(text) <= MAX_TEXT
        and len(reply) <= MAX_REPLY
        and "\n" not in reply
        and (kind != "work_with_us" or bool(reply))
    )


class FeedbackDialog(QDialog):
    def __init__(
        self,
        kind: ReportKind,
        read_log: Callable[[], str | None],
        versions: str,
        with_session: bool,
        parent: QWidget | None = None,
        check_result: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._check_result = check_result
        self.setObjectName("FeedbackDialog")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        layout.addWidget(self.title)

        self.kind = QComboBox()
        self.kind.setObjectName("feedback.kind")
        for value, name in (
            ("problem", self.tr("A problem")),
            ("suggestion", self.tr("A suggestion")),
            ("question", self.tr("A question")),
            ("work_with_us", self.tr("I'd like to work on Polyglotic")),
        ):
            self.kind.addItem(name, value)
        layout.addWidget(self.kind)

        self.text = QPlainTextEdit()
        self.text.setObjectName("feedback.text")
        self.text.setTabChangesFocus(True)  # Tab goes on, never types a tab (278)
        self.text.setMinimumHeight(120)
        layout.addWidget(self.text)
        self.count = QLabel()
        self.count.setObjectName("Faint")
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.count)

        self.reply_label = QLabel()
        self.reply_label.setObjectName("Dim")
        layout.addWidget(self.reply_label)
        self.reply = QLineEdit()
        self.reply.setObjectName("feedback.reply")
        self.reply.setMaxLength(MAX_REPLY)
        self.reply.setPlaceholderText(self.tr("Your email or Discord name"))
        layout.addWidget(self.reply)

        if check_result:
            self.check_note = QLabel(
                self.tr(
                    'Help\'s "no captions?" check is added to your report: '
                    "ticks and crosses only. This is exactly what's added:"
                )
            )
            self.check_note.setObjectName("Faint")
            self.check_note.setWordWrap(True)
            layout.addWidget(self.check_note)
            self.check_view = QPlainTextEdit(check_result)
            self.check_view.setObjectName("feedback.check")
            self.check_view.setReadOnly(True)
            self.check_view.setMaximumHeight(96)
            layout.addWidget(self.check_view)

        self._log = read_log()
        self.attach = QCheckBox(self.tr("Attach the app's log"))
        self.attach.setObjectName("feedback.attach_log")
        layout.addWidget(self.attach)
        self.log_note = QLabel(
            self.tr(
                "This is exactly what's sent. The log records what the app did - "
                "never captions, audio or your settings."
            )
            if self._log is not None
            else pc_or_mac(
                self.tr("There's no log on this PC yet."),
                self.tr("There's no log on this Mac yet."),
            )
        )
        self.log_note.setObjectName("Faint")
        self.log_note.setWordWrap(True)
        layout.addWidget(self.log_note)
        self.log_view = QPlainTextEdit(self._log or "")
        self.log_view.setObjectName("feedback.log")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        )
        self.log_view.setMinimumHeight(140)
        layout.addWidget(self.log_view)

        about = QLabel(
            (
                self.tr("Also sent: {versions}, and the listening session's ID.")
                if with_session
                else self.tr("Also sent: {versions}.")
            ).format(versions=versions)
            + " "
            + self.tr("No screenshot is taken.")
            + " "
            + self.tr(
                "Please don't paste captions of other people's words. We may read "
                "feedback with the help of AI tools (Anthropic's Claude) to sort "
                "and summarise it."
            )
        )
        about.setObjectName("Faint")
        about.setWordWrap(True)
        layout.addWidget(about)

        buttons = QDialogButtonBox()
        self.send = QPushButton(self.tr("Send"))
        self.send.setObjectName("feedback.send")
        self.send.setDefault(True)
        buttons.addButton(self.send, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.text.textChanged.connect(self._check)
        self.reply.textChanged.connect(self._check)
        self.attach.toggled.connect(self._attach_changed)
        self.kind.setCurrentIndex(KINDS.index(kind))
        self._kind_changed()

    def chosen_kind(self) -> ReportKind:
        value: ReportKind = self.kind.currentData()
        return value

    def _kind_changed(self) -> None:
        kind = self.chosen_kind()
        self.title.setText(
            {
                "problem": self.tr("Report a problem"),
                "suggestion": self.tr("Suggest something"),
                "question": self.tr("Ask a question"),
                "work_with_us": self.tr("Help build Polyglotic"),
            }[kind]
        )
        self.setWindowTitle(self.title.text())
        self.text.setPlaceholderText(
            {
                "problem": self.tr(
                    "What happened, roughly when, and what you were captioning "
                    "(the kind of app is enough)."
                ),
                "suggestion": self.tr("What would make Polyglotic better for you?"),
                "question": self.tr("Ask us anything."),
                "work_with_us": self.tr(
                    "A little about you, and what you'd like to work on."
                ),
            }[kind]
        )
        self.reply_label.setText(
            self.tr("How can we reach you? (needed, so we can reply)")
            if kind == "work_with_us"
            else self.tr("How can we reply? (optional)")
        )
        self.attach.setChecked(kind == "problem" and self._log is not None)
        self._attach_changed()
        self._check()

    def _attach_changed(self) -> None:
        self.attach.setEnabled(self._log is not None)
        self.log_view.setVisible(self.attach.isChecked())

    def _check(self) -> None:
        text = self.text.toPlainText()
        self.count.setText(
            self.tr("{count} of {limit}").format(count=len(text), limit=MAX_TEXT)
        )
        self.count.setVisible(len(text) > MAX_TEXT * 0.8)
        added = len(self._check_result or "") + 40  # the check's heading and result
        self.send.setEnabled(
            can_send(self.chosen_kind(), text, self.reply.text())
            and len(text) + added <= MAX_TEXT
        )

    def report(self) -> tuple[ReportKind, str, str | None, str | None]:
        """What the user chose: the kind, the text, how to reply (None if
        not given) and the log (None if not attached)."""
        reply = self.reply.text().strip() or None
        attached = self._log if self.attach.isChecked() else None
        text = self.text.toPlainText().strip()
        if self._check_result:
            text = f"{text}\n\n--- no-captions check ---\n{self._check_result}"
        return self.chosen_kind(), text, reply, attached
