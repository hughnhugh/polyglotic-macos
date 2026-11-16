"""Captions failing on the server (core.listening.failing): said after
FAILING_AFTER finished captions failed in a row, over at the next caption."""

from polyglotic_desktop.core.listening.failing import FAILING_AFTER, FailingCaptions


def test_failing_starts_after_failures_in_a_row_and_is_said_once() -> None:
    failures = FailingCaptions()
    assert FAILING_AFTER == 2
    assert not failures.failed()  # one could be a one-off
    assert not failures.failing
    assert failures.failed()  # two in a row: failing from now
    assert failures.failing
    assert not failures.failed()  # still failing: not said again


def test_a_caption_between_failures_starts_the_count_again() -> None:
    failures = FailingCaptions()
    failures.failed()
    assert not failures.captioned()  # wasn't failing: nothing to end
    assert not failures.failed()
    assert not failures.failing


def test_a_caption_ends_a_failing_time() -> None:
    failures = FailingCaptions()
    failures.failed()
    failures.failed()
    assert failures.captioned()  # the model is back
    assert not failures.failing
    assert not failures.captioned()
