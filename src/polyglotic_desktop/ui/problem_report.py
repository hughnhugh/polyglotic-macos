"""Report a problem, for alpha testers: one click, everything ticked, each part shown (polyglotic-hq 275).

The user, 2026-11-11: "Give the testers a one click functionality to
submit issues including all data associated with their bug. We can
retrace it and fix it." Decided with the user: audio and caption text go
only inside a report the tester sends, shown and agreed each time.

A small window, not modal - captions go on while it's open:
- a line for what happened (optional);
- **the parts**, each ticked, with its size and **Look** (exactly what
  goes, read-only): the app's log; the settings; the app, Windows and
  audio devices; the last few minutes of captions as shown; and each
  source's last 2 minutes of audio. A call app's or the mic's audio says
  "This includes other people's voices." under it - still ticked;
  unticking is one click;
- Help's "no captions?" check, when it was opened from there;
- what else goes, and how long it's kept; Send and Cancel.

The window only asks: `chosen()` is what the tester left ticked, and
`main` builds the report from it, keeps it and sends it off the
interface's thread. Holds caption text and audio sizes: never log them.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from PySide6.QtCore import QEvent, QLocale, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.report_text import (
    COUNTER_THRESHOLD,
    REPLY_TO_LIMIT,
    TEXT_LIMITS,
    clean_report_text,
    limited_clean_text,
)
from polyglotic_desktop.ui.feedback import (
    FeedbackLog,
    ReplyField,
    can_send,
    optional_reply_label,
)
from polyglotic_desktop.ui.os_words import pc_or_mac
from polyglotic_desktop.ui.widgets import Segmented

ReportMode = Literal["problem", "suggestion"]
"""The two-way choice at the top of the modal: Report a problem or Make a suggestion."""


def _tr(text: str) -> str:
    return QApplication.translate("ProblemReport", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("ProblemReport", text, None, n)


@dataclass(frozen=True)
class Part:
    """One thing the report can carry. `key` names it to `main`; `label`
    and `detail` are what the tester reads; `size` is in bytes as sent;
    `look` gives exactly what goes, as text."""

    key: str
    label: str
    size: int
    look: Callable[[], str]
    detail: str = ""
    others_voices: bool = False


def size_text(size: int) -> str:
    """A size in the interface language's way (`34 KB`)."""
    return QLocale().formattedDataSize(
        size,
        0 if size < 1024 * 1024 else 1,
        QLocale.DataSizeFormat.DataSizeTraditionalFormat,
    )


def duration_text(seconds: float) -> str:
    """A short duration: `40 s`, `1 min 40 s`."""
    whole = max(0, round(seconds))
    minutes, rest = divmod(whole, 60)
    if minutes:
        #: a duration: minutes and seconds
        return _tr("{minutes} min {seconds} s").format(minutes=minutes, seconds=rest)
    #: a duration in seconds
    return _tr("{seconds} s").format(seconds=rest)


class LookDialog(QDialog):
    """A part exactly as it goes, read-only."""

    def __init__(self, title: str, text: str, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setObjectName("ProblemReportLook")
        self.setWindowTitle(title)
        self.setMinimumSize(560, 360)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit(text)
        self.view.setObjectName("problem_report.look.text")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


WINDOW_FRAME = 40
"""Room left for the window's frame and title bar on the work area (as Your
data's, `ui.consent`)."""
MIN_SCROLL = 120
"""The least the parts' area shrinks to on a screen too short for them."""


class ProblemReportDialog(QDialog):
    """`sent` when the tester sends it; read `chosen()` then.

    The title stays at the top and Send at the bottom; what's between them
    (the line, the parts, what else goes) scrolls on a screen too short for
    it all (`_fit`; polyglotic-hq 300: in German at the Largest text size on
    a 1366 x 768 laptop the window was squeezed to the screen and its text
    overlapped - the note's box over the first part, the last lines cut)."""

    sent = Signal()

    def __init__(
        self,
        parts: Sequence[Part],
        versions: str,
        parent: QWidget | None = None,
        mode: ReportMode = "problem",
        with_session: bool = True,
        problem_requires_text: bool = False,
        *,
        read_suggestion_log: Callable[[], str | None] = lambda: None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProblemReportDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.setMinimumWidth(560)
        self.parts = tuple(parts)
        self._versions = versions
        self._with_session = with_session
        self._problem_requires_text = problem_requires_text
        self._read_suggestion_log = read_suggestion_log
        self._suggestion_log: FeedbackLog | None = None
        self._look: LookDialog | None = None
        self._fitting = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(8)
        self.mode = Segmented(
            [
                ("problem", _tr("Report a problem")),
                ("suggestion", _tr("Make a suggestion")),
            ],
            mode,
        )
        for key in ("problem", "suggestion"):
            if (button := self.mode.button_for(key)) is not None:
                button.setObjectName(f"problem_report.mode.{key}")
        outer.addWidget(self.mode, 0, Qt.AlignmentFlag.AlignLeft)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        outer.addWidget(self.title)
        self.body = QWidget()
        self.body.setObjectName("problem_report.body")
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self.intro.setObjectName("Dim")
        layout.addWidget(self.intro)
        self.text = QPlainTextEdit()
        self.text.setObjectName("problem_report.text")
        # Tab goes on to the ticks and Send, as everywhere else: a tab
        # character is never wanted here, and the keyboard was stuck (278)
        self.text.setTabChangesFocus(True)
        self.text.setMinimumHeight(90)
        layout.addWidget(self.text)
        counter_line = QWidget()
        counter_layout = QHBoxLayout(counter_line)
        counter_layout.setContentsMargins(0, 0, 0, 0)
        self.cut_note = QLabel()
        self.cut_note.setObjectName("Faint")
        counter_layout.addWidget(self.cut_note)
        counter_layout.addStretch(1)
        self.count = QLabel()
        self.count.setObjectName("Faint")
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight)
        counter_layout.addWidget(self.count)
        layout.addWidget(counter_line)

        self.parts_box = QWidget(self.body)
        self.parts_box.setObjectName("problem_report.parts")
        parts_layout = QVBoxLayout(self.parts_box)
        parts_layout.setContentsMargins(0, 0, 0, 0)
        parts_layout.setSpacing(8)  # constant: matches body layout row spacing
        self.ticks: dict[str, QCheckBox] = {}
        for part in self.parts:
            parts_layout.addWidget(self._part_row(part))
            if part.others_voices:
                note = QLabel(_tr("This includes other people's voices."))
                note.setObjectName("Faint")
                note.setContentsMargins(26, 0, 0, 0)
                parts_layout.addWidget(note)
        layout.addWidget(self.parts_box)

        self._suggestion_box = QWidget(self.body)
        self._suggestion_layout = QVBoxLayout(self._suggestion_box)
        self._suggestion_layout.setContentsMargins(0, 0, 0, 0)
        self._suggestion_layout.setSpacing(layout.spacing())
        reply_label = QLabel(optional_reply_label())
        reply_label.setObjectName("Dim")
        self._suggestion_layout.addWidget(reply_label)
        self.reply = ReplyField()
        self.reply.setObjectName("problem_report.reply")
        self.reply.setAccessibleName(reply_label.text())
        self._suggestion_layout.addWidget(self.reply)
        layout.addWidget(self._suggestion_box)

        self.about = QLabel()
        self.about.setObjectName("Faint")
        self.about.setWordWrap(True)
        layout.addWidget(self.about)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("problem_report.scroll")
        self.scroll_area.setWidget(self.body)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.viewport().setAutoFillBackground(False)
        # never the focus itself: the window opens ready to type in the line
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.body.setAutoFillBackground(False)
        outer.addWidget(self.scroll_area, 1)
        self.body.installEventFilter(self)

        buttons = QDialogButtonBox()
        self.send = QPushButton(_tr("Send"))
        self.send.setObjectName("problem_report.send")
        self.send.setDefault(True)
        buttons.addButton(self.send, QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText(_tr("Cancel"))
        buttons.accepted.connect(self._send)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.mode.changed.connect(self._mode_changed)
        self.text.textChanged.connect(self._check)
        self.reply.textChanged.connect(self._check)
        for tick in self.ticks.values():
            tick.toggled.connect(self._check)
        self._apply_mode(mode)
        self.text.setFocus()

    def chosen_mode(self) -> ReportMode:
        """The selected tab: `"problem"` or `"suggestion"`."""
        return "suggestion" if self.mode.value() == "suggestion" else "problem"

    def set_mode(self, mode: ReportMode) -> None:
        """Switches the modal between `"problem"` and `"suggestion"`."""
        self.mode.set_value(mode)
        self._apply_mode(mode)

    def limit(self) -> int:
        """Character limit for the active mode (`core.report_text.TEXT_LIMITS`)."""
        return TEXT_LIMITS[self.chosen_mode()]

    def _mode_changed(self, value: object) -> None:
        mode: ReportMode = "suggestion" if value == "suggestion" else "problem"
        self._apply_mode(mode)

    def _apply_mode(self, mode: ReportMode) -> None:
        is_problem = mode == "problem"
        title = _tr("Report a problem") if is_problem else _tr("Make a suggestion")
        self.title.setText(title)
        self.setWindowTitle(title)
        if is_problem:
            self.intro.setText(
                _tr(
                    "Tell us what happened, if you like. What's ticked goes with it, "
                    "so we can see the problem again and fix it - untick anything "
                    "you'd rather not send."
                )
            )
            prompt = _tr("What happened, and roughly when? (optional)")
            self.about.setText(
                _tr(
                    "Also sent: {versions}, and the listening session's ID. "
                    "Kept for 30 days to fix the problem, then deleted. "
                    "No screenshot is taken."
                ).format(versions=self._versions)
            )
        else:
            self.intro.setText(
                _tr("Share an idea for how Polyglotic could work better for you.")
            )
            prompt = _tr("What would you like Polyglotic to do?")
            self.about.setText(
                (
                    _tr("Also sent: {versions}, and the listening session's ID.")
                    if self._with_session
                    else _tr("Also sent: {versions}.")
                ).format(versions=self._versions)
                + " "
                + _tr("No screenshot is taken.")
                + " "
                + _tr(
                    "Please don't paste captions of other people's words. We may read "
                    "feedback with the help of AI tools (Anthropic's Claude) to sort "
                    "and summarise it."
                )
            )
        self.text.setPlaceholderText(prompt)
        self.text.setAccessibleName(prompt)
        self.parts_box.setVisible(is_problem and bool(self.parts))
        if not is_problem and self._suggestion_log is None:
            self._suggestion_log = FeedbackLog(
                self._suggestion_layout, self._read_suggestion_log()
            )
        self._suggestion_box.setVisible(not is_problem)
        self.cut_note.clear()
        self._check()
        if (body_layout := self.body.layout()) is not None:
            body_layout.invalidate()
        self._fit()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(
            0, self, self._fit
        )  # again once styled: its fonts set its height

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """The parts' area changed size (styled, the text size): fitted again."""
        if watched is self.body and event.type() == QEvent.Type.LayoutRequest:
            QTimer.singleShot(0, self, self._fit)
        return False

    def _fit(self) -> None:
        """As tall as the line, the parts and what else goes need at this
        width - or, on a screen too short for that, as tall as its work area
        leaves room for, with them scrolling between the title and Send. Also
        never narrower than the widest part row (capped to the work area)."""
        screen = self.screen()
        outer = self.layout()
        if screen is None or outer is None or self._fitting:
            return
        margins = outer.contentsMargins()
        pad_x = margins.left() + margins.right()
        bar = self.scroll_area.verticalScrollBar().sizeHint().width()
        max_w = screen.availableGeometry().width() - WINDOW_FRAME
        min_body = self.body.minimumSizeHint().width()
        view_w = max(self.scroll_area.width(), min(min_body, max(0, max_w - pad_x)))
        natural = self.body.heightForWidth(view_w - bar)
        if natural < 0:
            natural = self.body.sizeHint().height()
        self._fitting = True
        try:
            self.scroll_area.setFixedHeight(0)
            outer.invalidate()
            rest = outer.totalSizeHint().height()
            room = screen.availableGeometry().height() - WINDOW_FRAME
            # a scroll bar only on a screen too short for it all (as Your
            # data), with room for it: the text never runs under it
            scrolls = natural > room - rest
            self.scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
                if scrolls
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            # wider by the widest part (plus the bar when scrolling) so Look
            # and long part labels never clip past the viewport's right edge
            extra = bar + 4 if scrolls else 0
            needed_scroll_w = min(min_body + extra, max(0, max_w - pad_x))
            self.scroll_area.setMinimumWidth(needed_scroll_w)
            final_view_w = max(self.scroll_area.width(), needed_scroll_w) - (
                bar if scrolls else 0
            )
            natural = self.body.heightForWidth(final_view_w)
            if natural < 0:
                natural = self.body.sizeHint().height()
            self.scroll_area.setFixedHeight(max(MIN_SCROLL, min(natural, room - rest)))
            outer.invalidate()
            hint = outer.totalSizeHint()
            target_w = min(max_w, max(self.width(), hint.width()))
            target_h = hint.height()
            self.setMinimumHeight(target_h)
            if (self.width(), self.height()) != (target_w, target_h):
                self.resize(target_w, target_h)
        finally:
            self._fitting = False
        self._keep_on_screen()

    def _keep_on_screen(self) -> None:
        """Moved as little as keeps its frame on the work area."""
        screen = self.screen()
        if screen is None or not self.isVisible():
            return
        area = screen.availableGeometry()
        frame = self.frameGeometry()
        left = max(area.left(), min(frame.left(), area.right() + 1 - frame.width()))
        top = max(area.top(), min(frame.top(), area.bottom() + 1 - frame.height()))
        if (left, top) != (frame.left(), frame.top()):
            self.move(left, top)

    def _part_row(self, part: Part) -> QWidget:
        row = QWidget(self)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        detail = f"{part.detail} · " if part.detail else ""
        tick = QCheckBox(f"{part.label} ({detail}{size_text(part.size)})", row)
        tick.setObjectName(f"problem_report.part.{part.key}")
        tick.setChecked(True)
        self.ticks[part.key] = tick
        line.addWidget(tick, 1)
        look = QPushButton(_tr("Look"), row)
        look.setObjectName(f"problem_report.look.{part.key}")
        look.setProperty("kind", "ghost")
        look.setCursor(Qt.CursorShape.PointingHandCursor)
        look.clicked.connect(lambda: self._show(part))
        line.addWidget(look)
        return row

    def _show(self, part: Part) -> None:
        if self._look is not None:
            self._look.close()
        self._look = LookDialog(part.label, part.look(), self)
        self._look.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._look.destroyed.connect(self._looked)
        self._look.show()

    def _looked(self) -> None:
        self._look = None

    def _check(self) -> None:
        limit = self.limit()
        raw_text = self.text.toPlainText()
        text = limited_clean_text(raw_text, limit)
        # Keep whitespace in the editable draft: trimming belongs at the
        # preview/send boundary.  Replacing the document on every keystroke
        # would also discard the learner's caret and selection.
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
                _tr("Cut to {limit} characters").format(limit=f"{limit:,}")
            )
        self.count.setText(
            _tr("{count} / {limit}").format(count=f"{len(text):,}", limit=f"{limit:,}")
        )
        self.count.setVisible(len(text) >= limit * COUNTER_THRESHOLD)
        if self.chosen_mode() == "suggestion":
            reply, cut = self.reply.cap()
            if cut:
                self.cut_note.setText(
                    _tr("Cut to {limit} characters").format(limit=f"{REPLY_TO_LIMIT:,}")
                )
            something = can_send("suggestion", text, reply)
        elif self._problem_requires_text:
            something = bool(text.strip())
        else:
            something = bool(text.strip()) or any(
                t.isChecked() for t in self.ticks.values()
            )
        self.send.setEnabled(something)

    def suggestion_details(self) -> tuple[str | None, str | None]:
        """The optional reply and opted-in plain log for a suggestion."""
        if self.chosen_mode() != "suggestion" or self._suggestion_log is None:
            return None, None
        return self.reply.cleaned(), self._suggestion_log.attached()

    def _send(self) -> None:
        self.sent.emit()
        self.accept()

    def chosen(self) -> tuple[str, frozenset[str]]:
        """What the learner wrote, and (in problem mode) the keys of the parts
        left ticked. Suggestion mode sends no problem-report attachments."""
        mode = self.chosen_mode()
        text = limited_clean_text(self.text.toPlainText(), TEXT_LIMITS[mode])
        if mode == "suggestion":
            return text, frozenset()
        ticked = frozenset(k for k, t in self.ticks.items() if t.isChecked())
        return text, ticked


class OneReportWindow:
    """At most one report window at a time: asked for again while one is
    open - a double-click on the caption window's button, or the tray's
    entry after the bar's - the open one comes to the front instead of a
    second (polyglotic-hq 278: a double-click opened two)."""

    def __init__(self) -> None:
        self._open: ProblemReportDialog | None = None

    def front(self, mode: ReportMode | None = None) -> bool:
        """The open report window to the front: False if none is open.
        Switches to `mode` if one is given."""
        if self._open is None:
            return False
        if mode is not None:
            self._open.set_mode(mode)
        self._open.show()
        self._open.raise_()
        self._open.activateWindow()
        return True

    def opened(self, dialog: ProblemReportDialog) -> None:
        """`dialog` is the report window now, until it's sent or closed."""
        self._open = dialog
        dialog.finished.connect(lambda _result: self._closed(dialog))
        dialog.destroyed.connect(lambda: self._closed(dialog))

    def _closed(self, dialog: ProblemReportDialog) -> None:
        if self._open is dialog:
            self._open = None


def captions_look(captions: Sequence[dict[str, object]]) -> str:
    """The captions part, as text: each caption's time on this PC's clock,
    what was said and its translations - exactly the words that go."""
    lines = []
    for caption in captions:
        started = str(caption["started_at"]).replace("Z", "+00:00")
        at = datetime.fromisoformat(started).astimezone().strftime("%H:%M:%S")
        lines.append(f"{at}  {caption['original']}")
        translations = caption.get("translations")
        if isinstance(translations, dict):
            lines += [
                f"          {lang}: {text}" for lang, text in translations.items()
            ]
    return "\n".join(lines)


def speech_look(clips: Sequence[tuple[str, float]], said: dict[str, str]) -> str:
    """A source's audio part, as text: each clip's length and the caption
    it was heard as, if that's still shown. `clips`: (caption id, seconds)."""
    return "\n".join(
        f"{n:>3}.  {duration_text(seconds):>8}  {said.get(caption_id, '')}"
        for n, (caption_id, seconds) in enumerate(clips, 1)
    )


def part_labels() -> dict[str, str]:
    """The fixed parts' names, as the tester reads them."""
    return {
        "log": _tr("The app's log"),
        "settings": _tr("Your settings"),
        "facts": pc_or_mac(
            _tr("About this PC: the app, the system and the audio devices"),
            _tr("About this Mac: the app, the system and the audio devices"),
        ),
        "captions": _tr("Captions from the last few minutes, as shown"),
        "check": _tr('Help\'s "no captions?" check'),
    }


def captions_detail(count: int) -> str:
    return _trn("%n caption(s)", count)


def speech_label(source: str) -> str:
    """A source's audio part: `Audio from Discord`. Each source holds its
    last 2 minutes of finished speech."""
    #: {source} is an app's name as the tester knows it, or "your mic"
    return _tr("Audio from {source}").format(source=source)


def speech_detail(seconds: float) -> str:
    #: how much speech a source's audio part holds: "1 min 40 s of speech"
    return _tr("{duration} of speech").format(duration=duration_text(seconds))


def mic_name() -> str:
    #: the user's own mic, as a source in "Audio from {source}"
    return _tr("your mic")
