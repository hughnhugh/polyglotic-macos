"""A certificate outside its dates, against a real TLS handshake (connection.tls, decision 0104).

polyglotic-hq 313 (2026-11-14): a tester's PC couldn't sign in - "Check
this PC's date and time" - with its date right. Each case here is a TLS
server on 127.0.0.1 with certificates made for the test
(tests/tls_certificates.py), a trust store of the test's own roots in
place of Windows', and this PC's time and the app's build time chosen by
the test. OpenSSL still checks the real clock on the first try, so the
certificates' dates are far from any day the tests run.
"""

from __future__ import annotations

import logging
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self

import pytest
from tests.fake_server import FakeServer, wait_until
from tests.fakes import MemoryCredentialStore
from tests.test_connection import App
from tests.test_session import Harness
from tests.tls_certificates import (
    FAR_AHEAD,
    LONG_AGO,
    Authority,
    certificate,
    https_server,
    server_context,
)

from polyglotic_desktop.adapters import signed_feed
from polyglotic_desktop.connection import app as app_module
from polyglotic_desktop.connection import tls
from polyglotic_desktop.connection.app import AppInfo, Release
from polyglotic_desktop.connection.failures import why_not_opened
from polyglotic_desktop.connection.session import SessionState
from polyglotic_desktop.connection.sign_in import RedeemFailed, redeem
from polyglotic_desktop.core.listening.unreachable import Unreachable

ENDED = datetime(2020, 1, 1, tzinfo=UTC)
"""An end in the past whenever the tests run."""
STARTS = datetime(2090, 1, 1, tzinfo=UTC)
"""A start in the future whenever the tests run."""
BUILT = datetime(2026, 11, 14, tzinfo=UTC)
CODE = "7KQM-X2PD-9VHT-C4RA"


@dataclass
class Pki:
    root: Authority
    root_pem: str
    old: Authority
    """An intermediate whose certificate in the store ended in 2020 - as
    an old cross-signed root left in Windows' store."""
    old_pem: str
    current: Authority
    current_pem: str


@pytest.fixture
def pki(monkeypatch: pytest.MonkeyPatch) -> Pki:
    """The test's roots in place of Windows' stores: the root and the old
    intermediate are trusted, as `load_default_certs` trusts Windows' CA
    store; the build time is BUILT unless a test says otherwise; and the
    log's "once" starts afresh."""
    root, old, current = Authority("Test Root"), Authority("Old Mid"), Authority("Mid")
    made = Pki(
        root,
        certificate(root, root, LONG_AGO, FAR_AHEAD),
        old,
        certificate(old, root, LONG_AGO, ENDED, serial=2),
        current,
        certificate(current, root, LONG_AGO, FAR_AHEAD, serial=3),
    )
    roots = made.root_pem + made.old_pem
    monkeypatch.setattr(
        tls, "trusted", lambda: ssl.create_default_context(cadata=roots)
    )
    monkeypatch.setattr(tls, "built_no_earlier", lambda: BUILT)
    tls._said.clear()
    return made


def serve(tmp_path: Path, chain: list[str], leaf: Authority) -> ssl.SSLContext:
    return server_context(tmp_path, leaf, chain)


def get(url: str) -> int:
    request = urllib.request.Request(url + "/feed", headers={"User-Agent": "test"})
    with tls.urlopen(request, 5) as response:
        status: int = response.status
        return status


def refused_by(url: str) -> ssl.SSLCertVerificationError:
    with pytest.raises(urllib.error.URLError) as raised:
        get(url)
    reason = raised.value.reason
    assert isinstance(reason, ssl.SSLCertVerificationError)
    return reason


# -- the rule ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "let"),
    [
        (datetime(2026, 12, 1, tzinfo=UTC), tls.Let.INSIDE),
        (datetime(2026, 6, 3, tzinfo=UTC), tls.Let.CLOCK_BEHIND),
        (datetime(2001, 1, 1, tzinfo=UTC), tls.Let.CLOCK_BEHIND),
        (datetime(2027, 6, 3, tzinfo=UTC), tls.Let.CLOCK_AHEAD),
    ],
)
def test_a_leaf_that_ends_after_the_build_is_let_through_wherever_the_clock_is(
    now: datetime, let: tls.Let
) -> None:
    leaf = tls.Dates(
        datetime(2026, 11, 8, 11, 35, tzinfo=UTC),
        datetime(2027, 2, 6, 11, 35, tzinfo=UTC),
    )
    assert tls.let_through(leaf, now, BUILT) is let


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 12, 1, tzinfo=UTC),
        datetime(2019, 1, 1, tzinfo=UTC),
    ],
)
def test_a_leaf_that_ended_before_the_build_is_never_let_through(now: datetime) -> None:
    """Out of date for certain, whatever this PC's clock says - even a
    clock set back into the leaf's own dates."""
    leaf = tls.Dates(
        datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 10, 30, tzinfo=UTC)
    )
    assert tls.let_through(leaf, now, BUILT) is None


def test_the_floor_is_the_build_time_or_when_this_code_was_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stamped(built: datetime | None) -> Callable[[], Release]:
        return lambda: Release("0.1.0", "win-x64-alpha", built)

    later = tls.WRITTEN + timedelta(days=40)
    for built, floor in [(later, later), (None, tls.WRITTEN), (LONG_AGO, tls.WRITTEN)]:
        monkeypatch.setattr(app_module, "this_release", stamped(built))
        tls.built_no_earlier.cache_clear()
        assert tls.built_no_earlier() == floor
    tls.built_no_earlier.cache_clear()


def test_only_a_failure_on_dates_is_tried_again() -> None:
    def failure(code: int) -> ssl.SSLCertVerificationError:
        error = ssl.SSLCertVerificationError(1, "certificate verify failed")
        error.verify_code = code
        return error

    assert tls.on_dates(failure(9)) is not None
    assert tls.on_dates(urllib.error.URLError(failure(10))) is not None
    assert tls.on_dates(failure(20)) is None  # unable to get local issuer
    assert tls.on_dates(failure(62)) is None  # the host name
    assert tls.on_dates(urllib.error.URLError("timed out")) is None
    assert tls.on_dates(ConnectionRefusedError()) is None
    with pytest.raises(ValueError, match="dates"):
        tls.context(failure(62))


def test_the_try_again_turns_off_only_openssls_date_check(pki: Pki) -> None:
    """X509_V_FLAG_NO_CHECK_TIME reaches OpenSSL through `verify_flags`;
    the host name and the path are still checked."""
    failed = ssl.SSLCertVerificationError(1, "certificate verify failed")
    failed.verify_code = tls.CERT_HAS_EXPIRED
    again = tls.context(failed)
    assert again.verify_flags & tls.NO_CHECK_TIME
    assert again.check_hostname
    assert again.verify_mode == ssl.CERT_REQUIRED
    assert not tls.context().verify_flags & tls.NO_CHECK_TIME


# -- over HTTPS: sign-in, feedback, problem reports, the update feed ----------------------


def test_an_out_of_date_certificate_in_the_store_doesnt_stop_a_good_leaf(
    pki: Pki, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The tester's case: the leaf is good, but OpenSSL builds the path
    through an intermediate in the store that ended in 2020 (code 10)."""
    leaf = Authority("leaf")
    chain = [
        certificate(
            leaf,
            pki.old,
            datetime(2019, 6, 1, tzinfo=UTC),
            FAR_AHEAD,
            hosts=("localhost",),
        )
    ]
    caplog.set_level(logging.WARNING, logger=tls.__name__)
    with https_server(serve(tmp_path, chain, leaf)) as server:
        assert get(server.url) == 200
        assert server.requests == ["/feed"]
    said = caplog.text
    assert "verify code 10 (certificate has expired)" in said
    assert "CN=Old Mid from O=Polyglotic test, CN=Test Root" in said
    assert "(out of date at this PC's time)" in said
    assert "let through (inside)" in said


def test_a_clock_behind_the_leaf_signs_in(pki: Pki, tmp_path: Path) -> None:
    """This PC's clock (the real one, here) is before the leaf began: a
    clock set back. The leaf ends after the build: let through."""
    leaf = Authority("leaf")
    chain = [
        certificate(leaf, pki.current, STARTS, FAR_AHEAD, hosts=("localhost",)),
        pki.current_pem,
    ]
    with https_server(serve(tmp_path, chain, leaf)) as server:
        result = redeem(
            server.url, CODE, MemoryCredentialStore(), AppInfo("0.1.0", "windows-11")
        )
        assert server.requests == [
            "/v1/redeem"
        ]  # reached: `{}` isn't a token, that's all
        assert isinstance(result, RedeemFailed) and result.unreachable is None


def test_a_clock_ahead_of_the_leaf_is_let_through_when_it_ended_after_the_build(
    pki: Pki, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaf = Authority("leaf")
    chain = [
        certificate(leaf, pki.current, LONG_AGO, ENDED, hosts=("localhost",)),
        pki.current_pem,
    ]
    monkeypatch.setattr(tls, "built_no_earlier", lambda: ENDED - timedelta(days=30))
    with https_server(serve(tmp_path, chain, leaf)) as server:
        assert get(server.url) == 200


@pytest.mark.parametrize(
    ("now", "said"),
    [
        # the clock is after the build: the leaf really is out of date - the
        # learner hears "something in the way", not to check the clock (313)
        (BUILT + timedelta(days=3), Unreachable.OUT_OF_DATE),
        # the clock is before the build: wrong for certain - set it
        (datetime(2025, 3, 1, tzinfo=UTC), Unreachable.CLOCK),
    ],
)
def test_a_leaf_that_ended_before_the_build_is_refused_before_anything_is_sent(
    pki: Pki,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
    said: Unreachable,
) -> None:
    leaf = Authority("leaf")
    chain = [
        certificate(leaf, pki.current, LONG_AGO, ENDED, hosts=("localhost",)),
        pki.current_pem,
    ]
    monkeypatch.setattr(tls, "utc_now", lambda: now)
    with https_server(serve(tmp_path, chain, leaf)) as server:
        refused = refused_by(server.url)
        assert refused.verify_code == tls.CERT_HAS_EXPIRED
        assert isinstance(refused, tls.LeafRefused)
        assert why_not_opened(refused) is said
        result = redeem(
            server.url, CODE, MemoryCredentialStore(), AppInfo("0.1.0", "windows-11")
        )
        assert isinstance(result, RedeemFailed)
        assert result.unreachable is said
        assert server.requests == []


@pytest.mark.parametrize(
    ("start", "end", "doubted"),
    [
        (datetime(2019, 6, 1, tzinfo=UTC), FAR_AHEAD, False),  # inside: the store's
        (STARTS, FAR_AHEAD, True),  # behind the leaf's start
    ],
)
def test_what_let_the_leaf_through_says_whether_the_clock_looks_wrong(
    pki: Pki, tmp_path: Path, start: datetime, end: datetime, doubted: bool
) -> None:
    """313: Home's quiet line only when this PC's time was outside the
    leaf's dates - not when another certificate was the stale one."""
    leaf = Authority("leaf")
    issuer = pki.old if not doubted else pki.current
    chain = [certificate(leaf, issuer, start, end, hosts=("localhost",))]
    if doubted:
        chain.append(pki.current_pem)
    failed = ssl.SSLCertVerificationError(1, "certificate verify failed")
    failed.verify_code = tls.CERT_NOT_YET_VALID
    with https_server(serve(tmp_path, chain, leaf)) as server:
        made = tls.context(failed)
        request = urllib.request.Request(server.url, headers={"User-Agent": "test"})
        with urllib.request.urlopen(request, timeout=5, context=made) as response:
            assert response.status == 200
    assert tls.clock_looks_wrong(tls.let_for(made)) is doubted
    assert tls.let_for(tls.context()) is None  # verified as usual: nothing to say


def test_without_the_dates_and_no_check_set_up_it_never_opens(
    pki: Pki, tmp_path: Path
) -> None:
    """Fail closed: a context with OpenSSL's date check off is let through
    only by the app's own check - none set up, nothing gets through."""
    leaf = Authority("leaf")
    chain = [
        certificate(leaf, pki.current, LONG_AGO, FAR_AHEAD, hosts=("localhost",)),
        pki.current_pem,
    ]
    loose = ssl.create_default_context(cadata=pki.root_pem)
    loose.verify_flags |= tls.NO_CHECK_TIME
    loose.sslsocket_class = tls._CheckedSocket
    with https_server(serve(tmp_path, chain, leaf)) as server:
        request = urllib.request.Request(server.url, headers={"User-Agent": "test"})
        with pytest.raises(urllib.error.URLError, match="no check of the leaf"):
            urllib.request.urlopen(request, timeout=5, context=loose)
        assert server.requests == []


def test_a_wrong_host_name_is_refused_on_the_try_again_too(
    pki: Pki, tmp_path: Path
) -> None:
    """OpenSSL checks the host name before the dates, so a wrong one is
    refused at once (62) - and the try without the dates still checks it."""
    leaf = Authority("leaf")
    chain = [
        certificate(
            leaf,
            pki.old,
            datetime(2019, 6, 1, tzinfo=UTC),
            FAR_AHEAD,
            hosts=("other.example",),
            this_pc=False,
        )
    ]
    with https_server(serve(tmp_path, chain, leaf)) as server:
        assert refused_by(server.url).verify_code == 64  # IP address mismatch
        failed = ssl.SSLCertVerificationError(1, "certificate verify failed")
        failed.verify_code = tls.CERT_HAS_EXPIRED
        request = urllib.request.Request(server.url, headers={"User-Agent": "test"})
        with pytest.raises(urllib.error.URLError) as raised:
            urllib.request.urlopen(request, timeout=5, context=tls.context(failed))
        reason = raised.value.reason
        assert isinstance(reason, ssl.SSLCertVerificationError)
        assert reason.verify_code == 64
        assert server.requests == []


def test_a_signature_that_doesnt_check_is_refused_on_the_try_again(
    pki: Pki, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A leaf in the old intermediate's name, signed by another key: the
    first try stops at the intermediate's dates (10) before reaching the
    leaf's signature; the try without the dates reaches it (7)."""
    leaf = Authority("leaf")
    forged = certificate(
        leaf,
        pki.old,
        datetime(2019, 6, 1, tzinfo=UTC),
        FAR_AHEAD,
        hosts=("localhost",),
        signed_by=Authority("someone else").key,
    )
    caplog.set_level(logging.WARNING, logger=tls.__name__)
    with https_server(serve(tmp_path, [forged], leaf)) as server:
        refused = refused_by(server.url)
        assert refused.verify_code == 7  # X509_V_ERR_CERT_SIGNATURE_FAILURE
        assert server.requests == []
    assert "verify code 10" in caplog.text  # the first try
    assert "the try without the dates, refused on the rest" in caplog.text


def test_a_root_this_pc_doesnt_trust_is_never_tried_again(
    pki: Pki, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    stranger, leaf = Authority("Stranger Root"), Authority("leaf")
    chain = [
        certificate(
            leaf,
            stranger,
            datetime(2019, 6, 1, tzinfo=UTC),
            FAR_AHEAD,
            hosts=("localhost",),
        ),
    ]
    caplog.set_level(logging.WARNING, logger=tls.__name__)
    with https_server(serve(tmp_path, chain, leaf)) as server:
        refused = refused_by(server.url)
        assert refused.verify_code not in tls.ON_DATES
        assert why_not_opened(refused) is Unreachable.NOT_SECURE
        assert server.requests == []
    assert "tried again" not in caplog.text
    assert "the try without the dates" not in caplog.text


def test_each_failure_is_logged_once_with_this_pcs_time_and_offset(
    pki: Pki,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = Authority("leaf")
    chain = [
        certificate(
            leaf,
            pki.old,
            datetime(2019, 6, 1, tzinfo=UTC),
            FAR_AHEAD,
            hosts=("localhost",),
        )
    ]
    caplog.set_level(logging.WARNING, logger=tls.__name__)
    # the clock stopped where the log reads it: a "today" read after the
    # lines were written was the next day when the PC's midnight fell
    # between (polyglotic-hq 344)
    now = datetime.now(UTC)
    monkeypatch.setattr(tls, "utc_now", lambda: now)
    with https_server(serve(tmp_path, chain, leaf)) as server:
        for _ in range(3):
            assert get(server.url) == 200
    lines = [r.getMessage() for r in caplog.records if r.name == tls.__name__]
    assert len(lines) == 2  # the first try's failure, and what the try again found
    local = now.astimezone()
    offset = local.strftime("%z")
    assert all(f"(UTC{offset[:3]}:{offset[3:]})" in line for line in lines)
    assert all("this PC's time " + local.strftime("%Y-%m-%d") in line for line in lines)


def test_the_log_names_no_host_but_ours() -> None:
    def name(common: str) -> tuple[tuple[tuple[str, str], ...], ...]:
        return ((("organizationName", "Org"),), (("commonName", common),))

    host = "api.polyglotic.io"
    assert tls._named(name("polyglotic.io"), host) == "O=Org, CN=polyglotic.io"
    assert tls._named(name("*.polyglotic.io"), host) == "O=Org, CN=*.polyglotic.io"
    assert tls._named(name("proxy.corp.example"), host) == "O=Org, CN=(another host)"
    assert tls._named(name("ISRG Root X2"), host) == "O=Org, CN=ISRG Root X2"


def test_the_update_feed_is_fetched_with_the_opener_main_gives(tmp_path: Path) -> None:
    """main hands the updater connection.tls's `urlopen` (decision 0104):
    the feed's signature, not TLS, is what protects an update."""
    seen: list[tuple[str, float]] = []

    class Answer:
        status = 200

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, n: int = -1) -> bytes:
            return b"{}"

    def opener(request: urllib.request.Request, timeout: float) -> Answer:
        seen.append((request.full_url, timeout))
        return Answer()

    assert signed_feed.fetch("https://updates.example.invalid/f.json", opener) == b"{}"
    signed_feed.fetch_to(
        "https://updates.example.invalid/p.nupkg", tmp_path / "p", 10, opener
    )
    assert [url for url, _ in seen] == [
        "https://updates.example.invalid/f.json",
        "https://updates.example.invalid/p.nupkg",
    ]


# -- over WebSockets: the session ----------------------------------------------------


@pytest.fixture
def secure_server(
    pki: Pki, tmp_path: Path
) -> Iterator[Callable[[list[str], Authority], FakeServer]]:
    made: list[FakeServer] = []

    def make(chain: list[str], leaf: Authority) -> FakeServer:
        server = FakeServer(tls=serve(tmp_path, chain, leaf))
        made.append(server)
        return server

    yield make
    for server in made:
        server.stop()


def test_the_session_opens_past_an_out_of_date_certificate_in_the_store(
    pki: Pki, secure_server: Callable[[list[str], Authority], FakeServer]
) -> None:
    """asyncio's side (websockets' handshake): the same try again."""
    leaf = Authority("leaf")
    server = secure_server(
        [
            certificate(
                leaf,
                pki.old,
                datetime(2019, 6, 1, tzinfo=UTC),
                FAR_AHEAD,
                hosts=("localhost",),
            )
        ],
        leaf,
    )
    app = App(server.url)
    app.connection.start()
    wait_until(lambda: server.app_closes == [1000])
    assert server.hellos[0]["purpose"] == "sync"
    app.connection.close()


def test_the_session_refuses_a_leaf_that_ended_before_the_build(
    pki: Pki,
    secure_server: Callable[[list[str], Authority], FakeServer],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = Authority("leaf")
    server = secure_server(
        [
            certificate(leaf, pki.current, LONG_AGO, ENDED, hosts=("localhost",)),
            pki.current_pem,
        ],
        leaf,
    )
    caplog.set_level(logging.INFO, logger="polyglotic_desktop.connection.session")
    monkeypatch.setattr(tls, "utc_now", lambda: BUILT + timedelta(days=3))
    app = App(server.url)
    app.connection.start()
    wait_until(lambda: "couldn't open a session" in caplog.text)
    app.connection.close()
    assert "LeafRefused (out_of_date)" in caplog.text  # the clock is after the build
    assert server.connections == 0  # no WebSocket: refused in the handshake


def test_a_listening_session_let_through_on_the_clock_says_so(
    pki: Pki, secure_server: Callable[[list[str], Authority], FakeServer]
) -> None:
    """313: the session opens, and its `welcome`'s status says the clock
    looks wrong - Home's quiet line (main's `clock_doubted`)."""
    leaf = Authority("leaf")
    server = secure_server(
        [
            certificate(leaf, pki.current, STARTS, FAR_AHEAD, hosts=("localhost",)),
            pki.current_pem,
        ],
        leaf,
    )
    with Harness(server) as harness:
        wait_until(
            lambda: any(
                s.state is SessionState.LISTENING for s in harness.listener.statuses
            )
        )
    listening = [
        s for s in harness.listener.statuses if s.state is SessionState.LISTENING
    ]
    assert listening[0].clock_looks_wrong
