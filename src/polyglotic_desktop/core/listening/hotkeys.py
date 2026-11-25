"""The app's hotkeys: what each does, its key, and the keys it can't be.

polyglotic-hq 567 and the desktop's decision 0273 (the user, 2026-11-20:
"Hotkey to jump to line ... customiseable ... global hotkeys customisation
section"). Global hotkeys work over other apps. The default Space binding acts
inside Polyglotic caption and transcript windows. Its key is kept as `DictationKey` keeps
dictation's ("ctrl+alt+l", "f9"): the modifiers in a fixed order, then the
key. The learner sets each in Settings > Hotkeys; one they cleared is kept
as "" and does nothing; one they never set has its default (`defaults`).

- **On by default:** Lock, Pause and Hide (Ctrl+Alt+L, P, H since the
  proof of concept) and Back to live (Space in a caption or transcript
  window). The global hotkeys' modifiers are the platform's
  (`Platform`, `OWN_MODIFIERS`): on a Mac Control+Command (polyglotic-hq
  428), kept as "ctrl+win" - Qt's names there; on Linux Ctrl+Alt+Shift
  (polyglotic-hq 570, decision 0293: Ctrl+Alt+L locks the screen on
  Cinnamon, MATE and Xfce).
- **Unset by default:** the rest, including opening the caption bar's
  dropdowns for keyboard navigation. The learner chooses a key for each.

A hotkey's key can't be (`refusal`): one dictation's rules refuse
(`dictation_keys.refusal`: it types, Windows keeps it, every program uses
it, Alt without Ctrl); a modifier alone or modifiers alone, which a pressed
hotkey can't be (`Refusal.HELD_ALONE` - dictation's key can); or a key
another of the app's hotkeys or hold keys already has (`holder`). Whether
another program has it is only known by trying (the platform's).
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum

from polyglotic_desktop.core.listening.dictation_keys import (
    DictationKey,
    Modifier,
    Refusal,
)
from polyglotic_desktop.core.listening.dictation_keys import refusal as key_refusal


class Hotkey(StrEnum):
    """What a hotkey does, as the settings name it."""

    LOCK = "lock"
    """Lock every caption window: clicks pass through."""
    PAUSE = "pause"
    """Pause captions, or resume them."""
    HIDE = "hide"
    """Hide every caption window, or show them."""
    LIVE = "live"
    """Back to live: every caption window and transcript to its newest line."""
    COPY = "copy"
    """Copy the newest caption."""
    PRESET = "preset"
    """The next preset (polyglotic-hq 556)."""
    BIGGER = "bigger"
    """Every caption window's text a step bigger."""
    SMALLER = "smaller"
    """Every caption window's text a step smaller."""
    BAR = "bar"
    """Open the caption bar's three dropdowns for keyboard navigation."""


ORDER = tuple(Hotkey)
"""The hotkeys in the order Settings lists them."""
DICTATE = "dictate"
"""Dictation's key's name beside the hotkeys' (`holder`, `clashes`): a
hotkey can't share it."""
RESPEAK = "respeak"
"""Re-speaking's own key's name beside them, when it has one (polyglotic-hq
636; optionally shared with dictation)."""

_LETTERS = {
    Hotkey.LOCK: "l",
    Hotkey.PAUSE: "p",
    Hotkey.HIDE: "h",
}
"""The hotkeys on by default, and their letter."""


LIVE_SPACE = DictationKey(frozenset(), "space")


class Platform(StrEnum):
    """The OS whose keys the app's own hotkeys follow - told by the caller
    (`os_words.platform`): core reads no OS."""

    WINDOWS = "windows"
    MAC = "mac"
    LINUX = "linux"


OWN_MODIFIERS = {
    Platform.WINDOWS: frozenset((Modifier.CTRL, Modifier.ALT)),
    # Control + Command: Qt's Meta ("win") and Ctrl there (polyglotic-hq 428)
    Platform.MAC: frozenset((Modifier.CTRL, Modifier.WIN)),
    # Shift too: Ctrl+Alt+L locks the screen on Cinnamon, MATE and Xfce
    # (polyglotic-hq 570's survey of each desktop's own defaults, decision 0293)
    Platform.LINUX: frozenset((Modifier.CTRL, Modifier.ALT, Modifier.SHIFT)),
}
"""The modifiers of the app's own hotkeys on each platform, with the letter."""


def defaults(
    platform: Platform = Platform.WINDOWS,
) -> dict[Hotkey, DictationKey | None]:
    """Each hotkey's key until the learner sets one: None for none."""
    held = OWN_MODIFIERS[platform]
    found: dict[Hotkey, DictationKey | None] = dict.fromkeys(ORDER)
    found.update(
        (hotkey, DictationKey(held, letter)) for hotkey, letter in _LETTERS.items()
    )
    found[Hotkey.LIVE] = LIVE_SPACE
    return found


def keys(
    chosen: Mapping[str, str], platform: Platform = Platform.WINDOWS
) -> dict[Hotkey, DictationKey | None]:
    """Each hotkey's key now: the learner's (`chosen`: by its name, "" for
    none), or its platform's default. A key kept that can't be read is the
    default."""
    found = defaults(platform)
    for hotkey in ORDER:
        if hotkey.value not in chosen:
            continue
        text = chosen[hotkey.value]
        if text == "":
            found[hotkey] = None
        elif (key := DictationKey.parse(text)) is not None:
            found[hotkey] = key
    return found


def holder(
    key: DictationKey,
    taken: Mapping[str, DictationKey | None],
    but: str | None = None,
) -> str | None:
    """Which of `taken` (by name: hotkeys and hold keys) has `key` - any
    but `but` - if one does."""
    return next(
        (name for name, held in taken.items() if held == key and name != but),
        None,
    )


def refusal(
    key: DictationKey,
    others: Iterable[DictationKey] = (),
    *,
    hotkey: Hotkey | None = None,
) -> Refusal | None:
    """Why `key` can't be a hotkey's, if it can't; `others`: the app's
    other keys, hotkeys' and hold keys' both (a match is `APP_HOTKEY`)."""
    if hotkey is Hotkey.LIVE and key == LIVE_SPACE:
        return Refusal.APP_HOTKEY if key in others else None
    if key.held_alone:
        return Refusal.HELD_ALONE
    return key_refusal(key, others)


def clashes(keys: Mapping[str, DictationKey | None]) -> dict[str, str]:
    """Keys two of `keys` share (a file edited by hand, or a hold key set to
    a hotkey's): each name to the one before it in order with the same
    key - the first keeps it, the others don't work."""
    first: dict[DictationKey, str] = {}
    found: dict[str, str] = {}
    for name, key in keys.items():
        if key is None:
            continue
        if key in first:
            found[name] = first[key]
        else:
            first[key] = name
    return found
