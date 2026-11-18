"""What the app needs from the operating system beyond audio (decision 0038).

Small interfaces each OS implements in `platform/<os>/` (Windows now; macOS
and Linux later), which `main` picks in one place (`main.os_adapters`) and
hands over:
- `OnTop` and `ForegroundWatch` - the caption windows kept above a game
  that is itself always on top;
- `Hotkeys` - Ctrl+Alt+L, P and H, wherever the learner is;
- `HoldKey`, `TypeText`, `KeyboardWindow` - dictation's key, held, and
  its text typed into the program with the keyboard (polyglotic-hq 283);
  `TypingPermission` - where the OS lets an app type only with the
  learner's leave (a Mac's Accessibility), whether it has it and where to
  give it (polyglotic-hq 438);
- `MicPermission` - where the OS asks the learner before an app hears the
  microphone (a Mac's), whether it may and the question (polyglotic-hq 478);
- `KeyState` - whether a key or the mouse is held now, for the settings
  popovers;
- `LightTaskbar` - whether the taskbar the tray icon sits on is light;
- `TaskbarIdentity` - the ID the taskbar knows the app by (decision 0051);
- `StorePackage` - whether this copy is the OS's app store's package
  (decision 0056);
- `OsVersion` - the OS's version number, as feedback carries it (its name,
  protocol.md's `os`, is typed with the protocol: `connection.protocol.Os`);
- `DataFolder` - where the user's own files live (decision 0014);
- `ErrorBox` - the box an installed app shows when it can't start, without
  Qt;
- `LaunchClock` - seconds since this process was launched, for the
  install check's start time;
- `Translocation` - whether macOS runs the app from a temporary copy it
  can't update itself in, and moving it to Applications (polyglotic-hq 433).

Audio has its own: `ports/capture.py`; the device token too:
`ports/credentials.py`.
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol


class OnTop(Protocol):
    """The OS's always-on-top band, for the caption windows."""

    def game_in_front(self) -> bool:
        """Whether the foreground window is a game that is itself always on
        top, covering its screen."""
        ...

    def put_on_top(self, windows: Sequence[int]) -> None:
        """These native windows, bottom first, at the top of the band -
        none activated."""
        ...


class ForegroundWatch(Protocol):
    """Tells (on a thread of its own) whenever another app's window comes to
    the front; made with what to call."""

    def start(self) -> bool:
        """Starts watching; False if the OS wouldn't say."""
        ...

    def stop(self) -> None: ...


class Hotkeys(Protocol):
    """Key combinations for the whole system; made with each key (a letter
    or digit) and what to call, on the hotkeys' own thread, when it's
    pressed."""

    def start(self) -> list[str]:
        """Takes the keys and starts listening; returns those another app
        already has (not working here)."""
        ...

    def stop(self) -> None: ...


class HoldKey(Protocol):
    """A key or combination held anywhere - dictation's (polyglotic-hq 283,
    289); made with the key as kept (`core.listening.dictation_keys.
    DictationKey`, "ctrl+alt+d", "right_ctrl") and what to call, on the
    key's own thread: when the whole of it is down, when any of it comes
    up, and - for a key held alone (Right Ctrl), which other programs still
    get - when another key went down with it: a shortcut, not dictation.
    A key that isn't held alone is the app's while it's held: other
    programs don't get it."""

    def start(self) -> bool:
        """Takes the key and starts listening; False if another program
        has it (nothing then happens when it's held)."""
        ...

    def stop(self) -> None: ...


TypeText = Callable[[str], bool]
"""Types text into the program that has the keyboard, as the keyboard
would - the clipboard untouched; False if the OS took none of it."""


class TypingPermission(Protocol):
    """The OS's leave to type into other programs, where it asks for one
    (a Mac: Privacy & Security > Accessibility; Windows has none)."""

    def allowed(self) -> bool:
        """Whether the app has it now - asking nothing."""
        ...

    def open_settings(self) -> None:
        """Opens the OS's settings where the learner gives it."""
        ...


class MicPermission(Protocol):
    """The OS's leave to hear the microphone, where it asks the learner for
    one (a Mac: Privacy & Security > Microphone; Windows asks none) - asked
    when a caption window first shows the learner's speech (polyglotic-hq
    478)."""

    def allowed(self) -> bool | None:
        """True if given, False if refused (or not the learner's to give),
        None if never asked yet - asking nothing."""
        ...

    def ask(self, answered: Callable[[bool], None]) -> None:
        """The OS's own question, with the app's line saying why (a Mac
        app's `NSMicrophoneUsageDescription`); `answered` is called once
        with the answer, on any thread."""
        ...


KeyboardWindow = Callable[[], int]
"""The window that has the keyboard now, as the OS's handle (0: none) -
dictation types only into the one that had it when the speech was cut."""

KeyState = Callable[[str], bool]
"""Whether "escape", "backspace" or "mouse" (any button) is held now (or
was pressed since last asked), anywhere."""

LightTaskbar = Callable[[], bool]
"""Whether the taskbar (or menu bar) the tray icon sits on is light; it can
differ from the apps' colours."""

TaskbarIdentity = Callable[[str], str]
"""Names this process to the taskbar as the app, before any window: the ID
the installer already gave it, if it did (so it agrees with the installer's
shortcuts), else the one given here. Returns the ID the taskbar has ("" if
the OS wouldn't take one). The taskbar groups, pins and draws the app's
windows by it."""

StorePackage = Callable[[], str | None]
"""The package this copy runs from, if the OS installed it as one - on
Windows an MSIX, the Microsoft Store's copy - by its name; None for our
installer's copy or a run from source. The store then updates it, not the
app (decision 0056)."""

OsVersion = Callable[[], str]
"""The OS's version number, as feedback carries it ("10.0.26200")."""

DataFolder = Callable[[], Path]
"""The folder for the user's own files - settings, learning data, the
outbox - that installing and uninstalling leave alone."""

ErrorBox = Callable[[str, str], None]
"""Shows a title and a message in the OS's own box, and waits until it's
closed - for when the app can't start, so not through Qt."""

LaunchClock = Callable[[], float]
"""Seconds since this process was launched (the interpreter and the
imports included)."""


class Translocation(Protocol):
    """macOS's App Translocation (polyglotic-hq 433, decision 0205): an app
    downloaded from the internet and opened outside Applications (from
    Downloads, say) runs from a read-only copy macOS makes at a random path,
    which Velopack can't replace, so it never updates."""

    def translocated(self) -> bool:
        """Whether this app runs from such a copy."""
        ...

    def move(self) -> Path:
        """Moves the app itself (not the copy) into Applications - or the
        user's own Applications folder when that one can't be written - and
        returns where it is now. Raises `OSError` if it can't."""
        ...

    def reopen(self, app: Path) -> None:
        """Opens the app at `app` once this process has ended."""
        ...
