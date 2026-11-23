"""The main window's theme on its parts, not on the window (polyglotic-hq
355): a theme change restyles the sidebar and the page on show, and each
other page as it's next shown - and everything looks as it did when the
stylesheet was on the window. Qt restyles every widget under a changed
stylesheet, shown or not: the pages not on show had made the UI lab's
theme change 2.3 times slower in a week (33 to 77 ms, 326 to 857
widgets)."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import label
from polyglotic_desktop.ui_next.main_window import MainWindow
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)

LIGHT = style.Theme(
    {"BG": "#fafafa", "TEXT": "#111111", "SURFACE": "#ffffff", "BORDER": "#dddddd"},
    "Literata",
    dark=False,
)
DARK = style.Theme(
    {"BG": "#101418", "TEXT": "#eeeeee", "SURFACE": "#1a2026", "BORDER": "#2a3036"},
    "Literata",
    dark=True,
)


class StyleChanges(QObject):
    """Which widgets Qt restyled (sent a StyleChange) while it watched."""

    def __init__(self) -> None:
        super().__init__()
        self.restyled: set[int] = set()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.StyleChange:
            self.restyled.add(_address(watched))
        return False


def _page(name: str) -> QWidget:
    """A page with what reads the palette where the stylesheet may not say:
    a card, a field, a list, a box to tick, a button and a scroll bar."""
    page = QScrollArea()
    page.setWidgetResizable(True)
    inside = QWidget()
    column = QVBoxLayout(inside)
    card = QWidget()
    card.setObjectName("Card")
    QVBoxLayout(card).addWidget(label(f"{name}'s card", "CardTitle"))
    column.addWidget(label(name.title(), "PageTitle"))
    column.addWidget(card)
    column.addWidget(QLineEdit(name))
    choice = QComboBox()
    choice.addItems(["one", "two"])
    column.addWidget(choice)
    column.addWidget(QCheckBox("Tick it"))
    column.addWidget(QPushButton("Do it"))
    for n in range(30):  # enough to scroll
        column.addWidget(label(f"Line {n}", "Dim"))
    page.setWidget(inside)
    return page


def _window(theme: style.Theme) -> MainWindow:
    style.use(theme)
    window = MainWindow(QAction("Quit"))
    window.add_page("home", "Home", _page("home"))
    window.add_page("words", "Words", _page("words"), "top", 720)
    window.add_page("help", "Help", _page("help"), "foot", 720)
    window.resize(1100, 740)  # wider than a column: the margins show
    window.show()
    for key in ("words", "help", "home"):  # each shown (polished) once
        window.go_to(key)
    QApplication.processEvents()
    return window


def _close(window: MainWindow) -> None:
    window.close()
    window.deleteLater()
    QApplication.processEvents()


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    found = _window(LIGHT)
    yield found
    _close(found)
    style.use(style.Theme())


def _address(each: QObject) -> int:
    """Which C++ object: Qt's own children (a scroll bar, a list's view) get
    a new Python wrapper each time they're found."""
    return int(shiboken6.getCppPointer(each)[0])


def _widgets(part: QWidget) -> set[int]:
    return {_address(part), *(_address(w) for w in part.findChildren(QWidget))}


def test_a_theme_change_restyles_only_whats_on_show(
    window: MainWindow, qapp: QApplication
) -> None:
    """The sidebar and Home now; Words and Help when next shown - a page
    not on show isn't restyled while it can't be seen."""
    changes = StyleChanges()
    qapp.installEventFilter(changes)
    try:
        window.set_theme(DARK)
        qapp.processEvents()
        assert _widgets(window.pages["home"]) <= changes.restyled
        assert _widgets(window.sidebar) <= changes.restyled
        for key in ("words", "help"):
            assert not _widgets(window.pages[key]) & changes.restyled, key
        window.go_to("words")
        qapp.processEvents()
        assert _widgets(window.pages["words"]) <= changes.restyled
        assert not _widgets(window.pages["help"]) & changes.restyled
    finally:
        qapp.removeEventFilter(changes)
    for part in [window.sidebar, *window.pages.values()]:
        if part is not window.pages["help"]:
            assert part.styleSheet() == window.sheet == style.stylesheet(DARK)


def test_a_page_shown_after_a_theme_change_looks_as_if_built_in_it(
    window: MainWindow, qapp: QApplication
) -> None:
    """Restyled late, every page looks as in a window built in the theme -
    the margins beside a column too (the window paints them)."""
    window.set_theme(DARK)
    built_dark = _window(DARK)
    try:
        for key in ("words", "help", "home"):
            window.go_to(key)
            built_dark.go_to(key)
            qapp.processEvents()
            assert window.grab().toImage() == built_dark.grab().toImage(), key
    finally:
        _close(built_dark)
        style.use(DARK)


def test_a_page_has_its_stylesheet_from_its_first_show_and_looks_the_same(
    qapp: QApplication,
) -> None:
    """At the start only the page on show has the stylesheet: each page
    with one of its own, polished when the window was first shown, cost
    the start about 30 ms (polyglotic-hq 357, decision 0149). Each other
    page gets it when first shown, and looks as it did with it from the
    start."""
    style.use(LIGHT)
    late = MainWindow(QAction("Quit"))
    early = MainWindow(QAction("Quit"))
    try:
        for window in (late, early):
            window.add_page("home", "Home", _page("home"))
            window.add_page("words", "Words", _page("words"), "top", 720)
            window.add_page("help", "Help", _page("help"), "foot", 720)
            window.resize(1100, 740)
        for page in early.pages.values():  # as every page had it before 357
            page.setStyleSheet(early.sheet)
        for window in (late, early):
            window.show()
        qapp.processEvents()
        assert late.pages["home"].styleSheet() == late.sheet
        assert late.pages["words"].styleSheet() == ""
        assert late.pages["help"].styleSheet() == ""
        for key in ("words", "help", "home"):
            late.go_to(key)
            early.go_to(key)
            qapp.processEvents()
            assert late.pages[key].styleSheet() == late.sheet
            assert late.grab().toImage() == early.grab().toImage(), key
    finally:
        _close(late)
        _close(early)
        style.use(style.Theme())


def test_pages_styled_ahead_one_a_turn_and_their_first_show_restyles_nothing(
    qapp: QApplication,
) -> None:
    """Decision 0158 (polyglotic-hq 367): `main` styles the pages not on show
    a second after the start, one page per turn of the event loop. Words'
    first show had taken 20 ms more restyling itself at 10,000 words met
    (decision 0149's cost). Then a first show restyles nothing, and looks as
    it did."""
    style.use(LIGHT)
    ahead = MainWindow(QAction("Quit"))
    late = MainWindow(QAction("Quit"))
    changes = StyleChanges()
    try:
        for window in (ahead, late):
            window.add_page("home", "Home", _page("home"))
            window.add_page("words", "Words", _page("words"), "top", 720)
            window.add_page("help", "Help", _page("help"), "foot", 720)
            window.resize(1100, 740)
            window.show()
        qapp.processEvents()
        ahead.style_ahead()  # one page now, the next on the next turn
        assert [
            ahead.pages[k].styleSheet() == ahead.sheet for k in ("words", "help")
        ] == [
            True,
            False,
        ]
        qapp.processEvents()
        assert ahead.pages["help"].styleSheet() == ahead.sheet
        qapp.installEventFilter(changes)
        for key in ("words", "help"):
            ahead.go_to(key)
            late.go_to(key)
            qapp.processEvents()
            assert not _widgets(ahead.pages[key]) & changes.restyled, key
            assert ahead.grab().toImage() == late.grab().toImage(), key
    finally:
        qapp.removeEventFilter(changes)
        _close(ahead)
        _close(late)
        style.use(style.Theme())


def test_the_margins_beside_a_column_are_the_themes_background(
    window: MainWindow, qapp: QApplication
) -> None:
    window.go_to("words")  # a column 720 px wide: margins either side
    for theme in (DARK, LIGHT):
        window.set_theme(theme)
        qapp.processEvents()
        image = window.grab().toImage()
        right = window.stack.geometry().right() - 2
        assert image.pixelColor(right, 300) == QColor(theme["BG"])


def test_a_question_over_the_window_is_in_its_theme(
    window: MainWindow, qapp: QApplication
) -> None:
    """A dialog the window opens (main's questions, the level picker) has
    its stylesheet, as when it was the window's - and a change of theme
    while it's open reaches it."""
    window.set_theme(DARK)
    box = QMessageBox(QMessageBox.Icon.Question, "Remove it?", "Words.", parent=window)
    seen: list[str] = []

    def look() -> None:
        seen.append(box.styleSheet())
        window.set_theme(LIGHT)
        seen.append(box.styleSheet())
        box.reject()

    QTimer.singleShot(0, look)
    box.exec()
    assert seen == [style.stylesheet(DARK), style.stylesheet(LIGHT)]
    box.deleteLater()


def _with_settings(theme: style.Theme) -> MainWindow:
    """A window with Home and the real Settings page, on Settings."""
    style.use(theme)
    window = MainWindow(QAction("Quit"))
    window.add_page("home", "Home", _page("home"))
    settings = SettingsPage(
        [("margin", "Margin"), ("glaze", "Glaze")],
        QAction("Tell us"),
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
    )
    window.add_page("settings", "Settings", settings, "foot")
    window.resize(1100, 740)
    window.show()
    window.go_to("settings")
    QApplication.processEvents()
    return window


def test_a_theme_change_on_settings_restyles_only_the_section_on_show(
    qapp: QApplication,
) -> None:
    """A stylesheet on Settings restyled its six sections, 481 widgets,
    with one on show: a theme change there took 50 ms against Home's 15
    (polyglotic-hq 355, 360; decision 0152). The section on show and the
    page's head now; each other section when shown - and it all looks as
    in a window built in the theme."""
    window = _with_settings(LIGHT)
    built_dark = _with_settings(DARK)
    changes = StyleChanges()
    try:
        settings = window.pages["settings"]
        assert isinstance(settings, SettingsPage)
        qapp.installEventFilter(changes)
        try:
            window.set_theme(DARK)
            qapp.processEvents()
            look, timing = settings.section["look"], settings.section["timing"]
            assert _widgets(look) <= changes.restyled
            assert _widgets(settings.sections) <= changes.restyled
            assert not _widgets(timing) & changes.restyled
            hidden = [b for k, b in settings.section.items() if k != "look"]
            assert not any(_widgets(box) & changes.restyled for box in hidden)
            settings.show_section("timing")
            qapp.processEvents()
            assert _widgets(timing) <= changes.restyled
        finally:
            qapp.removeEventFilter(changes)
        for key in ("timing", "app", "look"):
            dark = built_dark.pages["settings"]
            assert isinstance(dark, SettingsPage)
            settings.show_section(key)
            dark.show_section(key)
            qapp.processEvents()
            assert window.grab().toImage() == built_dark.grab().toImage(), key
    finally:
        _close(built_dark)
        _close(window)
        style.use(style.Theme())


def test_settings_dialog_and_column_follow_the_window(qapp: QApplication) -> None:
    """With no stylesheet on the page itself, its notices dialog still has
    the window's, and its column still grows with the text size."""
    window = _with_settings(LIGHT)
    try:
        settings = window.pages["settings"]
        assert isinstance(settings, SettingsPage)
        settings.set_notices("Some notices.")
        settings.show_section("app")
        seen: list[QColor] = []

        def look() -> None:
            shown = QApplication.activeModalWidget()
            assert shown is not None
            seen.append(shown.grab().toImage().pixelColor(2, 2))
            shown.close()

        QTimer.singleShot(0, look)
        settings.notices.click()
        assert seen == [QColor(LIGHT["BG"])]
        column = settings.content.parentWidget()
        assert column is not None
        before = column.maximumWidth()
        try:
            window.set_app_text_size("larger")
            qapp.processEvents()
            assert column.maximumWidth() > before
        finally:
            style.use_app_text_size("normal")
    finally:
        _close(window)
        style.use(style.Theme())


def test_settings_first_shown_is_laid_out_at_once(qapp: QApplication) -> None:
    """With no stylesheet on the page itself, nothing told its scroll area
    its content had grown: the first frame had Look squashed into the
    window's height, and nothing scrolled until a second pass (360)."""
    window = _with_settings(LIGHT)  # one pass of events after `go_to`
    try:
        settings = window.pages["settings"]
        assert isinstance(settings, SettingsPage)
        inner = settings.widget()
        assert inner is not None
        bar = settings.verticalScrollBar()
        first = (inner.height(), bar.maximum())
        assert first[1] > 0
        for _ in range(3):  # nothing left to lay out: as it'll stay
            qapp.processEvents()
        assert (inner.height(), bar.maximum()) == first
    finally:
        _close(window)
        style.use(style.Theme())
