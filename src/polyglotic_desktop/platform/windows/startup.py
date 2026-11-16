"""Starting with Windows (polyglotic-hq 176; `ports.startup`): a value in
the user's own Run key, `HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\
CurrentVersion\\Run` - no administrator, and Windows' own Settings > Apps >
Startup lists it and can turn it off. The value starts the installed app
in the tray (`--in-tray`), not over what the learner opens first.

The registry is handed in (`winreg` itself in the app), so tests never
touch the PC's.
"""

import winreg
from typing import Any, Protocol

from polyglotic_desktop.ports.startup import IN_TRAY  # main reads it too (0038)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Polyglotic"


class Registry(Protocol):
    """The parts of `winreg` used here."""

    HKEY_CURRENT_USER: Any
    KEY_READ: int
    KEY_SET_VALUE: int
    REG_SZ: int

    def OpenKey(
        self, key: Any, sub_key: str, reserved: int = 0, access: int = ...
    ) -> Any: ...
    def QueryValueEx(self, key: Any, name: str) -> tuple[Any, int]: ...
    def SetValueEx(
        self, key: Any, name: str, reserved: int, kind: int, value: str
    ) -> None: ...
    def DeleteValue(self, key: Any, name: str) -> None: ...


def command_for(executable: str) -> str:
    """What the Run value says: the app, quoted, started in the tray. The
    installer keeps the app at the same path across updates (Velopack's
    `current` folder)."""
    return f'"{executable}" {IN_TRAY}'


class RunAtSignIn:
    """`StartWithWindows` through the user's Run key, for the app at
    `executable`."""

    def __init__(self, executable: str, registry: Registry | None = None) -> None:
        self.command = command_for(executable)
        self._registry: Registry = registry or winreg

    def enabled(self) -> bool:
        reg = self._registry
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
                value, _ = reg.QueryValueEx(key, VALUE)
        except OSError:
            return False
        return value == self.command

    def set_enabled(self, on: bool) -> None:
        reg = self._registry
        try:
            with reg.OpenKey(
                reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE
            ) as key:
                if on:
                    reg.SetValueEx(key, VALUE, 0, reg.REG_SZ, self.command)
                else:
                    reg.DeleteValue(key, VALUE)
        except OSError:
            pass  # not there to delete, or Windows refused: nothing to fix
