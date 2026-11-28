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
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_lock_says_how_to_unlock import wired  # noqa: F401 - fixture

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.dictation_keys import DictationKey
from polyglotic_desktop.core.listening.hotkeys import (
    DICTATE,
    Hotkey,
    HotkeyScope,
)
from polyglotic_desktop.core.listening.hotkeys import keys as hotkey_keys
from polyglotic_desktop.core.listening.hotkeys import scopes as hotkey_scopes
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.main import (
    AppHotkeys,
    LocalDictationKey,
    LocalHotkeys,
    type_in_app,
)
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
    press(box, Qt.Key.Key_C, 0x43, Qt.KeyboardModifier.NoModifier)
    assert wanted == [("copy", "c")]  # 966: bare letter is valid
    card._pressed("copy", "ctrl+shift+c")
    card.lines["live"].clear.click()
    card.show_keys({"copy": "ctrl+shift+c"}, ())
    card.reset.click()
    assert wanted == [("copy", "c"), ("copy", "ctrl+shift+c"), ("live", "")]
    assert resets == [True]


def test_a_key_that_can_t_be_one_says_why_on_its_own_line(card: HotkeysCard) -> None:
    wanted: list[tuple[str, str]] = []
    card.hotkey_wanted.connect(lambda name, key: wanted.append((name, key)))
    note = card.lines["bigger"].note
    card._pressed("bigger", "right_ctrl")
    assert note.text() == HELD_ALONE
    card._pressed("bigger", f"{OWN}+l")  # Lock's
    assert note.text() == (
        "Lock all caption windows has that key: clear it there, or choose another."
    )
    card.show_keys({}, (), dictation="insert")
    card._pressed("bigger", "insert")  # dictation's
    assert note.text() == "Dictate has that key: clear it there, or choose another."
    assert wanted == []
    # 966: letters, digits, punctuation, Space, arrows, media keys and combos are accepted
    for accepted in (
        "a",
        "7",
        "comma",
        "enter",
        "left",
        "media_play",
        "ctrl+c",
        "alt+b",
        "ctrl+shift+up",
    ):
        card._pressed("bigger", accepted)
    assert wanted == [
        ("bigger", k)
        for k in (
            "a",
            "7",
            "comma",
            "enter",
            "left",
            "media_play",
            "ctrl+c",
            "alt+b",
            "ctrl+shift+up",
        )
    ]
    assert not note.isVisibleTo(card)


def test_a_key_another_program_has_and_one_two_share_are_said(
    card: HotkeysCard,
) -> None:
    card.show_keys(
        {"live": f"{OWN}+p"},
        {"pause"},
        alternatives={"pause": ("ctrl+alt+shift+p", "f9")},
    )
    assert "Another program uses" in card.lines["pause"].note.text()
    assert "won't work here" in card.lines["pause"].note.text()
    assert card.lines["pause"].alt_buttons[0].isVisibleTo(card)
    assert card.lines["pause"].alt_buttons[1].isVisibleTo(card)
    chosen: list[tuple[str, str]] = []
    card.hotkey_wanted.connect(lambda n, k: chosen.append((n, k)))
    card.lines["pause"].alt_buttons[1].click()
    assert chosen == [("pause", "f9")]
    assert card.lines["live"].note.text() == (
        "Pause captions has this key too, and only it works."
    )
    assert card.lines["lock"].note.text() == ""


def test_everywhere_typing_key_warns_and_shared_hook_says_shared_with_alternatives(
    card: HotkeysCard,
) -> None:
    """966: Everywhere on a typing key shows a plain warning; a Windows
    low-level hook fallback says it shares the keys with another program and
    offers two free alternatives."""
    scope_changes: list[tuple[str, str]] = []
    card.hotkey_scope_wanted.connect(lambda n, s: scope_changes.append((n, s)))
    card.show_keys({"copy": "a"}, ())
    assert card.scopes["copy"] is HotkeyScope.APP
    assert card.lines["copy"].note.text() == ""
    card.lines["copy"].scope.buttons[1].click()
    assert scope_changes == [("copy", "everywhere")]
    card.show_keys(
        {"copy": "a"},
        (),
        scopes={"copy": "everywhere"},
        shared={"lock"},
        alternatives={"lock": ("ctrl+alt+shift+l", "f10")},
    )
    assert "types" in card.lines["copy"].note.text().lower()
    assert "still goes through" in card.lines["copy"].note.text()
    assert "shares it" in card.lines["lock"].note.text()
    assert card.lines["lock"].alt_buttons[0].text().startswith("Use ")
    assert card.lines["lock"].alt_buttons[1].text().startswith("Use ")


def test_unavailable_hotkeys_never_say_another_program_and_explain_cli(
    qapp: QApplication, card: HotkeysCard
) -> None:
    """644 bug 3 / 647 / 966: on GNOME Wayland (`NoHotkeys`), Settings > Hotkeys
    never labels shortcuts 'Another program uses ...' - it explains global
    hotkeys aren't available and shows `polyglotic --lock`, while allowing
    In Polyglotic's windows hotkeys."""
    from polyglotic_desktop.platform.linux.hotkeys import NoHotkeys

    held = AppHotkeys(NoHotkeys, lambda _name: None)
    assert held.follow(hotkey_keys({}))
    assert not held.available
    assert set(held.not_working(["lock", "pause", "hide"])) == {"lock", "pause", "hide"}
    assert held.not_working(["live"]) == []  # APP-scoped Space still works

    card.show_keys({}, held.taken, unavailable=not held.available)
    assert card.subtitle is not None
    assert "doesn't allow global hotkeys" in card.subtitle.text()
    assert "polyglotic --lock" in card.subtitle.text()
    for name, line in card.lines.items():
        assert "Another program" not in line.note.text()
        assert line.box.isEnabled()
        if card.keys[name] is not None:
            assert not line.scope.buttons[1].isEnabled()  # Everywhere disabled
            assert line.scope.buttons[0].isEnabled()  # In Polyglotic's windows works
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
    """The OS's hotkeys: `taken` combinations are another app's; `hooked`
    simulates Windows' WH_KEYBOARD_LL fallback sharing a refused key."""

    made: ClassVar[list["FakeHotkeys"]] = []

    def __init__(
        self,
        bindings: Mapping[str, Callable[[], None]],
        taken: tuple[str, ...] = (),
        *,
        hooked: tuple[str, ...] = (),
        passthrough: frozenset[str] = frozenset(),
    ) -> None:
        self.bindings = dict(bindings)
        self.passthrough = frozenset(passthrough)
        self.taken = [k for k in bindings if k in taken]
        self.hooked = [k for k in self.taken if k in hooked]
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
    held = AppHotkeys(
        lambda b, passthrough=frozenset(): FakeHotkeys(
            b, ("ctrl+alt+p", "ctrl+alt+shift+p"), passthrough=passthrough
        ),
        pressed.append,
    )
    dictation = {DICTATE: DictationKey.parse("right_ctrl")}
    assert held.follow(hotkey_keys({}), dictation)
    # FakeHotkeys.made[0] is the active registration; made[1] was the free-alt probe
    first = FakeHotkeys.made[0]
    probe = FakeHotkeys.made[1]
    assert probe.stopped
    assert set(first.bindings) == {
        "ctrl+alt+l",
        "ctrl+alt+p",
        "ctrl+alt+h",
    }
    assert held.taken == {"pause"}
    assert held.shared == set()
    # Two tested free alternatives, skipping the also-taken ctrl+alt+shift+p
    assert len(held.alternatives["pause"]) == 2
    assert "ctrl+alt+shift+p" not in held.alternatives["pause"]
    assert held.not_working(["lock", "pause", "copy"]) == ["pause", "copy"]
    assert held.live_space
    assert held.not_working(["live"]) == []
    assert not held.follow(hotkey_keys({}), dictation)  # nothing changed
    before = len(FakeHotkeys.made)
    assert held.follow(hotkey_keys({"live": "f9", "copy": "ctrl+alt+c"}), dictation)
    assert first.stopped
    second = FakeHotkeys.made[before]
    assert {"f9", "ctrl+alt+c"} <= set(second.bindings)
    assert not held.live_space
    second.bindings["f9"]()
    assert pressed == ["live"]
    # dictation's key made a hotkey's (a file edited by hand): dictation keeps it
    insert = {DICTATE: DictationKey.parse("insert")}
    before = len(FakeHotkeys.made)
    held.follow(hotkey_keys({"copy": "insert"}), insert)
    assert "insert" not in FakeHotkeys.made[before].bindings
    # while Settings listens for a key, the app's let go - and back after
    held.box_listening = True
    assert held.follow(hotkey_keys({}), dictation)
    assert held.bound == {} and held.local_bound == {}
    held.box_listening = False
    before = len(FakeHotkeys.made)
    assert held.follow(hotkey_keys({}), dictation)
    active = FakeHotkeys.made[before]
    assert not active.stopped
    held.stop()
    assert active.stopped


def test_app_scoped_typing_key_stays_local_and_everywhere_uses_passthrough() -> None:
    """966: a typing key defaults to APP scope (never handed to global OS
    hotkeys, so it does nothing in other apps); switching its scope to
    Everywhere passes `passthrough` to the OS adapter."""
    FakeHotkeys.made.clear()
    held = AppHotkeys(
        lambda b, passthrough=frozenset(): FakeHotkeys(b, passthrough=passthrough),
        lambda _name: None,
    )
    chosen = hotkey_keys({"copy": "a"})
    held.follow(chosen, scopes=hotkey_scopes(chosen, {}))
    assert "a" not in FakeHotkeys.made[-1].bindings
    assert DictationKey.parse("a") in held.local_bound

    held.follow(chosen, scopes=hotkey_scopes(chosen, {"copy": "everywhere"}))
    assert "a" in FakeHotkeys.made[-1].bindings
    assert "a" in FakeHotkeys.made[-1].passthrough
    assert DictationKey.parse("a") not in held.local_bound


def test_shared_hook_keeps_hotkey_working_and_still_offers_two_alternatives() -> None:
    """966: when the Windows low-level hook takes over a refused chord, it
    is in `shared` (not `taken`), stays working, and still probes 2 free alts."""
    FakeHotkeys.made.clear()
    held = AppHotkeys(
        lambda b, passthrough=frozenset(): FakeHotkeys(
            b, ("ctrl+alt+p",), hooked=("ctrl+alt+p",), passthrough=passthrough
        ),
        lambda _name: None,
    )
    held.follow(hotkey_keys({}))
    assert held.shared == {"pause"}
    assert held.taken == set()
    assert held.not_working(["pause"]) == []
    assert len(held.alternatives["pause"]) == 2


def test_tray_reports_hotkey_conflicts_without_silent_failure(
    qapp: QApplication,
) -> None:
    """966: OS hotkey conflicts show in the tray menu, tooltip, and tray
    notification, and clicking the tray item opens Settings > Hotkeys."""

    class FakeTray:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str, int]] = []
            self.tip = ""

        def icon(self) -> object:
            return None

        def setToolTip(self, tip: str) -> None:
            self.tip = tip

        def showMessage(self, title: str, body: str, _icon: object, ms: int) -> None:
            self.messages.append((title, body, ms))

        def hide(self) -> None:
            pass

    desktop = DesktopApp(MemorySettingsStore({}), None, FakeAppList())
    fake_tray = FakeTray()
    desktop.tray = fake_tray  # type: ignore[assignment]
    opened: list[bool] = []
    desktop.hotkeys_settings_wanted.connect(lambda: opened.append(True))
    try:
        desktop.show_hotkey_conflicts(
            {"pause": ("Pause captions", "Ctrl + Alt + P", False)}
        )
        assert desktop.hotkey_conflict.isVisible()
        assert "Ctrl + Alt + P" in desktop.hotkey_conflict.text()
        assert "Ctrl + Alt + P" in fake_tray.tip
        assert len(fake_tray.messages) == 1
        assert "Pause captions" in fake_tray.messages[0][1]
        assert "Ctrl + Alt + P" in fake_tray.messages[0][1]
        # Identical state does not spam another notification.
        desktop.show_hotkey_conflicts(
            {"pause": ("Pause captions", "Ctrl + Alt + P", False)}
        )
        assert len(fake_tray.messages) == 1
        # Clicking the tray item requests Settings > Hotkeys.
        desktop.hotkey_conflict.trigger()
        assert opened == [True]
        # Clearing conflicts hides the tray item.
        desktop.show_hotkey_conflicts({})
        assert not desktop.hotkey_conflict.isVisible()
    finally:
        desktop.close()


def test_local_hotkeys_fire_for_any_app_scoped_key_and_leave_edits_alone(
    qapp: QApplication,
) -> None:
    window = window_of(qapp, captions=25)
    fired: list[str] = []
    local = LocalHotkeys(qapp, fired.append)
    key_a = DictationKey.parse("a")
    key_f9 = DictationKey.parse("f9")
    assert key_a is not None and key_f9 is not None
    local.set_bindings({key_a: "copy", key_f9: "pause"})
    try:
        QTest.keyClick(window, Qt.Key.Key_A)
        QTest.keyClick(window, Qt.Key.Key_F9)
        assert fired == ["copy", "pause"]

        line = QLineEdit(window)
        line.show()
        line.setFocus()
        QTest.keyClick(line, Qt.Key.Key_A)
        assert line.text() == "a"
        assert fired == ["copy", "pause"]  # typing key left alone in QLineEdit
        QTest.keyClick(line, Qt.Key.Key_F9)
        assert fired == ["copy", "pause", "pause"]  # non-typing key still fires
    finally:
        qapp.removeEventFilter(local)
        local.deleteLater()
        window.close()


def test_local_dictation_key_holds_releases_and_cancels_in_app(
    qapp: QApplication,
) -> None:
    window = window_of(qapp, captions=25)
    outside = QLineEdit()
    inside = QLineEdit(window)
    inside.show()
    inside.setFocus()
    key = DictationKey.parse("a")
    assert key is not None
    events: list[str] = []
    local = LocalDictationKey(
        qapp,
        key,
        lambda: events.append("down"),
        lambda: events.append("up"),
        lambda: events.append("cancel"),
    )
    assert local.start()
    try:
        QTest.keyClick(outside, Qt.Key.Key_A)
        assert outside.text() == "a"
        assert events == []

        QTest.keyPress(inside, Qt.Key.Key_A)
        assert events == ["down"]
        repeat = QKeyEvent(
            QEvent.Type.KeyRelease,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
            "a",
            True,
        )
        QApplication.sendEvent(inside, repeat)
        assert events == ["down"]
        QTest.keyRelease(inside, Qt.Key.Key_A)
        assert events == ["down", "up"]
        assert inside.text() == ""
        assert type_in_app("a cat")
        assert inside.text() == "a cat"
        assert events == ["down", "up"]

        QTest.keyPress(inside, Qt.Key.Key_A)
        QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
        assert events == ["down", "up", "down", "cancel", "up"]
        QTest.keyRelease(outside, Qt.Key.Key_A)
        assert events == ["down", "up", "down", "cancel", "up"]
    finally:
        local.stop()
        outside.close()
        window.close()


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
