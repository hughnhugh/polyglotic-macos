"""Secure connections when a certificate's dates and this PC's clock disagree (decision 0104).

polyglotic-hq 313 (2026-11-14): a tester couldn't sign in - "Check this
PC's date and time" - with the date right. Python verifies our server's
certificate with OpenSSL against the certificates in Windows' stores
(`load_default_certs` reads its trusted roots *and* its intermediates),
and when one of those is out of date - an old cross-signed root, an
antivirus's own certificate - OpenSSL can build the path through it and
fail on its dates (verify code 9, not yet valid; 10, expired), though
the browser on the same PC, verifying another way, is fine. A wrong clock
fails the same way: every certificate looks out of date.

So a failure on dates alone is tried once more (`context(after=...)`):
- **everything but the dates is still checked by OpenSSL** - the path to
  a root Windows trusts, every signature on it, the host name - with
  X509_V_FLAG_NO_CHECK_TIME (never `CERT_NONE`, never
  `check_hostname = False`);
- **the leaf's dates are then checked here** (`let_through`), during the
  handshake, before a byte of the request is sent: let through unless it
  expired before this copy of the app was built - a time known to have
  passed whatever the clock says (`built_no_earlier`). The other
  certificates in the path are the CAs' and the stores': their dates
  aren't held against the connection once everything else checks.
A refused leaf ends the handshake with `LeafRefused` (code 10): said as
this PC's clock when it's before the build too, else as something in the
way with an out-of-date certificate (connection.failures). A leaf let
through with this PC's time outside its dates is said on Home, quietly
(`clock_looks_wrong`): the session goes on.

Every verification failure writes one line to the log, once per kind:
the verify code and message, the certificates in the path with their
dates, this PC's time and UTC offset, and what let the retry through -
names only, no address but our own host's (`_say`).

Ports and adapters: connection only. `urlopen` is `urllib.request.urlopen`
with this, for sign-in, feedback, problem reports and (through main) the
update feed; the session hands `context()` to websockets.
"""

from __future__ import annotations

import functools
import logging
import re
import ssl
import sys
import urllib.error
import urllib.request
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from http.client import HTTPResponse
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

CERT_NOT_YET_VALID = 9
CERT_HAS_EXPIRED = 10
"""OpenSSL's verify codes for a certificate outside its dates
(X509_V_ERR_CERT_NOT_YET_VALID, X509_V_ERR_CERT_HAS_EXPIRED)."""

ON_DATES = (CERT_NOT_YET_VALID, CERT_HAS_EXPIRED)

NO_CHECK_TIME = 0x200000
"""OpenSSL's X509_V_FLAG_NO_CHECK_TIME (1.1.0 on): verify everything but
the dates. Python's `ssl.VerifyFlags` doesn't name it; `verify_flags`
passes it to OpenSSL as it is (proved by tests/test_tls.py)."""

WRITTEN = datetime(2026, 11, 14, tzinfo=UTC)
"""When this code was written: no copy of it runs earlier. The floor when
the build left no time of its own (run from source, or a stamp from
before 313)."""


def utc_now() -> datetime:
    return datetime.now(UTC)


@functools.cache
def built_no_earlier() -> datetime:
    """A time that has certainly passed, whatever this PC's clock says:
    when this copy of the app was built (`release.json`'s `built`), or
    when this code was written, whichever is later."""
    from polyglotic_desktop.connection.app import this_release

    built = this_release().built
    return max(built, WRITTEN) if built is not None else WRITTEN


MAC_ROOTS: Path | None = Path("/etc/ssl/cert.pem") if sys.platform == "darwin" else None
"""The roots a Mac trusts, as macOS ships them (decision 0236): the list
its own LibreSSL reads. The packed Mac app's OpenSSL looks for roots only
where python.org's Python keeps them
(/Library/Frameworks/Python.framework/Versions/3.12/etc/openssl), which a
learner's Mac hasn't: no roots, so every secure connection failed, said
as something on the network in the way (polyglotic-hq 512). None off a
Mac: Windows' stores are read as before (decision 0104)."""


LINUX_BUNDLES = (
    Path("/etc/ssl/certs/ca-certificates.crt"),  # Debian, Ubuntu, Mint, Arch
    Path("/etc/pki/tls/certs/ca-bundle.crt"),  # Fedora, RHEL
    Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"),  # Fedora's own
    Path("/etc/ssl/ca-bundle.pem"),  # openSUSE
    Path("/etc/ssl/cert.pem"),  # Alpine, and others that link one here
)
"""Where each Linux keeps the roots it trusts, as one file (polyglotic-hq
550). The packed app's OpenSSL looks only where the build's Python was
configured to (`/etc/ssl` and its `certs` folder of hashed links): Fedora
keeps its roots under /etc/pki, so a packed app found none there and no
secure connection - sign-in above all - would have worked, as on the Mac
(512)."""


def linux_roots(
    bundles: tuple[Path, ...] = LINUX_BUNDLES, system: str = sys.platform
) -> Path | None:
    """The first of `bundles` this PC has (None off Linux, or none there)."""
    if not system.startswith("linux"):
        return None
    return next((bundle for bundle in bundles if bundle.is_file()), None)


def trusted() -> ssl.SSLContext:
    """Python's default client context, the host name checked: Windows'
    stores - on a Mac, macOS's own roots (`MAC_ROOTS`), and on Linux the
    distribution's (`linux_roots`). Tests put their own roots here
    instead."""
    made = ssl.create_default_context()
    if MAC_ROOTS is not None:
        try:
            made.load_verify_locations(cafile=MAC_ROOTS)
        except (OSError, ssl.SSLError) as error:
            _say_once(("mac_roots", type(error).__name__), "macOS's roots", error)
    bundle = linux_roots()
    if bundle is not None:
        try:
            made.load_verify_locations(cafile=bundle)
        except (OSError, ssl.SSLError) as error:
            _say_once(("linux_roots", type(error).__name__), "Linux's roots", error)
    return made


def _say_once(key: tuple[object, ...], what: str, error: BaseException) -> None:
    """A warning about this copy's own roots, once per kind."""
    if key in _said or len(_said) >= _SAID_MAX:
        return
    _said.add(key)
    log.warning("%s couldn't be read (%s): %s", what, type(error).__name__, error)


def roots() -> dict[str, object]:
    """Where this copy's secure connections find the roots they trust, and
    how many they have - OpenSSL's default places and `trusted()`'s store
    counts (`--check-tls`, polyglotic-hq 512). Names and counts only."""
    paths = ssl.get_default_verify_paths()
    return {
        "openssl": ssl.OPENSSL_VERSION,
        "default_paths": {
            "cafile": paths.cafile,
            "capath": paths.capath,
            "openssl_cafile": paths.openssl_cafile,
            "openssl_capath": paths.openssl_capath,
        },
        "store": trusted().cert_store_stats(),
    }


class Let(StrEnum):
    """Why a leaf outside its dates at this PC's time - or inside them,
    with another certificate in the path out - was let through."""

    INSIDE = "inside"
    """The leaf is inside its dates at this PC's time: another certificate
    in the path - an intermediate or a root from Windows' stores - was
    the one out of date."""
    CLOCK_BEHIND = "clock_behind"
    """This PC's time is before the leaf was issued: its clock is behind."""
    CLOCK_AHEAD = "clock_ahead"
    """This PC's time is after the leaf's end, which is after the app was
    built: the clock may be ahead, or the leaf has expired since."""


@dataclass(frozen=True, slots=True)
class Dates:
    """A certificate's validity, in UTC."""

    not_before: datetime
    not_after: datetime

    def hold_at(self, when: datetime) -> bool:
        return self.not_before <= when <= self.not_after


def let_through(leaf: Dates, now: datetime, built: datetime) -> Let | None:
    """Whether to take a leaf whose path checked but for the dates, at this
    PC's time `now`: not if it expired before `built` - by then it's out of
    date for certain - otherwise yes, saying how it stands to the clock.

    The bound (decision 0104): a key the CA no longer vouches for is taken
    only for a leaf that ended after this copy of the app was built. On a
    PC whose clock is right, that lets an expired leaf through for as long
    as the app isn't updated past its end - whoever holds that key and a
    place on the network in between. Our leaves' keys are Cloudflare's;
    the window is the time since the app's last update."""
    if leaf.not_after < built:
        return None
    if now < leaf.not_before:
        return Let.CLOCK_BEHIND
    if now > leaf.not_after:
        return Let.CLOCK_AHEAD
    return Let.INSIDE


def on_dates(error: BaseException | None) -> ssl.SSLCertVerificationError | None:
    """`error` - or the reason urllib wrapped - when it's a verification
    that failed on a certificate's dates; None for anything else."""
    if isinstance(error, urllib.error.URLError) and not isinstance(
        error, urllib.error.HTTPError
    ):
        error = error.reason if isinstance(error.reason, BaseException) else None
    if isinstance(error, ssl.SSLCertVerificationError) and (
        error.verify_code in ON_DATES
    ):
        return error
    return None


@dataclass(frozen=True, slots=True)
class _Check:
    after: ssl.SSLCertVerificationError | None
    """The failure on dates this context tries again after (None: the first
    try, verified as usual)."""
    clock: Callable[[], datetime]
    built: datetime


_checks: weakref.WeakKeyDictionary[ssl.SSLContext, _Check] = weakref.WeakKeyDictionary()
_lets: weakref.WeakKeyDictionary[ssl.SSLContext, Let] = weakref.WeakKeyDictionary()


def let_for(made: ssl.SSLContext | None) -> Let | None:
    """What let a connection made with `made` through on its leaf's dates
    (None: verified as usual, or not made here) - the session tells Home
    when it says this PC's clock looks wrong."""
    return _lets.get(made) if made is not None else None


def clock_looks_wrong(let: Let | None) -> bool:
    """The leaf was let through with this PC's time outside its dates: the
    clock is behind its start, or past its end (`INSIDE`: another
    certificate was the stale one; the clock may be right)."""
    return let in (Let.CLOCK_BEHIND, Let.CLOCK_AHEAD)


class LeafRefused(ssl.SSLCertVerificationError):
    """The try without the dates refused the leaf: it ended before this
    app was built, so it's out of date for certain. Said as OpenSSL says
    an expired certificate (code 10), and `clock_wrong` when this PC's
    clock is before the build too - wrong for certain - so the learner is
    told to set it (connection.failures)."""

    clock_wrong: bool = False


def context(
    after: ssl.SSLCertVerificationError | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    built: datetime | None = None,
) -> ssl.SSLContext:
    """A client context that logs what failed (`_say`). With `after` - a
    failure on dates - one that checks everything but the dates and then
    the leaf's against `built` (`let_through`). `clock` is this PC's (UTC);
    `built`, `built_no_earlier()` unless a test says otherwise."""
    if after is not None and after.verify_code not in ON_DATES:
        raise ValueError("tried again only after a failure on dates")
    made = trusted()
    if after is not None:
        made.verify_flags |= NO_CHECK_TIME
    made.sslsocket_class = _CheckedSocket
    made.sslobject_class = _CheckedObject
    _checks[made] = _Check(after, clock or utc_now, built or built_no_earlier())
    return made


class SameHost(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to the same scheme and host as the request:
    one to another host, or from `https` to `http`, is refused before it's
    followed - that host never learns the PC's address (decision 0122)."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        asked, sent_to = urlsplit(req.full_url), urlsplit(newurl)
        if (asked.scheme, asked.netloc) != (sent_to.scheme, sent_to.netloc):
            raise urllib.error.HTTPError(
                req.full_url, code, "redirect to another host refused", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(
    request: urllib.request.Request,
    timeout: float,
    made: ssl.SSLContext | None,
    same_host: bool,
) -> HTTPResponse:
    if not same_host:
        if made is None:
            response: HTTPResponse = urllib.request.urlopen(request, timeout=timeout)
        else:
            response = urllib.request.urlopen(request, timeout=timeout, context=made)
        return response
    handlers: list[urllib.request.BaseHandler] = [SameHost()]
    if made is not None:
        handlers.append(urllib.request.HTTPSHandler(context=made))
    opened: HTTPResponse = urllib.request.build_opener(*handlers).open(
        request, timeout=timeout
    )
    return opened


def urlopen(
    request: urllib.request.Request, timeout: float, same_host: bool = False
) -> HTTPResponse:
    """`urllib.request.urlopen`, with `context()` for `https://` - and after
    a failure on dates, once more with `context(after=...)`. Nothing was
    sent on the try that failed: it failed in the handshake. `request` is
    the caller's, naming the app (`USER_AGENT`, core/shared/client.py).
    `same_host`: a redirect only to the request's own scheme and host
    (`SameHost`)."""
    if urlsplit(request.full_url).scheme != "https":
        return _open(request, timeout, None, same_host)
    try:
        response = _open(request, timeout, context(), same_host)
    except urllib.error.URLError as error:
        failed = on_dates(error)
        if failed is None:
            raise
        response = _open(request, timeout, context(failed), same_host)
    return response


class _CheckedSocket(ssl.SSLSocket):
    """urllib's side (a socket): the handshake, then the check."""

    def do_handshake(self, block: bool = False) -> None:
        try:
            super().do_handshake(block)
        except ssl.SSLCertVerificationError as error:
            _failed(self, error)
            raise
        _passed(self)


class _CheckedObject(ssl.SSLObject):
    """asyncio's side (websockets): the handshake, then the check."""

    def do_handshake(self) -> None:
        try:
            super().do_handshake()
        except ssl.SSLCertVerificationError as error:
            _failed(self, error)
            raise
        _passed(self)


_Secured = ssl.SSLSocket | ssl.SSLObject


def _failed(secured: _Secured, error: ssl.SSLCertVerificationError) -> None:
    """The handshake failed verification: said once, with the certificates
    the server sent (the path OpenSSL built isn't known) - and, when this
    copy trusts no roots at all, that it's the app's fault, not the
    network's (polyglotic-hq 512)."""
    check = _checks.get(secured.context)
    now = check.clock() if check is not None else utc_now()
    outcome = ""
    if check is not None and check.after is not None:
        outcome = "; this was the try without the dates, refused on the rest"
    if not secured.context.cert_store_stats().get("x509_ca"):
        outcome += (
            "; this copy trusts no roots at all: the app's fault, not the network's"
        )
    try:
        _say(secured, error, now, _chain(secured, verified=False), outcome)
    except Exception:  # noqa: BLE001 - the log never stops a connection
        log.warning("a secure connection failed: %s", error.verify_message)


def _passed(secured: _Secured) -> None:
    """After a handshake that checked everything but the dates: the leaf's
    dates here, refused by raising - the connection is closed before
    anything is sent."""
    check = _checks.get(secured.context)
    if check is None and secured.context.verify_flags & NO_CHECK_TIME:
        raise _refused("no check of the leaf's dates was set up", False)  # never open
    if check is None or check.after is None:
        return  # verified as usual, dates and all
    peer: dict[str, Any] = dict(secured.getpeercert() or {})
    now = check.clock()
    leaf = _dates(peer)
    let = let_through(leaf, now, check.built) if leaf is not None else None
    outcome = (
        f"; tried again without the dates: let through ({let})"
        if let is not None
        else "; tried again without the dates: refused, the leaf expired"
        " before this app was built"
    )
    try:
        _say(secured, check.after, now, _chain(secured, verified=True), outcome)
    except Exception:  # noqa: BLE001 - the log never stops a connection
        log.warning("a secure connection was tried again: %s", let)
    if let is None:
        raise _refused(
            "the certificate expired before this app was built", now < check.built
        )
    _lets[secured.context] = let


def _refused(why: str, clock_wrong: bool) -> LeafRefused:
    """A refusal on the leaf's dates, as OpenSSL would have said it (code
    10)."""
    refused = LeafRefused(1, f"certificate verify failed: {why}")
    refused.verify_code = CERT_HAS_EXPIRED
    refused.verify_message = why
    refused.clock_wrong = clock_wrong
    return refused


def _dates(info: dict[str, Any]) -> Dates | None:
    try:
        return Dates(
            datetime.fromtimestamp(ssl.cert_time_to_seconds(info["notBefore"]), UTC),
            datetime.fromtimestamp(ssl.cert_time_to_seconds(info["notAfter"]), UTC),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _chain(secured: _Secured, verified: bool) -> list[dict[str, Any]]:
    """The certificates as `getpeercert()` gives them, leaf first: the
    path OpenSSL built (`verified`), or what the server sent. Python 3.12
    has them only on the private `_sslobj` (public from 3.13); none if
    it's not there."""
    raw = getattr(secured, "_sslobj", None)
    get = getattr(
        raw, "get_verified_chain" if verified else "get_unverified_chain", None
    )
    certificates = get() if callable(get) else None
    return [c.get_info() for c in certificates or () if hasattr(c, "get_info")]


_said: set[tuple[object, ...]] = set()
_SAID_MAX = 64


def _say(
    secured: _Secured,
    error: ssl.SSLCertVerificationError,
    now: datetime,
    chain: list[dict[str, Any]],
    outcome: str,
) -> None:
    """One line, once per host, failure and path: the verify code and
    message, this PC's time and UTC offset, each certificate (its subject,
    issuer and dates, marked if out of date at this PC's time) and, tried
    again, what came of it."""
    host = secured.server_hostname or "?"
    certificates = []
    for depth, info in enumerate(chain):
        dates = _dates(info)
        out = dates is not None and not dates.hold_at(now)
        certificates.append(
            f"[{depth}] {_named(info.get('subject'), host)}"
            f" from {_named(info.get('issuer'), host)},"
            f" {info.get('notBefore', '?')} to {info.get('notAfter', '?')}"
            + (" (out of date at this PC's time)" if out else "")
        )
    key = (host, error.verify_code, tuple(certificates), outcome)
    if key in _said or len(_said) >= _SAID_MAX:
        return
    _said.add(key)
    local = now.astimezone()
    offset = local.strftime("%z")
    log.warning(
        "secure connection to %s: verify code %s (%s); this PC's time %s"
        " (UTC%s:%s); the path: %s%s",
        host,
        error.verify_code,
        error.verify_message,
        local.strftime("%Y-%m-%d %H:%M:%S"),
        offset[:3],
        offset[3:],
        "; ".join(certificates) or "not known",
        outcome,
    )


_HOST_NAME = re.compile(r"\*?[\w-]+(\.[\w-]+)+")


def _named(name: Any, host: str) -> str:
    """A certificate's subject or issuer as `O=..., CN=...`; a common name
    that's another host's address is left out - only our own host's is
    logged."""
    fields: dict[str, str] = {}
    for part in name or ():
        for key, value in part:
            if key in ("organizationName", "commonName"):
                fields[key] = str(value)
    common = fields.get("commonName", "")
    if _HOST_NAME.fullmatch(common) and not _ours(common, host):
        common = "(another host)"
    said = [f"O={fields['organizationName']}"] if "organizationName" in fields else []
    if common:
        said.append(f"CN={common}")
    return ", ".join(said) or "(no name)"


def _ours(name: str, host: str) -> bool:
    """`name` is `host`'s own domain or one under it (`polyglotic.io` for
    `api.polyglotic.io`)."""
    domain = ".".join(host.split(".")[-2:])
    bare = name.removeprefix("*.")
    return bare == domain or bare.endswith("." + domain)
