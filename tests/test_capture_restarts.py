"""A capture's waits between tries after it failed, and how its errors are
logged (polyglotic-hq 557, decision 0266). Plain numbers."""

from polyglotic_desktop.platform.capture_restarts import (
    FIRST_SEC,
    MAX_SEC,
    RESET_AFTER_SEC,
    Backoff,
    why,
)


def test_the_wait_doubles_from_the_first_up_to_the_most() -> None:
    backoff = Backoff()
    waits = [backoff.failed() for _ in range(8)]
    assert waits[:3] == [FIRST_SEC, 2 * FIRST_SEC, 4 * FIRST_SEC]
    assert max(waits) == MAX_SEC and waits[-1] == MAX_SEC
    assert backoff.failures == 8


def test_a_long_run_before_failing_starts_from_the_first_wait_again() -> None:
    backoff = Backoff()
    for _ in range(5):
        backoff.failed(ran=1.0)
    assert backoff.failed(ran=RESET_AFTER_SEC) == FIRST_SEC
    assert backoff.failed(ran=1.0) == 2 * FIRST_SEC


class Refused(OSError):
    """An OSError carrying Windows' code, as ctypes raises one there (only
    Windows fills `winerror` from OSError's arguments)."""

    winerror = -2004287480


def test_an_error_is_logged_by_its_type_and_windows_code_never_its_text() -> None:
    assert why(Refused("Couldn't capture My Secret Game")) == "Refused 0x88890008"
    assert why(OSError("Couldn't open AirPods Pro")) == "OSError"
    assert why(RuntimeError("a caption's text")) == "RuntimeError"
