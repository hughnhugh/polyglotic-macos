"""A language's dictionary pack on its Learning card (decision 0122): what
it is doing in plain words, a bar, and the way on - Download, Cancel,
Retry, Download anyway, Get it now.

Nothing ever just spins: the line names what the download waits for -
another download, a connection, the next try (in how many seconds, which
try), a connection that isn't metered, room on the disk - or why it was
refused. The bar is drawn here, flat, and moves only as bytes arrive: it
stands still with Windows' animations off as with them on (a native
progress bar's glow would not).

Only shows and asks: `main` hands over the facts (`views.learning.PackLine`)
and turns what's asked (`wanted`: the language and `download`, `cancel`,
`retry`, `anyway`, `update`) into the downloads' work.
"""

from PySide6.QtCore import QT_TRANSLATE_NOOP, QLocale, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.lexicon.pack_download import (
    STALL_SEC,
    TRIES,
    PackProgress,
    Problem,
    Step,
)
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.copying import Text
from polyglotic_desktop.ui_next.languages import learned_name
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.learning import PackLine


def _tr(text: str) -> str:
    return QApplication.translate("Learning", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("Learning", text, None, n)


def megabytes(size: int) -> str:
    """`size` bytes as megabytes in the interface's own numbers: "62.4"."""
    return QLocale().toString(size / 1_000_000, "f", 1)


def size_text(size: int) -> str:
    return _tr("{size} MB").format(size=megabytes(size))


def _time_left(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return _tr("less than a minute left")
    return _trn("about %n minute(s) left", round(seconds / 60))


def _trying_again(progress: PackProgress) -> str:
    if progress.retry_in is None:
        return _tr("It won't try again by itself.")
    return _tr("Trying again in {seconds} s (try {tries} of {total}).").format(
        seconds=QLocale().toString(max(1, round(progress.retry_in))),
        tries=QLocale().toString(progress.tries + 1),
        total=QLocale().toString(TRIES),
    )


def progress_text(code: str, progress: PackProgress) -> str:
    """What a download is doing, or why it stands still, in plain words."""
    name = learned_name(code)
    problem = progress.problem
    if problem is Problem.OFFLINE:
        return _tr("No connection.") + " " + _trying_again(progress)
    if problem is Problem.STALLED:
        return (
            _tr("The download stalled: no data for {seconds} s.").format(
                seconds=QLocale().toString(round(STALL_SEC))
            )
            + " "
            + _trying_again(progress)
        )
    if problem is Problem.SERVER:
        return (
            _tr("Our server answered with an error ({status}).").format(
                status=progress.status or "?"
            )
            + " "
            + _trying_again(progress)
        )
    if problem is Problem.METERED:
        return _tr(
            "Paused: Windows says this connection is metered. {size} left to download."
        ).format(size=size_text(max(0, progress.total - progress.done)))
    if problem is Problem.NO_ROOM:
        return pc_or_mac(
            _tr("Not enough room on this PC: it needs {size} free."),
            _tr("Not enough room on this Mac: it needs {size} free."),
        ).format(size=size_text(progress.needed))
    if problem is Problem.LIST_REFUSED:
        return _tr(
            "Refused: the list of dictionaries failed our signature check, so "
            "nothing was downloaded."
        )
    if problem is Problem.FILE_REFUSED:
        return _tr("Refused: the file didn't match our list, so it was deleted.")
    if problem is Problem.UNREADABLE:
        return _tr(
            "Refused: the file isn't the {language} dictionary, so it was deleted."
        ).format(language=name)
    if problem is Problem.NEEDS_NEWER_APP:
        return _tr("Its dictionary needs a newer Polyglotic. Update the app to get it.")
    if problem is Problem.NOT_OFFERED:
        return _tr("Its dictionary isn't ready to download yet.")
    if progress.step is Step.WAITING:
        return _tr("Waiting for another dictionary to finish.")
    if progress.step is Step.LIST:
        return _tr("Checking the list of dictionaries.")
    if progress.step is Step.DOWNLOADING:
        said = _tr("Downloading: {done} of {total} MB").format(
            done=megabytes(progress.done), total=megabytes(progress.total)
        )
        left = _time_left(progress.seconds_left)
        return f"{said} · {left}" if left else said
    if progress.step is Step.CHECKING:
        return _tr("Checking the file.")
    if progress.step is Step.OPENING:
        return _tr("Opening the dictionary.")
    return ""


ACTIONS = {
    "download": QT_TRANSLATE_NOOP("Learning", "Download"),
    "cancel": QT_TRANSLATE_NOOP("Learning", "Cancel"),
    "retry": QT_TRANSLATE_NOOP("Learning", "Retry"),
    "anyway": QT_TRANSLATE_NOOP("Learning", "Download anyway"),
    "update": QT_TRANSLATE_NOOP("Learning", "Get it now"),
}


def shown(code: str, line: PackLine) -> tuple[str, tuple[str, ...], float | None]:
    """The line's words, its buttons (`ACTIONS`' keys, in order) and the
    bar's share (None: no bar)."""
    progress = line.progress
    if progress is not None and progress.step not in (Step.DONE, Step.CANCELLED):
        said = progress_text(code, progress)
        if progress.problem is Problem.NEEDS_NEWER_APP:
            return said, (), None
        if progress.problem is Problem.NOT_OFFERED:
            return said, ("retry",), None
        if progress.problem is Problem.METERED:
            return said, ("anyway", "cancel"), progress.share
        if progress.problem is not None:  # stopped, or a try coming: Retry now
            return said, ("retry", "cancel"), progress.share or None
        share = progress.share if progress.step is not Step.WAITING else 0.0
        return said, ("cancel",), share
    if line.newer_app:
        newer = PackProgress(code, Step.LIST, problem=Problem.NEEDS_NEWER_APP)
        return progress_text(code, newer), (), None
    if line.installed:
        said = pc_or_mac(
            _tr("On this PC: version {version}, {size}."),
            _tr("On this Mac: version {version}, {size}."),
        ).format(version=line.installed_version, size=size_text(line.installed_size))
        if line.recorded_size:
            said += " " + _tr("Its commonest words are recorded ({size}).").format(
                size=size_text(line.recorded_size)
            )
        if line.update_size:
            said += " " + _tr(
                "A newer version ({size}) waits for a connection that isn't metered."
            ).format(size=size_text(line.update_size))
            return said, ("update",), None
        return said, (), None
    if line.size:
        if line.recorded_offered:  # both sizes before it starts (0192)
            said = _tr(
                "Its dictionary: {size} to download, then {recorded} of recorded words."
            ).format(
                size=size_text(line.size), recorded=size_text(line.recorded_offered)
            )
        else:
            said = _tr("Its dictionary: {size} to download.").format(
                size=size_text(line.size)
            )
        return said, ("download",), None
    # Retry tries for real - a pack published since is found - and then says
    # why. None to be had (not in the list held, or none published) isn't
    # "checking"; a list that couldn't be read says only that (330)
    if line.not_offered:
        return _tr("Its dictionary isn't ready to download yet."), ("retry",), None
    if line.unlisted:
        return _tr("The list of dictionaries couldn't be checked."), ("retry",), None
    return _tr("Checking the list of dictionaries."), ("download",), None


class PackBar(QWidget):
    """A flat bar, `share` of it filled - no animation of its own."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.share = 0.0
        self.setObjectName("learning.pack_bar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(max(4, style.px(6)))
        self.setAccessibleName(_tr("Download progress"))

    def set_share(self, share: float) -> None:
        share = min(1.0, max(0.0, share))
        if share != self.share:
            self.share = share
            self.setAccessibleDescription(f"{round(share * 100)} %")
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        ink = self.palette().color(QPalette.ColorRole.WindowText)
        track = QColor(ink)
        track.setAlphaF(0.18)
        whole = QRectF(self.rect())
        radius = whole.height() / 2
        painter.setBrush(track)
        painter.drawRoundedRect(whole, radius, radius)
        if self.share > 0:
            filled = QRectF(whole)
            filled.setWidth(max(whole.height(), whole.width() * self.share))
            painter.setBrush(ink)
            painter.drawRoundedRect(filled, radius, radius)
        painter.end()


class PackRow(QWidget):
    """One language's pack: its line, the bar, its buttons."""

    wanted = Signal(str, str)
    """The language, and what's asked (`ACTIONS`' keys)."""

    def __init__(self, code: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.code = code
        self.setObjectName(f"learning.{code}.pack")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        line = QHBoxLayout()
        line.setSpacing(12)
        self.said = Text(self)  # its words can be copied (343)
        self.said.setObjectName(f"learning.{code}.pack_said")
        self.said.setWordWrap(True)
        line.addWidget(self.said, 1)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in ACTIONS.items():
            button = QPushButton(_tr(str(text)), self)
            button.setObjectName(f"learning.{code}.pack_{key}")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if key == "cancel":
                button.setProperty("kind", "ghost")
            button.clicked.connect(
                lambda _=False, k=key: self.wanted.emit(self.code, k)
            )
            button.hide()
            line.addWidget(button)
            self.buttons[key] = button
        column.addLayout(line)
        self.bar = PackBar(self)
        column.addWidget(self.bar)
        self.line: PackLine | None = None

    def show_line(self, line: PackLine) -> None:
        if line == self.line:
            return
        self.line = line
        said, actions, share = shown(self.code, line)
        self.said.setText(said)
        self.said.setToolTip(line.credits)
        for key, button in self.buttons.items():
            button.setVisible(key in actions)
        self.bar.setVisible(share is not None)
        self.bar.set_share(share or 0.0)


def ready_notice(code: str) -> str:
    """Home's notice, once, when a pack the learner asked for is in."""
    return _tr(
        "The {language} dictionary is ready: look up words in {language} captions."
    ).format(language=learned_name(code))


def failed_notice(code: str) -> str:
    """Home's notice, once, when it stopped without it (Learning says why)."""
    return _tr(
        "The {language} dictionary couldn't be downloaded: see Learning."
    ).format(language=learned_name(code))


def remove_question(code: str, size: int) -> tuple[str, str, str, str]:
    """Stopping a language with a pack on this PC: the question's title, its
    words, and its two answers."""
    name = learned_name(code)
    return (
        _tr("Remove the {language} dictionary too?").format(language=name),
        pc_or_mac(
            _tr(
                "It frees {size} on this PC. It downloads again if you learn "
                "{language} later."
            ),
            _tr(
                "It frees {size} on this Mac. It downloads again if you learn "
                "{language} later."
            ),
        ).format(size=size_text(size), language=name),
        _tr("Remove it"),
        _tr("Keep it"),
    )
