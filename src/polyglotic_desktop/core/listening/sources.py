"""Sources: where audio comes from - an app, the whole system, everything
else the PC plays (beside one app), or the mic.

A source's speech leaves the PC with its id and its category only, never
an app's name or window title (DOMAIN.md, "Data and privacy"). The
category, `SourceCategory`, is in `ports.capture`: the app list reports
it. The one exception, with the user's consent to usage statistics: the
public name of a well-known app (`Source.known_app`), in the session's
summary (polyglotic-hq DECISIONS.md #30, the user, 2026-11-05).

A **source label** is how a source's captions are shown on this PC: a
name (the app's, the learner's own for it, or "You" for the mic) and a
colour, on the caption's label row - never sent anywhere. `colors_for`
gives each source its colour: the learner's choice, or the first one of a
palette no other source has.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from polyglotic_desktop.ports.capture import SourceCategory

SourceId = NewType("SourceId", str)
"""A source's identity within a listening session (protocol.md: `source.id`)."""

MIC = SourceId("mic")
"""The user's own mic: its captions are "by you"."""
WHOLE_SYSTEM = SourceId("system")
"""Everything the PC plays."""
EVERYTHING_ELSE = SourceId("everything_else")
"""Everything else the PC plays, beside the one app captioned on its own -
that app left out, so nothing is heard twice (polyglotic-hq DECISIONS.md
#59). Its category is `system`, as everything the PC plays is."""
SAMPLE = SourceId("sample")
"""The short recording Home offers when nothing is playing, played by the
app itself (polyglotic-hq 176). Its category is `other`: the server learns
no more of it than of an app."""
DICTATION = SourceId("dictation")
"""The learner's mic while they hold the dictation key (polyglotic-hq 283,
decision 0073): its category is `mic`, its text is typed into another
program - never a caption line (`core.listening.dictation`)."""


@dataclass(frozen=True, slots=True)
class Source:
    """A source being captioned: its id and category. `known_app` names
    the app if it's on the known-apps list, as the tracking plan does
    (`known_app_id`: `discord`): it goes only into the session's usage
    statistics, sent only with the user's consent (polyglotic-hq
    DECISIONS.md #30) - never with its speech."""

    id: SourceId
    category: SourceCategory
    known_app: str | None = None


def known_app_id(public_name: str) -> str:
    """A known app as polyglotic-server's tracking plan names it: its public
    name in lower case, words joined by `-` (`Google Chrome` ->
    `google-chrome`). The plan lists every one; a name changed is a new id
    there first."""
    return "-".join(re.findall("[a-z0-9]+", public_name.lower()))


class CaptureMode(StrEnum):
    """What the learner chose to caption: apps, each on its own; one app
    and everything else the PC plays (DECISIONS.md #59); or everything the
    PC plays - or nothing yet. As polyglotic-server's tracking plan names
    it (`capture_mode`, polyglotic-hq project 134): a list that grows, each
    value there first. The number of apps is kept apart."""

    APPS = "apps"
    APPS_PLUS_REST = "apps_plus_rest"
    WHOLE_SYSTEM = "whole_system"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Capture:
    """What is captured, for the usage statistics only: the mode, how many
    apps on their own (everything the PC plays is 0; everything else beside
    an app isn't one), and whether the learner's own speech is ("Show my
    speech here"). Never an app's name."""

    mode: CaptureMode
    apps: int
    my_speech: bool


def capture_of(
    chosen: bool,
    whole_system: bool,
    apps: int,
    mic: bool,
    everything_else: bool = False,
) -> Capture:
    """What is captured: everything the PC plays; or the apps picked that
    are open - still the apps mode while none of them is - with everything
    else the PC plays beside them, or not; or, before the learner has
    chosen (`chosen` False), nothing."""
    if whole_system:
        return Capture(CaptureMode.WHOLE_SYSTEM, 0, mic)
    if not chosen:
        return Capture(CaptureMode.NONE, apps, mic)
    mode = CaptureMode.APPS_PLUS_REST if everything_else else CaptureMode.APPS
    return Capture(mode, apps, mic)


@dataclass(frozen=True, slots=True)
class SourceLabel:
    """How a source's captions are labelled on this PC - never sent: the
    name the learner knows it by, and its colour (`#rrggbb`)."""

    name: str
    color: str


def colors_for(
    keys: Sequence[str], chosen: Mapping[str, str], palette: Sequence[str]
) -> dict[str, str]:
    """Each source's colour, by its key: the colour chosen for it, else the
    first palette colour no other source has - in `keys` order, so the
    same sources get the same colours. Past the palette's end, colours
    repeat in turn."""
    taken = {chosen[k] for k in keys if k in chosen}
    free = [c for c in palette if c not in taken]
    colors: dict[str, str] = {}
    spare = 0
    for key in keys:
        if key in chosen:
            colors[key] = chosen[key]
        elif free:
            colors[key] = free.pop(0)
        else:
            colors[key] = palette[spare % len(palette)]
            spare += 1
    return colors
