"""SettingsStore: the user's settings, remembered between launches.

The settings themselves - what they are, their defaults, which values
are allowed - belong to whoever uses them (the interface's `AppSettings`);
the store only keeps them: a flat mapping of names to plain JSON values
(strings, numbers, booleans, None, lists and mappings of those). Like
`CredentialStore`, it's needed by a plug (the UI) rather than by core,
and lives here because two plugs can't import each other (decision 0008).
"""

from collections.abc import Mapping
from typing import Protocol


class SettingsStore(Protocol):
    def load(self) -> dict[str, object]:
        """The settings saved last - empty if none were, or they can't be
        read (the user then gets the defaults, not an error)."""
        ...

    def save(self, values: Mapping[str, object]) -> None:
        """Keeps `values` in place of what was saved, all or nothing."""
        ...
