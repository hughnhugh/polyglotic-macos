"""The Mac's leave to hear the microphone (polyglotic-hq 478): AVFoundation's
answer read as the port says it, with a stand-in for macOS's call - no test
asks for real. The question itself is proven only on a Mac (GitHub's Mac,
by hand: decision 0186)."""

import pytest

from polyglotic_desktop.platform.macos import mic_permission
from polyglotic_desktop.platform.macos.mic_permission import (
    AUTHORIZED,
    DENIED,
    NOT_DETERMINED,
    RESTRICTED,
    Permission,
    allowed_of,
)


@pytest.mark.parametrize(
    ("status", "allowed"),
    [(NOT_DETERMINED, None), (RESTRICTED, False), (DENIED, False), (AUTHORIZED, True)],
)
def test_the_status_as_the_port_says_it(status: int, allowed: bool | None) -> None:
    assert allowed_of(status) is allowed
    assert Permission(lambda: status).allowed() is allowed


def test_asking_nothing_reads_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def asked(*_args: object, **_named: object) -> None:
        raise AssertionError("asked macOS")

    monkeypatch.setattr(mic_permission.objc, "send", asked)
    assert Permission(lambda: DENIED).allowed() is False


def test_the_values_are_avfoundations() -> None:
    """`AVAuthorizationStatus` and `AVMediaTypeAudio`, as Apple defines them."""
    assert (NOT_DETERMINED, RESTRICTED, DENIED, AUTHORIZED) == (0, 1, 2, 3)
    assert mic_permission.AUDIO == "soun"
