"""Small widgets today's dialogs share: a dialog whose wrapped text always
fits, a label, segmented choices and a button that opens one of our web
pages in the browser. From the proof of concept's
`ui/widgets.py`. (The new interface's own controls are `ui_next.controls`.)"""

from collections.abc import Sequence

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

BASE_TEXT_PX = 13
"""The interface's base text at a text size factor of 1.0, in px: the new
interface's stylesheet's (`ui_next.style.stylesheet`, `px(13)`), which
`main` gives these dialogs - this package can't import it."""


class TextDialog(QDialog):
    """A dialog of wrapped paragraphs that is never shorter than they need.

    Qt sizes a dialog from its widgets' size hints, and a word-wrapped
    label's hint guesses a width - so a long paragraph in a dialog with a
    fixed minimum width is cut off at the bottom (the consent screen's
    "what the service needs" showed four of its nine lines, project 135,
    2026-11-07). Once the dialog has its width, the layout knows the
    height the text really needs; this keeps the dialog at least that
    tall. And never narrower than its widgets' own minimum - a drop-down's
    longest name, a title (polyglotic-hq 213).

    And its whole frame on the screen's work area - above the taskbar. Qt
    places a dialog for its first size; grown since by its wrapped text, it
    could end under the taskbar (polyglotic-hq 203: at 150 % text on a 150 %
    laptop, the level picker's OK was 1 px under it). Moved up, never
    shrunk: a screen too short for one is a test failure
    (tests/ui/test_first_run_fit.py), and a long one scrolls its own part,
    as the first screen does (`ConsentDialog`, #305).

    Its least width (`set_least_width`) grows with its text, so its
    paragraphs wrap into as many lines at any text size: at a fixed 520 px,
    the first screen at the app's Normal text size since decision 0244
    (1.3) scrolled on a 1920 x 1080 screen (polyglotic-hq 524)."""

    _least_width = 0

    def set_least_width(self, width: int) -> None:
        """Never narrower than `width` px at a text size factor of 1.0 -
        wider with its text (`at_text_size`), at most nine tenths of its
        screen's work area."""
        self._least_width = width
        self._keep_least_width()

    def at_text_size(self, width: int) -> int:
        """`width` (px at a text size factor of 1.0) at the size of this
        dialog's text, as styled (`BASE_TEXT_PX`) - never less."""
        font = self.font()
        size = font.pixelSize() if font.pixelSize() > 0 else font.pointSizeF() / 0.75
        return round(width * max(1.0, size / BASE_TEXT_PX))

    def _keep_least_width(self) -> None:
        if not self._least_width:
            return
        width = self.at_text_size(self._least_width)
        screen = self.screen()
        if screen is not None:
            width = min(width, screen.availableGeometry().width() * 9 // 10)
        # never under what's in it needs (`_fit_height`, `ConsentDialog`'s yes)
        self.setMinimumWidth(max(self.minimumWidth(), width))

    def showEvent(self, event: QShowEvent) -> None:
        self._keep_least_width()  # styled by now: at its text's size
        super().showEvent(event)
        QTimer.singleShot(0, self, self.keep_on_screen)  # once placed and styled

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        if event.type() == QEvent.Type.LayoutRequest and self.isVisible():
            # a paragraph changed since it was sized - the sign-in's answer,
            # three lines for an ended Plus code, lost its third (269)
            self._fit_height()
        return handled

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        layout = self.layout()
        if layout is None:
            return
        widest = layout.totalMinimumSize().width()
        if widest > self.minimumWidth():
            # never narrower than what's in it: a minimum width set on a
            # dialog stands in for its layout's (Qt), and Qt first sizes a
            # window at most two thirds of its screen's width - the level
            # picker's drop-down cut its scheme's name off (polyglotic-hq 213)
            narrower = self.width() < widest
            self.setMinimumWidth(widest)
            if narrower:
                return  # resized: its height follows from the new width
        needed = layout.totalHeightForWidth(self.width())
        if needed > self.height():
            self.setMinimumHeight(needed)
        if self.isVisible():
            self.keep_on_screen()

    def keep_on_screen(self) -> None:
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


def page_button(text: str, url: str, name: str) -> QPushButton:
    """A button that opens `url` - a page of our website, such as the privacy
    notice - in the learner's browser. Never shown inside the app, so the
    app and the site can't say different things (polyglotic-hq 185)."""
    button = QPushButton(text)
    button.setObjectName(name)
    button.setProperty("url", url)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(QApplication.translate("Pages", "Opens in your browser"))
    # in a dialog, a focused button takes Enter: the first screen opened with
    # the focus here, and Enter - "go on" - opened the browser instead
    # (polyglotic-hq 203). Space or a click still opens the page.
    button.setAutoDefault(False)
    button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
    return button


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    found = QLabel(text)
    if name:
        found.setObjectName(name)
    found.setWordWrap(wrap)
    return found


class Segmented(QWidget):
    """A row of choices, one at a time - for a handful that should all
    stay in view rather than in a dropdown. Each choice is a Tab stop."""

    changed = Signal(object)

    def __init__(
        self, options: Sequence[tuple[object, str]], value: object = None
    ) -> None:
        super().__init__()
        self._values = [v for v, _ in options]
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.setObjectName("Segmented")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground
        )  # the window's stylesheet
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.buttons: list[QPushButton] = []
        for i, (_, text) in enumerate(options):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, index=i: self._clicked(index))
            self.buttons.append(button)
            row.addWidget(button)
        self.set_value(value)

    def _clicked(self, index: int) -> None:
        self.set_value(self._values[index])  # a click on the chosen one keeps it
        self.changed.emit(self._values[index])

    def button_for(self, value: object) -> QPushButton | None:
        if value in self._values:
            return self.buttons[self._values.index(value)]
        return None

    def set_value(self, value: object) -> None:
        if value not in self._values:
            return
        chosen = self._values.index(value)
        for index, button in enumerate(self.buttons):
            button.setChecked(index == chosen)

    def value(self) -> object:
        for index, button in enumerate(self.buttons):
            if button.isChecked():
                return self._values[index]
        return None

    def choose(self, value: object) -> None:
        """Picks `value` as a click would."""
        self.set_value(value)
        self.changed.emit(value)
