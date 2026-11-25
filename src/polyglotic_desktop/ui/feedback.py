"""The feedback form: report a problem (non-alpha), ask a question, offer to work with us.

MVP.md's "Send feedback", project 053. Suggestions moved to the unified
"Report a problem / Make a suggestion" modal (`ui.problem_report`, project 955).
A short form:
- **what kind** - a problem, a question, or "I'd like to work on Polyglotic";
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
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QApplication,
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

from polyglotic_desktop.core.report_text import (
    COUNTER_THRESHOLD,
    LOG_TEXT_LIMIT,
    REPLY_TO_LIMIT,
    TEXT_LIMITS,
    clean_report_text,
    limited_clean_text,
)
from polyglotic_desktop.ports.feedback import ReportKind
from polyglotic_desktop.ui.os_words import pc_or_mac

KINDS: tuple[ReportKind, ...] = ("problem", "question", "work_with_us")


def _tr(text: str) -> str:
    return QApplication.translate("FeedbackDialog", text)


def optional_reply_label() -> str:
    return _tr("How can we reply? (optional)")


class ReplyField(QLineEdit):
    """Contact text for a report, cleaned at the report boundary."""

    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText(_tr("Your email or Discord name"))
        reply_palette = self.palette()
        reply_palette.setColor(
            QPalette.ColorRole.PlaceholderText,
            reply_palette.color(QPalette.ColorRole.Text),
        )
        self.setPalette(reply_palette)

    def cap(self) -> tuple[str, bool]:
        """Cap a long paste by cleaned characters, preserving the caret or selection."""
        raw_reply = self.text()
        reply = clean_report_text(raw_reply)
        cut = len(reply) > REPLY_TO_LIMIT
        if cut:
            reply = limited_clean_text(reply, REPLY_TO_LIMIT)
            position = self.cursorPosition()
            selection_start = self.selectionStart()
            selection_length = self.selectionLength()
            self.setText(reply)
            self.end(False)
            end = self.cursorPosition()
            if selection_start >= 0:
                start = min(selection_start, end)
                self.setSelection(start, min(selection_length, end - start))
            else:
                self.setCursorPosition(min(position, end))
        return reply, cut

    def cleaned(self) -> str | None:
        return limited_clean_text(self.text(), REPLY_TO_LIMIT) or None


class FeedbackLog:
    """The plain app log, with a checkbox and exact preview."""

    def __init__(self, layout: QVBoxLayout, raw_log: str | None) -> None:
        self._log = (
            limited_clean_text(raw_log, LOG_TEXT_LIMIT) if raw_log is not None else None
        )
        self.attach = QCheckBox(_tr("Attach the app's log"))
        self.attach.setObjectName("feedback.attach_log")
        layout.addWidget(self.attach)
        self.log_note = QLabel(
            _tr(
                "This is exactly what's sent. The log records what the app did - "
                "never captions, audio or your settings."
            )
            if self._log is not None
            else pc_or_mac(
                _tr("There's no log on this PC yet."),
                _tr("There's no log on this Mac yet."),
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
        self.attach.setEnabled(self._log is not None)
        self.attach.toggled.connect(self.log_view.setVisible)
        self.log_view.hide()

    def set_attached(self, attached: bool) -> None:
        self.attach.setChecked(attached and self._log is not None)

    def attached(self) -> str | None:
        return (self._log or None) if self.attach.isChecked() else None


def can_send(kind: ReportKind, text: str, reply_to: str) -> bool:
    """Something written, within the limit, and a way to reply for someone
    who'd like to work with us (one line)."""
    reply = reply_to.strip()
    return (
        bool(text.strip())
        and len(text) <= TEXT_LIMITS[kind]
        and len(reply) <= REPLY_TO_LIMIT
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
        self._check_result = (
            limited_clean_text(check_result, LOG_TEXT_LIMIT)
            if check_result is not None
            else None
        )
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
        self.cut_note = QLabel()
        self.cut_note.setObjectName("Faint")
        layout.addWidget(self.cut_note)

        self.reply_label = QLabel()
        self.reply_label.setObjectName("Dim")
        layout.addWidget(self.reply_label)
        self.reply = ReplyField()
        self.reply.setObjectName("feedback.reply")
        layout.addWidget(self.reply)

        if self._check_result:
            self.check_note = QLabel(
                self.tr(
                    'Help\'s "no captions?" check is added to your report: '
                    "ticks and crosses only. This is exactly what's added:"
                )
            )
            self.check_note.setObjectName("Faint")
            self.check_note.setWordWrap(True)
            layout.addWidget(self.check_note)
            self.check_view = QPlainTextEdit(self._check_result)
            self.check_view.setObjectName("feedback.check")
            self.check_view.setReadOnly(True)
            self.check_view.setMaximumHeight(96)
            layout.addWidget(self.check_view)

        self._app_log = FeedbackLog(layout, read_log())
        self.attach = self._app_log.attach
        self.log_view = self._app_log.log_view

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
                "question": self.tr("Ask a question"),
                "work_with_us": self.tr("Help build Polyglotic"),
            }[kind]
        )
        self.setWindowTitle(self.title.text())
        prompt = {
            "problem": self.tr(
                "What happened, roughly when, and what you were captioning "
                "(the kind of app is enough)."
            ),
            "question": self.tr("Ask us anything."),
            "work_with_us": self.tr(
                "A little about you, and what you'd like to work on."
            ),
        }[kind]
        self.text.setPlaceholderText(prompt)
        self.reply_label.setText(
            self.tr("How can we reach you? (needed, so we can reply)")
            if kind == "work_with_us"
            else optional_reply_label()
        )
        # These controls have no persistent visible labels of their own.  Give
        # screen readers the same translated words the learner sees in the
        # dialog rather than exposing their implementation object names.
        self.kind.setAccessibleName(self.title.text())
        self.text.setAccessibleName(prompt)
        self.reply.setAccessibleName(self.reply_label.text())
        self._app_log.set_attached(kind == "problem")
        self._check()

    def _check(self) -> None:
        limit = TEXT_LIMITS[self.chosen_kind()]
        raw_text = self.text.toPlainText()
        text = limited_clean_text(raw_text, limit)
        # Cleaning is a payload boundary, not an editing operation.  In
        # particular, clean_report_text() trims a trailing space or newline,
        # which is an ordinary intermediate state while someone is typing.
        # Only replace the draft when its cleaned payload actually exceeds the
        # cap (normally an over-long paste).
        if len(clean_report_text(raw_text)) > limit:
            cursor = self.text.textCursor()
            position, anchor = cursor.position(), cursor.anchor()
            self.text.setPlainText(text)
            cursor = self.text.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            end = cursor.position()  # Qt positions are UTF-16 units, not Python len().
            cursor.setPosition(min(anchor, end))
            cursor.setPosition(min(position, end), cursor.MoveMode.KeepAnchor)
            self.text.setTextCursor(cursor)
            self.cut_note.setText(
                self.tr("Cut to {limit} characters").format(limit=f"{limit:,}")
            )
        reply, cut = self.reply.cap()
        if cut:
            self.cut_note.setText(
                self.tr("Cut to {limit} characters").format(limit=f"{REPLY_TO_LIMIT:,}")
            )
        self.count.setText(
            self.tr("{count} / {limit}").format(
                count=f"{len(text):,}", limit=f"{limit:,}"
            )
        )
        self.count.setVisible(len(text) >= limit * COUNTER_THRESHOLD)
        self.send.setEnabled(can_send(self.chosen_kind(), text, reply))

    def report(self) -> tuple[ReportKind, str, str | None, str | None]:
        """What the user chose: the kind, the text, how to reply (None if
        not given) and the log (None if not attached)."""
        reply = self.reply.cleaned()
        attached = self._app_log.attached()
        text = limited_clean_text(
            self.text.toPlainText(), TEXT_LIMITS[self.chosen_kind()]
        )
        if self._check_result:
            text = f"{text}\n\n--- no-captions check ---\n{self._check_result}"
            text = limited_clean_text(text, TEXT_LIMITS[self.chosen_kind()])
        return self.chosen_kind(), text, reply, attached
