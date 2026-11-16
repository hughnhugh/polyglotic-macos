"""Why a try to open a session failed, from what the network said (polyglotic-hq 251).

The session used to read every failure alike - "couldn't open a session" -
and Home said "Reconnecting" whatever it was. What the network answers
tells the causes apart (core.listening.unreachable has whose side each is
on):
- **the name couldn't be looked up, or there's no route** (no network at
  all, DNS failing): offline;
- **refused**, or **the tunnel answered for the server** - Cloudflare's 502
  or 530 when the server behind it is down, 503, 404 from the tunnel's
  catch-all - our server is down, and the learner's internet works;
- **something else answered**: a 403, a 407, a page instead of the
  WebSocket, a proxy refusing to connect - a proxy or firewall is blocking;
- **TLS failed**: on the certificate's dates - still, after the try that
  checks the leaf's dates itself (connection.tls, decision 0104) - this
  PC's clock when it's before the app was built, else something in the way
  with an out-of-date certificate of its own; otherwise
  something on the network is in the way (an antivirus, a Wi-Fi sign-in
  page, a plain-HTTP answer);
- **nothing answered in time**, or the connection was cut before an
  answer: no telling whose.
A session our server closed says why with its code: 1001 after
`server_restarting` is a restart, 1011 a failed session. And two of its
refusals that wait aren't the connection at all: too many sessions on the
account, too many failed sign-ins from this network (`why_refused`).
"""

import errno
import socket
import ssl

from websockets.exceptions import (
    InvalidHandshake,
    InvalidMessage,
    InvalidProxy,
    InvalidStatus,
    InvalidURI,
    ProxyError,
)

from polyglotic_desktop.connection import protocol, tls
from polyglotic_desktop.connection.reconnect import GOING_AWAY, SERVER_ERROR, Refusal
from polyglotic_desktop.core.listening.unreachable import Unreachable

NO_ROUTE = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN}
"""No network, or no way to it (Windows' WSAENETUNREACH, WSAEHOSTUNREACH
and WSAENETDOWN on Windows)."""

SERVER_STATUSES = {404, 429}
"""HTTP answers that come from our side of the tunnel - its catch-all's 404,
a rate limit - besides every 5xx."""


def why_not_opened(error: BaseException) -> Unreachable:
    """Why `error`, raised while opening a session, kept it from opening."""
    if isinstance(error, tls.LeafRefused):  # tried again (tls): still refused
        return Unreachable.CLOCK if error.clock_wrong else Unreachable.OUT_OF_DATE
    if tls.on_dates(error) is not None:  # not tried again: none since 313
        return Unreachable.CLOCK
    if isinstance(error, ssl.SSLError):
        return Unreachable.NOT_SECURE
    if isinstance(error, socket.gaierror):
        return Unreachable.OFFLINE
    if isinstance(error, ConnectionRefusedError):
        return Unreachable.DOWN
    if isinstance(error, OSError) and error.errno in NO_ROUTE:
        return Unreachable.OFFLINE
    if isinstance(error, InvalidStatus):
        return why_answered(error.response.status_code)
    if isinstance(error, ProxyError | InvalidProxy):
        return Unreachable.BLOCKED
    if isinstance(error, InvalidMessage):  # no HTTP answer: cut, or not HTTP
        return Unreachable.NO_ANSWER
    if isinstance(error, InvalidURI):  # our address: not the learner's doing
        return Unreachable.SERVER_ERROR
    if isinstance(error, InvalidHandshake):  # answered, but not as the server
        return Unreachable.BLOCKED
    return Unreachable.NO_ANSWER


def why_answered(status: int) -> Unreachable:
    """Why an HTTP answer that isn't the server's own came instead: from
    our side of the tunnel (5xx, its catch-all's 404, a rate limit) the
    server is down; anything else came from something on the network."""
    if status >= 500 or status in SERVER_STATUSES:
        return Unreachable.DOWN
    return Unreachable.BLOCKED


def why_refused(refusal: Refusal | None) -> Unreachable | None:
    """Why the server, answering `hello`, won't serve this PC for now - for
    the refusals the app waits out without the learner (None: any other,
    or none; a full server is `server_busy`, said as it was - 208). A
    refusal for a planned maintenance window is the maintenance (319)."""
    if isinstance(refusal, protocol.ServerBusy) and refusal.reason == "maintenance":
        return Unreachable.MAINTENANCE
    if isinstance(refusal, protocol.TooManySessions):
        return Unreachable.TOO_MANY_SESSIONS
    if (
        isinstance(refusal, protocol.AuthFailed)
        and refusal.reason == "too_many_attempts"
    ):
        return Unreachable.TOO_MANY_TRIES
    return None


ANNOUNCED_GOING_AWAY = ("server_restarting", "maintenance_started")
"""The `notice` codes our server sends just before its close 1001
(protocol.md): a restart, or a planned maintenance window's start."""


def why_closed(close_code: int | None, announced: bool = False) -> Unreachable | None:
    """Why our server ended a session, by its close code - None when the
    code doesn't say it's the server's doing (a dropped connection is
    tried again before anything is said). A close 1001 is the restart only
    when the server announced it (`announced`: an `ANNOUNCED_GOING_AWAY`
    notice came first): ours always does, so one without came from
    something else on the way - a proxy, the tunnel - and isn't said as a
    restart (polyglotic-hq 368)."""
    if close_code == GOING_AWAY:
        return Unreachable.RESTARTING if announced else None
    if close_code == SERVER_ERROR:
        return Unreachable.SERVER_ERROR
    return None
