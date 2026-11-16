"""What the first Mac build doesn't have yet (polyglotic-hq 408, 409): each
piece says so through its port, the way the app already handles an OS
that refuses it, so the interface hides it or explains it.

- `HoldKey` - never taken (dictation's key; Settings says so); later with
  the Accessibility permission, as typing into other apps (`type_text`).
- `OnTop` and `ForegroundWatch` - Qt's always-on-top flag only: the caption
  windows stay above ordinary windows, not over full-screen Spaces; later
  a non-activating panel at a higher level (polyglotic-hq 171).
- `SoundOut` - Home's sample isn't played aloud.

The rest of Windows' pieces have no Mac counterpart at all: the store's
package, the taskbar's ID, fonts read and windows made ahead (`main`
reads False as "not done ahead" and goes on as before).
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyglotic_desktop.platform.speech_detection import Audio


class NoHoldKey:
    """`HoldKey`: dictation's key isn't held on a Mac yet."""

    def __init__(self, *_key_and_calls: object) -> None:
        pass

    def start(self) -> bool:
        return False

    def stop(self) -> None:
        pass


def type_text(_text: str) -> bool:
    """`TypeText`: nothing typed into other apps yet."""
    return False


def keyboard_window() -> int:
    """`KeyboardWindow`: none known."""
    return 0


def held(_name: str) -> bool:
    """`KeyState`: nothing known held outside the app."""
    return False


class QtOnTop:
    """`OnTop`: Qt's always-on-top flag, which the caption windows already
    have, is all there is on a Mac yet - no game is seen in front."""

    def game_in_front(self) -> bool:
        return False

    def put_on_top(self, _windows: Sequence[int]) -> None:
        pass


class NoForegroundWatch:
    """`ForegroundWatch`: macOS isn't asked which app is in front yet."""

    def __init__(self, _changed: Callable[[], None]) -> None:
        pass

    def start(self) -> bool:
        return False

    def stop(self) -> None:
        pass


class NoSound:
    """`SoundOut`: Home's sample isn't played aloud on a Mac yet."""

    def play(self, _audio: "Audio", _rate: int) -> bool:
        return False

    def stop(self) -> None:
        pass


def none_found() -> None:
    """`StorePackage`: no app store's package."""
    return


def same_name(name: str) -> str:
    """`TaskbarIdentity`: the Dock knows the app by its bundle, not an ID
    the app gives itself - the name given is logged as it is."""
    return name


def not_done() -> bool:
    """`read_fonts`: not read ahead (Qt reads them when first asked)."""
    return False


def not_made(_widget: int) -> bool:
    """`make_native_window`: not made ahead."""
    return False


def not_metered() -> bool:
    """Whether the connection is metered: macOS isn't asked yet."""
    return False
