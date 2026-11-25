"""Speaking pace uses voiced time, never pauses or processing time."""

from time import perf_counter

from polyglotic_desktop.core.listening.pace import PaceMeter


def test_short_pauses_hold_pace_then_silence_fades_it_linearly() -> None:
    pace = PaceMeter()
    assert pace.now(10.0) == 0
    assert pace.add(10, 2.0, 10.0) == 300
    assert [pace.now(at) for at in (11, 12, 15, 15.5, 17.5, 19, 20, 21)] == [
        300,
        300,
        300,
        270,
        150,
        60,
        0,
        0,
    ]
    assert pace.mean == 300


def test_last_five_seconds_of_speech_and_peak_ignore_wall_clock_gaps() -> None:
    pace = PaceMeter()
    assert pace.add(10, 2.0, 1.0) == 300
    assert pace.add(6, 3.0, 100.0) == 192
    assert pace.add(10, 2.0, 101.0) == 192
    assert pace.peak == 300
    assert pace.mean == round(26 * 60 / 7)


def test_rolling_pace_keeps_exactly_five_voiced_seconds_across_caption_boundaries() -> (
    None
):
    pace = PaceMeter()
    pace.add(3, 1.5, 1.5)  # One second of these two words per second remains.
    assert pace.add(5, 4.0, 10.0) == 84


def test_delayed_answer_does_not_displace_newer_speech_or_restart_its_hold() -> None:
    pace = PaceMeter()
    pace.add(10, 5.0, 10.0)
    pace.add(100, 5.0, 1.0)
    assert pace.now(15.0) == 120
    assert pace.now(17.5) == 60


def test_combined_own_pace_fades_and_leaves_the_other_stream_at_its_own_rate() -> None:
    mic = PaceMeter()
    respoken = PaceMeter()
    mic.add(4, 2.0, 5.0)
    respoken.add(2, 2.0, 0.0)
    combined = mic.reading(12.5).combined(respoken.reading(12.5))
    assert (combined.now, combined.mean) == (60, 90)
    almost = mic.reading(9.99).combined(respoken.reading(9.99))
    expired = mic.reading(10.0).combined(respoken.reading(10.0))
    assert (almost.now, expired.now) == (120, 120)


def test_voiced_seconds_are_banded_without_content() -> None:
    pace = PaceMeter()
    pace.add(2, 2.0, 0.0)
    pace.add(8, 2.0, 1.0)
    assert pace.seconds == {
        "1_60": 2,
        "61_120": 0,
        "121_180": 2,
        "181_240": 0,
        "241_plus": 0,
    }


def test_a_speaking_second_counts_only_when_its_bucket_has_words() -> None:
    pace = PaceMeter()
    pace.add(0, 1.0, 0.0)
    pace.add(1, 1.0, 1.0)
    assert sum(pace.seconds.values()) == 1


def test_add_stays_within_the_point_zero_five_ms_budget() -> None:
    pace = PaceMeter()
    started = perf_counter()
    for n in range(10_000):
        pace.add(3, 0.4, float(n))
    elapsed_ms = (perf_counter() - started) * 1_000 / 10_000
    assert elapsed_ms < 0.05
