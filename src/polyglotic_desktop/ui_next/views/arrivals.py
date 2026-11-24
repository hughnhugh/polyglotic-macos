"""How a new caption arrives in a caption window, and how the ones before it
step back (the user's rehearsal feedback F21, polyglotic-hq 249: "visibly
obvious from a subtle contrast different ... You should be able to perceive
what just came in when from peripherals").

polyglotic-hq 253 prototyped five arrivals (draft desktop #388); the user
took its recommendation, D with B as its no-motion form (DECISIONS.md
#104, 2026-11-09; built in 267):

- **Step and slide** (`Arrival.STEP_AND_SLIDE`, D, the default): B's step,
  and nothing jumps. When a caption arrives the established text keeps
  its place for the first frame, then rises to its new place, easing to
  rest; the new caption enters from below, `ENTRY_GAP_PX` further down,
  and closes on the line above as it rises - "moving upwards toward the
  established transcript text" (the user, 2026-11-08). It takes
  `SLIDE_MIN_SEC` to `SLIDE_MAX_SEC`, by the speech's pace (`pace_of`):
  captions that come faster push it up faster.
- **Step** (`Arrival.STEP`, B): no motion, no fade. The newest caption is
  at full ink; every older one a step back - what was said at
  `OLDER_ALPHA`, its yellow translation at `OLDER_TRANSLATION_ALPHA`.
  When a caption arrives, the one before it steps back at once - a change
  the corner of the eye catches - and the new one is simply there. Not a
  bolder weight: a weight change lays the line out again and moves text
  being read.

Step is also what step and slide becomes with Windows' animation effects
off (`effective`): pixel for pixel the same.

A preview line becoming its finished caption keeps its key. The rows
reflow with the newest caption anchored at the foot. Newly shown
captions and newly revealed paced lines start a slide.

With Windows' high contrast nothing steps back (`older_alphas`): every
line keeps full contrast. Nor while the learner has scrolled back: they're
reading deliberately, so every line is at full ink until they're back at
the newest (249's detail, taken with DECISIONS.md #104; 267). Plain
Python, no Qt: times are seconds on whatever clock the window keeps.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from polyglotic_desktop.ui_next.views.cards import ease

OLDER_ALPHA = 0.85
OLDER_TRANSLATION_ALPHA = 0.85
"""Contrast retained by older captions, as a share of the newest line's
WCAG contrast ratio (0..1). This is deliberately contrast, not paint alpha:
`contrast_alpha` converts it for each look and text colour. The named setting
is a percentage in the Lab, with a supported 50--100 % range and an 85 %
default; original, translation and reading rows therefore keep the same light
fade on light and dark panels."""
SLIDE_SEC = 0.55
"""A slide at a typical pace (`pace` 1.0), start to rest (253's films)."""
SLIDE_MIN_SEC, SLIDE_MAX_SEC = 0.22, 0.9
"""The quickest and slowest slides: quick enough to be over before the
next caption at the fastest pace, slow enough to follow (253)."""
ENTRY_GAP_PX = 18.0
"""How much further below its resting place a new caption starts, at text
size 1.0: the gap it closes as it rises to meet the line above."""
TYPICAL_GAP_SEC = 2.5
"""Seconds between finished captions in ordinary conversation - pace 1.0.
An estimate (2026-11-09), not a measurement: Steady finishes a caption
at each breath, and 253's recorded conversation had them 1.3-2.5 s
apart."""
SPEAKING_LIFT = 1.5
"""How much faster the slide goes while speech is still under way as the
caption lands: the next one is already on its way."""
PACE_RANGE = (0.5, 2.5)


class Arrival(StrEnum):
    """How a new caption arrives (the look's `arrival`)."""

    STEP = "step"
    STEP_AND_SLIDE = "step_and_slide"

    @property
    def slides(self) -> bool:
        return self is Arrival.STEP_AND_SLIDE


def effective(arrival: Arrival, reduced_motion: bool) -> Arrival:
    """The arrival to draw: with Windows' animation effects off, nothing
    slides - step and slide is the step."""
    return Arrival.STEP if reduced_motion else arrival


def older_alphas(
    high_contrast: bool,
    following: bool,
    older: tuple[float, float] = (OLDER_ALPHA, OLDER_TRANSLATION_ALPHA),
) -> tuple[float, float]:
    """How much of the newest caption's contrast older rows retain:
    B's step, which both arrivals take - `older`
    (the Lab can change it, `views.lab`) - none with Windows' high
    contrast, or while the learner has scrolled back (not `following` the
    newest)."""
    if high_contrast or not following:
        return 1.0, 1.0
    return older


def pace_of(since_last: float | None, speaking: bool) -> float:
    """The speech's pace, 1.0 typical, from the listening session: how
    long since the caption before this one (`since_last`; None for the
    first), and whether speech is still `speaking` - under way - as it
    lands. Not from the text's length (253's films estimated it so)."""
    low, high = PACE_RANGE
    pace = 1.0 if not since_last or since_last <= 0 else TYPICAL_GAP_SEC / since_last
    if speaking:
        pace *= SPEAKING_LIFT
    return min(high, max(low, pace))


def slide_seconds(pace: float) -> float:
    """How long a slide takes at `pace`: faster speech pushes the text up
    faster, within what a reader can follow."""
    return min(SLIDE_MAX_SEC, max(SLIDE_MIN_SEC, SLIDE_SEC / max(pace, 0.01)))


def ease_out(t: float) -> float:
    """Cubic ease-out: quick off the mark, easing to rest. 0..1 -> 0..1."""
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


def _left(started: float, seconds: float, now: float) -> float:
    """The share of a movement still to go at `now`: 1.0 at the start, 0.0
    at rest."""
    return 1.0 - ease_out((now - started) / seconds)


@dataclass
class Slide:
    """The stack drawn `from_px` below its place at `started`, rising to
    it over `seconds`."""

    started: float
    seconds: float
    from_px: float

    def offset(self, now: float) -> float:
        """How far below its place the stack is drawn at `now`."""
        # Keep the speech-paced duration. Easing into a long move avoids
        # the abrupt first frame of a cubic ease-out and gets a new row
        # clear of the lower edge sooner as the stack comes to rest.
        return self.from_px * (1.0 - ease((now - self.started) / self.seconds))

    def done(self, now: float) -> bool:
        return now - self.started >= self.seconds


@dataclass
class Motion:
    """A window's arrivals in flight: the stack's slide, and each new
    line's entry (its key -> when it started and for how long). When the
    mouse comes over the window, whatever is in flight is at rest at once
    (`stop`) and nothing more comes in while it's there - nothing moves
    under it (109's rule), and nothing is left half below the window's
    edge (polyglotic-hq 291: a slide stopped where it was, the newest
    caption's last rows below the bottom for as long as the mouse moved
    over it - the user's "text will get cut off at the bottom")."""

    slide: Slide | None = None
    entries: dict[int, tuple[float, float]] = field(default_factory=dict)

    def start(
        self, now: float, risen_px: float, new: set[int], seconds: float, most_px: float
    ) -> None:
        """The stack rose `risen_px` for this change - it slides there
        instead of jumping, from wherever a slide still in flight has it;
        the `new` lines enter from `ENTRY_GAP_PX` further down. More than
        `most_px` to go at once (a burst of captions, nothing painted
        between) is too much to follow: everything is at rest at once."""
        to_go = risen_px + self.offset(now)
        if to_go > most_px:
            self.stop()
            return
        if risen_px > 0.0:
            self.slide = Slide(now, seconds, to_go)
        for key in new:
            self.entries[key] = (now, seconds)

    def offset(self, now: float) -> float:
        """How far below its place the stack is drawn at `now`."""
        return 0.0 if self.slide is None else self.slide.offset(now)

    def entry(self, key: int, now: float) -> float:
        """How much of its entry gap line `key` is still below its place
        (beyond the stack's offset): 1.0 as it enters, 0.0 at rest."""
        found = self.entries.get(key)
        return 0.0 if found is None else _left(found[0], found[1], now)

    def moving(self, now: float) -> bool:
        """Anything moving now (the frame timer keeps going); what has come
        to rest is forgotten."""
        if self.slide is not None and self.slide.done(now):
            self.slide = None
        self.entries = {
            key: (at, seconds)
            for key, (at, seconds) in self.entries.items()
            if now - at < seconds
        }
        return self.slide is not None or bool(self.entries)

    def stop(self) -> None:
        """Everything at rest at once (scrolled back, more to go than can
        be followed, or the mouse came over the window)."""
        self.slide = None
        self.entries.clear()
