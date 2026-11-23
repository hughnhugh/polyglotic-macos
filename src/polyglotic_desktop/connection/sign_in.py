"""Signing in: an invite code redeemed for a device token (protocol.md, "Signing in").

`POST /v1/redeem` with the code and this install's id; the token that
comes back is saved in the `CredentialStore` (Windows Credential Manager)
with the install id it was redeemed for. The code is read as protocol.md
says - case, spaces and dashes don't matter, `O` is `0` and `I`/`L` are
`1` - and one that can't be a code at all is answered here, without a
request (so a typo doesn't count towards the server's guessing limit).

**The install id is this PC's for good** (polyglotic-hq 288, decision
0080): the one kept since the first sign-in, signed out or not, is sent
again - a new one only on a PC that has never signed in. So the same
invite code signs this PC in again after signing out, a refused token or
a reinstall (server decision 0057), and a new code for the same PC keeps
its install.

Plain HTTP from the standard library: one small request, made rarely, and
it must work when no session can be opened. It blocks - call it off the
UI thread. Neither the invite code nor the token is ever logged or put in
an error.

Signed in, the code from a Plus email goes onto this account: the request
carries the device token (`Authorization: Bearer`, protocol.md; server
#192, polyglotic-hq 193 and 185) - without it the server would open a
second account. A subscription already paying is answered `PlusAlready`
(the code isn't used); a token the server no longer takes, `SignInAgain`;
an invite code, which would start a new account, `SignOutFirst` (the code
isn't used: server #205, polyglotic-hq 208) - so signed in, a code never
changes the account this PC is signed in to. A Plus email's code whose
subscription was cancelled before it was used is `SubscriptionEnded`
(server #252, polyglotic-hq 258).
"""

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from polyglotic_desktop.connection import protocol, tls
from polyglotic_desktop.connection.addresses import server_address
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.failures import why_answered, why_not_opened
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.shared.client import USER_AGENT
from polyglotic_desktop.ports.credentials import CredentialStore, DeviceCredentials

TIMEOUT_SEC = 15.0
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford's base32 (protocol.md)
CODE_LENGTH = 16
# U+FF01 through U+FF5E are the full-width counterparts of printable ASCII.
_FULL_WIDTH_ASCII = dict(zip(range(0xFF01, 0xFF5F), range(0x21, 0x7F), strict=True))


def narrow_code(text: str) -> str:
    """Accept full-width ASCII from an input method and trim edge whitespace."""
    return text.translate(_FULL_WIDTH_ASCII).strip()


_LOOK_ALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


def invite_code(text: str) -> str | None:
    """`text` as an invite code in four groups (`7KQM-X2PD-9VHT-C4RA`), or
    None if it can't be one: 16 characters of Crockford's base32 once
    case, spaces and dashes are set aside and look-alikes read as digits."""
    cleaned = "".join(narrow_code(text).upper().replace("-", "").split()).translate(
        _LOOK_ALIKES
    )
    if len(cleaned) != CODE_LENGTH or any(c not in ALPHABET for c in cleaned):
        return None
    return "-".join(cleaned[i : i + 4] for i in range(0, CODE_LENGTH, 4))


@dataclass(frozen=True, slots=True)
class SignedIn:
    cohort: str


@dataclass(frozen=True, slots=True)
class NotACode:
    """Not 16 letters and digits: mistyped, or not an invite code at all.
    Nothing was sent."""


@dataclass(frozen=True, slots=True)
class InviteNotValid:
    """Unknown, used, expired or revoked - the server doesn't say which."""


@dataclass(frozen=True, slots=True)
class SubscriptionEnded:
    """A code from a Plus email whose subscription ended before the code
    was used - cancelled at Paddle - so it gives no Plus. The server
    answers `invite_code_not_valid` with `reason` `subscription_ended`
    (protocol.md; server #252, polyglotic-hq 256 and 258)."""


@dataclass(frozen=True, slots=True)
class PlusAlready:
    """A subscription pays for this account's Plus already: the code wasn't
    used, and still works later or on another account."""


@dataclass(frozen=True, slots=True)
class SignInAgain:
    """The server doesn't take this PC's sign-in any more (signed in, the
    code was sent with it)."""


@dataclass(frozen=True, slots=True)
class SignOutFirst:
    """Signed in, an invite code: it would start a new account, so the
    server didn't use it. It works once this PC has signed out - signing
    out keeps what's this account's from reaching the next (208)."""


@dataclass(frozen=True, slots=True)
class TooManyAttempts:
    retry_after: int


@dataclass(frozen=True, slots=True)
class RedeemFailed:
    """The server couldn't be reached, or answered something unexpected.
    `why` is for the user and the log: never the code or a token.
    `unreachable`: why it couldn't be reached, if that's known - said as
    Home says it (connection.failures; polyglotic-hq 251)."""

    why: str
    unreachable: Unreachable | None = None


RedeemResult = (
    SignedIn
    | NotACode
    | InviteNotValid
    | SubscriptionEnded
    | PlusAlready
    | SignInAgain
    | SignOutFirst
    | TooManyAttempts
    | RedeemFailed
)


def redeem(
    server: str,
    invite_code_text: str,
    store: CredentialStore,
    app: AppInfo,
    timeout: float = TIMEOUT_SEC,
    signed_in: bool = False,
) -> RedeemResult:
    """Redeems the invite code the user typed at `server` (`https://<host>`, or
    `http://127.0.0.1:8080` for a local test server) and, if it works,
    saves the device token in `store`. ValueError for a plain `http://`
    address to another machine: the token would travel in the clear
    (connection/addresses.py). `signed_in`: this PC is signed in, so the
    code goes onto its account with the saved token."""
    address = server_address(server)
    code = invite_code(invite_code_text)
    if code is None:
        return NotACode()
    saved = store.load()
    # the id this PC signed in with before, signed out or not: the same code
    # signs that install in again (server decision 0057; decision 0080)
    install_id = store.install_id() or str(uuid.uuid4())
    body = protocol.encode(
        protocol.RedeemRequest(
            invite_code=code,
            install_id=install_id,
            app_version=app.app_version,
            channel=app.channel,
            os=app.os,
        )
    )
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    if signed_in and saved is not None:
        headers["Authorization"] = f"Bearer {saved.device_token}"
    request = urllib.request.Request(
        f"{address}/v1/redeem",
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with tls.urlopen(request, timeout) as response:
            answer = protocol.validate(protocol.RedeemResponse, json.load(response))
    except urllib.error.HTTPError as error:
        return _refused(error)
    except (urllib.error.URLError, OSError) as error:
        cause = error.reason if isinstance(error, urllib.error.URLError) else error
        cause = cause if isinstance(cause, BaseException) else error
        return RedeemFailed(
            f"couldn't reach the server ({type(cause).__name__})",
            why_not_opened(cause),
        )
    except (ValueError, protocol.ProtocolError):
        return RedeemFailed("the server's answer couldn't be read")
    store.save(DeviceCredentials(install_id, answer.device_token))
    return SignedIn(answer.cohort)


def _refused(error: urllib.error.HTTPError) -> RedeemResult:
    try:
        answer = protocol.validate(protocol.HttpError, json.load(error))
    except (ValueError, protocol.ProtocolError):  # not our server's answer
        return RedeemFailed(
            f"the server answered {error.code}", why_answered(error.code)
        )
    if answer.error == "invite_code_not_valid":
        if answer.reason == "subscription_ended":
            return SubscriptionEnded()
        return InviteNotValid()  # any other reason, or none
    if answer.error == "too_many_attempts":
        return TooManyAttempts(answer.retry_after or 600)
    if answer.error == "subscription_running":
        return PlusAlready()
    if answer.error == "token_not_valid":
        return SignInAgain()
    if answer.error == "code_starts_new_account":
        return SignOutFirst()
    return RedeemFailed(f"the server answered {error.code} {answer.error}")
