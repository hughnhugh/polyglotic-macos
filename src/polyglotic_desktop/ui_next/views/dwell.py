"""How long a card must stay readable before another may take it out of
reading (polyglotic-hq 585's reading rules, decision 255, built into Steady's
cards by 583).
Every value is here, named, so the rules change in one edit.

A card's need to be read is `READ_START_SEC` plus its characters at a
reading pace - slower for what was said (the learner's new language)
than for its translation (their own) - between `READ_LEAST_SEC` and
`READ_MOST_SEC`. A card is read once both sides are:

- **what was said:** its need from its first word shown, and at least
  `AFTER_LAST_WORD_SEC` after its last;
- **its translation:** its need from when it landed; with none yet, the
  card waits for it until `TRANSLATION_AWAITED_SEC` after its last word.

Short captions sharing a line are one card: their need is counted on the
card's whole text. Each value says its unit and the range it can be tuned
in: the values are 585's; the ranges are 583's guesses, not measured.
Plain Python, no Qt.
"""

from dataclasses import dataclass
from unicodedata import combining, east_asian_width

from polyglotic_desktop.core.shared.tunables import tunable

READ_START_SEC = tunable(
    "dwell.read_start",
    0.35,
    "seconds",
    (0.2, 0.6),
    source="585 reading need; 583 cards",
)
"""Seconds: finding the line before reading it."""
SAID_PACE = tunable(
    "dwell.said_pace",
    3.25,
    "CJK-characters/s",
    (1.5, 9.0),
    source="585 reading need; 583 cards",
)
"""Characters a second: what was said in Chinese or Japanese, read by
a learner."""
SAID_PACE_SPACED = tunable(
    "dwell.said_pace_spaced",
    10.0,
    "letters/s",
    (5.0, 20.0),
    source="585 reading need; 583 cards",
)
"""Letters a second: what was said in other writing, read by a
learner."""
MEANT_PACE = tunable(
    "dwell.meant_pace",
    9.0,
    "CJK-characters/s",
    (5.0, 12.0),
    source="585 reading need; 583 cards",
)
"""Characters a second: a translation in Chinese or Japanese - the
reader's own language."""
MEANT_PACE_SPACED = tunable(
    "dwell.meant_pace_spaced",
    17.0,
    "letters/s",
    (10.0, 25.0),
    source="585 reading need; 583 cards",
)
"""Letters a second: a translation in other writing (subtitle
standards' 17)."""
READ_LEAST_SEC = tunable(
    "dwell.read_least", 1.0, "seconds", (0.8, 3.0), source="585 reading need; 583 cards"
)
"""Seconds: the least any line needs, however short."""
READ_MOST_SEC = tunable(
    "dwell.read_most", 7.0, "seconds", (1.0, 10.0), source="585 reading need; 583 cards"
)
"""Seconds: the most any line needs (the subtitle standards' longest)."""
AFTER_LAST_WORD_SEC = tunable(
    "dwell.after_last_word",
    1.0,
    "seconds",
    (0.5, 3.0),
    source="585 reading need; 583 cards",
)
"""Seconds: what was said stays this long after its last word, at
least - a word just come is read too."""
TRANSLATION_AWAITED_SEC = tunable(
    "dwell.translation_awaited",
    2.5,
    "seconds",
    (1.0, 6.0),
    source="585 reading need; 583 cards",
)
"""Seconds: a card with no translation yet waits for one this long
after its last word, then may go (585: translations came 2.2 s after the
last word at p50)."""
HOLD_VIDEO_SEC = tunable(
    "dwell.hold_video", 2.0, "seconds", (0.0, 4.0), source="585 reading need; 583 cards"
)
"""Seconds, 0-4 (0: off). Video: a new card is held, and the window runs behind the speech, at
most this long while the card it would take out of reading isn't read
(`CaptionWindow.set_reading_hold`) - it catches up in the next pause.
Elsewhere the hold is off: there a new card pushes the stack by a card,
and the card it takes out of reading turns away on the drum, still there
(585 proposes 4 s if it is turned on)."""


# Other windows place a new card immediately unless the override enables a hold.
HOLD_EVERYDAY = tunable(
    "dwell.hold_everyday", 0.0, "seconds", (0, 8), source="585 rule 5"
)
HOLD_CONVERSATION = tunable(
    "dwell.hold_conversation", 0.0, "seconds", (0, 8), source="585 rule 5"
)
HOLD_LEARNING = tunable(
    "dwell.hold_learning", 0.0, "seconds", (0, 10), source="585 rule 5"
)
OTHER_HOLDS = {
    "everyday": HOLD_EVERYDAY,
    "conversation": HOLD_CONVERSATION,
    "learning": HOLD_LEARNING,
}


def _unspaced(char: str) -> bool:
    return "㐀" <= char <= "鿿" or "぀" <= char <= "ヿ"


def need(text: str, pace: float, pace_spaced: float) -> float:
    """Seconds to read `text` at `pace` characters a second for Chinese
    and Japanese, `pace_spaced` for other letters."""
    unspaced = sum(1 for c in text if _unspaced(c))
    spaced = sum(1 for c in text if c.isalnum() and not _unspaced(c))
    seconds = READ_START_SEC.value + unspaced / pace + spaced / pace_spaced
    return min(READ_MOST_SEC.value, max(READ_LEAST_SEC.value, seconds))


def subtitle_need(
    text: str, pace: float, pace_spaced: float, *, continuing: bool = False
) -> float:
    """Seconds to read a fixed-size subtitle page, including punctuation
    and spaces. A long page stays until the reader can finish it."""
    characters = [char for char in text if not combining(char)]
    wide = sum(east_asian_width(char) in ("W", "F") for char in characters)
    seconds = wide / pace + (len(characters) - wide) / pace_spaced
    notice = 0.0 if continuing else READ_START_SEC.value
    return max(READ_LEAST_SEC.value, notice + seconds)


@dataclass(slots=True)
class Reading:
    """One card as it has been shown: when, and what."""

    first: float
    """Its first word shown."""
    last: float
    """Its last word shown (what was said last grew)."""
    said: str = ""
    meant: str = ""
    landed: float | None = None
    """Its translation landed (last changed); None: none yet."""
    awaited: bool = True
    """A translation will come (the window translates what it says)."""

    def read_by(self) -> float:
        """When it has stood readable long enough on both sides."""
        said = max(
            self.first + need(self.said, SAID_PACE.value, SAID_PACE_SPACED.value),
            self.last + AFTER_LAST_WORD_SEC.value,
        )
        if self.meant and self.landed is not None:
            meant = self.landed + need(
                self.meant, MEANT_PACE.value, MEANT_PACE_SPACED.value
            )
            return max(said, meant)
        if self.awaited:
            return max(said, self.last + TRANSLATION_AWAITED_SEC.value)
        return said
