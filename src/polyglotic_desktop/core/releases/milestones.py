"""An install's milestones, as usage statistics: installed, updated, first caption shown.

polyglotic-server's tracking plan (`app_installed`, `app_updated`,
`first_caption_shown`; polyglotic-hq project 134): what activation,
retention and version adoption are worked out from. The rules only -
what this PC remembers between runs is `Kept`, which the connection
stores and sends from, and only with consent to usage statistics. An
install's first run comes before its consent screen, so a milestone waits
until it can go (`due`), and goes once.

An install from before this was built (`fresh` False on its first run
with it) never says it was installed or when its first caption was: its
install time isn't known, and a guess would skew retention.
"""

from dataclasses import dataclass, replace
from datetime import datetime

INSTALLED = "app_installed"
UPDATED = "app_updated"
FIRST_CAPTION = "first_caption_shown"


@dataclass(frozen=True)
class Kept:
    """What this PC remembers: when it was installed, the version that ran
    last, when its first caption was shown, and which milestones went."""

    installed_at: datetime | None = None
    version_run: str | None = None
    first_caption_at: datetime | None = None
    sent: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Milestone:
    """A milestone to send: its plan name, when it happened, its properties."""

    name: str
    at: datetime
    props: dict[str, str | float]


def started(
    kept: Kept, version: str, fresh: bool, now: datetime
) -> tuple[Kept, Milestone | None]:
    """The app started as `version`: the first run of a `fresh` install is
    its install; a different version from the last run is an update (the
    `app_updated` to send now, or None)."""
    if kept.installed_at is None and kept.version_run is None:
        if fresh:
            kept = replace(kept, installed_at=now)
        else:  # installed before this was built: when isn't known
            kept = replace(kept, sent=kept.sent | {INSTALLED, FIRST_CAPTION})
    update = None
    if kept.version_run is not None and kept.version_run != version:
        update = Milestone(
            UPDATED, now, {"from_version": kept.version_run, "to_version": version}
        )
    return replace(kept, version_run=version), update


def caption_shown(kept: Kept, now: datetime) -> Kept:
    """A finished caption was shown: the first one is remembered."""
    if kept.first_caption_at is not None or FIRST_CAPTION in kept.sent:
        return kept
    return replace(kept, first_caption_at=now)


def due(kept: Kept) -> list[Milestone]:
    """The milestones that happened and haven't gone yet."""
    found = []
    installed = kept.installed_at
    if installed is not None and INSTALLED not in kept.sent:
        found.append(Milestone(INSTALLED, installed, {}))
    first = kept.first_caption_at
    if first is not None and installed is not None and FIRST_CAPTION not in kept.sent:
        seconds = round(max(0.0, (first - installed).total_seconds()), 1)
        found.append(
            Milestone(FIRST_CAPTION, first, {"seconds_since_install": seconds})
        )
    return found
