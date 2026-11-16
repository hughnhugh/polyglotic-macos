"""The macOS job's capture part (polyglotic-hq 412): how it judges what a
capture heard, its verdicts and its plan - here on any OS; the captures
themselves run on GitHub's macOS machine (.github/workflows/macos.yml)."""

from pathlib import Path

import numpy as np
import pytest

from polyglotic_desktop.platform.macos.capture import Format, Resampler, mono_float
from polyglotic_desktop.platform.replay import read_clip
from polyglotic_desktop.platform.sample import sample_file
from tools import macos_capture_checks as checks


def through_a_tap(audio: np.ndarray, rate: int = 16_000) -> np.ndarray:
    """`audio` as a tap delivers it: played at 48kHz in stereo, mixed down
    and resampled to 16kHz in 10 ms pieces, as capture.py does."""
    up = np.interp(
        np.arange(round(len(audio) * 48_000 / rate)) * (rate / 48_000),
        np.arange(len(audio)),
        audio,
    ).astype(np.float32)
    stereo = np.repeat(up, 2).astype("<f4").tobytes()
    form = Format(48_000.0, 2)
    resampler = Resampler(48_000.0)
    out = [
        resampler(mono_float(stereo[i : i + 480 * 8], form))
        for i in range(0, len(stereo), 480 * 8)
    ]
    return np.concatenate(out)


def fleurs() -> np.ndarray:
    sample = sample_file("zh")
    assert sample is not None
    return np.asarray(read_clip(sample), dtype=np.float32)


def test_a_capture_of_the_clip_follows_its_loudness_and_noise_does_not() -> None:
    """411's check 4: "compare the energy envelope with the clip". The tap
    starts at an unknown moment, so a stretch of it is matched anywhere in
    what played."""
    clip = fleurs()
    heard = np.concatenate([np.zeros(8_000, np.float32), through_a_tap(clip[40_000:])])
    played = checks.envelope(clip, 16_000)
    assert checks.likeness(checks.envelope(heard, 16_000), played) >= 0.9
    noise = np.random.default_rng(4).normal(0, 0.1, len(heard)).astype(np.float32)
    assert checks.likeness(checks.envelope(noise, 16_000), played) < checks.LIKE
    assert checks.likeness(np.zeros(100), played) == 0.0


def test_a_short_stretch_of_a_looped_clip_is_found_in_the_loop() -> None:
    """The global, device and mic taps listen 10 s to the clip looped."""
    clip = fleurs()
    loop = checks.looped(clip, 16_000, 90)
    assert len(loop) == 90 * 16_000
    stretch = through_a_tap(loop[33 * 16_000 : 43 * 16_000])
    like = checks.likeness(
        checks.envelope(stretch, 16_000), checks.envelope(loop, 16_000)
    )
    assert like >= 0.9


def test_each_players_tone_is_told_apart_after_the_tap() -> None:
    """411's check 6: the first player's 1kHz, the second's 3kHz."""
    both = checks.tone(1000, 2) * 0 + checks.tone(3000, 2)
    heard = through_a_tap(both, 48_000)
    low, high = (checks.tone_level(heard, 16_000, hz) for hz in checks.TONES)
    assert high == pytest.approx(0.3, abs=0.03)
    assert low < 0.005
    assert checks.everything_else_verdict(False, low, high, True)[0] == checks.PASS
    assert checks.everything_else_verdict(False, high, high, True)[0] == checks.FAIL


def test_two_players_core_audio_calls_one_app_must_both_be_left_out() -> None:
    """Two copies of one app (one bundle ID) are one app to Polyglotic, so
    everything else leaves both out; and with no tap yet heard in the run,
    silence proves nothing."""
    assert checks.everything_else_verdict(True, 0.0, 0.001, True)[0] == checks.PASS
    assert checks.everything_else_verdict(True, 0.0, 0.2, True)[0] == checks.FAIL
    assert checks.everything_else_verdict(False, 0.0, 0.0, False)[0] == checks.UNKNOWN


@pytest.mark.parametrize(
    ("peak", "like", "error", "outcome"),
    [
        (0.3, 0.95, None, checks.PASS),
        (0.3, 0.95, "The app has closed.", checks.PASS),  # afplay finished
        (0.3, 0.2, None, checks.FAIL),  # sound, but not the clip's
        (0.0, None, None, checks.FAIL),
        (0.0, None, "not allowed", checks.UNKNOWN),  # the grant wasn't honoured
        (0.3, 0.95, "Couldn't start the tap: OSError", checks.FAIL),
    ],
)
def test_a_capture_of_something_playing_is_judged(
    peak: float, like: float | None, error: str | None, outcome: str
) -> None:
    assert checks.heard_verdict(peak, like, error)[0] == outcome


@pytest.mark.parametrize(
    ("peak", "after", "playing", "outcome"),
    [
        (0.0, 10.6, True, checks.PASS),  # 411's 5: within about 11 s
        (0.0, 14.0, True, checks.FAIL),
        (0.0, None, True, checks.FAIL),  # zeros, and never said
        (0.2, None, True, checks.UNKNOWN),  # the rows' removal didn't take
        (0.0, None, False, checks.UNKNOWN),  # no tap was opened
    ],
)
def test_the_permission_taken_away_must_be_said_within_about_eleven_seconds(
    peak: float, after: float | None, playing: bool, outcome: str
) -> None:
    assert checks.not_allowed_verdict(peak, after, playing, None)[0] == outcome


def test_the_clocks_drift_is_a_slope_and_restarts_are_counted() -> None:
    """411's check 9: 5 ms a minute, seen through jitter, after the first
    seconds."""
    rng = np.random.default_rng(9)
    lags = [
        (t, 0.1 + 0.005 * t / 60 + rng.normal(0, 0.002))
        for t in np.arange(0, 180, 0.01)
    ]
    assert checks.drift_ms_a_minute(lags) == pytest.approx(5.0, abs=0.2)
    assert checks.drift_ms_a_minute(lags[:100]) is None  # all inside the settling
    assert checks.drift_verdict(True, 3, 3.0)[0] == checks.PASS
    assert checks.drift_verdict(True, 30, 3.0)[0] == checks.FAIL
    assert checks.drift_verdict(False, 0, 3.0)[0] == checks.UNKNOWN


def test_only_a_fail_fails_the_job() -> None:
    unknown = checks.Result("mic", checks.UNKNOWN, "")
    passed = checks.Result("apps", checks.PASS, "")
    assert checks.exit_code([unknown, passed]) == 0
    assert checks.exit_code([unknown, checks.Result("drift", checks.FAIL, "")]) == 1
    found = checks.report([unknown, passed], {"macos": "26.1"})
    assert found["summary"] == {"pass": 1, "fail": 0, "unknown": 1}
    assert found["checks"][0] == {"check": "mic", "outcome": "unknown", "said": "",
                                  "facts": {}}  # fmt: skip


def test_the_permission_is_taken_away_last_and_the_packed_app_only_when_given(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A granted answer macOS may remember mustn't come after the denied
    check, so the denied one is last."""
    assert checks.main(["out.json", "--dry-run", "--app", "dist/Polyglotic.app"]) == 0
    steps = capsys.readouterr().out.splitlines()
    assert steps[-1].startswith("not_allowed:")
    assert any(s.startswith("packed:") for s in steps)
    assert not any(s.startswith("packed:") for s in checks.plan(None, 3))
    assert not [s for s in steps if s.startswith(("killall", "pkill"))]


@pytest.mark.skipif(__import__("sys").platform == "darwin", reason="runs it on a Mac")
def test_off_a_mac_it_runs_nothing(tmp_path: Path) -> None:
    assert checks.main([str(tmp_path / "out.json")]) == 2
    assert not (tmp_path / "out.json").exists()
