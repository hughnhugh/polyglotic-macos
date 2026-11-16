"""The apps a caption window can caption, as its settings list them (the
user's rehearsal feedback F12, polyglotic-hq 249: "Allow you to select the
app you want to caption in captioning window. Browsers should be a default
app you can select to caption, it doesn't have to be playing sound first.
Do most of the main apps").

Two kinds, in this order:
- **found:** apps Windows has an audio session for now (`AppList`) - the
  ones playing first;
- **common:** browsers and the main apps (the OS's list, `CommonApp`),
  listed before they play - matched by their executable's name.

An app needs a process for its sound to be caught (Windows' process
loopback captures a process tree by its id), and Polyglotic finds it by
its audio session, which an app opens the first time it plays. So a
common app that isn't playing yet is picked now and captioned once it
plays: the app looks for it every few seconds (`main.APP_CHECK_MS`) and
its source starts then - the first seconds of its sound can be missed.
Each choice says which (`AppState`). Apps another window captions aren't
listed. Plain Python, no Qt. Names stay on this PC.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum


class AppState(StrEnum):
    PLAYING = "playing"  # found, playing now
    QUIET = "quiet"  # found, quiet now
    NOT_PLAYING_YET = "not_playing_yet"  # a common app with no audio session yet


@dataclass(frozen=True, slots=True)
class AppChoice:
    """One app a window can caption: `name` its executable's (what the
    settings keep), `title` what it's called on screen."""

    name: str
    title: str
    state: AppState


def app_choices(
    found: Sequence[tuple[str, str, bool]],
    common: Sequence[tuple[str, str]],
    current: str,
    elsewhere: Collection[str],
) -> list[AppChoice]:
    """The apps a window captioning `current` can switch to: `found` (each
    its name, title and whether it plays now) - playing first, then by
    title - then `common` (name, title) not found; neither those another
    window captions (`elsewhere`) nor one name twice. `current` is listed
    too, where it falls, so the list shows what's chosen."""
    taken = {name.lower() for name in elsewhere} - {current.lower()}
    seen: set[str] = set()
    choices = []
    for name, title, playing in sorted(found, key=lambda f: (not f[2], f[1].lower())):
        key = name.lower()
        if key in taken or key in seen:
            continue
        seen.add(key)
        state = AppState.PLAYING if playing else AppState.QUIET
        choices.append(AppChoice(name, title, state))
    for name, title in common:
        key = name.lower()
        if key in taken or key in seen:
            continue
        seen.add(key)
        choices.append(AppChoice(name, title, AppState.NOT_PLAYING_YET))
    return choices
