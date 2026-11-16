"""What the first Mac build doesn't have yet (polyglotic-hq 408, 409): each
piece says so through its port, the way the app already handles an OS
that refuses it, so the interface hides it or explains it.

- `SoundOut` - Home's sample isn't played aloud.

The rest of Windows' pieces have no Mac counterpart at all: the store's
package, the taskbar's ID, fonts read and windows made ahead (`main`
reads False as "not done ahead" and goes on as before).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from polyglotic_desktop.platform.speech_detection import Audio


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
