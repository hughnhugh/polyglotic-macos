"""Sound without speech (platform.sound_unheard; polyglotic-hq 549, decision 0256):
the stretches where a source played sound that speech detection never
heard as speech, counted from its frames - and, on recorded songs and
speech under music, how the reset after 5 s (decision 0254) shortens them."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import soundfile as sf

from polyglotic_desktop.core.listening.timing import FRAME_SEC
from polyglotic_desktop.perf.trace import Unheard
from polyglotic_desktop.platform import speech_detection
from polyglotic_desktop.platform.sound_unheard import (
    FLOOR_DBFS,
    MIN_SEC,
    QUIET_SEC,
    SoundUnheard,
    dbfs,
)
from polyglotic_desktop.platform.speech_detection import (
    FrameResult,
    SpeechDetector,
    load_model,
)

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

AUDIO = Path(__file__).parent / "audio"


def _frames(
    start: float,
    seconds: float,
    level_dbfs: float,
    speech: bool = False,
    resets_at: tuple[float, ...] = (),
) -> list[FrameResult]:
    """Frames from `start` for `seconds`, each at `level_dbfs` - reset
    after the frames ending nearest `resets_at`."""
    count = round(seconds / FRAME_SEC)
    ends = [start + (i + 1) * FRAME_SEC for i in range(count)]
    resets = {min(range(count), key=lambda i: abs(ends[i] - at)) for at in resets_at}
    level = 10 ** (level_dbfs / 20)
    return [FrameResult(end, speech, level, i in resets) for i, end in enumerate(ends)]


def _run(tracker: SoundUnheard, frames: list[FrameResult]) -> list[Unheard]:
    found = []
    for frame in frames:
        stretch = tracker.frame(frame)
        if stretch is not None:
            found.append(stretch)
    return found


def test_sound_heard_as_not_speech_then_speech_is_a_stretch() -> None:
    tracker = SoundUnheard("video")
    frames = [
        *_frames(0.0, 2.0, -70.0),  # quiet first: not part of it
        *_frames(2.0, 8.0, -30.0, resets_at=(7.0,)),
        *_frames(10.0, 1.0, -25.0, speech=True),
    ]
    found = _run(tracker, frames)
    assert len(found) == 1
    stretch = found[0]
    assert stretch.source == "video" and stretch.end == "speech"
    assert stretch.began == pytest.approx(2.0, abs=FRAME_SEC)
    assert stretch.ended == pytest.approx(10.0, abs=FRAME_SEC)
    assert stretch.dbfs == (-30, -30, -30)
    assert stretch.resets == 1
    assert stretch.after_reset == pytest.approx(3.0, abs=FRAME_SEC)
    record = stretch.as_json()
    assert record["kind"] == "sound_unheard" and record["len"] == pytest.approx(
        8.0, abs=0.05
    )
    assert set(record) == {
        "kind",
        "src",
        "t",
        "len",
        "dbfs",
        "resets",
        "after_reset",
        "end",
    }


def test_short_dips_under_the_floor_stay_inside_and_a_second_of_quiet_ends_it() -> None:
    """The gaps between a missed speaker's words don't cut the stretch into
    pieces too short to count; a second under the floor ends it at its last
    sound."""
    tracker = SoundUnheard("call")
    frames = []
    at = 0.0
    for _ in range(4):  # 1.5 s of sound, 0.5 s of quiet, four times
        frames += _frames(at, 1.5, -28.0)
        frames += _frames(at + 1.5, 0.5, -60.0)
        at += 2.0
    frames += _frames(at, 2.0, -60.0)
    found = _run(tracker, frames)
    assert len(found) == 1
    assert found[0].end == "quiet"
    assert found[0].began == pytest.approx(0.0, abs=FRAME_SEC)
    assert found[0].ended == pytest.approx(7.5, abs=FRAME_SEC)  # the last sound
    p10, p50, p90 = found[0].dbfs
    assert p10 == -60 and p50 == -28 and p90 == -28  # the dips are in its levels


def test_speech_too_short_to_send_is_part_of_the_stretch() -> None:
    """A moment heard as speech sent nothing either: the stretch goes on.
    Speech enough to send ends it where that speech began."""
    tracker = SoundUnheard("game")
    frames = [
        *_frames(0.0, 4.0, -30.0),
        *_frames(4.0, 0.2, -30.0, speech=True),  # under MIN_SPEECH_SEC
        *_frames(4.2, 4.0, -30.0),
        *_frames(8.2, 1.0, -30.0, speech=True),
    ]
    found = _run(tracker, frames)
    assert [s.end for s in found] == ["speech"]
    assert found[0].ended == pytest.approx(8.2, abs=FRAME_SEC)


def test_three_seconds_or_less_or_quiet_audio_is_not_counted() -> None:
    tracker = SoundUnheard("video")
    frames = [
        *_frames(0.0, MIN_SEC - 0.1, -30.0),
        *_frames(MIN_SEC - 0.1, 1.0, -25.0, speech=True),
        *_frames(10.0, 20.0, FLOOR_DBFS - 3),  # a quiet room: not sound
        *_frames(30.0, 1.0, -25.0, speech=True),
    ]
    assert _run(tracker, frames) == []


def test_one_under_way_is_given_as_it_stands_and_ends_when_the_source_stops() -> None:
    tracker = SoundUnheard("music")
    _run(tracker, _frames(0.0, 2.0, -20.0))
    assert tracker.open() is None  # not over MIN_SEC yet
    _run(tracker, _frames(2.0, 4.0, -20.0))
    going = tracker.open()
    assert going is not None and going.end == "open"
    assert going.seconds == pytest.approx(6.0, abs=FRAME_SEC)
    stopped = tracker.stop()
    assert stopped is not None and stopped.end == "stopped"
    # a capture's last callback after the stop starts nothing
    assert _run(tracker, _frames(6.0, 10.0, -20.0)) == []
    assert tracker.open() is None and tracker.stop() is None


def test_levels_are_dbfs_of_the_root_mean_square() -> None:
    assert dbfs(1.0) == 0.0
    assert dbfs(0.01) == pytest.approx(-40.0)
    assert dbfs(0.0) == dbfs(None) == -120.0
    assert QUIET_SEC < MIN_SEC


# -- recorded audio: the old detector against decision 0254's -----------------


@pytest.fixture(scope="module")
def model() -> "InferenceSession":
    return load_model()


def _stretches(
    model: "InferenceSession",
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    carried: bool,
    bed: bool = True,
) -> list[Unheard]:
    """The stretches of sound without speech in `name`, fed as Windows'
    capture delivers it (10 ms at a time) - with the state carried through
    sound heard as not speech, as before decision 0254, if `carried`; and
    without the lower threshold under a steady bed of sound (decision 0267,
    polyglotic-hq 558) unless `bed`."""
    if carried:
        monkeypatch.setattr(speech_detection, "_QUIET_RESET_FRAMES", 10**9)
    if not bed:
        monkeypatch.setattr(speech_detection, "_BED_HOLD_FRAMES", 10**9)
    audio, rate = sf.read(str(AUDIO / name), dtype="float32")
    assert rate == 16000 and audio.ndim == 1
    detector = SpeechDetector(model)
    tracker = SoundUnheard("music")
    found = []
    for i in range(0, len(audio), 160):
        for frame in detector.feed(i / rate, audio[i : i + 160]):
            stretch = tracker.frame(frame)
            if stretch is not None:
                found.append(stretch)
    last = tracker.stop()
    monkeypatch.undo()
    return [*found, *([last] if last is not None else [])]


@pytest.mark.parametrize(
    ("name", "longest_carried", "longest_afresh"),
    [
        # 梦中的你 (Adeline Yeo, CC BY 4.0), its first 48 s: the carried
        # state heard none of the singing after the first notes
        ("song-zh-mengzhong-0-48.opus", 40.0, 30.0),
        # FLEURS Mandarin with a song's band 5 dB under it: 29 s of the
        # speech went unheard, the length of the user's 28.2 s gap
        ("talk-under-music-zh-236-272.opus", 25.0, 12.0),
    ],
)
def test_the_stretches_show_on_the_old_detector_and_shrink_with_the_reset(
    model: "InferenceSession",
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    longest_carried: float,
    longest_afresh: float,
) -> None:
    """polyglotic-hq 549 (536's CC files, `tests/audio/README.md`): carried
    through the band, one long stretch with nothing heard as speech and no
    reset in it; with the reset, shorter stretches, each with the reset in
    it, and at least one ended by speech heard within a second of it - the
    detector had gone deaf, and the reset brought it back. The reset alone,
    without the bed's lower threshold (0267), which hears some of that
    speech before a reset; the detector with both keeps the stretches as
    short."""
    carried = _stretches(model, name, monkeypatch, carried=True, bed=False)
    afresh = _stretches(model, name, monkeypatch, carried=False, bed=False)
    both = _stretches(model, name, monkeypatch, carried=False)
    assert max(s.seconds for s in both) <= max(s.seconds for s in afresh)

    assert max(s.seconds for s in carried) > longest_carried
    assert all(s.resets == 0 for s in carried)

    assert max(s.seconds for s in afresh) < longest_afresh
    assert sum(s.seconds for s in afresh) < sum(s.seconds for s in carried)
    assert any(
        s.end == "speech" and s.after_reset is not None and s.after_reset <= 1.0
        for s in afresh
    )
    assert all(s.dbfs[0] <= s.dbfs[1] <= s.dbfs[2] <= 0 for s in [*carried, *afresh])
