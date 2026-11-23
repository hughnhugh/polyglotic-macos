"""Any text a learner reads in the main window can be copied (polyglotic-hq
343): selected with the mouse, then Ctrl+C or the right-click menu's Copy
and Select All - made so in one place (`controls.label`), never a Tab stop,
and never where a click on the whole row is what the row is for. Real
pages, offscreen."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QAction,
    QContextMenuEvent,
    QEnterEvent,
    QGuiApplication,
    QKeyEvent,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import tools_for
from tests.ui_next.test_account_settings_help import facts_with, settings_page
from tests.ui_next.test_home import home

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.ui_next import controls, copying
from polyglotic_desktop.ui_next.account_page import AccountPage
from polyglotic_desktop.ui_next.help_page import HelpPage
from polyglotic_desktop.ui_next.home import AddRow
from polyglotic_desktop.ui_next.learning_page import LearningPage
from polyglotic_desktop.ui_next.settings_page import SECTIONS
from polyglotic_desktop.ui_next.transcripts import question
from polyglotic_desktop.ui_next.views.home import AddableApp, Picker
from polyglotic_desktop.ui_next.words_page import WordsPage

UNTOUCHED = "what was on the clipboard before"
SELECTABLE = Qt.TextInteractionFlag.TextSelectableByMouse


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before and shiboken6.isValid(widget):
            widget.close()
            shiboken6.delete(widget)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settle() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def worded(page: QWidget) -> list[QLabel]:
    """The page's labels that hold words (not a picture)."""
    return [w for w in page.findChildren(QLabel) if w.text()]


def in_add_row(found: QLabel) -> bool:
    parent = found.parentWidget()
    while parent is not None:
        if isinstance(parent, AddRow):
            return True
        parent = parent.parentWidget()
    return False


def pages() -> list[QWidget]:
    settings = settings_page()
    # every section shown once: a caption section's cards are made when it
    # first is (polyglotic-hq 544)
    for section in (*SECTIONS, "captions", "learning", "app"):
        settings.show_section(section)
    homepage, _commands = home(
        Picker(available=(AddableApp("Spotify", "Spotify", True),))
    )
    return [
        AccountPage(),
        HelpPage(lambda: facts_with(True)),
        LearningPage(),
        settings,
        homepage,
        WordsPage(tools_for(ChineseDictionary(chinese_sample()), "hsk-2025"), None),
    ]


# -- one place: every page's words ------------------------------------------------------


def test_every_page_s_words_can_be_selected_but_are_never_a_tab_stop(
    qapp: QApplication,
) -> None:
    made = pages()
    for page in made:
        labels = worded(page)
        assert labels, page
        for found in labels:
            if in_add_row(found):  # the whole row is the click: not its words
                assert not isinstance(found, copying.Text)
                continue
            assert isinstance(found, copying.Text), found.text()
            hover(found)  # selectable from when the mouse comes to it
            assert found.textInteractionFlags() & SELECTABLE, found.text()
            assert not found.focusPolicy() & Qt.FocusPolicy.TabFocus, found.text()
    for page in made:
        page.deleteLater()
    settle()


def test_the_word_class_legend_copies_plain_text(qapp: QApplication) -> None:
    page = settings_page()
    page.show_section("links")
    legend = page.findChild(QLabel, "word_class_legend.labels")
    assert isinstance(legend, copying.Text)
    assert "<span" in legend.text()

    copying.copy_label(legend)
    copied = QGuiApplication.clipboard().text()
    assert [row.lstrip(" \u25cf\xa0") for row in copied.splitlines()] == [
        "Noun",
        "Verb",
        "Adjective",
        "Adverb",
        "Pronoun or determiner",
        "Particle, connector or interjection",
        "Number",
        "Class unavailable",
    ]


def hover(found: QLabel) -> None:
    """The mouse comes to `found`."""
    at = QPointF(2, 2)
    QApplication.sendEvent(found, QEnterEvent(at, at, found.mapToGlobal(at)))


def test_not_selectable_till_the_mouse_comes_to_it(qapp: QApplication) -> None:
    """A selectable label lays its words out as a document: about 0.2 ms
    each, over 250 labels at the start - so only once it's wanted."""
    found = controls.label("Polyglotic")
    assert not found.textInteractionFlags() & SELECTABLE
    hover(found)
    assert found.textInteractionFlags() & SELECTABLE
    assert found.focusPolicy() == Qt.FocusPolicy.ClickFocus
    found.deleteLater()


def test_a_link_in_a_label_still_opens(qapp: QApplication) -> None:
    found = controls.label("Open <a href='learning'>Learning</a>")
    hover(found)
    assert found.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByMouse
    assert found.textInteractionFlags() & SELECTABLE
    found.deleteLater()


def test_quit_s_question_can_be_copied_too(qapp: QApplication) -> None:
    box = question("Video Player", 12)
    assert box.textInteractionFlags() & SELECTABLE
    box.deleteLater()


# -- copying, in a real window ----------------------------------------------------------


@pytest.fixture
def shown(qapp: QApplication) -> Iterator[tuple[QWidget, QLabel, QPushButton]]:
    window = QWidget()
    found = controls.label("Polyglotic 0.1.5 - the dictionary is up to date", wrap=True)
    found.setParent(window)
    found.setGeometry(10, 10, 360, 40)
    button = QPushButton("Check again", window)
    button.setGeometry(10, 60, 160, 30)
    window.resize(400, 110)
    window.show()
    QTest.qWaitForWindowExposed(window)
    yield window, found, button
    window.close()
    window.deleteLater()
    settle()


def press_copy(target: QWidget) -> None:
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, "\x03"
    )
    QApplication.sendEvent(target, event)


def test_a_drag_selects_and_ctrl_c_copies_what_s_selected(
    shown: tuple[QWidget, QLabel, QPushButton],
) -> None:
    _window, found, _button = shown
    start = QPoint(2, found.height() // 2)
    end = QPoint(found.fontMetrics().horizontalAdvance("Polyglotic") + 2, start.y())
    hover(found)
    QTest.mousePress(found, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(found, end)
    QTest.mouseRelease(found, Qt.MouseButton.LeftButton, pos=end)
    assert found.selectedText().startswith("Polyglotic")
    assert found.hasFocus()  # the click gave it the keyboard: Ctrl+C is its
    press_copy(found)
    assert QGuiApplication.clipboard().text() == found.selectedText()


def named(action: QAction) -> str:
    return action.text().replace("&", "")


def right_click(found: QLabel) -> QMenu:
    """The menu a right-click on `found` opens (shown: popped up)."""
    at = QPoint(5, 5)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, at, found.mapToGlobal(at))
    QApplication.sendEvent(found, event)
    menus = [m for m in found.findChildren(QMenu) if m.isVisible()]
    assert len(menus) == 1
    return menus[0]


def test_the_right_click_menu_copies_what_s_selected(
    shown: tuple[QWidget, QLabel, QPushButton],
) -> None:
    _window, found, _button = shown
    hover(found)
    found.setSelection(0, len("Polyglotic"))
    menu = right_click(found)
    assert [named(a) for a in menu.actions()] == ["Copy", "Select all"]
    menu.actions()[0].trigger()
    assert QGuiApplication.clipboard().text() == "Polyglotic"
    menu.close()


def test_with_nothing_selected_copy_copies_all_of_it_and_select_all_selects_it(
    shown: tuple[QWidget, QLabel, QPushButton],
) -> None:
    _window, found, _button = shown
    menu = right_click(found)
    menu.actions()[0].trigger()
    assert QGuiApplication.clipboard().text() == found.text()
    menu.close()
    menu = right_click(found)
    menu.actions()[1].trigger()
    assert found.selectedText() == found.text()
    menu.close()


def test_a_link_s_words_are_copied_not_its_markup(qapp: QApplication) -> None:
    found = controls.label("Open <a href='learning'>Learning</a> to add it")
    copying.copy_label(found)
    assert QGuiApplication.clipboard().text() == "Open Learning to add it"
    found.deleteLater()


def test_the_menu_is_in_the_interface_language(qapp: QApplication) -> None:
    """Qt's own menu has no words in Vietnamese, Thai or Hindi: ours is
    translated with the rest (each language's file has these drafted)."""
    found = controls.label("Polyglotic")
    menu = copying.menu_for(found)
    assert [named(a) for a in menu.actions()] == ["Copy", "Select all"]
    found.deleteLater()


def test_a_button_beside_it_still_clicks(
    shown: tuple[QWidget, QLabel, QPushButton],
) -> None:
    _window, _found, button = shown
    clicked: list[bool] = []
    button.clicked.connect(lambda: clicked.append(True))
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert clicked == [True]


def test_tab_goes_from_button_to_button_past_the_words(qapp: QApplication) -> None:
    window = QWidget()
    first = QPushButton("First", window)
    found = controls.label("Words between")
    found.setParent(window)
    second = QPushButton("Second", window)
    for y, each in enumerate((first, found, second)):
        each.setGeometry(10, 10 + 40 * y, 160, 30)
    window.show()
    QTest.qWaitForWindowExposed(window)
    window.activateWindow()
    first.setFocus()
    window.focusNextChild()
    assert QApplication.focusWidget() is not found
    window.close()
    window.deleteLater()
    settle()


def test_a_click_on_a_row_to_add_still_captions_its_app(qapp: QApplication) -> None:
    page, commands = home(Picker(available=(AddableApp("Spotify", "Spotify", True),)))
    page.resize(800, 700)
    page.show()
    QTest.qWaitForWindowExposed(page)
    row = page.picker_card.add_rows["Spotify"]
    QTest.mouseClick(row.title, Qt.MouseButton.LeftButton)
    assert commands.asked == [("add", ("Spotify",))]
    page.close()
    page.deleteLater()
    settle()


def test_a_label_made_not_copyable_is_as_qt_makes_it(qapp: QApplication) -> None:
    found = controls.label("Spotify", copyable=False)
    assert not found.textInteractionFlags() & SELECTABLE
    assert found.focusPolicy() == Qt.FocusPolicy.NoFocus
    found.deleteLater()


def test_a_link_in_a_label_is_in_the_themes_text_colour(qapp: QApplication) -> None:
    """Qt's own link blue is about 2:1 on the dark theme's cards: the
    links on Settings > Look ("Learning"), the Lab and Learning's load card
    couldn't be read (polyglotic-hq 377). Judged from the label's own
    picture: a palette's link colour isn't drawn under a stylesheet."""
    from polyglotic_desktop.ui_next import style

    def blue(found: QLabel) -> int:
        image = found.grab().toImage()
        return sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if (c := image.pixelColor(x, y)).blue() > 200 and c.red() < 80
        )

    before = style.current()
    try:
        style.use(style.Theme())
        found = controls.label("Which words are new is on <a href='x'>Learning</a>.")
        found.setStyleSheet("QLabel { color: #8c95a5; background: #181d27; }")
        found.resize(found.sizeHint())
        assert style.current()["TEXT"] in found.text()
        assert blue(found) == 0
        assert copying.words(found) == "Which words are new is on Learning."
        light = style.Theme({**style.current().tokens, "TEXT": "#101418"})
        style.use(light)  # a theme change styles the window again
        found.setStyleSheet("QLabel { color: #444444; background: #ffffff; }")
        assert "#101418" in found.text()
        assert found.text().count("style=") == 1
        plain = controls.label("No link here")
        assert plain.text() == "No link here"
        found.deleteLater()
        plain.deleteLater()
    finally:
        style.use(before)
