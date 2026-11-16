"""Where the app keeps what signs it in to the server.

An invite code is redeemed for a device token (protocol.md, "Signing in");
every `hello` then carries the token and the install id it was redeemed
with. `CredentialStore` keeps the two together - on Windows in Credential
Manager (`adapters/windows_credentials.py`), never in a file, never
logged. `main` hands one to the connection.

**The install id outlives the token** (polyglotic-hq 288, decision 0080):
signing out, or a token the server refused, forgets the token only. The
same invite code then signs this PC in again - the server knows the
install it signed in (server decision 0057) - so the id must stay the one
the code was used with. It is a random UUID the app made, never a
hardware or Windows identifier.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DeviceCredentials:
    """This install's id (a UUID the app made; not secret) and the device
    token redeemed for it (secret: kept out of `repr`)."""

    install_id: str
    device_token: str = field(repr=False)


class CredentialStore(Protocol):
    def load(self) -> DeviceCredentials | None:
        """The saved credentials, or None if this install isn't signed in."""
        ...

    def install_id(self) -> str | None:
        """This install's id, signed in or not - kept since its first
        sign-in - or None if it has never signed in here."""
        ...

    def save(self, credentials: DeviceCredentials) -> None: ...

    def forget(self) -> None:
        """Forgets the device token (signed out, or the token was refused);
        the install id stays. Nothing happens if there's no token."""
        ...
