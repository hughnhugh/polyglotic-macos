"""Dictation's key on a Mac (polyglotic-hq 429): Qt's names read as a Mac's
keys (Ctrl is Command), a key registered through Carbon - a stand-in here
- and a modifier held alone read from the modifiers' state, with stand-ins
for macOS's calls. Carbon's own registration is proven on GitHub's Mac
(`tools.macos_full_screen_checks`)."""

import threading
import time
from collections.abc import Callable
from typing import ClassVar

import pytest

from polyglotic_desktop.core.listening.dictation_keys import DictationKey
from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.macos import hold_key
from polyglotic_desktop.platform.macos.hold_key import MODIFIERS, MacHoldKey, plan

COMMAND = MODIFIERS[hold_key.Modifier.CTRL]
CONTROL = MODIFIERS[hold_key.Modifier.WIN]
SHIFT = MODIFIERS[hold_key.Modifier.SHIFT]
CTRL_CMD = CONTROL.either | COMMAND.either


def parsed(text: str) -> DictationKey:
    key = DictationKey.parse(text)
    assert key is not None
    return key


def test_right_ctrl_the_default_is_right_command() -> None:
    assert plan(parsed("right_ctrl")) == hold_key.Plan(None, 0, (COMMAND.right,), 0)


def test_a_combination_is_registered_with_carbons_modifiers() -> None:
    """Control+Command+D, as Qt keeps it ("ctrl" Command, "win" Control)."""
    assert plan(parsed("ctrl+win+d")) == hold_key.Plan(
        2, COMMAND.carbon | CONTROL.carbon, (), CTRL_CMD
    )
    assert plan(parsed("f9")) == hold_key.Plan(101, 0, (), 0)


def test_modifiers_alone_are_read_together() -> None:
    assert plan(parsed("ctrl+win")) == hold_key.Plan(
        None, 0, (COMMAND.either, CONTROL.either), CTRL_CMD
    )


def test_a_key_a_mac_hasnt_got_isnt_planned() -> None:
    assert plan(parsed("f21")) is None
    assert not MacHoldKey("f21", lambda: None, lambda: None).start()


def test_every_key_but_f21_to_f24_has_a_mac_key_code() -> None:
    from polyglotic_desktop.core.listening.dictation_keys import KEYS, MEDIA_KEYS

    missing = {key for key in KEYS if key not in hold_key.KEY_CODES}
    assert missing == {"f21", "f22", "f23", "f24", *MEDIA_KEYS}
    # a PC keyboard's Print Screen, Scroll Lock and Pause are F13-F15 on a Mac
    shared = {"print_screen": "f13", "scroll_lock": "f14", "pause": "f15"}
    codes = hold_key.KEY_CODES
    assert all(codes[pc] == codes[mac] for pc, mac in shared.items())
    own = [code for name, code in codes.items() if name not in shared]
    assert len(set(own)) == len(own)


class FakeCarbon:
    """Carbon's hotkey: taken or refused, as told."""

    made: ClassVar[list["FakeCarbon"]] = []
    refuse: ClassVar[bool] = False

    def __init__(
        self, pressed: Callable[[], None], released: Callable[[], None]
    ) -> None:
        self.pressed, self.released = pressed, released
        self.registered: tuple[int, int] | None = None
        FakeCarbon.made.append(self)

    def register(self, key_code: int, modifiers: int) -> bool:
        if FakeCarbon.refuse:
            return False
        self.registered = (key_code, modifiers)
        return True

    def unregister(self) -> None:
        self.registered = None


class Calls:
    def __init__(self) -> None:
        self.said: list[str] = []
        self._changed = threading.Condition()

    def call(self, what: str) -> Callable[[], None]:
        def said() -> None:
            with self._changed:
                self.said.append(what)
                self._changed.notify_all()

        return said

    def wait_for(self, *said: str) -> None:
        with self._changed:
            assert self._changed.wait_for(lambda: self.said == list(said), timeout=3), (
                self.said
            )


@pytest.fixture
def carbon() -> type[FakeCarbon]:
    FakeCarbon.made, FakeCarbon.refuse = [], False
    return FakeCarbon


def key(
    text: str,
    calls: Calls,
    carbon: type[FakeCarbon],
    flags: Callable[[], int] = lambda: 0,
    since_key: Callable[[], float] = lambda: 999.0,
) -> MacHoldKey:
    return MacHoldKey(
        text,
        calls.call("down"),
        calls.call("up"),
        calls.call("other"),
        flags=flags,
        since_key=since_key,
        carbon=carbon,  # type: ignore[arg-type]
        poll=0.002,
    )


def test_carbons_down_and_up_are_dictations(carbon: type[FakeCarbon]) -> None:
    calls = Calls()
    held = key("ctrl+win+d", calls, carbon, flags=lambda: CTRL_CMD)
    assert held.start()
    assert carbon.made[0].registered == (2, COMMAND.carbon | CONTROL.carbon)
    carbon.made[0].pressed()
    calls.wait_for("down")
    carbon.made[0].released()
    calls.wait_for("down", "up")
    held.stop()
    assert carbon.made[0].registered is None


def test_a_modifier_let_go_first_ends_it(carbon: type[FakeCarbon]) -> None:
    flags = [CTRL_CMD]
    calls = Calls()
    held = key("ctrl+win+d", calls, carbon, flags=lambda: flags[0])
    held.start()
    held.post("down")
    calls.wait_for("down")
    flags[0] = COMMAND.either  # Control let go, D still down
    calls.wait_for("down", "up")
    held.stop()


def test_unreadable_modifiers_leave_it_to_carbons_up(carbon: type[FakeCarbon]) -> None:
    """If the modifiers' state can't be read (all up as seen here), only
    Carbon's "up" ends the hold - never at once."""
    calls = Calls()
    held = key("ctrl+win+d", calls, carbon, flags=lambda: 0)
    held.start()
    held.post("down")
    calls.wait_for("down")
    time.sleep(0.05)
    assert calls.said == ["down"]
    held.post("up")
    calls.wait_for("down", "up")
    held.stop()


def test_a_key_another_app_has_isnt_taken(carbon: type[FakeCarbon]) -> None:
    carbon.refuse = True
    assert not key("ctrl+win+d", Calls(), carbon).start()


def test_stopping_while_held_lets_it_up(carbon: type[FakeCarbon]) -> None:
    calls = Calls()
    held = key("f9", calls, carbon)
    held.start()
    held.post("down")
    calls.wait_for("down")
    held.stop()
    calls.wait_for("down", "up")


def test_right_command_held_alone(carbon: type[FakeCarbon]) -> None:
    flags = [0]
    calls = Calls()
    held = key("right_ctrl", calls, carbon, flags=lambda: flags[0])
    assert held.start()
    assert not carbon.made  # a modifier isn't registered
    flags[0] = COMMAND.either | COMMAND.right
    calls.wait_for("down")
    flags[0] = 0
    calls.wait_for("down", "up")
    held.stop()


def test_left_command_isnt_right_command(carbon: type[FakeCarbon]) -> None:
    flags = [COMMAND.either | COMMAND.left]
    calls = Calls()
    held = key("right_ctrl", calls, carbon, flags=lambda: flags[0])
    held.start()
    time.sleep(0.05)
    held.stop()
    assert calls.said == []


def test_a_key_pressed_with_it_is_a_shortcut(carbon: type[FakeCarbon]) -> None:
    """Right Command + C: the hold dropped (`on_other`), up when let go."""
    flags = [0]
    since = [999.0]
    calls = Calls()
    held = key(
        "right_ctrl", calls, carbon, flags=lambda: flags[0], since_key=lambda: since[0]
    )
    held.start()
    flags[0] = COMMAND.either | COMMAND.right
    calls.wait_for("down")
    since[0] = 0.0  # C went down just now
    calls.wait_for("down", "other")
    flags[0] = 0
    calls.wait_for("down", "other", "up")
    held.stop()


def test_another_modifier_with_it_is_a_shortcut(carbon: type[FakeCarbon]) -> None:
    flags = [0]
    calls = Calls()
    held = key("right_ctrl", calls, carbon, flags=lambda: flags[0])
    held.start()
    flags[0] = COMMAND.either | COMMAND.right
    calls.wait_for("down")
    flags[0] |= SHIFT.either | SHIFT.left
    calls.wait_for("down", "other")
    held.stop()
    calls.wait_for("down", "other", "up")


def test_a_shortcut_begun_with_another_modifier_never_starts_it(
    carbon: type[FakeCarbon],
) -> None:
    calls = Calls()
    both = COMMAND.either | COMMAND.right | SHIFT.either | SHIFT.left
    held = key("right_ctrl", calls, carbon, flags=lambda: both)
    held.start()
    time.sleep(0.05)
    held.stop()
    assert calls.said == []


def test_the_macs_record_holds_dictations_key() -> None:
    """Taken with the Accessibility permission asked first, once a run."""
    mac = os_adapters("darwin")
    assert mac.hold_key.__name__ == "dictation_key"


@pytest.mark.macos_only
def test_the_modifiers_state_and_the_last_key_are_read() -> None:
    assert hold_key.flags_now() >= 0
    assert hold_key.since_key_down() >= 0
