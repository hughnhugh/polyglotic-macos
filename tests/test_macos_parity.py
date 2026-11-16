"""The Mac's hotkeys, voices and login item (polyglotic-hq 428): each one's
logic on any OS, through fakes of Carbon and ServiceManagement; what
touches macOS itself is `macos_only` (the macOS job's tests part), and
tools/macos_parity_checks.py presses the keys, hears the voice and has
the packed app add itself to the login items on GitHub's Mac (only a
bundle can be a login item: from source macOS has nothing to say)."""

import io
import json
import threading
import wave
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest

from polyglotic_desktop.main import check_parity, os_adapters
from polyglotic_desktop.platform.macos import hotkeys, startup, voices
from polyglotic_desktop.platform.macos.hotkeys import (
    CONTROL_COMMAND,
    EXISTS,
    KEY_CODES,
    SIGNATURE,
    MacHotkeys,
    Refused,
    combination,
)
from polyglotic_desktop.platform.speaking import Clip
from polyglotic_desktop.ports.speaker import Voice

# --- hotkeys ------------------------------------------------------------------


class FakeCarbon:
    """Carbon's hotkeys as the adapter sees them: `taken` combinations are
    another app's; `press` is macOS calling the handler."""

    def __init__(self, taken: set[tuple[int, int]] = frozenset()) -> None:  # type: ignore[assignment]
        self.taken = taken
        self.registered: dict[int, tuple[int, int, int]] = {}
        self.listeners: list[Callable[[int, int], None]] = []
        self._next = 100

    def listen(self, pressed: Callable[[int, int], None]) -> None:
        self.listeners.append(pressed)

    def quiet(self, pressed: Callable[[int, int], None]) -> None:
        self.listeners.remove(pressed)

    def register(self, key_code: int, modifiers: int, hotkey_id: int) -> int:
        if (key_code, modifiers) in self.taken:
            raise Refused(EXISTS)
        self._next += 1
        self.registered[self._next] = (key_code, modifiers, hotkey_id)
        return self._next

    def unregister(self, ref: int) -> None:
        del self.registered[ref]

    def press(self, key: str, signature: int = SIGNATURE) -> None:
        for ref_key, _modifiers, hotkey_id in self.registered.values():
            if ref_key == KEY_CODES[key]:
                for listener in list(self.listeners):
                    listener(signature, hotkey_id)


def test_the_hotkeys_are_control_command_and_the_letter() -> None:
    carbon = FakeCarbon()
    keys = MacHotkeys(
        {"L": lambda: None, "P": lambda: None, "H": lambda: None}, carbon=carbon
    )
    assert keys.start() == []
    taken = sorted((code, mods) for code, mods, _ in carbon.registered.values())
    assert taken == sorted((KEY_CODES[k], CONTROL_COMMAND) for k in "LPH")
    assert (KEY_CODES["L"], KEY_CODES["P"], KEY_CODES["H"]) == (0x25, 0x23, 0x04)
    assert combination(CONTROL_COMMAND, "L") == "⌃⌘L"


def test_a_pressed_hotkey_calls_its_binding_only() -> None:
    carbon = FakeCarbon()
    pressed: list[str] = []
    keys = MacHotkeys({k: partial(pressed.append, k) for k in "LPH"}, carbon=carbon)
    keys.start()
    carbon.press("P")
    carbon.press("H", signature=hotkeys.four("XXXX"))  # another app's: not ours
    assert pressed == ["P"]


def test_a_combination_another_app_has_is_said_and_the_rest_work(
    caplog: pytest.LogCaptureFixture,
) -> None:
    carbon = FakeCarbon(taken={(KEY_CODES["H"], CONTROL_COMMAND)})
    pressed: list[str] = []
    keys = MacHotkeys({k: partial(pressed.append, k) for k in "LPH"}, carbon=carbon)
    assert keys.start() == ["H"]
    assert "⌃⌘H" in caplog.text  # the log names it, as on Windows (291)
    carbon.press("L")
    assert pressed == ["L"]


def test_two_sets_of_hotkeys_never_call_each_others() -> None:
    """The ids are the process's: a second set's press isn't the first's."""
    carbon = FakeCarbon()
    first: list[str] = []
    second: list[str] = []
    MacHotkeys({"L": lambda: first.append("L")}, carbon=carbon).start()
    MacHotkeys({"P": lambda: second.append("P")}, carbon=carbon).start()
    carbon.press("P")
    assert (first, second) == ([], ["P"])


def test_a_failing_action_doesnt_end_the_hotkeys() -> None:
    carbon = FakeCarbon()
    pressed: list[str] = []

    def fails() -> None:
        raise RuntimeError("an action's bug")

    keys = MacHotkeys({"L": fails, "P": lambda: pressed.append("P")}, carbon=carbon)
    keys.start()
    carbon.press("L")
    carbon.press("P")
    assert pressed == ["P"]


def test_stop_gives_every_hotkey_back() -> None:
    carbon = FakeCarbon()
    keys = MacHotkeys({k: lambda: None for k in "LPH"}, carbon=carbon)
    keys.start()
    keys.stop()
    assert carbon.registered == {} and carbon.listeners == []
    keys.stop()  # twice: nothing more


def test_only_letters_and_digits_are_hotkeys() -> None:
    with pytest.raises(ValueError, match="not a letter or digit"):
        MacHotkeys({"l": lambda: None})  # as Windows': upper case


def test_post_presses_without_a_keyboard() -> None:
    called = threading.Event()
    keys = MacHotkeys({"L": called.set}, carbon=FakeCarbon())
    keys.start()
    keys.post("L")
    assert called.is_set()


def test_the_mac_record_has_its_hotkeys_voices_and_login_item() -> None:
    mac = os_adapters("darwin")
    assert mac.hotkeys is MacHotkeys
    assert mac.start_at_sign_in is startup.LoginItem
    assert mac.speaker is not None


# --- voices -------------------------------------------------------------------


def _listed(
    ident: str, language: str, quality: int = 1, traits: int = 0
) -> voices.Listed:
    return voices.Listed(Voice(ident, ident, language), quality, traits)


def test_novelty_and_personal_voices_are_left_out() -> None:
    found = [
        _listed("bells", "en-US", traits=voices.NOVELTY),
        _listed("me", "en-US", traits=voices.PERSONAL),
        _listed("samantha", "en-US"),
    ]
    assert [v.id for v in voices.ordered(found, [])] == ["samantha"]


def test_the_best_voice_of_a_language_comes_first() -> None:
    """The card says a word in the first voice of its language
    (`views.speech.voice_for`): premium, enhanced, then macOS's own pick."""
    found = [
        _listed("albert", "en-US"),
        _listed("samantha", "en-US"),
        _listed("tingting", "zh-CN"),
        _listed("ava-premium", "en-US", quality=3),
        _listed("lili-enhanced", "zh-CN", quality=2),
    ]
    order = [v.id for v in voices.ordered(found, ["samantha", "tingting"])]
    assert order == ["ava-premium", "lili-enhanced", "samantha", "tingting", "albert"]


@pytest.mark.parametrize(
    ("rate", "av"), [(1.0, 0.5), (0.7, 0.35), (3.0, 1.0), (-1, 0.0)]
)
def test_the_pace_on_macs_scale(rate: float, av: float) -> None:
    assert voices.av_rate(rate) == pytest.approx(av)


def test_a_clip_plays_as_a_wav_file() -> None:
    clip = Clip(b"\x01\x00\xff\x7f" * 10, 22050)
    with wave.open(io.BytesIO(voices.wav_of(clip))) as read:
        assert (read.getframerate(), read.getnchannels(), read.getsampwidth()) == (
            22050,
            1,
            2,
        )
        assert read.readframes(read.getnframes()) == clip.pcm


def test_float_samples_become_16_bit_clipped() -> None:
    pcm = voices.int16_of_floats([0.0, 1.0, -1.0, 2.0])
    assert pcm == b"\x00\x00\xff\x7f\x01\x80\xff\x7f"


# --- the login item -----------------------------------------------------------


class FakeService:
    def __init__(self, status: int = startup.NOT_REGISTERED, refuse: int = 0) -> None:
        self.state = status
        self.refuse = refuse
        self.calls: list[str] = []

    def status(self) -> int:
        return self.state

    def register(self) -> int:
        self.calls.append("register")
        if self.refuse:
            return self.refuse
        self.state = startup.ENABLED
        return 0

    def unregister(self) -> int:
        self.calls.append("unregister")
        self.state = startup.NOT_REGISTERED
        return 0


@pytest.mark.parametrize(
    ("status", "on"),
    [
        (startup.ENABLED, True),
        (startup.REQUIRES_APPROVAL, False),  # waiting in Login Items: not yet
        (startup.NOT_REGISTERED, False),
        (startup.NOT_FOUND, False),
    ],
)
def test_enabled_only_while_macos_says_so(status: int, on: bool) -> None:
    assert (
        startup.LoginItem("/Applications/Polyglotic.app", FakeService(status)).enabled()
        is on
    )


def test_yes_registers_and_no_unregisters() -> None:
    service = FakeService()
    item = startup.LoginItem("x", service)
    item.set_enabled(True)
    assert item.enabled()
    item.set_enabled(False)
    assert not item.enabled() and service.calls == ["register", "unregister"]


def test_no_with_nothing_registered_asks_nothing() -> None:
    service = FakeService()
    startup.LoginItem("x", service).set_enabled(False)
    assert service.calls == []


def test_a_refusal_is_quiet_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    item = startup.LoginItem("x", FakeService(refuse=1))
    item.set_enabled(True)  # no exception: the port's rule
    assert not item.enabled() and "error 1" in caplog.text


def test_the_packed_apps_check_is_refused_off_a_mac(tmp_path: Path) -> None:
    """`--check-parity` would change Windows' Run key and hotkeys: never there."""
    report = tmp_path / "parity.json"
    assert check_parity(report, os_adapters("darwin"), "windows-11") == 1
    found = json.loads(report.read_text(encoding="utf-8"))
    assert found["ok"] is False and "refused" in found["error"]


# --- on a Mac itself ----------------------------------------------------------


@pytest.mark.macos_only
def test_macos_lists_its_voices() -> None:
    """AVFoundation from ctypes (a word made and heard: the parity checks,
    which run macOS's event loop as the app does)."""
    found = voices.MacVoices().found()
    assert found and all(v.id and v.language for v in found)
    assert any(v.language.startswith("en") for v in found)


@pytest.mark.macos_only
def test_macos_takes_and_gives_back_the_hotkeys() -> None:
    """Carbon from ctypes: ⌃⌘L, P and H taken, given back, taken again."""
    for _ in range(2):
        keys = MacHotkeys({k: lambda: None for k in "LPH"})
        assert keys.start() == []
        keys.stop()
