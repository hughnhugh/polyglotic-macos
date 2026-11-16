"""Starting at sign-in on a Mac (polyglotic-hq 428; `ports.startup`, as
`platform/windows/startup.py` is Windows'): the app as a login item,
through ServiceManagement's `SMAppService.mainAppService` (macOS 13 and
later; the app needs 14.2). No administrator, and System Settings >
General > Login Items lists it and can turn it off.

- **enabled:** macOS says the app is a login item (`status` enabled). One
  waiting for the learner's approval in Login Items, or turned off there,
  isn't.
- **set_enabled:** registers or unregisters it; quietly does nothing if
  macOS won't (the port's rule) - the log says why, by its error code.
- **In the menu bar, not over what opens first:** macOS opens a login item
  without arguments, so the app can't be given `--in-tray` as Windows'
  Run value gives it: on a Mac it opens with its window (docs/macos.md).

Only the packed app (`Polyglotic.app`, signed) can be a login item: `main`
offers it only there. The service is handed in, so tests never touch the
Mac's.
"""

import ctypes
import logging
from typing import Protocol

log = logging.getLogger(__name__)

NOT_REGISTERED, ENABLED, REQUIRES_APPROVAL, NOT_FOUND = 0, 1, 2, 3
"""`SMAppServiceStatus`."""


class AppService(Protocol):
    """The parts of `SMAppService.mainAppService` used here."""

    def status(self) -> int: ...

    def register(self) -> int:
        """0, or the error's code."""
        ...

    def unregister(self) -> int:
        """0, or the error's code."""
        ...


class LoginItem:
    """`StartWithWindows` on a Mac: the app at `executable` (inside its
    bundle; macOS knows the bundle, so it isn't used) as a login item."""

    def __init__(self, _executable: str, service: AppService | None = None) -> None:
        self._service = service if service is not None else MainAppService()

    def enabled(self) -> bool:
        try:
            return self._service.status() == ENABLED
        except OSError:
            return False

    def set_enabled(self, on: bool) -> None:
        try:
            if on:
                code = self._service.register()
            elif self._service.status() in (NOT_REGISTERED, NOT_FOUND):
                return  # nothing to take away (never added: NOT_FOUND, 428's run)
            else:
                code = self._service.unregister()
        except OSError as error:
            log.warning("macOS's login items can't be reached: %s", error)
            return
        if code:
            what = "add the app to" if on else "take the app off"
            log.warning("macOS wouldn't %s its login items: error %d", what, code)


class MainAppService:
    """`AppService` through ServiceManagement, on whatever thread asks
    (Home's, the interface's): each call inside an autorelease pool."""

    def status(self) -> int:
        from polyglotic_desktop.platform.macos import objc

        with objc.pool():
            return int(objc.send(self._service(), "status", restype=ctypes.c_long))

    def register(self) -> int:
        return self._call("registerAndReturnError:")

    def unregister(self) -> int:
        return self._call("unregisterAndReturnError:")

    def _call(self, selector: str) -> int:
        from polyglotic_desktop.platform.macos import objc

        with objc.pool():
            error = ctypes.c_void_p()
            done = objc.send(
                self._service(),
                selector,
                ctypes.byref(error),
                restype=ctypes.c_bool,
                argtypes=[ctypes.POINTER(ctypes.c_void_p)],
            )
            if done:
                return 0
            if not error.value:
                return -1
            return int(objc.send(error.value, "code", restype=ctypes.c_long)) or -1

    @staticmethod
    def _service() -> int:
        from polyglotic_desktop.platform.macos import objc

        objc.load("ServiceManagement")
        found = objc.send(objc.cls("SMAppService"), "mainAppService")
        if not found:
            raise OSError("macOS has no app service for this app")
        return int(found)
