"""Whether this copy is an MSIX package - the Microsoft Store's (decision
0056).

Windows gives a process started from an installed MSIX a package
identity; any other process has none. The Store's copy then differs from
our installer's: the Store updates it (Velopack can't), Windows knows it on
the taskbar by the package's own app ID, and its writes to
`HKEY_CURRENT_USER` stay in the package's private copy of it - so a Run
value there would never start it with Windows. `main` reads it once, at
start. A sideloaded rehearsal of the package (tools/package/msix.py) is a
package too.
"""

import ctypes
from collections.abc import Callable
from ctypes import wintypes

_kernel32 = ctypes.WinDLL("kernel32")
for _name in ("GetCurrentPackageFamilyName", "GetCurrentApplicationUserModelId"):
    _function = getattr(_kernel32, _name)
    _function.argtypes = [ctypes.POINTER(ctypes.c_uint32), wintypes.LPWSTR]
    _function.restype = wintypes.LONG

_ERROR_INSUFFICIENT_BUFFER = 122  # the length is in, ask again with room


def _asked(call: Callable[..., int]) -> str | None:
    """A string an AppModel call gives, or None when there's none
    (APPMODEL_ERROR_NO_PACKAGE, _NO_APPLICATION: not a package)."""
    length = ctypes.c_uint32(0)
    if call(ctypes.byref(length), None) != _ERROR_INSUFFICIENT_BUFFER:
        return None
    found = ctypes.create_unicode_buffer(length.value)
    if call(ctypes.byref(length), found) != 0:
        return None
    return found.value or None


def store_package() -> str | None:
    """This copy's package family name (`Name_publisherhash`) if it runs
    from an MSIX package, else None: our installer's copy, or from
    source."""
    return _asked(_kernel32.GetCurrentPackageFamilyName)


def packaged_app_id() -> str | None:
    """The app ID Windows gave this package's app (`<family name>!<app
    ID>`), the only one it may use on the taskbar; None if not a package."""
    return _asked(_kernel32.GetCurrentApplicationUserModelId)
