"""Recorded words (decision 0133): a language's commonest words spoken ahead
of time - the build that makes the file, the file, and the speaker's
voices over it and the PC's own."""

import math
from pathlib import Path
from typing import Any

import pytest
from tools.dictionaries import audio

from polyglotic_desktop.adapters.audio_file import (
    NotAnAudioFile,
    SqliteAudio,
    audio_beside,
)
from polyglotic_desktop.platform.recorded_voices import (
    RecordedVoices,
    Recordings,
    clip_of_ogg,
)
from polyglotic_desktop.platform.speaking import Clip, Made
from polyglotic_desktop.ports.speaker import RECORDED, Voice
from polyglotic_desktop.ui_next.word_speech import WordSpeech

RATE = 24000
HORTENSE = Voice("os-fr", "Microsoft Hortense", "fr-FR")
ZIRA = Voice("os-en", "Microsoft Zira", "en-US")


def tone(word: str) -> tuple[Any, int]:
    """A "voice": half a second of tone, its pitch the word's length, with
    silence around it - or nothing at all for "rien"."""
    import numpy

    if word == "rien":
        return numpy.zeros(RATE // 2, dtype="float32"), RATE
    quiet = numpy.zeros(RATE // 4, dtype="float32")
    t = numpy.arange(RATE // 2) / RATE
    sound = (0.4 * numpy.sin(2 * math.pi * 100 * len(word) * t)).astype("float32")
    return numpy.concatenate([quiet, sound, quiet]), RATE


def built(folder: Path, name: str = "wiktfr.audio", **info: str) -> Path:
    head, clips, _ = audio.record(["homme", "Paris", "rien"], tone)
    folder.mkdir(exist_ok=True)
    facts = {"dictionary": "wiktfr", "language": "fr", "voice_language": "fr-FR"}
    audio.write_audio(folder / name, {**facts, **info}, head, clips)
    return folder / name


class OsVoices:
    """The PC's voices: each says a word as one second of silence."""

    def __init__(self, *voices: Voice) -> None:
        self.voices = voices
        self.asked: list[tuple[str, str, float]] = []

    def found(self) -> tuple[Voice, ...]:
        return self.voices

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        self.asked.append((text, voice.id, rate))
        return Clip(b"\0\0" * 16000, 16000)


def test_words_are_recorded_cut_and_kept_with_one_shared_start(tmp_path: Path) -> None:
    head, clips, seconds = audio.record(["homme", "Paris", "rien"], tone)
    assert [word for word, _ in clips] == ["homme", "Paris"]  # "rien": no sound
    # about 870 bytes: the comment page names the encoder, so it varies by build
    assert 400 < len(head) < 2000 and head.startswith(b"OggS")
    assert 1.1 < seconds < 1.3  # two words of 0.5 s, a little silence kept
    file = SqliteAudio(built(tmp_path))
    assert file.info["words"] == "2" and file.info["codec"] == "ogg-opus"
    whole = file.clip("homme")
    assert whole is not None and whole.startswith(head)
    clip = clip_of_ogg(whole)
    assert clip.rate == RATE and clip.channels == 1 and 0.55 < clip.seconds < 0.65
    assert file.clip("Homme") == whole  # as written first, then in lower case
    assert file.clip("Paris") is not None and file.clip("femme") is None
    file.close()
    assert file.clip("homme") is None  # closed: never an error


def test_an_ogg_stream_that_isnt_one_is_refused() -> None:
    with pytest.raises(ValueError, match="Ogg"):
        audio.ogg_pages(b"RIFF" + b"\0" * 100)
    with pytest.raises(OSError):
        clip_of_ogg(b"not sound")


def test_the_file_is_about_the_size_of_its_sound(tmp_path: Path) -> None:
    """405: 10,000 clips of ~2.6 kB took 40 MB for 26 MB of sound on
    SQLite's 4 kB pages - one clip a page. The file is downloaded."""
    clips = [(f"w{n:05d}", bytes([n % 251]) * 2600) for n in range(3000)]
    path = tmp_path / "wiktfr.audio"
    audio.write_audio(path, {"dictionary": "wiktfr"}, b"head", clips)
    sound = sum(len(clip) for _, clip in clips)
    assert path.stat().st_size < sound * 1.15
    file = SqliteAudio(path)
    assert file.clip("w02999") == b"head" + bytes([2999 % 251]) * 2600
    file.close()


def test_another_kind_of_file_isnt_read_and_the_newest_is(tmp_path: Path) -> None:
    (tmp_path / "wiktfr-junk.audio").write_bytes(b"junk" * 500)
    with pytest.raises(NotAnAudioFile):
        SqliteAudio(tmp_path / "wiktfr-junk.audio")
    built(tmp_path, "wiktfr-2026.11.15.audio", version="2026.11.15")
    built(tmp_path, "wiktfr-2026.11.20.audio", version="2026.11.20")
    built(tmp_path, "wiktfr-other.audio", version="2027.1.1", dictionary="wiktes")
    found = audio_beside([tmp_path / "none", tmp_path], "wiktfr")
    assert found is not None and found.info["version"] == "2026.11.20"
    found.close()
    assert audio_beside([tmp_path], "wiktru") is None


def rate(made: Made) -> int:
    """A sound's rate: a recording is always a sound, never said by a
    voice itself (591)."""
    assert isinstance(made, Clip)
    return made.rate


def test_a_recorded_word_is_played_and_the_rest_fall_to_the_pcs_voice(
    tmp_path: Path,
) -> None:
    recordings = Recordings()
    file = SqliteAudio(built(tmp_path))
    recordings.use("fr", "fr-FR", "Kokoro", file)
    os_voices = OsVoices(ZIRA, HORTENSE)
    voices = RecordedVoices(os_voices, recordings)
    ours = voices.found()[0]
    assert ours == Voice(f"{RECORDED}fr", "Kokoro", "fr-FR")
    assert voices.found()[1:] == (ZIRA, HORTENSE)  # ours first
    assert recordings.has(ours, "homme") and not recordings.has(ours, "femme")
    # recorded: played, the PC's voice not asked
    assert rate(voices.synthesize("homme", ours, 1.0)) == RATE and not os_voices.asked
    # at any pace: the recording, never the PC's voice (518: the same sound
    # at every press)
    assert rate(voices.synthesize("homme", ours, 0.7)) == RATE and not os_voices.asked
    # not recorded: the PC's French voice
    voices.synthesize("femme", ours, 1.0)
    assert os_voices.asked == [("femme", "os-fr", 1.0)]
    # a PC with no French voice: the recording at its own pace; nothing for the rest
    alone = RecordedVoices(OsVoices(ZIRA), recordings)
    assert rate(alone.synthesize("homme", ours, 0.7)) == RATE
    with pytest.raises(OSError):
        alone.synthesize("femme", ours, 1.0)
    # the pack removed: its voice goes
    recordings.use("fr", "", "", None)
    assert voices.found() == (ZIRA, HORTENSE)
    with pytest.raises(OSError):
        alone.synthesize("homme", ours, 1.0)
    file.close()


class Speaker:
    def __init__(self, *voices: Voice) -> None:
        self.installed = voices

    def voices(self) -> tuple[Voice, ...]:
        return self.installed


def test_the_card_takes_the_recording_for_a_word_it_has_else_the_pcs_voice(
    tmp_path: Path, qapp: object
) -> None:
    """A word nothing can say - not recorded, no voice of its language -
    shows as that, not as a button that stays silent."""
    recordings = Recordings()
    file = SqliteAudio(built(tmp_path))
    recordings.use("fr", "fr-FR", "Kokoro", file)
    ours = Voice(f"{RECORDED}fr", "Kokoro", "fr-FR")
    no_french = WordSpeech(Speaker(ours, ZIRA), recorded=recordings.has)  # type: ignore[arg-type]
    assert no_french.voice("fr", "homme") == ours
    assert no_french.voice("fr", "femme") is None
    assert no_french.voice("en", "house") == ZIRA
    french = WordSpeech(Speaker(ours, HORTENSE), recorded=recordings.has)  # type: ignore[arg-type]
    assert french.voice("fr", "homme") == ours
    assert french.voice("fr", "femme") == HORTENSE
    for speech in (no_french, french):
        speech.deleteLater()
    file.close()


def test_recordings_that_arrive_while_running_are_said_from_the_next_card(
    tmp_path: Path, qapp: object
) -> None:
    """A pack's recordings that arrive while the app runs (`PackDelivery.record`)
    are said from the next card: the speaker's list of voices is kept a few
    seconds and was read before they came, so the card asks the recordings
    themselves (polyglotic-hq 453: the first card after Spanish's arrived said
    "no voice", or would have used Windows' voice). A removed pack's voice
    goes at once too."""
    recordings = Recordings()
    ours = Voice(f"{RECORDED}fr", "Kokoro", "fr-FR")
    # the speaker's lists, read before the recordings came (or, last, after they went)
    live = {"recorded": recordings.has, "recorded_voices": recordings.voices}
    french = WordSpeech(Speaker(HORTENSE), **live)  # type: ignore[arg-type]
    no_french = WordSpeech(Speaker(ZIRA), **live)  # type: ignore[arg-type]
    gone = WordSpeech(Speaker(ours, HORTENSE), **live)  # type: ignore[arg-type]
    assert (
        french.voice("fr", "homme") == HORTENSE
        and no_french.voice("fr", "homme") is None
    )
    file = SqliteAudio(built(tmp_path))
    recordings.use("fr", "fr-FR", "Kokoro", file)  # they arrive
    assert french.voice("fr", "homme") == ours  # the recording, not Windows' voice
    assert french.voice("fr", "femme") == HORTENSE  # not recorded: the PC's
    assert no_french.voice("fr", "homme") == ours  # not "no voice"
    recordings.use("fr", "", "", None)  # the pack removed
    assert gone.voice("fr", "homme") == HORTENSE
    for speech in (french, no_french, gone):
        speech.deleteLater()
    file.close()
