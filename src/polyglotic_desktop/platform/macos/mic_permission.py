"""The Mac's leave to hear the microphone (Privacy & Security >
Microphone; polyglotic-hq 478), through AVFoundation's `AVCaptureDevice`
(`objc`, no extra dependency: decision 0006).

A new learner's first caption window shows their speech: the app asks
then, with macOS's own question and the bundle's line saying why
(`NSMicrophoneUsageDescription`, `tools.package.build.MIC_USE`). Without
asking, the mic only records silence (`capture.SilenceWatch`), found ten
seconds later; asked first, a refusal is known at once and the window's
switch goes off saying so (`main`).

Restricted (a parent's or a company's profile) counts as refused: it isn't
the learner's to give. Nothing here runs on another OS: the classes load on
first use.
"""

import ctypes
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from polyglotic_desktop.platform.macos import cf, objc

NOT_DETERMINED, RESTRICTED, DENIED, AUTHORIZED = 0, 1, 2, 3
"""`AVAuthorizationStatus`'s values."""
AUDIO = "soun"
"""`AVMediaTypeAudio`'s value: the microphone."""


def status() -> int:
    """The microphone's `AVAuthorizationStatus` now - asking nothing."""
    with _audio() as (device, audio):
        return int(
            objc.send(
                device,
                "authorizationStatusForMediaType:",
                audio,
                restype=ctypes.c_long,
                argtypes=[ctypes.c_void_p],
            )
        )


def allowed_of(found: int) -> bool | None:
    """An `AVAuthorizationStatus` as `ports.system.MicPermission` says it:
    given, refused (restricted too) or never asked (None)."""
    if found == NOT_DETERMINED:
        return None
    return found == AUTHORIZED


class Permission:
    """`ports.system.MicPermission` on a Mac."""

    def __init__(self, read: Callable[[], int] = status) -> None:
        self._read = read
        self._blocks: list[objc.FlagBlock] = []
        """Every question's answer block: macOS calls it later, so it's kept
        for the app's run (a question or two a run, at most)."""

    def allowed(self) -> bool | None:
        return allowed_of(self._read())

    def ask(self, answered: Callable[[bool], None]) -> None:
        block = objc.FlagBlock(answered)
        self._blocks.append(block)
        with _audio() as (device, audio):
            objc.send(
                device,
                "requestAccessForMediaType:completionHandler:",
                audio,
                block.address,
                restype=None,
                argtypes=[ctypes.c_void_p, ctypes.c_void_p],
            )


@contextmanager
def _audio() -> Iterator[tuple[int, int]]:
    """`AVCaptureDevice`'s class and the audio media type (released after)."""
    objc.load("AVFoundation")
    audio = objc.string(AUDIO)
    try:
        yield objc.cls("AVCaptureDevice"), audio
    finally:
        cf.release(audio)
