"""A setting changed on Learning, or a category renamed on Words, leaves the
page where it was: scrolled as it was, and the keyboard on the same control
(polyglotic-hq 480; the user, 2026-11-18: "pressing each setting resets the
page view to the center of the screen, really unusable").

Each change makes the language's card (or the category rows) again, and the
control that had the keyboard went with its old card. Qt hands the keyboard
of a widget that hides to the next control along, and a scroll area scrolls
that one into view - one card after another as each old one hid, so the
page ran down to about its middle. Offscreen, the window active, as the
learner's is when they click."""

from collections.abc import Callable, Iterator

import pytest
import shiboken6
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import LinkChoice
from polyglotic_desktop.ui_next.controls import Segmented
from polyglotic_desktop.ui_next.home import Page
from polyglotic_desktop.ui_next.learning_page import LanguageCardView, LearningPage
from polyglotic_desktop.ui_next.views.learning import (
    WINDOW_CHOICES,
    Custom,
    InstalledPackLine,
    cards,
)


def settle(qapp: QApplication) -> None:
    for _ in range(8):
        qapp.processEvents()


def shown(qapp: QApplication, built: Built, page: str) -> None:
    window = built.hub.window
    window.resize(1000, 700)
    window.go_to(page)
    window.show()
    window.activateWindow()
    settle(qapp)


def scrolled_to(qapp: QApplication, page: Page, control: QWidget) -> int:
    """`page` scrolled down to `control`, just inside the top of the view -
    or as far as it goes, for one at the bottom of the page; the scroll
    position, never the top of the page."""
    inner = page.widget()
    assert inner is not None
    top = control.mapTo(inner, QPoint(0, 0)).y()
    bar = page.verticalScrollBar()
    bar.setValue(min(top - 40, bar.maximum()))
    settle(qapp)
    assert bar.value() > 0
    return bar.value()


def choice_named(control: Segmented, value: object) -> QWidget:
    """`control`'s button for `value`."""
    return control.buttons[control._values.index(value)]


# -- Learning ---------------------------------------------------------------------------


@pytest.fixture
def learning(qapp: QApplication) -> Iterator[Built]:
    """A long Learning page: five languages, the one in use with its level
    in words (its learning window, Mark known, where links start)."""
    built = Built(
        MemorySettingsStore(
            {"learning": "zh", "also_learning": ["vi", "ja", "en", "ru"]}
        ),
        tools=True,
    )
    tools = built.desktop.tools
    assert tools is not None
    tools.vocabulary.set_known_words(1000)
    shown(qapp, built, "learning")
    yield built
    built.close()


def card(built: Built, code: str) -> LanguageCardView:
    found = built.hub.learning.card(code)
    assert found is not None
    return found


def window_choice(built: Built, size: object) -> QWidget:
    segmented = card(built, "zh").window_size
    assert segmented is not None
    return choice_named(segmented, size)


def clicked(qapp: QApplication, control: Callable[[], QWidget]) -> None:
    QTest.mouseClick(control(), Qt.MouseButton.LeftButton)
    settle(qapp)


def test_the_page_was_long_enough_to_scroll(learning: Built) -> None:
    bar = learning.hub.learning.verticalScrollBar()
    assert bar.maximum() > 2 * learning.hub.learning.viewport().height()
    assert [c.code for c in learning.hub.learning.cards] == [
        "zh",
        "vi",
        "ja",
        "en",
        "ru",
    ]


def mark_known(built: Built) -> QWidget:
    button = card(built, "zh").mark_known
    assert button is not None and button.isEnabled()
    return button


CLICKED: list[tuple[str, Callable[[Built], QWidget]]] = [
    ("window size", lambda built: window_choice(built, WINDOW_CHOICES[1])),
    (
        "links on the first card",
        lambda built: choice_named(card(built, "zh").links, LinkChoice.PAST_KNOWN),
    ),
    (
        "links on the last card",
        lambda built: choice_named(card(built, "ru").links, LinkChoice.OFF),
    ),
    ("Mark known", mark_known),
    (
        "word introductions",
        lambda built: choice_named(
            built.hub.learning.introductions, WordIntroductions.EVERY
        ),
    ),
]
"""Each control clicked: found again after, on its card made again."""


@pytest.mark.parametrize(
    "control", [c for _, c in CLICKED], ids=[w for w, _ in CLICKED]
)
def test_a_click_on_learning_leaves_the_page_and_the_keyboard_where_they_were(
    qapp: QApplication, learning: Built, control: Callable[[Built], QWidget]
) -> None:
    page = learning.hub.learning
    before = list(page.cards)
    at = scrolled_to(qapp, page, control(learning))
    clicked(qapp, lambda: control(learning))
    assert page.verticalScrollBar().value() == at
    assert QApplication.focusWidget() is control(learning)
    if control is not CLICKED[-1][1]:  # word introductions are no card's
        assert page.cards != before  # made again: what the bug needed


def test_where_links_start_chosen_from_its_list_leaves_the_page_where_it_was(
    qapp: QApplication, learning: Built
) -> None:
    page = learning.hub.learning
    clicked(
        qapp, lambda: choice_named(card(learning, "zh").links, LinkChoice.PAST_KNOWN)
    )
    combo = card(learning, "zh").links_from
    assert combo is not None
    at = scrolled_to(qapp, page, combo)
    combo.setFocus()
    settle(qapp)
    index = combo.findData(3000)
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    settle(qapp)
    assert page.verticalScrollBar().value() == at
    again = card(learning, "zh").links_from
    assert again is not combo and again is not None  # made again
    assert QApplication.focusWidget() is again
    assert again.currentData() == 3000


def test_a_window_size_typed_leaves_the_page_where_it_was(
    qapp: QApplication, learning: Built
) -> None:
    page = learning.hub.learning
    clicked(qapp, lambda: window_choice(learning, Custom.CUSTOM))
    typed = card(learning, "zh").window_custom
    assert typed is not None and typed.hasFocus()
    at = scrolled_to(qapp, page, typed)
    typed.selectAll()
    QTest.keyClicks(typed, "3000")
    QTest.keyClick(typed, Qt.Key.Key_Return)
    settle(qapp)
    assert page.verticalScrollBar().value() == at
    again = card(learning, "zh").window_custom
    assert again is not typed and again is not None  # made again
    assert QApplication.focusWidget() is again
    assert again.text() == "3,000"


# -- Words ---------------------------------------------------------------------------------


@pytest.fixture
def words(qapp: QApplication) -> Iterator[Built]:
    """Words with a long list of categories: the next control after them
    (New category) well below the view."""
    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    tools = built.desktop.tools
    assert tools is not None
    for n in range(30):
        tools.vocabulary.add_category(f"Category {n}")
    shown(qapp, built, "words")
    yield built
    built.close()


def name_field(built: Built, n: int) -> QLineEdit:
    fields = [
        f
        for f in built.hub.window.findChildren(QLineEdit)
        if f.objectName().startswith("category.name.")
        and f.isVisibleTo(built.hub.window)
    ]
    return fields[n]


def test_a_category_renamed_leaves_the_page_and_the_keyboard_where_they_were(
    qapp: QApplication, words: Built
) -> None:
    page = words.hub.words
    assert page is not None
    field = name_field(words, 2)
    name = field.objectName()
    at = scrolled_to(qapp, page, field)
    QTest.mouseClick(field, Qt.MouseButton.LeftButton)
    field.selectAll()
    QTest.keyClicks(field, "Verbs")
    QTest.keyClick(field, Qt.Key.Key_Return)
    settle(qapp)
    assert page.verticalScrollBar().value() == at
    focused = QApplication.focusWidget()
    assert focused is not field and isinstance(focused, QLineEdit)  # made again
    assert focused.objectName() == name and focused.text() == "Verbs"


# -- the page stays put whatever it is given -------------------------------------------------


def test_learning_made_again_from_outside_leaves_the_keyboard_where_it_was(
    qapp: QApplication, learning: Built
) -> None:
    """Not only a click: anything that makes the cards again (a level set
    on Words, a dictionary arriving) while the keyboard is on one."""
    page: LearningPage = learning.hub.learning
    links = choice_named(card(learning, "ru").links, LinkChoice.EVERY)
    at = scrolled_to(qapp, page, links)
    links.setFocus()
    settle(qapp)
    tools = learning.desktop.tools
    assert tools is not None
    tools.vocabulary.set_known_words(2000)  # the first card made again
    settle(qapp)
    assert page.verticalScrollBar().value() == at
    assert QApplication.focusWidget() is choice_named(
        card(learning, "ru").links, LinkChoice.EVERY
    )


def test_cards_made_again_behind_another_window_keep_its_keyboard_for_its_return(
    qapp: QApplication, learning: Built
) -> None:
    """The window not active - a dialog over it (Change your level's), the
    learner in a game while a dictionary arrives: back in it, the keyboard
    is on the same control, not the window's first."""
    page = learning.hub.learning
    links = choice_named(card(learning, "ru").links, LinkChoice.EVERY)
    at = scrolled_to(qapp, page, links)
    links.setFocus()
    settle(qapp)
    elsewhere = QWidget()
    try:
        elsewhere.show()
        elsewhere.activateWindow()
        settle(qapp)
        assert not learning.hub.window.isActiveWindow()
        tools = learning.desktop.tools
        assert tools is not None
        tools.vocabulary.set_known_words(2000)  # the cards made again
        settle(qapp)
        learning.hub.window.activateWindow()
        settle(qapp)
        assert QApplication.focusWidget() is choice_named(
            card(learning, "ru").links, LinkChoice.EVERY
        )
        assert page.verticalScrollBar().value() == at
    finally:
        elsewhere.close()
        shiboken6.delete(elsewhere)  # now, not at the interpreter's exit


def test_a_dictionary_removed_leaves_learning_where_it_was(qapp: QApplication) -> None:
    """Dictionaries on this PC are made again when one is removed: its
    Remove's keyboard was handed on down the rows, and the page scrolled
    after it (729 to 803 here). Now it's handed to nothing - not on to
    Delete learning data either - and the page stays."""
    delete = QAction("Delete learning data…")
    delete.setObjectName("delete")  # as Account's: its button learning.delete
    page = LearningPage(delete)
    try:
        languages = LearningLanguages("zh")
        page.show_learning(
            languages,
            cards(languages, ("zh",), lambda _: None),
            WordIntroductions.A_FEW,
        )
        here = [
            InstalledPackLine(c, "1", 20_000_000)
            for c in ("vi", "ru", "es", "fr", "de", "it", "pt", "ko", "th", "id")
        ]
        page.show_installed(here)
        page.resize(800, 500)
        page.show()
        page.activateWindow()
        settle(qapp)
        remove = page.findChild(QPushButton, "learning.ru.pack_remove")
        assert remove is not None
        inner = page.widget()
        assert inner is not None
        bar = page.verticalScrollBar()
        bar.setValue(remove.mapTo(inner, QPoint(0, 0)).y() - 300)  # low in the view
        settle(qapp)
        at = bar.value()
        assert 0 < at < bar.maximum() - 100  # room for the page to get shorter
        remove.setFocus()
        settle(qapp)
        page.show_installed([p for p in here if p.code != "ru"])
        settle(qapp)
        removes = page.findChildren(QPushButton, "learning.ru.pack_remove")
        assert not [b for b in removes if b.isVisibleTo(page)]  # its row gone
        assert page.verticalScrollBar().value() == at
        delete_button = page.findChild(QPushButton, "learning.delete")
        assert delete_button is not None
        assert QApplication.focusWidget() is not delete_button
    finally:
        page.close()
        shiboken6.delete(page)
