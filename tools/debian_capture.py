"""Exercise the app's two device captures inside the Debian release check."""

import logging
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

import numpy as np

from polyglotic_desktop.platform.linux.capture import (
    LEVEL_CHECK_SEC,
    MicCapture,
    SystemCapture,
)
from polyglotic_desktop.ports.capture import SOUND_PEAK, CaptureIssue


def check(with_server: bool) -> None:
    captures = (SystemCapture(), MicCapture())
    heard = [Event(), Event()]

    def listener(event: Event) -> Callable[[float, bytes], None]:
        def piece(_at: float, audio: bytes) -> None:
            if np.any(np.abs(np.frombuffer(audio, "<f4")) > SOUND_PEAK):
                event.set()

        return piece

    try:
        for source, event in zip(captures, heard, strict=True):
            source.start(listener(event))
        end = time.monotonic() + 12
        if not with_server:
            while not all(source.error for source in captures):
                assert time.monotonic() < end, "no failure reported"
                time.sleep(0.05)
            assert all(source.error == CaptureIssue.SERVER for source in captures)
            assert all(source.capturing is None for source in captures)
            assert all(not event.is_set() for event in heard)
            print("Both capture workers reported a connection failure.")
            return
        while not all(source.capturing for source in captures):
            assert time.monotonic() < end, [s.error for s in captures]
            time.sleep(0.05)
        # Some servers suspend an idle virtual device; others keep sending zeros.
        quiet = (CaptureIssue.NO_FRAMES, CaptureIssue.SILENT)
        end = time.monotonic() + LEVEL_CHECK_SEC + 5
        while not all(source.error in quiet for source in captures):
            assert time.monotonic() < end, "idle sources did not report a level check"
            time.sleep(0.05)
        print("Idle virtual devices:", *(source.error for source in captures))
        # Each public sample must reach only the intended source.
        samples = Path("src/polyglotic_desktop/platform/data/samples")
        for index, (device, name) in enumerate(
            (("session_speakers", "zh.flac"), ("session_mic_feed", "en.flac"))
        ):
            heard[0].clear()
            heard[1].clear()
            player = subprocess.Popen(
                ["paplay", "--device", device, str(samples / name)]
            )
            try:
                assert heard[index].wait(5), f"No signal from {device}"
                assert not heard[1 - index].is_set(), "Signal reached the wrong capture"
                end = time.monotonic() + 2
                while captures[index].error is not None:
                    assert time.monotonic() < end, (
                        "live audio did not clear the warning"
                    )
                    time.sleep(0.05)
            finally:
                player.terminate()
                player.wait()
            time.sleep(0.5)
        print(
            "Public playback reached the speaker monitor and virtual microphone separately."
        )
    finally:
        for source in captures:
            source.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    check(sys.argv[1] == "connected")
