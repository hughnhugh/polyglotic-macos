"""What Listening's timing rules need to tell the user speaking from mic bleed.

`platform/mic_bleed.py` implements it (the mic's audio against what the
PC played); `main` hands one to `CaptionTiming.add_source` for the mic.
"""

from typing import Protocol


class MicBleedCheck(Protocol):
    """True if a source's audio from `start` to `end` is mostly the PC's own
    audio picked up by the mic (mic bleed), not the user speaking."""

    def __call__(self, start: float, end: float, /) -> bool: ...
