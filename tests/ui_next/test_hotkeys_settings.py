"""Settings > Hotkeys, the app's hotkeys taken again as they change, and
Back to live from anywhere (polyglotic-hq 567, decision 0273; the user,
2026-11-20: "Hotkey to jump to line ... customiseable ... global hotkeys
customisation section").

Nothing here presses a key on the PC: the key boxes get Qt's events, and
the OS's hotkeys are a fake made with what the app would register."""

import sys
from collections.abc import Callable, Iterator, Mapping
from typing import ClassVar

import pytest
import shiboken6
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_lock_says_how_to_unlock import wired  # noqa: F401 - fixture

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.dictation_keys import DictationKey
from polyglotic_desktop.core.listening.hotkeys import DICTATE, Hotkey
from polyglotic_desktop.core.listening.hotkeys import keys as hotkey_keys
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.main import AppHotkeys
from polyglotic_desktop.ui.app import DesktopApp, key_sequence
from polyglotic_desktop.ui.recorded_captions import APP
from polyglotic_desktop.ui_next.caption_window import live_tip
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.hotkeys_card import HotkeysCard
from polyglotic_desktop.ui_next.os_words import pc_mac_or_linux, pc_or_mac
from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.scroll import Anchor

LINUX = sys.platform.startswith("linux")
OWN = pc_mac_or_linux("ctrl+alt", "ctrl+win", "ctrl+alt+shift")
"""The app's own hotkeys' modifiers as kept: Shift too on Linux (570)."""
SHOWN = pc_mac_or_linux("Ctrl + Alt + ", "⌃⌘", "Ctrl + Alt + Shift + ")
"""And as Settings writes them."""
TIP = pc_mac_or_linux("Ctrl+Alt+", "⌃⌘", "Ctrl+Alt+Shift+")
"""And as a tip writes them."""
HELD_ALONE = (
    "Hold Ctrl, Alt, Shift or Super with a key, or choose an F key."
    if LINUX
    else "Hold ⌘, ⌥, ⇧ or ⌃ with a key, or choose an F key."
    if sys.platform == "darwin"
    else "Hold Ctrl, Alt, Shift or Win with a key, or choose an F key."
)
"""Refusal for a modifier pressed alone: Super on Linux (642), symbols on Mac."""


def press(box: object, key: Qt.Key, vk: int, modifiers: Qt.KeyboardModifier) -> None:
    """A key down and up in a box that listens, as Windows hands Qt one."""
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        event = QKeyEvent(kind, key, modifiers, 0, vk, 0)
        QApplication.sendEvent(box, event)  # type: ignore[arg-type]


CTRL_ALT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier


@pytest.fixture
def card(qapp: QApplication) -> Iterator[HotkeysCard]:
    made = HotkeysCard()
    yield made
    shiboken6.delete(made)


def test_each_hotkey_is_listed_with_its_key_and_a_way_to_clear_it(
    card: HotkeysCard,
) -> None:
    assert list(card.lines) == [h.value for h in Hotkey]
    assert card.lines["live"].box.text() == "Space"
    assert card.lines["lock"].box.text() == SHOWN + "L"
    assert card.lines["copy"].box.text() == "No key"
    assert not card.lines["copy"].clear.isEnabled()
    assert card.lines["live"].clear.isEnabled()
    assert not card.reset.isEnabled()  # every key its own
    card.show_keys({"copy": "ctrl+alt+c"}, ())
    assert card.lines["copy"].box.text() == pc_or_mac("Ctrl + Alt + C", "⌥⌘C")
    assert card.reset.isEnabled()


def test_a_key_pressed_is_asked_for_and_clear_and_reset_too(card: HotkeysCard) -> None:
    wanted: list[tuple[str, str]] = []
    resets: list[bool] = []
    card.hotkey_wanted.connect(lambda name, key: wanted.append((name, key)))
    card.reset_wanted.connect(lambda: resets.append(True))
    box = card.lines["copy"].box
    box.click()
    assert box.listening
    press(box, Qt.Key.Key_C, 0x43, CTRL_ALT | Qt.KeyboardModifier.ShiftModifier)
    assert wanted == []  # modifiers aren't down as Qt's own events here
    card._pressed("copy", "ctrl+shift+c")
    card.lines["live"].clear.click()
    card.show_keys({"copy": "ctrl+shift+c"}, ())
    card.reset.click()
    assert wanted == [("copy", "ctrl+shift+c"), ("live", "")]
    assert resets == [True]


def test_a_key_that_can_t_be_one_says_why_on_its_own_line(card: HotkeysCard) -> None:
    wanted: list[tuple[str, str]] = []
    card.hotkey_wanted.connect(lambda name, key: wanted.append((name, key)))
    note = card.lines["bigger"].note
    card._pressed("bigger", "ctrl+c")
    assert note.text() == pc_or_mac(
        "Every program uses that one (copy, paste…): add Alt or Shift to it.",
        "Every app uses that one (copy, paste…): add ⌥ or ⇧ to it.",
    )
    card._pressed("bigger", "right_ctrl")
    assert note.text() == HELD_ALONE
    card._pressed("bigger", f"{OWN}+l")  # Lock's
    assert note.text() == (
        "Lock all caption windows has that key: clear it there, or choose another."
    )
    card.show_keys({}, (), dictation="insert")
    card._pressed("bigger", "insert")  # dictation's
    assert note.text() == "Dictate has that key: clear it there, or choose another."
    card._pressed("bigger", "escape")
    assert "Esc" in note.text()
    card._pressed("bigger", "alt+b")
    assert note.text().startswith(
        pc_or_mac(
            "Letting go of Alt opens a program's menu", "⌥ with a key types a character"
        )
    )
    assert wanted == []
    card._pressed("bigger", "ctrl+shift+up")
    assert wanted == [("bigger", "ctrl+shift+up")] and not note.isVisibleTo(card)


def test_a_key_another_program_has_and_one_two_share_are_said(
    card: HotkeysCard,
) -> None:
    card.show_keys({"live": f"{OWN}+p"}, {"pause"})
    assert card.lines["pause"].note.text() == (
        "Another program has this key: choose another."
    )
    assert card.lines["live"].note.text() == (
        "Pause captions has this key too, and only it works."
    )
    assert card.lines["lock"].note.text() == ""


def test_unavailable_hotkeys_never_say_another_program_and_explain_cli(
    qapp: QApplication, card: HotkeysCard
) -> None:
    """644 bug 3 / 647: on GNOME Wayland (`NoHotkeys`), Settings > Hotkeys must
    not label every shortcut 'Another program has this key' - it must say
    plainly that this desktop doesn't allow global hotkeys and show how to use
    `polyglotic --lock` instead."""
    from polyglotic_desktop.platform.linux.hotkeys import NoHotkeys

    held = AppHotkeys(NoHotkeys, lambda _name: None)
    assert held.follow(hotkey_keys({}))
    assert not held.available
    assert set(held.not_working(["lock", "pause", "hide"])) == {"lock", "pause", "hide"}

    card.show_keys({}, held.taken, unavailable=not held.available)
    assert card.subtitle is not None
    assert "doesn't allow global hotkeys" in card.subtitle.text()
    assert "polyglotic --lock" in card.subtitle.text()
    for name, line in card.lines.items():
        local = name == "live"
        assert bool(line.note.text()) == local
        assert line.box.isEnabled() == local
        assert line.clear.isEnabled() == local
    assert not card.reset.isEnabled()

    # Custom AppImage command is reflected when set
    card.set_command("/home/learner/Applications/Polyglotic.AppImage")
    assert (
        "/home/learner/Applications/Polyglotic.AppImage --lock" in card.subtitle.text()
    )

    # Through SettingsPage too
    page = settings_page()
    try:
        page.show_command("polyglotic")
        page.show_hotkeys({}, held.taken, unavailable=True)
        assert page.hotkeys_card.subtitle is not None
        assert "polyglotic --lock" in page.hotkeys_card.subtitle.text()
        assert page.hotkeys_card.lines["live"].box.isEnabled()
    finally:
        shiboken6.delete(page)


def settings_page() -> SettingsPage:
    return SettingsPage(
        [("margin", "Margin")],
        QAction("Tell us"),
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
    )


def test_an_unavailable_key_only_starts_capture_after_a_learner_choice(
    qapp: QApplication,
) -> None:
    page = settings_page()
    try:
        page.show_section("hotkeys")
        page.show()
        listening: list[bool] = []
        page.dictation_key_listening.connect(listening.append)

        page.show_respeaking(True, "")
        page.show_dictation(True, "f9", None, False, taken=True)
        assert all("F9" in card.respeak_note.text() for card in page.respeak_cards)
        page.show_respeaking(True, "f8", taken=True)
        assert all("F8" in card.respeak_note.text() for card in page.respeak_cards)
        assert listening == []

        page.respeak_key_not_taken("f7")
        assert listening == [True]
        assert page.hotkeys_for_others.respeak_box.listening
        assert not page.dictation_for_others.respeak_box.listening
    finally:
        shiboken6.delete(page)


def test_settings_has_a_hotkeys_section_after_dictation(qapp: QApplication) -> None:
    page = settings_page()
    try:
        assert SECTIONS.index("hotkeys") == SECTIONS.index("dictation") + 1
        page.show_section("dictation")
        card = page.dictation_for_others
        assert card.isVisibleTo(page) and card.respeak.switch.isChecked()
        page.show_section("hotkeys")
        assert not card.isVisibleTo(page)
        page.show_section("hotkeys")
        page.show()
        QApplication.processEvents()
        names = [card.objectName() for card in page.cards("hotkeys")]
        assert names == [
            "settings.hotkeys_card",
            "settings.hold_keys",
            "settings.hotkeys_for_others",
            "settings.window_keys",
        ]
        wanted_hold: list[str] = []
        page.respeak_key_wanted.connect(wanted_hold.append)
        page.show_respeaking(True, "f8")
        assert page.hotkeys_for_others.respeak_box.text() == "F8"
        page.hotkeys_for_others.respeak_box.pressed_key.emit("f7")
        assert wanted_hold == ["f7"]
        # App's read-only list went: every key is here now
        assert "settings.hotkeys_card" not in [
            c.objectName() for c in page.cards("app")
        ]
        wanted: list[tuple[str, str]] = []
        page.hotkey_wanted.connect(lambda name, key: wanted.append((name, key)))
        page.show_hotkeys({"live": "f9"}, set())
        assert page.hotkeys_card.lines["live"].box.text() == "F9"
        page.hotkeys_card.lines["live"].clear.click()
        assert wanted == [("live", "")]
        # dictation's key named there, while it's on
        page.show_dictation(True, "insert", None, False)
        assert page.hold_keys.dictation.text() == "Dictate: hold Insert and speak."
        # and dictation can't take a hotkey's key - the one it has now
        page.show_hotkeys({"live": "f9"}, set())
        page._dictation_key_pressed("f9")
        assert page.dictation_key_note.text() == (
            "That's one of Polyglotic's own hotkeys: choose another."
        )
        change = page.hold_keys.findChild(QPushButton, "hotkeys.dictate.change")
        assert change is not None
        change.click()
        assert page._current == "dictation"
    finally:
        shiboken6.delete(page)


class FakeHotkeys:
    """The OS's hotkeys: `taken` combinations are another app's."""

    made: ClassVar[list["FakeHotkeys"]] = []

    def __init__(
        self, bindings: Mapping[str, Callable[[], None]], taken: tuple[str, ...] = ()
    ) -> None:
        self.bindings = dict(bindings)
        self.taken = [k for k in bindings if k in taken]
        self.started = self.stopped = False
        FakeHotkeys.made.append(self)

    def start(self) -> list[str]:
        self.started = True
        return self.taken

    def stop(self) -> None:
        self.stopped = True


def test_the_app_takes_its_hotkeys_again_when_one_changes() -> None:
    FakeHotkeys.made.clear()
    pressed: list[str] = []
    held = AppHotkeys(lambda b: FakeHotkeys(b, ("ctrl+alt+p",)), pressed.append)
    dictation = {DICTATE: DictationKey.parse("right_ctrl")}
    assert held.follow(hotkey_keys({}), dictation)
    first = FakeHotkeys.made[-1]
    assert set(first.bindings) == {
        "ctrl+alt+l",
        "ctrl+alt+p",
        "ctrl+alt+h",
    }
    assert held.taken == {"pause"}
    assert held.not_working(["lock", "pause", "copy"]) == ["pause", "copy"]
    assert held.live_space
    assert held.not_working(["live"]) == []
    assert not held.follow(hotkey_keys({}), dictation)  # nothing changed
    assert held.follow(hotkey_keys({"live": "f9", "copy": "ctrl+alt+c"}), dictation)
    assert first.stopped
    second = FakeHotkeys.made[-1]
    assert {"f9", "ctrl+alt+c"} <= set(second.bindings)
    assert not held.live_space
    second.bindings["f9"]()
    assert pressed == ["live"]
    # dictation's key made a hotkey's (a file edited by hand): dictation keeps it
    insert = {DICTATE: DictationKey.parse("insert")}
    held.follow(hotkey_keys({"copy": "insert"}), insert)
    assert "insert" not in FakeHotkeys.made[-1].bindings
    # while Settings listens for a key, the app's let go - and back after
    held.box_listening = True
    assert held.follow(hotkey_keys({}), dictation)
    assert FakeHotkeys.made[-1].stopped and held.bound == {}
    held.box_listening = False
    assert held.follow(hotkey_keys({}), dictation)
    assert not FakeHotkeys.made[-1].stopped
    held.stop()
    assert FakeHotkeys.made[-1].stopped


def test_a_hotkey_s_key_is_shown_on_its_command_as_the_os_writes_it(
    qapp: QApplication,
) -> None:
    desktop = DesktopApp(MemorySettingsStore({}), None, FakeAppList())
    try:
        desktop.set_hotkeys(hotkey_keys({"live": "shift+f9", "lock": ""}))
        assert desktop.go_live.shortcut().toString() == "Shift+F9"
        assert desktop.lock_windows.shortcut().isEmpty()
        assert key_sequence(DictationKey.parse("ctrl+win+page_up")).toString() == (
            "Meta+Ctrl+PgUp"
        )
        assert key_sequence(DictationKey.parse("right_ctrl")).isEmpty()
    finally:
        desktop.close()


def test_back_to_live_from_anywhere_and_its_tip_names_the_key(
    qapp: QApplication,
    wired: tuple[DesktopApp, CaptionWindows],  # noqa: F811
) -> None:
    """The hotkey does what each window's Back to live does, in every
    window; the pill's tip names it as it is now."""
    desktop, windows = wired
    (window,) = windows.windows.values()
    assert window.pill.toolTip() == live_tip("Space")
    desktop.set_hotkeys(hotkey_keys({"live": "f9"}))
    assert window.pill.toolTip() == "Back to the newest captions (F9)"
    desktop.set_hotkeys(hotkey_keys({"live": ""}))
    assert window.pill.toolTip() == "Back to the newest captions"
    window.view.scroll.anchor = Anchor(1, 0.0)  # scrolled back, reading
    assert not window.view.scroll.following
    desktop.go_live.trigger()
    assert window.view.scroll.following


def test_text_size_and_copying_from_anywhere(
    qapp: QApplication,
    wired: tuple[DesktopApp, CaptionWindows],  # noqa: F811
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    size = window.size_readout(0, 1.0)
    desktop.text_bigger.trigger()
    assert window.size_readout(0, 1.0) > size
    desktop.text_smaller.trigger()
    assert window.size_readout(0, 1.0) == size
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("before")
    desktop.copy_caption.trigger()  # nothing captioned yet: left alone
    assert clipboard.text() == "before"
    desktop.feed.apply(
        CaptionUpdate(CaptionId("c1"), APP, CaptionKind.FINISHED, (Clause("明天见"),))
    )
    desktop.copy_caption.trigger()
    assert clipboard.text() == "明天见"
    assert window.notice.text() == "Copied the newest caption"


def test_a_window_opened_later_has_back_to_live_s_key_too(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        window.set_live_keys("Ctrl+Alt+J")
        assert window.pill.toolTip() == "Back to the newest captions (Ctrl+Alt+J)"
    finally:
        window.close()


def test_space_goes_live_but_a_focused_edit_keeps_it(qapp: QApplication) -> None:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit
    from tests.ui_next.test_caption_window import window_of

    from polyglotic_desktop.main import LocalLiveShortcut

    window = window_of(qapp, captions=25)
    action = QAction(window)
    calls: list[bool] = []
    action.triggered.connect(lambda: calls.append(True))
    action.triggered.connect(window.go_live)
    shortcut = LocalLiveShortcut(qapp, action)
    shortcut.enabled = True
    try:
        window.canvas.scroll_by(400)
        assert not window.view.scroll.following
        QTest.keyClick(window, Qt.Key.Key_Space)
        assert calls == [True]

        window.canvas.scroll_by(400)
        line = QLineEdit(window)
        line.show()
        line.setFocus()
        QTest.keyClick(line, Qt.Key.Key_Space)
        assert line.text() == " "
        assert calls == [True]
        assert not window.view.scroll.following
    finally:
        qapp.removeEventFilter(shortcut)
        shortcut.deleteLater()
        window.close()
