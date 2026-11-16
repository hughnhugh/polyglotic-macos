"""What the first Mac build doesn't have yet (polyglotic-hq 408, 409): each
piece says so through its port, the way the app already handles an OS
that refuses it, so the interface hides it or explains it.

- `Hotkeys` - every key reported as not working here, so the menus stop
  showing Ctrl+Alt+L, P and H (`ui.app.hotkeys_taken`); later Carbon's
  `RegisterEventHotKey`.
- `SoundOut` - Home's sample isn't played aloud.
- `KeyState` - nothing is known held outside the app: Esc pressed in
  another app doesn't cancel dictation, and a settings popover closes on
  a click in it, not elsewhere.
- Voices and starting at sign-in have no adapter yet: `OsAdapters.speaker`
  and `start_at_sign_in` are None, so the word card offers no voice and
  Home never offers to start the app at sign-in; later
  AVSpeechSynthesizer and `SMAppService`.

The rest of Windows' pieces have no Mac counterpart at all: the store's
package, the taskbar's ID, fonts read and windows made ahead (`main`
reads False as "not done ahead" and goes on as before).
"""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyglotic_desktop.platform.speech_detection import Audio


class NoHotkeys:
    """`Hotkeys`: none on a Mac yet - each reported as not working here."""

    def __init__(self, keys: Mapping[str, Callable[[], None]]) -> None:
        self._keys = list(keys)

    def start(self) -> list[str]:
        return list(self._keys)

    def stop(self) -> None:
        pass


def held(_name: str) -> bool:
    """`KeyState`: nothing known held outside the app."""
    return False


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
