"""The caption window's strip buttons say what they do on hover
(polyglotic-hq 395: "hovering caption nav bar icons should say what they
do"). The window is never active, so Qt never showed their tooltips: the
strip has a hover label of its own (`strip_tips`)."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import STRIP, CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.os_words import hotkeys_here as keys
from polyglotic_desktop.ui_next.strip_tips import (
    OVER_CAPTIONS_MS,
    REST_MS,
    SHOWN_MS,
    tip_place,
)
from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.word_classes import legend_html

AREA = Rect(0, 0, 1920, 1040)
SCREEN = QRect(0, 0, 1920, 1040)


def areas() -> list[Rect]:
    return [AREA]


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = CaptionWindow(
        "Discord.exe", APP, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
        mic=MIC, areas=areas,
    )  # fmt: skip
    for update in finished_updates(10):
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    shown.show()
    shown.set_reporting(True)  # every button there is
    shown.hovered = True
    shown._show_band(True)
    qapp.processEvents()
    yield shown
    shown.close()
    shown.deleteLater()


def enter(widget: QWidget, x: float = 4) -> None:
    point = QPointF(x, 4)
    QApplication.sendEvent(widget, QEnterEvent(point, point, point))


def leave(widget: QWidget) -> None:
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))


def labels_shown() -> list[str]:
    """The words of every hover label on the screen: a top-level label,
    which Qt's own tooltips aren't (they're shown only on active windows)."""
    return [
        w.text()
        for w in QApplication.topLevelWidgets()
        if isinstance(w, QLabel) and w.isVisible() and w.objectName() == "strip_tip"
    ]


def rest(window: CaptionWindow) -> None:
    """The mouse rests REST_MS on what it entered."""
    assert window.tips._rest.interval() == REST_MS
    window.tips._rest.timeout.emit()


def test_every_strip_button_says_what_it_does_on_hover(window: CaptionWindow) -> None:
    """The user's preview-1 feedback (2026-11-16): hovering an icon said
    nothing. Each button's own tooltip, the same words as before - each
    one shown (Fill the width isn't on the strip: polyglotic-hq 555, 556).
    Class colouring on, so the links button's tip carries its legend (799)."""
    window.set_look(replace(window.look, colour_links_by_word_class=True))
    said = {}
    for name in STRIP:
        button = window.buttons[name]
        enter(button)
        assert labels_shown() == []  # not at once: only on resting
        rest(window)
        said[name] = labels_shown()
        leave(button)
        assert labels_shown() == []
    expected = {name: [window.controls[name].toolTip()] for name in STRIP}
    expected["links"] = [legend_html(window.look, window.controls["links"].toolTip())]
    assert said == expected
    assert "Noun" in said["links"][0] and "Class unavailable" in said["links"][0]
    assert said["stop"] == ["Stop captioning Discord"]
    assert said["lock"] == [
        keys("Lock - clicks pass through to what's underneath, Ctrl+Alt+L")
    ]


def test_moving_to_the_next_button_says_it_at_once_and_a_press_hides_it(
    window: CaptionWindow,
) -> None:
    enter(window.buttons["lock"])
    rest(window)
    leave(window.buttons["lock"])
    enter(window.buttons["stop"])
    assert labels_shown() == []  # the last one went as the mouse left
    rest(window)
    assert labels_shown() == [window.controls["stop"].toolTip()]
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(4, 4), QPointF(4, 4),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    QApplication.sendEvent(window.buttons["stop"], press)
    assert labels_shown() == []
    leave(window.buttons["stop"])


def test_each_chip_icon_says_its_full_value_and_opens_its_dropdown(
    window: CaptionWindow,
) -> None:
    window.set_timing(CaptionMode.INSTANT)
    window.resize(window._minimum().width, window.height())
    for chip, name, popup in (
        (window.chip, "Languages: Detect → English", "languages"),
        (window.preset_chip, "Preset: Everyday", "presets"),
        (window.timing_chip, "Timing: Instant", "timings"),
    ):
        assert chip.isVisible() and not chip.icon().isNull() and chip.text() == ""
        enter(chip)
        rest(window)
        assert labels_shown() == [name]
        leave(chip)
        chip.click()
        assert getattr(window, popup).isVisible()
        window.close_settings()


def test_from_one_button_to_the_next_while_one_shows(window: CaptionWindow) -> None:
    """Like Qt's tooltips: once one shows, the next is said without the wait."""
    enter(window.buttons["lock"])
    rest(window)
    enter(window.buttons["settings"])  # its enter before the last one's leave
    assert labels_shown() == [window.controls["settings"].toolTip()]
    leave(window.buttons["settings"])


def test_a_changed_tip_is_the_one_said(window: CaptionWindow) -> None:
    """A button's tip as it is when it's said, changed since it was made
    (Word links with what was said hidden said why they were off, until
    their strip button went into the presets' dropdown: polyglotic-hq 556)."""
    window.controls["stop"].setToolTip("Stop captioning it, said afresh")
    enter(window.buttons["stop"])
    rest(window)
    assert labels_shown() == ["Stop captioning it, said afresh"]
    leave(window.buttons["stop"])


def test_the_mic_button_says_whether_own_speech_is_on_or_off(
    window: CaptionWindow,
) -> None:
    mic = window.mic_button
    enter(mic)
    rest(window)
    assert labels_shown() == ["Caption what I say: off"]
    leave(mic)
    window.set_show_mic(True)
    enter(mic)
    rest(window)
    assert labels_shown() == ["Caption what I say: on"]
    leave(mic)
    enter(window.tag, x=20)
    rest(window)
    assert labels_shown() == ["Discord"]
    leave(window.tag)


def test_the_label_never_takes_the_focus_or_the_mouse(window: CaptionWindow) -> None:
    label = window.tips.label
    flags = label.windowFlags()
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert label.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert label.parent() is window  # parented before it's ever shown


def test_it_sits_above_the_window_clear_of_the_captions(window: CaptionWindow) -> None:
    enter(window.buttons["settings"])
    rest(window)
    label = window.tips.label
    assert label.geometry().bottom() < window.frameGeometry().top()
    assert not label.over_captions
    assert window.tips._gone.interval() == SHOWN_MS
    leave(window.buttons["settings"])


def test_at_the_top_of_the_screen_it_covers_the_captions_only_briefly(
    window: CaptionWindow, qapp: QApplication
) -> None:
    window.move(window.x(), 0)
    qapp.processEvents()
    enter(window.buttons["settings"])
    rest(window)
    label = window.tips.label
    assert label.over_captions
    assert window.tips._gone.interval() == OVER_CAPTIONS_MS
    window.tips._gone.timeout.emit()
    assert labels_shown() == []
    leave(window.buttons["settings"])


def test_tip_place() -> None:
    button = QRect(1000, 660, 24, 22)
    window = QRect(500, 650, 960, 300)
    place, over = tip_place((200, 30), button, window, SCREEN)
    assert place == QRect(911, 616, 200, 30) and not over
    # no room above: just under the button
    place, over = tip_place(
        (200, 30), QRect(1000, 10, 24, 22), QRect(500, 0, 960, 300), SCREEN
    )
    assert place.top() == 36 and over
    # never off the screen's edge
    place, _ = tip_place((200, 30), QRect(1900, 660, 20, 22), window, SCREEN)
    assert place.right() == SCREEN.right()
    place, _ = tip_place((200, 30), QRect(0, 660, 20, 22), window, SCREEN)
    assert place.left() == 0


def test_a_joined_windows_lock_and_settings_say_what_they_do(
    qapp: QApplication,
) -> None:
    class Store:
        def __init__(self) -> None:
            self.values: dict[str, object] = {"targets": ["en"]}

        def load(self) -> dict[str, object]:
            return dict(self.values)

        def save(self, values: object) -> None:
            assert isinstance(values, dict)
            self.values = dict(values)

    second = SourceId("app-2")
    windows = CaptionWindows(Store(), MIC, areas)
    windows.set_labels(
        {
            APP: SourceLabel("Discord", "#4dd0e1"),
            second: SourceLabel("Video", "#a5d66f"),
        },
        "You",
    )
    windows.set_captioned([("a", APP), ("b", second)])
    windows.join("b")
    joined = windows.joined_window
    assert joined is not None
    joined.show()
    joined.show_bands(True)
    try:
        for name in ("lock", "settings"):
            button = joined.buttons[name]
            enter(button)
            joined.tips._rest.timeout.emit()
            assert labels_shown() == [joined.controls[name].toolTip()]
            leave(button)
    finally:
        windows.close()
    qapp.processEvents()


def test_qts_own_tooltip_is_never_shown_beside_it(window: CaptionWindow) -> None:
    """Should the window ever be active, Qt's tooltip would show too: the
    strip eats it."""
    event = QEvent(QEvent.Type.ToolTip)
    assert window.tips.eventFilter(window.buttons["lock"], event)


def test_the_label_is_in_the_interface_language(qapp: QApplication) -> None:
    from PySide6.QtCore import QLocale

    from polyglotic_desktop.ui.interface_language import ENGLISH, formats, install

    installed = install(qapp, "zh_CN")
    try:
        shown = CaptionWindow(
            "Discord.exe", APP, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
            mic=MIC, areas=areas,
        )  # fmt: skip
        shown.show()
        shown.hovered = True
        shown._show_band(True)
        enter(shown.buttons["lock"])
        rest(shown)
        said = labels_shown()
        leave(shown.buttons["lock"])
        shown.close()
        shown.deleteLater()
    finally:
        for translator in installed:
            qapp.removeTranslator(translator)
        QLocale.setDefault(formats(ENGLISH, QLocale.system()))
    assert len(said) == 1
    assert any("一" <= c <= "鿿" for c in said[0])  # in Chinese
