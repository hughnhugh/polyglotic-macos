"""Every first-run screen fits a 150 % laptop (polyglotic-hq 203, 208).

A 1920 x 1080 laptop at 150 % - what Windows recommends on many 13-14 inch
laptops - has 1280 x 672 above the taskbar. #305 made the first screen fit
there; at 150 % text the level picker's OK was still 1 px under the
taskbar. Each first-run screen, at 100, 125 and 150 % text: at most the
work area's height with Windows' title bar, and its whole frame - OK or
Continue included - above the taskbar wherever Qt first put it.
"""

from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ui import interface_language
from polyglotic_desktop.ui.consent import WINDOW_FRAME, ConsentDialog
from polyglotic_desktop.ui.language_picker import LanguagePicker
from polyglotic_desktop.ui.level_picker import LevelPicker
from polyglotic_desktop.ui.sign_in import SignInDialog
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.views import known_words

WORK_AREA = QRect(0, 0, 1280, 672)


class LaptopScreen:
    """1920 x 1080 at 150 %, the taskbar left out."""

    def availableGeometry(self) -> QRect:
        return QRect(WORK_AREA)


FIRST_RUN: dict[str, Callable[[], QDialog]] = {
    "your language": lambda: LanguagePicker(interface_language.picker(), "de"),
    "the level, learning Chinese": lambda: LevelPicker(
        "Chinese", known_words.choices("zh"), known_words.not_sure("zh")
    ),
    "the level, learning English": lambda: LevelPicker(
        "English", known_words.choices("en"), known_words.not_sure("en")
    ),
    "the first screen": ConsentDialog,
    "the code": lambda: SignInDialog(lambda typed: None),
}
"""The first run's screens, in order (main.py's first run) - and the level
picker, the first run's once and Learning's and Words' now (293)."""


@pytest.fixture
def text_size(qapp: QApplication) -> Iterator[Callable[[int], None]]:
    """Windows' Text size simulated, as the UI lab does (`use_text_size`),
    and put back after."""
    before = QFont(qapp.font())

    def use(percent: int) -> None:
        font = QFont(before)
        font.setPointSizeF(style.DEFAULT_POINTS * percent / 100)
        qapp.setFont(font)
        style.use_text_scale(style.text_scale_of(qapp.font()))

    yield use
    qapp.setFont(before)
    style.use_text_scale(1.0)


@pytest.mark.parametrize("size", ["smaller", "normal"])
@pytest.mark.parametrize("percent", [100, 125, 150])
@pytest.mark.parametrize("screen", list(FIRST_RUN))
def test_every_first_run_screen_fits_a_150_percent_laptop(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    text_size: Callable[[int], None],
    screen: str,
    percent: int,
    size: str,
) -> None:
    """At Windows' text sizes, times the app's - Normal, the default, is 1.3
    since polyglotic-hq 524: at 150 % (1.95) the level picker, 580 px wide
    whatever its text, was 793 px tall."""
    style.use_app_text_size(size)
    text_size(percent)
    dialog = FIRST_RUN[screen]()
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    monkeypatch.setattr(dialog, "screen", lambda: LaptopScreen())
    dialog.move(300, 200)  # Qt placed it for a smaller size: it then grew
    dialog.show()
    for _ in range(3):
        qapp.processEvents()
    frame = dialog.frameGeometry()
    assert dialog.height() + WINDOW_FRAME <= WORK_AREA.height(), (
        f"{screen} at {percent} %: {dialog.height()} px tall"
    )
    assert WORK_AREA.contains(frame), f"{screen} at {percent} %: {frame}"
    ok = next(
        b
        for b in dialog.findChildren(QPushButton)
        if b.isVisible() and b.text() in ("OK", "Continue", "Sign in")
    )
    bottom = ok.mapToGlobal(ok.rect().bottomLeft()).y()
    assert bottom <= WORK_AREA.bottom(), f"{screen} at {percent} %: OK at y={bottom}"
    dialog.close()


@pytest.mark.parametrize("percent", [100, 125, 150, 200])
@pytest.mark.parametrize("screen", list(FIRST_RUN))
def test_nothing_on_a_first_run_screen_is_squeezed(
    qapp: QApplication,
    text_size: Callable[[int], None],
    screen: str,
    percent: int,
) -> None:
    """Polyglotic-hq 213 (208's shot): at 150 % text the level picker's
    drop-down cut its scheme's name off - "HSK 3.0 - the 2025 exam syllabus
    (what the exam te". The dialog's own minimum width stood in for its
    layout's (Qt does that), and Qt first sizes a window at most two thirds
    of its screen's width, so the dialog was narrower than the drop-down's
    name. Every widget at least as wide as its own minimum, whatever the
    screen (here the test platform's, 800 px wide)."""
    text_size(percent)
    dialog = FIRST_RUN[screen]()
    dialog.setStyleSheet(style.stylesheet(window_theme()))
    dialog.show()
    for _ in range(3):
        qapp.processEvents()
    squeezed = [
        f"{type(each).__name__} {each.objectName()!r}:"
        f" {each.width()} of {each.minimumSizeHint().width()} px"
        for each in dialog.findChildren(QWidget)
        if each.isVisible() and each.width() < each.minimumSizeHint().width()
    ]
    assert not squeezed, f"{screen} at {percent} %: {squeezed}"
    dialog.close()


class WindowsShown(QObject):
    """Every widget shown as a window of its own while it watches."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[str] = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and watched.isWindow()
        ):
            self.shown.append(type(watched).__name__)
        return False


@pytest.mark.parametrize("screen", list(FIRST_RUN))
def test_no_part_of_a_first_run_screen_shows_as_a_window_while_its_made(
    qapp: QApplication, screen: str
) -> None:
    """Polyglotic-hq 273: the level picker's drop-down was shown before
    it had a parent - a window of its own, for a moment, on the learner's
    screen. Making it held the interface 803 ms at the user's first run
    (2026-11-09's log); 280 ms with real windows here, 8 ms once fixed."""
    watching = WindowsShown()
    qapp.installEventFilter(watching)
    try:
        dialog = FIRST_RUN[screen]()
    finally:
        qapp.removeEventFilter(watching)
    assert watching.shown == [], f"{screen}: {watching.shown}"
    dialog.deleteLater()
