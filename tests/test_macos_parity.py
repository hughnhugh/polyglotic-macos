"""The Mac's hotkeys, voices and login item (polyglotic-hq 428): each one's
logic on any OS, through fakes of Carbon and ServiceManagement; what
touches macOS itself is `macos_only` (the macOS job's tests part), and
tools/macos_parity_checks.py presses the keys, hears the voice and has
the packed app add itself to the login items on GitHub's Mac (only a
bundle can be a login item: from source macOS has nothing to say)."""

import ctypes
import io
import json
import threading
import wave
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import ClassVar, cast

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


@pytest.mark.parametrize("status", [startup.NOT_REGISTERED, startup.NOT_FOUND])
def test_no_with_nothing_registered_asks_nothing(status: int) -> None:
    """GitHub's Mac said NOT_FOUND (3) for an app never added (2026-11-17)."""
    service = FakeService(status)
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


class FakeBuffers:
    """`objc.send` as an AVAudioPCMBuffer answers it: `frames` samples of
    float32, mono, or the format given."""

    def __init__(self, samples: list[float], common: int = voices.FLOAT32) -> None:
        self.samples = (ctypes.c_float * max(1, len(samples)))(*samples)
        first = ctypes.cast(self.samples, ctypes.POINTER(ctypes.c_float))
        self.channels = (ctypes.POINTER(ctypes.c_float) * 1)(first)
        self.frames = len(samples)
        self.common = common

    def __call__(
        self, _receiver: object, selector: str, *args: object, **types: object
    ) -> object:
        answers: dict[str, object] = {
            "frameLength": self.frames,
            "format": 1,
            "commonFormat": self.common,
            "sampleRate": 22050.0,
            "channelCount": 1,
            "isInterleaved": False,
            "floatChannelData": ctypes.cast(
                self.channels, ctypes.POINTER(ctypes.POINTER(ctypes.c_float))
            ),
        }
        return answers[selector]


def test_a_words_buffers_become_a_clip(monkeypatch: pytest.MonkeyPatch) -> None:
    made = voices._Made()
    monkeypatch.setattr(voices.objc, "send", FakeBuffers([0.0, 1.0, -1.0]))
    made.add(1)
    monkeypatch.setattr(voices.objc, "send", FakeBuffers([]))
    made.add(1)  # macOS's empty buffer: the word is over
    assert made.ended and made.done.is_set() and made.problem is None
    assert made.parts == [b"\x00\x00\xff\x7f\x01\x80"] and made.rate == 22050
    assert made.formats == {"1/22050.0/1/n"}


def test_a_buffer_it_cant_read_ends_the_wait_but_not_macos_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run that crashed (2026-11-17, GitHub's Mac): a word given up on
    let its block go while macOS still called it. A problem now ends the
    wait, but the word isn't over until macOS's empty buffer - the block
    is kept until then (`MacVoices._blocks`)."""
    made = voices._Made()
    monkeypatch.setattr(voices.objc, "send", FakeBuffers([0.5], common=2))  # Float64
    made.add(1)
    assert made.done.is_set() and not made.ended
    assert made.problem is not None and "format 2" in made.problem
    monkeypatch.setattr(voices.objc, "send", FakeBuffers([0.5]))
    made.add(1)  # more of the same word: not wanted, never a crash
    assert made.parts == [] and not made.ended


class FakeBlock:
    made: ClassVar[list["FakeBlock"]] = []

    def __init__(self, call: Callable[[int], None]) -> None:
        self.call = call
        FakeBlock.made.append(self)


def test_every_word_is_made_with_one_block_that_lives_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub's Mac, 2026-11-17: each word had a block of its own, freed
    once the word was over - and macOS, releasing it later, crashed the
    next word (SIGSEGV on its own thread, twice). One block now serves
    every word; one macOS may still call is retired with its own word."""
    FakeBlock.made = []
    monkeypatch.setattr(voices.objc, "Block", FakeBlock)
    speech = voices.MacVoices()
    first, second = voices._Made(), voices._Made()
    block = cast(FakeBlock, speech._block_for(first))
    first.ended = True
    speech._done_with(first)
    assert speech._block_for(second) is block and len(FakeBlock.made) == 1
    delivered: list[int] = []
    monkeypatch.setattr(second, "add", delivered.append)
    block.call(7)  # a buffer: the word being made now gets it
    assert delivered == [7]

    speech._done_with(second)  # given up on before its last buffer
    third = voices._Made()
    assert speech._block_for(third) is not block  # a new block for a new word
    block.call(8)  # the old one still calls into its own word, kept alive
    assert delivered == [7, 8] and speech._retired[0][0] is block


class FakeVoiceLookup:
    """`AVSpeechSynthesisVoice` as GitHub's Mac answered a running process on
    2026-11-17 (polyglotic-hq 452): its voices changed, and the id it had
    given Samantha was known neither by id nor in its list. `known` are
    the ids `voiceWithIdentifier:` still gives; `listed` the voices
    `speechVoices` names now (object: id, name, language); `usual` the
    voice `voiceWithLanguage:` gives (0: none)."""

    def __init__(
        self,
        known: dict[str, int],
        listed: dict[int, tuple[str, str, str]],
        usual: int = 0,
    ) -> None:
        self.known = known
        self.listed = listed
        self.usual = usual
        self.asked: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        strings: dict[int, str] = {}

        def string(value: str) -> int:
            strings[1000 + len(strings)] = value
            return 999 + len(strings)

        self.strings = strings
        monkeypatch.setattr(voices.objc, "cls", lambda name: 1)
        monkeypatch.setattr(voices.objc, "string", string)
        monkeypatch.setattr(voices.cf, "release", lambda ref: None)
        monkeypatch.setattr(voices.objc, "send", self.send)
        monkeypatch.setattr(voices.objc, "items", lambda array: list(self.listed))
        monkeypatch.setattr(voices.objc, "text", lambda ref: ref)

    def send(
        self, receiver: object, selector: str, *args: object, **_: object
    ) -> object:
        self.asked.append(selector)
        if selector == "voiceWithIdentifier:":
            return self.known.get(self.strings[cast(int, args[0])])
        if selector == "voiceWithLanguage:":
            return self.usual
        if selector == "speechVoices":
            return 7
        fields = {"identifier": 0, "name": 1, "language": 2}
        return self.listed[cast(int, receiver)][fields[selector]]


SAMANTHA = Voice("com.apple.voice.compact.en-US.Samantha", "Samantha", "en-US")


def test_a_voice_macos_still_knows_is_asked_for_by_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = FakeVoiceLookup({SAMANTHA.id: 55}, {})
    lookup.install(monkeypatch)
    assert voices.av_voice(SAMANTHA) == 55
    assert lookup.asked == ["voiceWithIdentifier:"]


def test_a_voice_whose_id_macos_changed_is_found_by_name_and_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub's Mac, 2026-11-17: macOS's voices changed under the process
    (165 listed, a second later 180) and Samantha's id was gone by id and
    from the list - the word ended unsaid. The same voice is used under its
    new id."""
    listed = {
        101: ("com.apple.voice.compact.en-GB.Daniel", "Daniel", "en-GB"),
        102: ("com.apple.voice.compact.en-AU.Samantha", "Samantha", "en-AU"),
        103: ("com.apple.voice.premium.en-US.Samantha", "Samantha", "en-US"),
    }
    lookup = FakeVoiceLookup({}, listed, usual=101)
    lookup.install(monkeypatch)
    assert voices.av_voice(SAMANTHA) == 103


def test_a_voice_gone_from_macos_gives_way_to_its_languages_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = FakeVoiceLookup({}, {}, usual=101)
    lookup.install(monkeypatch)
    assert voices.av_voice(SAMANTHA) == 101
    assert lookup.strings[max(lookup.strings)] == "en-US"  # asked for its language
    nothing = FakeVoiceLookup({}, {}, usual=0)
    nothing.install(monkeypatch)
    assert voices.av_voice(SAMANTHA) is None
