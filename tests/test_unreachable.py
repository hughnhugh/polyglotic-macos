"""Why the server can't be reached, and whose side it's on (polyglotic-hq 251).

The rule (core.listening.unreachable) and the reading of what the network
said (connection.failures), with the errors the network raises built as
they come: a name that can't be looked up, a refusal, no route, a timeout,
a certificate outside its dates or not trusted, a tunnel's 502 or 530, a
proxy's 403, a page instead of the WebSocket, an unusable proxy setting.
The session's own tries against stand-ins: tests/test_session_unreachable.py.
"""

import errno
import socket
import ssl

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import (
    InvalidMessage,
    InvalidProxy,
    InvalidProxyMessage,
    InvalidProxyStatus,
    InvalidStatus,
    InvalidUpgrade,
    InvalidURI,
)
from websockets.http11 import Response

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.failures import (
    why_closed,
    why_not_opened,
    why_refused,
)
from polyglotic_desktop.core.listening.unreachable import (
    RESTART_SEC,
    Side,
    Unreachable,
    after_restart,
    side,
)


def answered(status: int) -> InvalidStatus:
    """The HTTP answer that came instead of the WebSocket's 101."""
    return InvalidStatus(Response(status, "", Headers()))


def certificate(verify_code: int) -> ssl.SSLCertVerificationError:
    error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    error.verify_code = verify_code
    return error


@pytest.mark.parametrize(
    ("error", "why"),
    [
        # no network at all, or DNS failing: Windows' getaddrinfo error
        (socket.gaierror(11001, "getaddrinfo failed"), Unreachable.OFFLINE),
        (OSError(errno.ENETUNREACH, "unreachable network"), Unreachable.OFFLINE),
        (OSError(errno.EHOSTUNREACH, "unreachable host"), Unreachable.OFFLINE),
        (OSError(errno.ENETDOWN, "network is down"), Unreachable.OFFLINE),
        # the server down: refused (Windows' ERROR_CONNECTION_REFUSED), or the
        # tunnel answering for it - 502, 530 (Cloudflare's 1033), 503, 404
        (ConnectionRefusedError(22, "refused", None, 1225), Unreachable.DOWN),
        (answered(502), Unreachable.DOWN),
        (answered(530), Unreachable.DOWN),
        (answered(503), Unreachable.DOWN),
        (answered(404), Unreachable.DOWN),
        # something else answered: a firewall's 403, a proxy's 407, a page
        (answered(403), Unreachable.BLOCKED),
        (answered(407), Unreachable.BLOCKED),
        (answered(200), Unreachable.BLOCKED),
        (InvalidUpgrade("Upgrade"), Unreachable.BLOCKED),
        (
            InvalidProxyStatus(Response(403, "Forbidden", Headers())),
            Unreachable.BLOCKED,
        ),
        (InvalidProxyMessage("no answer"), Unreachable.BLOCKED),
        (
            InvalidProxy("ftp://proxy", "scheme ftp isn't supported"),
            Unreachable.BLOCKED,
        ),
        # TLS: the clock, or something in the way
        (certificate(10), Unreachable.CLOCK),  # expired
        (certificate(9), Unreachable.CLOCK),  # not yet valid
        (certificate(18), Unreachable.NOT_SECURE),  # self-signed: intercepted
        (certificate(62), Unreachable.NOT_SECURE),  # another name: a sign-in page
        (ssl.SSLError(1, "wrong version number"), Unreachable.NOT_SECURE),
        # no telling
        (TimeoutError(), Unreachable.NO_ANSWER),
        (ConnectionResetError(10054, "reset"), Unreachable.NO_ANSWER),
        (
            InvalidMessage("did not receive a valid HTTP response"),
            Unreachable.NO_ANSWER,
        ),
        # the app's own address: ours
        (InvalidURI("wss://", "no host"), Unreachable.SERVER_ERROR),
    ],
)
def test_what_the_network_said_says_why(error: BaseException, why: Unreachable) -> None:
    assert why_not_opened(error) is why


def test_the_servers_close_says_when_its_the_server() -> None:
    assert why_closed(1001, announced=True) is Unreachable.RESTARTING
    assert why_closed(1011) is Unreachable.SERVER_ERROR
    for code in (None, 1000, 1006, 4008):  # dropped, timed out: try again first
        assert why_closed(code) is None


def test_a_close_1001_is_a_restart_only_when_the_server_said_so() -> None:
    """368: our server always sends `server_restarting` (or
    `maintenance_started`) before its close 1001; one without came from
    something else on the way, and the app said "restarting" all the same."""
    assert why_closed(1001) is None  # tried again first, then said as found
    assert why_closed(1001, announced=False) is None
    assert why_closed(1001, announced=True) is Unreachable.RESTARTING


def test_the_refusals_that_wait_say_what_they_are() -> None:
    """Both read "Reconnecting - trying again in 60 s", as if the learner's
    connection were down."""
    sessions = protocol.TooManySessions(limit=2, retry_after=60)
    assert why_refused(sessions) is Unreachable.TOO_MANY_SESSIONS
    tries = protocol.AuthFailed(reason="too_many_attempts", retry_after=30)
    assert why_refused(tries) is Unreachable.TOO_MANY_TRIES
    # the rest are said by their own states (sign in, update, Plus, busy)
    assert why_refused(protocol.AuthFailed(reason="token_not_valid")) is None
    assert why_refused(protocol.ServerBusy(retry_after=30)) is None
    assert why_refused(None) is None


def test_whose_side_each_is_on() -> None:
    yours = {
        Unreachable.OFFLINE,
        Unreachable.BLOCKED,
        Unreachable.NOT_SECURE,
        Unreachable.TOO_MANY_SESSIONS,  # quit it on another PC
    }
    ours = {
        Unreachable.DOWN,
        Unreachable.RESTARTING,
        Unreachable.SERVER_ERROR,
        Unreachable.MAINTENANCE,  # planned: captions come back by themselves (319)
    }
    assert {why for why in Unreachable if side(why) is Side.YOURS} == yours | {
        Unreachable.CLOCK,
        Unreachable.OUT_OF_DATE,  # an antivirus's or a VPN's certificate (313)
    }
    assert {why for why in Unreachable if side(why) is Side.OURS} == ours
    assert {why for why in Unreachable if side(why) is Side.EITHER} == {
        Unreachable.NO_ANSWER,
        Unreachable.TOO_MANY_TRIES,  # others on this network, or this PC
    }


def test_a_restart_is_said_as_one_while_the_server_comes_back() -> None:
    """A deploy: `server_restarting`, close 1001, then each try refused or
    answered by the tunnel (502) until the server is up - "restarting",
    not "down", for the first three minutes."""
    for why in (Unreachable.DOWN, Unreachable.NO_ANSWER, Unreachable.SERVER_ERROR):
        assert after_restart(why, 5.0) is Unreachable.RESTARTING
        assert after_restart(why, RESTART_SEC + 1) is why  # too long: down
        assert after_restart(why, None) is why  # no restart said
    # the learner's own side is said as it is, restart or not
    assert after_restart(Unreachable.OFFLINE, 5.0) is Unreachable.OFFLINE
    assert after_restart(Unreachable.CLOCK, 5.0) is Unreachable.CLOCK
    # and so is the server answering: it's back
    for answered_now in (Unreachable.TOO_MANY_SESSIONS, Unreachable.TOO_MANY_TRIES):
        assert after_restart(answered_now, 5.0) is answered_now
