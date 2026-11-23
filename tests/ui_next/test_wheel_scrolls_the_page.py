"""The mouse wheel scrolls the page and never changes a list, slider,
number box or key box it passes over - on every page of the main window
(Settings' sections and its Lab among them), a transcript's rail and a
caption window's settings popover; a slider takes the wheel only once
clicked into, and the keyboard works as it did (the user, 2026-11-13:
"scrolling settings will inadvertently change many settings as you
navigate the page"; polyglotic-hq 304, decision 0092)."""

import sys
from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFocusEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QScrollBar,
    QSlider,
    QWidget,
)
from tests.ui.fakes import Built
from tests.ui_next.made_up import OTHER_APP
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_transcript_window import DISCORD, Store, Views

from polyglotic_desktop.core.listening.sources import MIC, SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP
from polyglotic_desktop.ui_next import wheel
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.home import Page
from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.placement import Rect

A_LISTS_KEYS = (
    Qt.FocusPolicy.TabFocus if sys.platform == "darwin" else Qt.FocusPolicy.StrongFocus
)
"""How a list takes the keyboard once the rule has held it: by Tab and a
click; on a Mac by Tab alone (with macOS' keyboard navigation on), as its
own pop-up buttons do - Qt's own choice there, never the wheel's
(polyglotic-hq 420: in the first Mac run of the suite the arrow keys still
changed a list given the keyboard)."""


@pytest.fixture
def built(qapp: QApplication) -> Iterator[Built]:
    """The whole app's windows, a learner's (Words and Learning filled)."""
    app = Built(tools=True)
    app.hub.window.resize(1100, 760)
    app.hub.window.show()
    yield app
    app.close()


def turn(widget: QWidget, notches: int, at: QPoint | None = None) -> None:
    """The wheel turned `notches` (up: positive) at `at` in `widget` (its
    middle), reaching the widget there, as Windows' would."""
    where = at if at is not None else widget.rect().center()
    target = widget.childAt(where) or widget
    local = QPointF(target.mapFrom(widget, where))
    event = QWheelEvent(
        local,
        QPointF(target.mapToGlobal(local)),
        QPoint(0, 0),
        QPoint(0, 120 * notches),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(target, event)


def state(widget: QWidget) -> object:
    """What a learner would see change in `widget`, if anything can."""
    if isinstance(widget, QComboBox):
        return widget.currentIndex()
    if isinstance(widget, QAbstractSlider):
        return widget.value()
    if isinstance(widget, QAbstractSpinBox):
        return widget.text()
    if isinstance(widget, QAbstractButton):
        return (widget.isChecked(), widget.text(), getattr(widget, "key", None))
    if isinstance(widget, QAbstractItemView):
        model = widget.selectionModel()
        rows = sorted(i.row() for i in model.selectedIndexes()) if model else []
        return (widget.currentIndex().row(), rows)
    return None


def controls(root: QWidget) -> list[QWidget]:
    """Everything shown in `root` a learner changes: lists, sliders, number
    boxes, buttons (key boxes, switches, choices), lists of choices - not
    a page's own scroll bars."""
    kinds = (
        QComboBox,
        QAbstractSlider,
        QAbstractSpinBox,
        QAbstractButton,
        QAbstractItemView,
    )
    return [
        w
        for w in root.findChildren(QWidget)
        if w.isVisible() and isinstance(w, kinds) and not isinstance(w, QScrollBar)
    ]


def changed_by_the_wheel(root: QWidget, where: str) -> list[str]:
    """Each control in `root` that the wheel changed, turned a notch each
    way over it and looked at after each - none, if the rule holds. (Up
    then down puts a changed control back: each notch is looked at.)"""
    found = []
    shown = controls(root)
    assert shown, f"nothing to turn the wheel over on {where}"
    for control in shown:
        before = state(control)
        for notches in (1, -1, -1, 1):
            turn(control, notches)
            QApplication.processEvents()
            if state(control) != before:
                name = control.objectName() or control.accessibleName()
                found.append(f"{where}: {type(control).__name__} {name!r}")
                break
    return found


def never_wheel_focus(root: QWidget) -> list[str]:
    """Lists, sliders and number boxes the wheel would give the keyboard."""
    return [
        f"{type(w).__name__} {w.objectName()!r}"
        for w in root.findChildren(QWidget)
        if isinstance(w, wheel.HELD)
        and not isinstance(w, QScrollBar)
        and w.focusPolicy() == Qt.FocusPolicy.WheelFocus
    ]


def test_the_wheel_changes_nothing_on_any_page(
    built: Built, qapp: QApplication
) -> None:
    window = built.hub.window
    changed: list[str] = []
    for key in window.pages:
        window.go_to(key)
        page = window.pages[key]
        if isinstance(page, SettingsPage):
            for section in SECTIONS:
                page.show_section(section)
                qapp.processEvents()
                changed += changed_by_the_wheel(page, f"settings.{section}")
        else:
            qapp.processEvents()
            changed += changed_by_the_wheel(page, key)
    assert changed == []
    assert never_wheel_focus(window) == []


def test_the_wheel_changes_nothing_on_a_transcripts_rail(qapp: QApplication) -> None:
    store = Store()
    areas = [Rect(0, 0, 1920, 1040)]
    windows = CaptionWindows(store, MIC, lambda: areas)
    windows.set_labels({APP: DISCORD, OTHER_APP: SourceLabel("Zoom", "#a5d66f")}, "")
    transcripts = Transcripts(windows, store, areas=lambda: areas)
    transcripts.panels = Views()
    windows.set_captioned([("Discord.exe", APP)])
    try:
        transcripts.show("Discord.exe")
        shown = transcripts.shown["Discord.exe"]
        shown.animate = False
        shown.resize(1000, 700)
        shown.toggle_rail()
        qapp.processEvents()
        assert changed_by_the_wheel(shown.rail, "the rail") == []
        assert never_wheel_focus(shown.rail) == []
    finally:
        transcripts.close()
        windows.close()


def test_the_wheel_changes_nothing_in_a_caption_windows_popover(
    qapp: QApplication,
) -> None:
    window = window_of(qapp)
    try:
        window.hovered = True
        window._show_band(True)
        window.buttons["settings"].click()
        popover = window.popover
        assert popover is not None and popover.isVisible()
        assert changed_by_the_wheel(popover, "the popover") == []
        window.close_settings()
        # each list of choices open in the language chip popover: it scrolls,
        # and what's chosen stays (655: the bar chip is the one place)
        window.toggle_languages()
        lang_popover = window.languages
        assert lang_popover is not None and lang_popover.isVisible()
        for chip in ("spoken", "language"):
            getattr(lang_popover, chip).click()
            qapp.processEvents()
            assert changed_by_the_wheel(lang_popover, f"the popover, {chip} open") == []
            getattr(lang_popover, chip).click()
    finally:
        window.close()


def test_the_wheel_over_a_list_scrolls_settings(
    built: Built, qapp: QApplication
) -> None:
    built.hub.window.go_to("settings")
    page = built.hub.settings
    page.show_section("look")  # long enough to scroll on any grouping (304, 470)
    qapp.processEvents()
    box = page.faces.boxes["en"]  # the Font row, in Look's Fonts card (482)
    bar = page.verticalScrollBar()
    page.ensureWidgetVisible(box, 0, 40)  # Reset below it: room to scroll on
    qapp.processEvents()
    index, top = box.currentIndex(), bar.value()
    assert top < bar.maximum()  # room to scroll down
    turn(box, -1)  # down
    assert box.currentIndex() == index
    assert bar.value() > top  # the page went down instead
    assert not box.hasFocus()


def test_a_slider_takes_the_wheel_once_clicked_until_the_pointer_leaves(
    built: Built, qapp: QApplication
) -> None:
    built.hub.window.go_to("settings")
    page = built.hub.settings
    page.show_section("captions")
    qapp.processEvents()
    slider = page.look.background
    page.ensureWidgetVisible(slider, 0, 200)
    qapp.processEvents()
    slider.setValue((slider.minimum() + slider.maximum()) // 2)
    bar = page.verticalScrollBar()

    before = slider.value()
    turn(slider, 1)
    assert slider.value() == before  # passed over: unchanged

    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=slider.rect().center())
    clicked, top = slider.value(), bar.value()
    turn(slider, 1)
    assert slider.value() != clicked  # clicked into: it takes the wheel
    assert bar.value() == top  # and the page stays

    QApplication.sendEvent(slider, QEvent(QEvent.Type.Leave))  # the pointer moved off
    moved, top = slider.value(), bar.value()
    turn(slider, 1)  # back over it: let go, the page scrolls
    assert slider.value() == moved
    assert bar.value() < top

    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=slider.rect().center())
    moved = slider.value()
    # the keyboard moved on (Tab), as Qt says it
    QApplication.sendEvent(
        slider, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.TabFocusReason)
    )
    turn(slider, 1)
    assert slider.value() == moved


@pytest.fixture
def plain(qapp: QApplication) -> Iterator[Page]:
    """A page of the main window's kind, taller than its window: two
    sliders and a spacer under them, so it scrolls."""
    page = Page("A page")
    for name in ("one", "two"):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName(name)
        slider.setRange(0, 100)
        slider.setValue(50)
        page.content.addWidget(slider)
    spacer = QWidget()
    spacer.setFixedHeight(2000)
    page.content.addWidget(spacer)
    page.resize(500, 400)
    page.show()
    qapp.processEvents()
    yield page
    page.close()
    shiboken6.delete(page)


def test_a_click_on_another_slider_takes_the_wheel_from_the_first(
    plain: Page,
) -> None:
    one, two = (plain.findChild(QSlider, name) for name in ("one", "two"))
    assert one is not None and two is not None
    QTest.mouseClick(one, Qt.MouseButton.LeftButton, pos=one.rect().center())
    QTest.mouseClick(two, Qt.MouseButton.LeftButton, pos=two.rect().center())
    before = one.value(), two.value()
    turn(one, 1)
    assert one.value() == before[0]  # let go
    turn(two, 1)
    assert two.value() != before[1]  # clicked last: it has the wheel


def test_a_list_added_after_the_page_shows_is_held_too(
    plain: Page, qapp: QApplication
) -> None:
    """Rows come and go with what's chosen (Speech's second languages):
    one added to a page already shown is found as its layout changes."""
    box = QComboBox()
    box.addItems(["one", "two", "three"])
    box.setCurrentIndex(1)
    plain.content.insertWidget(1, box)
    for _ in range(3):  # the layout's change climbs a widget a round
        qapp.processEvents()
    bar = plain.verticalScrollBar()
    top = bar.value()
    turn(box, -1)
    assert box.currentIndex() == 1
    assert bar.value() > top
    assert box.focusPolicy() == A_LISTS_KEYS


def test_the_wheel_over_the_pinned_sections_scrolls_settings(
    built: Built, qapp: QApplication
) -> None:
    """The title and sections stay put above what scrolls (polyglotic-hq
    470): the wheel over them still scrolls the page, and never changes the
    section - not even where they're a dropdown."""
    built.hub.window.go_to("settings")
    page = built.hub.settings
    page.show_section("look")
    qapp.processEvents()
    bar = page.verticalScrollBar()
    top = bar.value()
    assert top < bar.maximum()
    # at the head itself: Qt passes a real wheel up from its title or a tab,
    # a test's (not spontaneous) it doesn't
    turn(page.head, -1, at=QPoint(page.head.width() - 1, page.head.height() - 1))
    assert bar.value() > top
    assert page.sections.value() == "look"
    page.section_picker.setHidden(False)  # as in a narrow window
    qapp.processEvents()
    index, top = page.section_picker.currentIndex(), bar.value()
    turn(page.section_picker, -1)
    assert page.section_picker.currentIndex() == index
    assert bar.value() > top and page.sections.value() == "look"


def test_the_keyboard_still_changes_a_list(built: Built, qapp: QApplication) -> None:
    built.hub.window.go_to("settings")
    page = built.hub.settings
    qapp.processEvents()
    box = page.dictation_language
    box.setCurrentIndex(0)
    QTest.keyClick(box, Qt.Key.Key_Down)
    assert box.currentIndex() == 1
    # Tab and a click (a Mac: Tab) give it the keyboard; never the wheel
    assert box.focusPolicy() == A_LISTS_KEYS


def test_without_the_rule_the_wheel_would_change_a_list(qapp: QApplication) -> None:
    """The walk catches a control the rule misses: Qt's own lists change
    with the wheel."""
    box = QComboBox()
    box.addItems(["one", "two", "three"])
    box.setCurrentIndex(1)
    box.resize(120, 30)
    box.show()
    try:
        turn(box, -1)
        assert box.currentIndex() != 1
    finally:
        box.close()
        shiboken6.delete(box)
