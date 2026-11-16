"""A pack download's rules: when it's tried again, how far along it is,
and a time left said only when it's honest (decision 0122)."""

from polyglotic_desktop.core.lexicon.pack_download import (
    TRIES,
    PackProgress,
    Problem,
    Rate,
    Step,
    retry_after,
)


def test_a_lost_connection_is_tried_again_further_apart_then_not() -> None:
    waits = [retry_after(n, Problem.OFFLINE) for n in range(1, TRIES + 1)]
    assert waits == [5.0, 15.0, 30.0, 60.0, 120.0, None]
    assert retry_after(1, Problem.STALLED) == 5.0
    assert retry_after(1, Problem.SERVER) == 5.0


def test_what_needs_the_learner_isnt_tried_again_by_itself() -> None:
    for problem in (
        Problem.METERED,
        Problem.NO_ROOM,
        Problem.LIST_REFUSED,
        Problem.FILE_REFUSED,
        Problem.UNREADABLE,
        Problem.NEEDS_NEWER_APP,
        Problem.NOT_OFFERED,
    ):
        assert retry_after(1, problem) is None


def test_stopped_is_a_problem_with_no_try_coming() -> None:
    assert PackProgress("ru", Step.DOWNLOADING, problem=Problem.NO_ROOM).stopped
    waiting = PackProgress("ru", Step.DOWNLOADING, problem=Problem.OFFLINE, retry_in=5)
    assert not waiting.stopped
    assert not PackProgress("ru", Step.DOWNLOADING).stopped


def test_how_far_along() -> None:
    assert PackProgress("ru", Step.DOWNLOADING, 12, 48).share == 0.25
    assert PackProgress("ru", Step.LIST).share == 0.0
    assert PackProgress("ru", Step.DONE).share == 1.0


def test_no_time_left_until_five_seconds_and_a_megabyte_in() -> None:
    rate = Rate()
    for second in range(5):
        rate.add(float(second), second * 1_000_000)
    assert rate.seconds_left(48_000_000) is None  # 4 s in
    rate.add(5.0, 5_000_000)
    assert rate.seconds_left(48_000_000) == 43.0


def test_the_time_left_follows_the_last_ten_seconds() -> None:
    rate = Rate()
    for second in range(20):  # 1 MB/s, then half that
        done = (
            second * 1_000_000 if second < 10 else 10_000_000 + (second - 10) * 500_000
        )
        rate.add(float(second), done)
    left = rate.seconds_left(48_000_000)
    assert left is not None and 55 < left < 65  # about 0.55 MB/s: not the average (0.7)


def test_nothing_arriving_says_no_time_left() -> None:
    rate = Rate()
    for second in range(12):
        rate.add(float(second), 2_000_000 if second else 0)
    assert rate.seconds_left(48_000_000) is None
