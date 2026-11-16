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

from polyglotic_desktop.ui.os_words import pc_or_mac

MAX_TEXT = 5000  # protocol.md's limit


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
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProblemReportDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.setMinimumWidth(560)
        self.parts = tuple(parts)
        self._look: LookDialog | None = None
        self._fitting = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(8)
        title = QLabel(_tr("Report a problem"))
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        self.setWindowTitle(title.text())
        self.body = QWidget()
        self.body.setObjectName("problem_report.body")
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        intro = QLabel(
            _tr(
                "Tell us what happened, if you like. What's ticked goes with it, "
                "so we can see the problem again and fix it - untick anything "
                "you'd rather not send."
            )
        )
        intro.setWordWrap(True)
        intro.setObjectName("Dim")
        layout.addWidget(intro)
        self.text = QPlainTextEdit()
        self.text.setObjectName("problem_report.text")
        # Tab goes on to the ticks and Send, as everywhere else: a tab
        # character is never wanted here, and the keyboard was stuck (278)
        self.text.setTabChangesFocus(True)
        self.text.setPlaceholderText(_tr("What happened, and roughly when? (optional)"))
        self.text.setMinimumHeight(90)
        layout.addWidget(self.text)

        self.ticks: dict[str, QCheckBox] = {}
        for part in self.parts:
            layout.addWidget(self._part_row(part))
            if part.others_voices:
                note = QLabel(_tr("This includes other people's voices."))
                note.setObjectName("Faint")
                note.setContentsMargins(26, 0, 0, 0)
                layout.addWidget(note)

        about = QLabel(
            _tr(
                "Also sent: {versions}, and the listening session's ID. "
                "Kept for 30 days to fix the problem, then deleted. "
                "No screenshot is taken."
            ).format(versions=versions)
        )
        about.setObjectName("Faint")
        about.setWordWrap(True)
        layout.addWidget(about)

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
        self.text.textChanged.connect(self._check)
        for tick in self.ticks.values():
            tick.toggled.connect(self._check)
        self._check()

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
        leaves room for, with them scrolling between the title and Send."""
        screen = self.screen()
        outer = self.layout()
        if screen is None or outer is None or self._fitting:
            return
        bar = self.scroll_area.verticalScrollBar().sizeHint().width()
        natural = self.body.heightForWidth(self.scroll_area.width() - bar)
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
            # wider by the bar, so the widest part still fits beside it
            self.scroll_area.setMinimumWidth(
                self.body.minimumSizeHint().width() + bar + 4 if scrolls else 0
            )
            self.scroll_area.setFixedHeight(max(MIN_SCROLL, min(natural, room - rest)))
            outer.invalidate()
            total = outer.totalSizeHint().height()
            self.setMinimumHeight(total)
            if self.height() != total:
                self.resize(self.width(), total)
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
        text = self.text.toPlainText()
        something = bool(text.strip()) or any(
            t.isChecked() for t in self.ticks.values()
        )
        self.send.setEnabled(something and len(text) <= MAX_TEXT)

    def _send(self) -> None:
        self.sent.emit()
        self.accept()

    def chosen(self) -> tuple[str, frozenset[str]]:
        """What the tester wrote, and the keys of the parts left ticked."""
        ticked = frozenset(k for k, t in self.ticks.items() if t.isChecked())
        return self.text.toPlainText().strip(), ticked


class OneReportWindow:
    """At most one report window at a time: asked for again while one is
    open - a double-click on the caption window's button, or the tray's
    entry after the bar's - the open one comes to the front instead of a
    second (polyglotic-hq 278: a double-click opened two)."""

    def __init__(self) -> None:
        self._open: ProblemReportDialog | None = None

    def front(self) -> bool:
        """The open report window to the front: False if none is open."""
        if self._open is None:
            return False
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
