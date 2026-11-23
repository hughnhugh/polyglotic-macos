"""Songs mode (core.listening.songs, decision 0287; polyglotic-hq 595,
DECISIONS.md #248): behind the Lyrics switch, a known music player heard
on Detect has sound that goes on unheard sent as speech, a piece at a time.

The rules on frames; the pipeline, which runs only the sources it's told
through songs mode; and the whole on a recorded song - 梦中的你 (CC BY,
tests/audio/README.md) - through the app's own detection and caption
timing: with songs mode the singing is sent with no long quiet, without it
the song goes long stretches with nothing sent.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import pytest
import soundfile as sf
from tests.test_speech_pipeline import FakeCapture, drain

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.songs import (
    SONGS_AFTER_SEC,
    SONGS_PEAK,
    SONGS_SEND_SEC,
    SongsMode,
    heard_as_songs,
)
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SAMPLES,
    MAX_WAIT_FOR_TEXT_SEC,
    ONSET_LEAD_IN_SEC,
    CaptionTiming,
    SpeechKind,
    TranscriptionRequest,
    default_caption_mode,
)
from polyglotic_desktop.platform.speech_detection import (
    Audio,
    FrameResult,
    SpeechDetector,
    load_model,
)
from polyglotic_desktop.platform.speech_pipeline import SpeechPipeline
from polyglotic_desktop.ports.capture import SourceCategory

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

SR = 16000
FRAME = FRAME_SAMPLES / SR
AFTER = int(SONGS_AFTER_SEC / FRAME)
SEND = int(SONGS_SEND_SEC / FRAME)
LOUD = SONGS_PEAK * 4
QUIET = SONGS_PEAK / 4


# --- when ----------------------------------------------------------------------------


def test_only_a_music_player_on_detect_with_the_switch_on() -> None:
    """DECISIONS.md #248's guard: the switch off, another app, or a
    language named - heard as speech only, as before."""
    assert heard_as_songs(True, True, None)
    assert not heard_as_songs(False, True, None)  # the switch off: the default
    assert not heard_as_songs(True, False, None)  # not a music player
    assert not heard_as_songs(True, True, Language("en"))  # kept to Detect


# --- the rules, frame by frame ------------------------------------------------------


def _verdicts(
    songs: SongsMode, frames: Sequence[tuple[bool, float | None]]
) -> list[bool]:
    return [songs.frame(speech, peak) for speech, peak in frames]


def test_off_it_changes_nothing() -> None:
    songs = SongsMode()
    frames = [(False, LOUD)] * (AFTER + SEND) + [(True, LOUD)]
    assert _verdicts(songs, frames) == [s for s, _ in frames]


def test_sound_unheard_is_sent_a_piece_at_a_time() -> None:
    """After SONGS_AFTER_SEC of sound heard as not speech, the next
    SONGS_SEND_SEC is speech; then it counts again from nothing."""
    songs = SongsMode()
    songs.on = True
    heard = _verdicts(songs, [(False, LOUD)] * (2 * (AFTER + SEND)))
    expected = ([False] * AFTER + [True] * SEND) * 2
    assert heard == expected


def test_speech_heard_starts_the_count_again() -> None:
    songs = SongsMode()
    songs.on = True
    frames = (
        [(False, LOUD)] * (AFTER - 1) + [(True, LOUD)] + [(False, LOUD)] * (AFTER - 1)
    )
    assert _verdicts(songs, frames) == [False] * (AFTER - 1) + [True] + [False] * (
        AFTER - 1
    )
    assert not songs.sending


def test_quiet_starts_the_count_again_and_silence_ends_a_piece() -> None:
    """A frame under SONGS_PEAK isn't sound: the count starts again. A
    piece being sent goes on through quiet sound, as a song's does, but
    digital silence - the player paused - ends it."""
    songs = SongsMode()
    songs.on = True
    gap = [(False, LOUD)] * (AFTER - 1) + [(False, QUIET)]
    assert not any(_verdicts(songs, gap * 3))
    _verdicts(songs, [(False, LOUD)] * AFTER)
    assert songs.sending
    assert songs.frame(False, QUIET)  # quiet: still sent
    assert not songs.frame(False, 0.0)  # silence: ended
    assert not songs.sending
    assert not songs.frame(False, None)  # a peak not known is never sound


def test_turned_off_mid_piece_it_stops_at_once() -> None:
    songs = SongsMode()
    songs.on = True
    _verdicts(songs, [(False, LOUD)] * (AFTER + 2))
    songs.on = False
    assert not songs.frame(False, LOUD) and not songs.sending
    songs.on = True  # and starts counting afresh
    assert not any(_verdicts(songs, [(False, LOUD)] * (AFTER - 1)))


# --- the pipeline --------------------------------------------------------------------

MUSIC = Source(SourceId("music"), SourceCategory.MUSIC)
VIDEO = Source(SourceId("video"), SourceCategory.VIDEO)


class MusicDetector:
    """Hears nothing as speech - singing under a band, as Silero hears it -
    and gives each frame's peak as the real detector does."""

    def __init__(self) -> None:
        self._leftover = np.zeros(0, dtype=np.float32)

    def feed(self, start: float, audio: Audio) -> list[FrameResult]:
        buffer = np.concatenate([self._leftover, audio])
        count = len(buffer) // FRAME_SAMPLES
        self._leftover = buffer[count * FRAME_SAMPLES :]
        first_end = start + (FRAME_SAMPLES - (len(buffer) - len(audio))) / SR
        frames = buffer[: count * FRAME_SAMPLES].reshape(count, FRAME_SAMPLES)
        return [
            FrameResult(
                first_end + i * FRAME,
                False,
                float(np.sqrt(np.mean(np.square(frame)))),
                peak=float(np.max(np.abs(frame))),
            )
            for i, frame in enumerate(frames)
        ]


def _band(seconds: float) -> Audio:
    rng = np.random.default_rng(2)
    return (rng.uniform(-0.3, 0.3, int(seconds * SR))).astype(np.float32)


def _finished(pipeline: SpeechPipeline) -> list[TranscriptionRequest]:
    return [
        d
        for d, _ in drain(pipeline)
        if isinstance(d, TranscriptionRequest) and d.kind is SpeechKind.FINISHED
    ]


@pytest.mark.parametrize("named", [False, True])
def test_the_pipeline_sends_a_song_only_from_the_sources_it_is_told(
    named: bool,
) -> None:
    """20 s of a band no speech is heard in: a source named in songs mode
    (`set_songs`) sends pieces of it; the same audio from any other
    source - or the same source, not named - sends nothing."""
    pipeline = SpeechPipeline(MusicDetector, CaptionTiming(None))
    if named:
        pipeline.set_songs(frozenset({MUSIC.id}))
    pipeline.add_source(MUSIC, FakeCapture(_band(20.0)))
    pipeline.add_source(VIDEO, FakeCapture(_band(20.0)))
    sent = _finished(pipeline)
    assert all(r.source.id == MUSIC.id for r in sent)
    if not named:
        assert sent == []
        return
    # one piece in every SONGS_AFTER_SEC + SONGS_SEND_SEC, each about
    # SONGS_SEND_SEC long with the timing's lead-in (ONSET_LEAD_IN_SEC);
    # the last may still be under way at the end
    assert len(sent) >= int(20.0 / (SONGS_AFTER_SEC + SONGS_SEND_SEC))
    for r in sent:
        length = r.speech_end - r.speech_start
        assert SONGS_SEND_SEC - 0.1 < length < SONGS_SEND_SEC + ONSET_LEAD_IN_SEC + 0.1


# --- a recorded song, through the app's own detection and timing -------------------

AUDIO = Path(__file__).parent / "audio"
SONG = "song-zh-mengzhong-0-48.opus"
"""梦中的你 (Adeline Yeo, CC BY 4.0), its first 48 s: sung under a band."""
BED = "music-bed-rock-558.opus"
"""30 s of a rock instrumental (Josh Woodward's NoVox, CC BY 4.0)."""


@pytest.fixture(scope="module")
def model() -> "InferenceSession":
    return load_model()


def _read(name: str) -> npt.NDArray[np.float32]:
    audio, rate = sf.read(str(AUDIO / name), dtype="float32")
    assert rate == SR
    return np.asarray(audio, dtype=np.float32)


def _sent(
    model: "InferenceSession", audio: npt.NDArray[np.float32], songs: bool
) -> list[tuple[float, float]]:
    """What the app sends of `audio` as finished captions (its detection,
    songs mode on or off, and the default caption timing): each caption's
    audio, start and end (s)."""
    mode = default_caption_mode()
    timing = CaptionTiming(
        mode.live_update_interval(1.0), rules=mode.rules, max_wait=MAX_WAIT_FOR_TEXT_SEC
    )
    source = Source(SourceId("music"), SourceCategory.MUSIC)
    timing.add_source(source)
    detector = SpeechDetector(model)
    stage = SongsMode()
    stage.on = songs
    finished: dict[str, tuple[float, float]] = {}
    audio = np.concatenate([audio, np.zeros(3 * SR, np.float32)])
    for start in range(0, len(audio), SR // 10):
        for r in detector.feed(start / SR, audio[start : start + SR // 10]):
            speech = stage.frame(r.speech, r.peak)
            for d in timing.frame(source.id, r.end, speech, r.level):
                if (
                    isinstance(d, TranscriptionRequest)
                    and d.kind is not SpeechKind.LIVE
                ):
                    for old in d.replaces:
                        finished.pop(old, None)
                    before, after = d.pads
                    finished[d.caption_id] = (
                        d.speech_start - before,
                        d.speech_end + after,
                    )
    return sorted(finished.values())


def _longest_quiet(sent: list[tuple[float, float]], seconds: float) -> float:
    """The longest stretch of the file with nothing sent (s)."""
    ends = [0.0, *(b for _, b in sent)]
    starts = [*(a for a, _ in sent), seconds]
    return max(max(0.0, s - e) for e, s in zip(ends, starts, strict=True))


def test_a_band_alone_is_sent_only_in_songs_mode(model: "InferenceSession") -> None:
    """30 s of a rock instrumental (558's bed): with songs mode off - every
    app, and a music player with the switch off - nothing is sent, as
    before (DECISIONS.md #248's guard); in songs mode a piece in every
    SONGS_AFTER_SEC + SONGS_SEND_SEC, so never a long stretch with nothing
    sent (on Detect live's model wrote nothing for such pieces: 558)."""
    bed = _read(BED)
    seconds = len(bed) / SR
    assert _sent(model, bed, songs=False) == []
    songs = _sent(model, bed, songs=True)
    assert _longest_quiet(songs, seconds) < SONGS_AFTER_SEC + SONGS_SEND_SEC + 1.0
    assert sum(b - a for a, b in songs) > seconds / 4


def test_a_song_is_sent_with_no_long_quiet_in_songs_mode(
    model: "InferenceSession",
) -> None:
    """梦中的你's first 48 s: in songs mode more of the song goes to the
    speech model than without, and no stretch with nothing sent is much
    longer than a count and a piece (a blip of speech too short to send
    starts the count again: about 8 s here, as 558 measured)."""
    song = _read(SONG)
    seconds = len(song) / SR
    plain = _sent(model, song, songs=False)
    songs = _sent(model, song, songs=True)
    assert sum(b - a for a, b in songs) > sum(b - a for a, b in plain) + 3.0
    assert _longest_quiet(songs, seconds) < SONGS_AFTER_SEC + SONGS_SEND_SEC + 2.0
