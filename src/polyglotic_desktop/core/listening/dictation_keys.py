"""Dictation's key: the key or combination the learner holds to dictate, and the ones it can't be.

polyglotic-hq 289 and the desktop's decision 0081. The learner presses the
key they want in Settings; it's kept as text (`str(key)`): the modifiers
in a fixed order, then the key - "ctrl+alt+d", "f9", "right_ctrl",
"ctrl+win" (modifiers alone, held together). The keys 283 offered
("insert", "f8", "f9", "f10", "scroll_lock", "pause") read as before.

- **A key that types or edits** (like Space or Shift+A) is available for
  dictation in Polyglotic's windows.
- **Other keys with or without modifiers** ("insert", "ctrl+alt+d") is the
  app's while dictation is on: other programs don't get it, so it never
  types into the program underneath.
- **Right Ctrl alone, or modifiers alone** (`held_alone`) can't be taken
  from other programs: they still get it, and another key pressed with it
  means it was a shortcut (Right Ctrl + C), not dictation.

`refusal` says why a key can't be dictation's - a key that types, one
Windows keeps, one every program uses, one of the app's own hotkeys -
before anything is tried; whether another program already has it is only
known by trying (the platform's).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from polyglotic_desktop.core.shared.tunables import tunable

HOLD_RELEASE_POLLS = tunable(
    "hotkeys.hold_release_polls",
    3,
    "polls",
    (1, 10),
    source="651: consecutive up-polls (15 ms each) to confirm a registered hold key is released, absorbing key bounce and auto-repeat gaps",
)


class Modifier(StrEnum):
    """The keys held with another, in the order they're written."""

    CTRL = "ctrl"
    ALT = "alt"
    SHIFT = "shift"
    WIN = "win"


_ORDER = tuple(Modifier)
_MODIFIER_NAMES = frozenset(m.value for m in Modifier)

LETTERS = tuple("abcdefghijklmnopqrstuvwxyz")
DIGITS = tuple("0123456789")
PUNCTUATION = (
    "minus",
    "equal",
    "bracket_left",
    "bracket_right",
    "backslash",
    "semicolon",
    "apostrophe",
    "grave",
    "comma",
    "period",
    "slash",
)
"""Punctuation keys that type characters on their own (or with Shift)."""
FUNCTION_KEYS = tuple(f"f{n}" for n in range(1, 25))
EDITING = (
    "space",
    "enter",
    "tab",
    "backspace",
    "delete",
    "left",
    "right",
    "up",
    "down",
    "home",
    "end",
    "page_up",
    "page_down",
)
"""Keys that edit text on their own (or with Shift)."""
_TYPING_KEYS = frozenset((*LETTERS, *DIGITS, *PUNCTUATION, *EDITING))
OTHER_KEYS = ("insert", "escape", "pause", "scroll_lock", "print_screen", "menu")
MEDIA_KEYS = (
    "media_play",
    "media_stop",
    "media_next",
    "media_prev",
    "volume_up",
    "volume_down",
    "volume_mute",
)
"""Dedicated media and volume keys."""
LONE_MODIFIERS = (
    "right_ctrl",
    "left_ctrl",
    "right_shift",
    "left_shift",
    "right_alt",
    "left_alt",
    "left_win",
    "right_win",
)
"""A modifier pressed and let go on its own, by its side."""
KEYS = frozenset(
    (
        *LETTERS,
        *DIGITS,
        *PUNCTUATION,
        *FUNCTION_KEYS,
        *EDITING,
        *OTHER_KEYS,
        *MEDIA_KEYS,
    )
)
"""Every non-modifier key a hotkey or dictation key can name."""


@dataclass(frozen=True, slots=True)
class DictationKey:
    """A key held to dictate: `key` with `modifiers` held too; `key` None:
    the modifiers alone, held together."""

    modifiers: frozenset[Modifier] = frozenset()
    key: str | None = None

    @classmethod
    def parse(cls, text: str) -> "DictationKey | None":
        """The key kept as `text`; None if it isn't one."""
        parts = text.split("+") if text else []
        if not parts or len(set(parts)) != len(parts):
            return None
        modifiers = []
        key = None
        for i, part in enumerate(parts):
            if part in _MODIFIER_NAMES:
                modifiers.append(Modifier(part))
            elif i == len(parts) - 1 and (
                part in KEYS or part in LONE_MODIFIERS and not modifiers
            ):
                key = part
            else:
                return None
        if key is None and len(modifiers) < 2:
            return None  # one modifier on its own has a side: "right_ctrl"
        if modifiers != sorted(modifiers, key=_ORDER.index):
            return None
        return cls(frozenset(modifiers), key)

    @property
    def parts(self) -> tuple[str, ...]:
        """Its keys, modifiers first, as kept ("ctrl", "alt", "d")."""
        held = tuple(m.value for m in _ORDER if m in self.modifiers)
        return (*held, self.key) if self.key else held

    @property
    def held_alone(self) -> bool:
        """A modifier on its own, or modifiers alone: other programs still
        get it, and another key pressed with it means a shortcut."""
        return self.key is None or self.key in LONE_MODIFIERS

    @property
    def types(self) -> bool:
        """Whether the key types or edits on its own or with Shift."""
        return self.key in _TYPING_KEYS and self.modifiers <= {Modifier.SHIFT}

    def __str__(self) -> str:
        return "+".join(self.parts)


DEFAULT_KEY = DictationKey(key="right_ctrl")
"""Right Ctrl, held alone: on every desktop keyboard and nearly every
laptop's, rarely used, one finger (polyglotic-hq 289; the user decides
against Ctrl + Win). Whoever saved another key keeps it."""


class Refusal(StrEnum):
    """Why a key can't be dictation's."""

    TYPES = "types"
    """It types or edits on its own, or with Shift."""
    ESCAPE = "escape"
    """Esc cancels dictation."""
    WINDOWS = "windows"
    """Windows keeps it (Win+L, Ctrl+Alt+Del, Alt+Tab, Win+H...)."""
    EVERY_PROGRAM = "every_program"
    """Ctrl with a letter or digit: copy, paste, save... in every program."""
    MODIFIER = "modifier"
    """Modifiers alone other than Right Ctrl, or with Win (Ctrl + Win):
    Shift and Alt type (capitals, AltGr's letters), Left Ctrl is every
    shortcut's, and Windows takes Ctrl + Alt for AltGr - each would open
    the mic for a moment at every shortcut begun with it."""
    ALT = "alt"
    """Alt without Ctrl: letting go of it opens a program's menu, and the
    words would be typed into the menu."""
    APP_HOTKEY = "app_hotkey"
    """One of Polyglotic's own hotkeys (Ctrl+Alt+L, P, H...)."""
    HELD_ALONE = "held_alone"
    """A modifier alone, or modifiers alone: a hotkey that's pressed needs a
    key with them (`core.listening.hotkeys`; dictation's, held, can be)."""


def _keys(*texts: str) -> frozenset[DictationKey]:
    keys = (DictationKey.parse(t) for t in texts)
    return frozenset(k for k in keys if k is not None)


WINDOWS_KEEPS = _keys(
    "left_win",
    "right_win",
    "win+l",
    "win+h",
    "win+d",
    "win+tab",
    "win+space",
    "ctrl+alt+delete",
    "ctrl+escape",
    "ctrl+shift+escape",
    "ctrl+space",  # a Chinese or Japanese input method on or off
    "ctrl+shift",  # the next keyboard layout
    "print_screen",  # the Snipping Tool, on Windows 11
    "f12",  # the debugger's, at all times (RegisterHotKey's documentation)
)
"""Keys Windows keeps for itself - those it lets nobody take are said
plainly here; the rest of Win's are found taken when tried. Alt's
(Alt+Tab, Alt+F4, Alt+Esc) are refused as `ALT`."""


def refusal(
    key: DictationKey,
    own: Iterable[DictationKey] = (),
    *,
    typing_in_app: bool = False,
) -> Refusal | None:
    """Why a hold key is refused. Typing keys require an app-scoped binding."""
    modifiers, name = key.modifiers, key.key
    if name == "escape":
        return Refusal.WINDOWS if Modifier.CTRL in modifiers else Refusal.ESCAPE
    if key in WINDOWS_KEEPS:
        return Refusal.WINDOWS
    if Modifier.ALT in modifiers and Modifier.CTRL not in modifiers:
        return Refusal.ALT
    if name in LONE_MODIFIERS and name != "right_ctrl":
        return Refusal.MODIFIER
    if name is None and Modifier.WIN not in modifiers:
        return Refusal.MODIFIER
    if key in frozenset(own):
        return Refusal.APP_HOTKEY
    if not typing_in_app and key.types:
        return Refusal.TYPES
    if (
        modifiers == {Modifier.CTRL}
        and name in (*LETTERS, *DIGITS)
        or key in _CLIPBOARD
    ):
        return Refusal.EVERY_PROGRAM
    return None


_CLIPBOARD = _keys("ctrl+insert", "shift+insert")
"""Copy and paste's older keys, which most programs still take."""
