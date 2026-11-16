"""How the app names itself in its own web requests: one place.

Python's default (`Python-urllib/3.x`) is refused by Cloudflare's Browser
Integrity Check with a 403 (error 1010), so sign-in, the update feed,
feedback and problem reports all failed through `api.polyglotic.io` and
`updates.polyglotic.io` on 2026-11-11 while a browser and curl got through
(polyglotic-hq journal, that day). The zone now skips that check on the two
hosts; the app also says who it is, so neither depends on the other.

Plain values only: no logic, no Qt.
"""

USER_AGENT = "Polyglotic-Desktop"
"""The `User-Agent` of every request the app makes itself. No version in it:
the server learns the version from the protocol, and a fixed name is one
thing to allow at the edge."""

HEADERS = {"User-Agent": USER_AGENT}
"""For a request with no other headers."""
