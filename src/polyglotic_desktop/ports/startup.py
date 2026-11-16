"""Starting with Windows (polyglotic-hq 176): the app in the tray when the
learner signs in to Windows - off until they say yes, asked once, after a
good first session. Implemented by `platform/windows/startup.py` (the
user's Run key); none on a copy run from source.
"""

from typing import Protocol

IN_TRAY = "--in-tray"
"""The command-line switch the app is started with at sign-in: in the tray,
not over what the learner opens first (`main` reads it; the OS's adapter
writes it into what starts the app)."""


class StartWithWindows(Protocol):
    def enabled(self) -> bool:
        """The app starts when the learner signs in to Windows."""
        ...

    def set_enabled(self, on: bool) -> None:
        """Start with Windows, or stop; quietly does nothing if Windows
        won't let it (the change isn't the learner's to fix)."""
        ...
