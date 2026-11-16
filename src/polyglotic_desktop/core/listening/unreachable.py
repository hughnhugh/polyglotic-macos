"""Why the server can't be reached or isn't serving, and whose side that is on.

polyglotic-hq 251 (the user, 2026-11-08: "if you cannot connect to server
for whatever reason ... it should notify the user"): while the app waited
to try again, Home, the caption windows and the tray said "Reconnecting"
for every cause - no internet, a firewall, our server down or restarting -
so nobody could tell whether to check their Wi-Fi or wait for us. The
connection now names the cause of each failed try (`Unreachable`); this
module says whose side it is on (`side`), and keeps a restart said as one
while the server comes back (`after_restart`). The words are the
interface's (ui_next).
"""

from enum import StrEnum


class Unreachable(StrEnum):
    """Why the last try to open a session failed, or why the server ended it."""

    OFFLINE = "offline"
    """This PC couldn't look the server's name up, or has no route to it:
    its internet is down - or, far less likely, our name is."""
    NO_ANSWER = "no_answer"
    """Nothing answered in time, or the connection was cut before the
    server answered: the learner's internet, or our server - no telling."""
    DOWN = "down"
    """Our server isn't serving: the connection was refused, or the tunnel
    in front of it answered for it (502, 503, 530 ...), so the learner's
    internet works."""
    RESTARTING = "restarting"
    """Our server said it's restarting (`notice` `server_restarting`, then
    close 1001)."""
    SERVER_ERROR = "server_error"
    """Our server took the connection but failed the session: close 1011,
    or no answer to `hello`."""
    BLOCKED = "blocked"
    """Something on this network answered instead of our server, or
    wouldn't pass the WebSocket on: a proxy or a firewall."""
    NOT_SECURE = "not_secure"
    """The secure connection failed: something on this network is in the
    way - a firewall, an antivirus, a Wi-Fi sign-in page."""
    CLOCK = "clock"
    """This PC's clock is wrong for certain - before this copy of the app
    was built - and a certificate on the way is out of date at the time it
    says, so the connection is refused (connection.tls, decision 0104). A
    clock that's wrong while the certificates check is let through, and
    said on Home without stopping anything."""
    OUT_OF_DATE = "out_of_date"
    """A certificate on the way to our server is out of date, and this
    PC's clock looks right: something on this network is in the way - an
    antivirus's HTTPS scanning or a VPN, most often - with a certificate
    of its own (connection.tls, decision 0104; polyglotic-hq 313)."""
    # the server answered, and won't serve this PC for now (protocol.md's
    # refusals that wait): read "Reconnecting", like a dropped connection
    TOO_MANY_SESSIONS = "too_many_sessions"
    """The account has as many sessions open as it may, on other PCs
    (`too_many_sessions`, close 4029)."""
    TOO_MANY_TRIES = "too_many_tries"
    """Too many failed sign-ins from this network: the server's guessing
    limit (`auth_failed` `too_many_attempts`, close 4003)."""
    MAINTENANCE = "maintenance"
    """Our server is in a planned maintenance window it told the app of: it
    refused listening for it (`server_busy` `reason` `maintenance`), or
    didn't answer while the window is on (core.listening.maintenance;
    polyglotic-hq 319)."""


class Side(StrEnum):
    """Whose problem it is, as far as the app can tell."""

    YOURS = "yours"
    """This PC or its network: something for the learner to check."""
    OURS = "ours"
    """Our server: nothing to do but wait - captions come back by themselves."""
    EITHER = "either"
    """No telling: check the internet; if it works, the problem is ours."""


_SIDES = {
    Unreachable.OFFLINE: Side.YOURS,
    Unreachable.NO_ANSWER: Side.EITHER,
    Unreachable.DOWN: Side.OURS,
    Unreachable.RESTARTING: Side.OURS,
    Unreachable.SERVER_ERROR: Side.OURS,
    Unreachable.BLOCKED: Side.YOURS,
    Unreachable.NOT_SECURE: Side.YOURS,
    Unreachable.CLOCK: Side.YOURS,
    Unreachable.OUT_OF_DATE: Side.YOURS,
    Unreachable.TOO_MANY_SESSIONS: Side.YOURS,
    Unreachable.TOO_MANY_TRIES: Side.EITHER,
    Unreachable.MAINTENANCE: Side.OURS,
}


def side(why: Unreachable) -> Side:
    return _SIDES[why]


RESTART_SEC = 180.0
"""How long after the server said it's restarting a failed try is still the
restart: a deploy takes the server down for under a minute (polyglotic-hq
184 measured 28.9 s), so three minutes is generous - after that, it's down."""


def after_restart(why: Unreachable, since_restart: float | None) -> Unreachable:
    """What to say about a failed try `since_restart` seconds after the
    server said it's restarting (None: it hasn't): while the restart may
    still be going on, a try our server didn't answer - refused, the tunnel
    answering for it, no answer, a failed session - is the restart, not the
    server down. Anything else - the learner's side, or the server
    answering - is said as it is."""
    if since_restart is None or since_restart > RESTART_SEC:
        return why
    return Unreachable.RESTARTING if why in NOT_ANSWERED else why


NOT_ANSWERED = (Unreachable.DOWN, Unreachable.NO_ANSWER, Unreachable.SERVER_ERROR)
"""The causes a restarting server shows as: it isn't answering."""
