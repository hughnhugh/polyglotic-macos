"""Windows' own voices (`platform.windows.voices`, polyglotic-hq 286): listed
through WinRT, a word made into sound and its samples checked, the pace
applied, and the output's format asked without opening a device. Nothing is
played - the PC's speakers are never used by a test."""

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.recorded_voices import Recordings
from polyglotic_desktop.platform.speaking import SILENT, SpeakerThread, trimmed
from polyglotic_desktop.platform.windows.voices import WindowsVoices, can_play
from polyglotic_desktop.ports.speaker import Voice


@pytest.fixture(scope="module")
def voices() -> WindowsVoices:
    return WindowsVoices()


@pytest.fixture(scope="module")
def found(voices: WindowsVoices) -> tuple[Voice, ...]:
    listed = voices.found()
    if not listed:
        pytest.skip("this Windows has no voices installed")
    return listed


def test_the_voices_are_listed_with_their_languages(found: tuple[Voice, ...]) -> None:
    for voice in found:
        assert voice.id and voice.name
        assert "-" in voice.language  # a BCP 47 tag: "en-US", "zh-CN"
    assert len({v.id for v in found}) == len(found)


def test_a_word_is_made_into_sound_and_slower_is_longer(
    voices: WindowsVoices, found: tuple[Voice, ...]
) -> None:
    voice = found[0]
    word = {"zh": "你好", "vi": "xin chào"}.get(voice.language[:2], "hello")
    normal = voices.synthesize(word, voice, 1.0)
    slower = voices.synthesize(word, voice, 0.7)
    assert normal.rate >= 8000 and normal.channels == 1
    assert 0.2 < normal.seconds < 3.0
    assert max(abs(s) for s in memoryview(normal.pcm).cast("h")) > SILENT * 3
    assert slower.seconds > normal.seconds * 1.2
    cut = trimmed(normal)
    assert cut.seconds < normal.seconds  # the voice's silence before it, cut
    assert can_play(cut)  # a format query: nothing opened, nothing played


def test_a_voice_that_isnt_installed_fails_as_an_os_error(
    voices: WindowsVoices,
) -> None:
    with pytest.raises(OSError):
        voices.synthesize("hello", Voice("no-such-voice", "Nobody", "en-US"), 1.0)


def test_main_hands_over_windows_speaker() -> None:
    windows_speaker = os_adapters().speaker
    assert windows_speaker is not None
    speaker = windows_speaker(Recordings())
    try:
        assert isinstance(speaker, SpeakerThread)
    finally:
        speaker.close()
