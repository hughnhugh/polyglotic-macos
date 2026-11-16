"""The server's address, checked: TLS to anything but this PC.

The device token travels in `hello` and as a bearer header (protocol.md),
so it goes over the network in the clear if the app is pointed at an
`http://` or `ws://` address. Plain `http://` is allowed only to a server
on this PC - `127.0.0.1`, `::1` or `localhost`, the local test server the
README and the harness use; anything else must be `https://` (or `wss://`).
Checked where an address is first used, so a wrong setting fails at once
with a clear error rather than leaking the token.
"""

import ipaddress
from urllib.parse import urlsplit

SECURE = ("https", "wss")
PLAIN = ("http", "ws")


def server_address(server: str) -> str:
    """`server` with any trailing slash removed, or ValueError: not an
    `https://` (or `wss://`) address, or a plain one to another machine."""
    cleaned = server.strip().rstrip("/")
    parts = urlsplit(cleaned)
    if parts.scheme not in SECURE + PLAIN or not parts.hostname:
        raise ValueError("the server's address starts with https:// or http://")
    if parts.scheme in PLAIN and not is_this_pc(parts.hostname):
        raise ValueError(
            "plain http:// is only for a server on this PC; the device token"
            " would travel in the clear - use https://"
        )
    return cleaned


def is_this_pc(host: str) -> bool:
    """`localhost` or a loopback address (`127.0.0.1`, `::1`)."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
