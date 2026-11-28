"""The app's hotkeys: what each does, its key, its scope, and free alternatives.

polyglotic-hq 567, decision 0273, and polyglotic-hq 966 (the user, 2026-11-25:
"I want to be able to assign things like space to it without holding from usage
in other apps. basically every key should be a valid hotkey, not just f keys").

- **Every key is valid:** letters, digits, punctuation, Space, Enter, Tab,
  Backspace, arrows, editing keys, F-keys, Pause, Insert, media keys — alone or
  with any modifiers. Only a bare modifier (`held_alone`) or a key another of
  the app's own hotkeys or hold keys already uses (`APP_HOTKEY`) is refused.
- **Each hotkey has a scope (`HotkeyScope`):**
  - `APP` (**In Polyglotic's windows**): acts only while one of Polyglotic's
    windows (caption, transcript, main) is active; other apps keep the key.
  - `EVERYWHERE` (**Everywhere**): a global hotkey over other apps.
  A typing key (letters, digits, punctuation, Space, Enter, Tab, Backspace,
  arrows, editing keys) alone or with Shift only defaults to `APP`; combinations
  and non-typing keys default to `EVERYWHERE`. Choosing `EVERYWHERE` on a typing
  key passes the key on to other apps (never swallows it).
- **On by default:** Lock, Pause and Hide (Ctrl+Alt+L, P, H on Windows;
  Control+Command on Mac; Ctrl+Alt+Shift on Linux) with scope `EVERYWHERE`, and
  Back to live (Space) with scope `APP`.
- **Conflicts:** when the OS refuses a global hotkey because another program
  holds it, `candidate_alternatives` and `find_free_alternatives` probe the OS
  and offer free alternatives the app has just tested.
"""

from collections.abc import Callable, Iterable, Mapping
from enum import StrEnum

from polyglotic_desktop.core.listening.dictation_keys import (
    LETTERS,
    DictationKey,
    Modifier,
    Refusal,
)
from polyglotic_desktop.core.shared.tunables import tunable

ALTERNATIVE_COUNT = tunable(
    "hotkeys.alternative_count",
    2,
    "alternatives",
    (1, 5),
    source="966: free hotkey alternatives tested and offered when another program holds a chosen hotkey",
)

CONFLICT_NOTIFY_MS = tunable(
    "hotkeys.conflict_notify_ms",
    10_000,
    "ms",
    (2_000, 30_000),
    source="966: duration of the tray notification shown when another program holds a hotkey",
)


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


class HotkeyScope(StrEnum):
    """Where a hotkey acts (polyglotic-hq 966)."""

    APP = "app"
    """Only while one of Polyglotic's own windows is active."""
    EVERYWHERE = "everywhere"
    """Global: works while other apps have focus."""


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

_MNEMONIC_LETTERS = {
    Hotkey.LOCK: "l",
    Hotkey.PAUSE: "p",
    Hotkey.HIDE: "h",
    Hotkey.LIVE: "j",
    Hotkey.COPY: "c",
    Hotkey.PRESET: "r",
    Hotkey.BIGGER: "u",
    Hotkey.SMALLER: "d",
    Hotkey.BAR: "b",
}
"""Preferred letter per hotkey when suggesting conflict-free combinations."""

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


def is_typing_key(key: DictationKey) -> bool:
    """Whether the key types or edits on its own or with Shift."""
    return key.types


def default_scope(key: DictationKey) -> HotkeyScope:
    """A typing key alone (or with Shift) defaults to In Polyglotic's windows;
    combinations and non-typing keys default to Everywhere."""
    return HotkeyScope.APP if is_typing_key(key) else HotkeyScope.EVERYWHERE


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


def scopes(
    chosen_keys: Mapping[Hotkey, DictationKey | None],
    chosen_scopes: Mapping[str, str] | None = None,
) -> dict[Hotkey, HotkeyScope]:
    """Each hotkey's scope now: the learner's saved scope if valid, else
    `default_scope` for its key (or `EVERYWHERE` while unset)."""
    saved = dict(chosen_scopes) if chosen_scopes else {}
    found: dict[Hotkey, HotkeyScope] = {}
    for hotkey in ORDER:
        key = chosen_keys.get(hotkey)
        if key is None:
            found[hotkey] = HotkeyScope.EVERYWHERE
            continue
        raw = saved.get(hotkey.value)
        if raw in (HotkeyScope.APP.value, HotkeyScope.EVERYWHERE.value):
            found[hotkey] = HotkeyScope(raw)
        else:
            found[hotkey] = default_scope(key)
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
    """Why `key` can't be a hotkey's, if it can't (polyglotic-hq 966): every
    non-modifier key alone or with modifiers is valid; only a modifier alone
    (`HELD_ALONE`) or a key another of the app's hotkeys/hold keys already has
    (`APP_HOTKEY`) is refused."""
    del hotkey  # kept for callers passing hotkey=...
    if key.held_alone:
        return Refusal.HELD_ALONE
    if key in frozenset(others):
        return Refusal.APP_HOTKEY
    return None


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


_SAFE_F_KEYS = ("f9", "f10", "f8", "f7", "f6", "f11", "f5", "f4", "f3", "f2", "f1")
"""Function keys tried as conflict-free alternatives (F12 skipped: Windows debugger)."""
_FALLBACK_LETTERS = ("j", "k", "m", "n", "b", "u", "y", "o", "g")


def candidate_alternatives(
    hotkey: Hotkey,
    current: DictationKey,
    taken_by_app: Iterable[DictationKey] = (),
    platform: Platform = Platform.WINDOWS,
) -> list[DictationKey]:
    """Ordered candidate non-typing global alternatives when `current` is held
    by another program, excluding `current` and any key already used by the app."""
    used = set(taken_by_app)
    used.add(current)
    own = OWN_MODIFIERS[platform]
    own_shift = own | {Modifier.SHIFT}
    letter = (
        current.key if current.key in LETTERS else _MNEMONIC_LETTERS.get(hotkey, "j")
    )
    if platform is Platform.MAC:
        alt_mods: tuple[frozenset[Modifier], ...] = (
            own_shift,
            own,
            frozenset((Modifier.ALT, Modifier.WIN)),
            frozenset((Modifier.ALT, Modifier.SHIFT, Modifier.WIN)),
            frozenset((Modifier.CTRL, Modifier.ALT, Modifier.SHIFT)),
        )
    else:
        alt_mods = (
            own_shift,
            own,
            frozenset((Modifier.CTRL, Modifier.SHIFT)),
            frozenset((Modifier.ALT, Modifier.SHIFT)),
            frozenset((Modifier.CTRL, Modifier.ALT, Modifier.WIN)),
        )
    raw: list[DictationKey] = []
    for mods in alt_mods:
        raw.append(DictationKey(mods, letter))
    for fk in _SAFE_F_KEYS:
        raw.append(DictationKey(frozenset(), fk))
    for fk in ("f9", "f10", "f8", "f7"):
        raw.append(DictationKey(own, fk))
    for extra in _FALLBACK_LETTERS:
        raw.append(DictationKey(own_shift, extra))
    result: list[DictationKey] = []
    seen: set[DictationKey] = set()
    for candidate in raw:
        if candidate in used or candidate in seen or is_typing_key(candidate):
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def find_free_alternatives(
    candidates: Iterable[DictationKey],
    can_take: Callable[[str], bool],
    limit: int | None = None,
) -> list[DictationKey]:
    """Test `candidates` against `can_take` (OS registration check) and return
    up to `limit` (default `ALTERNATIVE_COUNT`) free alternatives."""
    wanted = ALTERNATIVE_COUNT.value if limit is None else max(0, limit)
    if wanted == 0:
        return []
    found: list[DictationKey] = []
    for candidate in candidates:
        if can_take(str(candidate)):
            found.append(candidate)
            if len(found) >= wanted:
                break
    return found
