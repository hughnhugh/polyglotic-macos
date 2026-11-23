"""Which caption timings each use offers (polyglotic-hq 585's rule 11, its
starting list; 593's timing chip).

A caption window's bar has a timing chip after the preset chip ("Steady
▾"). It offers only the timings that can keep a line readable in the way
the captions are used - the preset's *use* - as 585 measured on preview 2
(DESIGN.md section 3.1; the user, 2026-11-21: "So language detection,
preset, timing"):

- **Watching** (Video): Instant and Scrolling. Both show live originals and translations.
- **Talking** (Conversation): Steady and Instant. Calm and Whole captions
  are too late for a reply.
- **Studying** (Learning): Instant, Steady and Calm, and the translation's own
  timing: after the line has been read, or with it.
- **Everyday**: all four.

A preset of the learner's own, or Custom, is Everyday's: it says nothing
about its use. The table (`OFFERED`) is the one place this is decided, a
named value a registry of tunables can take over (polyglotic-hq 588).

Plain Python, no Qt: the chip asks `offered(use_of(preset))`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from polyglotic_desktop.core.listening.playout import ReadingPath
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode


class Use(StrEnum):
    """What a window's captions are used for: a built-in preset's use
    (585's section 3). The values are the built-in presets' keys
    (`ui.use_presets`)."""

    EVERYDAY = "everyday"
    TALKING = "conversation"
    WATCHING = "video"
    STUDYING = "learning"


@dataclass(frozen=True, slots=True)
class Offered:
    """What a use offers on the timing chip."""

    timings: tuple[CaptionMode, ...]
    """The caption timings, the one that suits the use best first (the
    usual fallback for a timing it doesn't offer: `nearest`)."""
    paths: tuple[ReadingPath, ...] = ()
    """The translation's timing - after the line has been read
    (`ACQUISITION`), or with it (`BOTH`) - where the use offers the
    choice; () where it doesn't (it stays in Settings > Timing)."""

    def allows(self, mode: CaptionMode) -> bool:
        return mode in self.timings

    def nearest(self, mode: CaptionMode) -> CaptionMode:
        """`mode` if offered, else the one that suits the use best."""
        if self.allows(mode):
            return mode
        return self.timings[0]


OFFERED: Mapping[Use, Offered] = {
    # every timing reads in Everyday's roomy window (585: none left a line
    # unread by a reader of one line)
    Use.EVERYDAY: Offered(OFFERED_MODES),
    # Instant by default (626); a reply can't wait for Calm or a whole caption.
    Use.TALKING: Offered((CaptionMode.INSTANT, CaptionMode.STEADY)),
    Use.WATCHING: Offered((CaptionMode.INSTANT, CaptionMode.SCROLLING)),
    # "translation after" needs the paced modes (`AppSettings.acquisition`)
    Use.STUDYING: Offered(
        (CaptionMode.INSTANT, CaptionMode.STEADY, CaptionMode.CALM),
        paths=(ReadingPath.ACQUISITION, ReadingPath.BOTH),
    ),
}
"""The timings each use offers (585's rule 11, its starting list), the
best suited first. Change a use's list here and the chip follows; Settings
> Timing still offers every timing."""


def use_of(preset: str) -> Use:
    """A preset's use: a built-in one's own, Everyday's for any other (a
    learner's own, Custom)."""
    try:
        return Use(preset)
    except ValueError:
        return Use.EVERYDAY


def offered(use: Use) -> Offered:
    return OFFERED[use]
