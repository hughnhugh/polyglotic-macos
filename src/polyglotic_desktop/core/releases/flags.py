"""Feature flags: the one module through which the app reads a flag
(polyglotic-hq ENGINEERING.md, "Feature flags"; decision 0263).

Every flag is declared here with an owner, an expiry date and its value
for everyone (`Flag.default`); `tests/releases/test_flags.py` fails once
one is past its expiry, so each is removed - or its code - in time. A
flag here is the app's own switch, the same for every learner: the
server's `welcome.features` sets none of them yet. When one needs a
rollout, its value comes from there through `set_value` at the start,
and nothing that reads it changes.

Off today:
- `SPOKEN_NUDGE`: a caption window's "This sounds like Russian. Always
  hear it as Russian?" (polyglotic-hq 317). Detect is the default
  everywhere and nothing pushes the learner to name a language (the user,
  2026-11-20: "Detect should be the default mode and we shouldn't push
  users to force a language choice to caption"; polyglotic-hq 555).
- `FILL_THE_WIDTH`: captions poured into lines as wide as the window
  (polyglotic-hq 309: the Lab's Captions fill the width, Between clauses
  and Captions run on, and the caption window's Fill the width button).
  The user, 2026-11-20: "Fill the width settings ... don't work well at
  all in these versions. Probably remove this from the app ... once we've
  implemented a working wide caption mode" - its code (`views.pour`,
  `caption_layout`'s poured rows) goes once the Smooth mode fills lines
  itself (polyglotic-hq 552).
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Flag:
    name: str
    description: str
    owner: str
    expires: date
    default: bool


SPOKEN_NUDGE = Flag(
    "spoken_nudge",
    "A caption window asks to name the language Detect has heard steadily",
    "polyglotic-hq 555",
    date(2027, 1, 31),
    False,
)

FILL_THE_WIDTH = Flag(
    "fill_the_width",
    "Captions can be poured into lines as wide as the window (the Lab's and a"
    " caption window's Fill the width)",
    "polyglotic-hq 555",
    date(2027, 1, 31),
    False,
)

DECLARED: tuple[Flag, ...] = (SPOKEN_NUDGE, FILL_THE_WIDTH)

_values: dict[str, bool] = {}
"""The flags set for this run (`set_value`): none but in tests and the UI
lab, which show what's behind one."""


def on(flag: Flag) -> bool:
    """Whether `flag` is on in this app."""
    return _values.get(flag.name, flag.default)


def set_value(flag: Flag, value: bool | None) -> None:
    """`flag` on or off for this run; None: its default again."""
    if value is None:
        _values.pop(flag.name, None)
    else:
        _values[flag.name] = value
