"""The packed app's own secure connections, checked on GitHub's Mac (`--check-tls`,
polyglotic-hq 512 and 523): the session's WebSocket opened over `wss://` as a
listening session opens it - the path captions take, through asyncio's
handshake rather than urllib's - against a real TLS server on 127.0.0.1 with
the test's own roots (tests/test_tls.py's)."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Self

import pytest
from tests.fake_server import FakeServer
from tests.test_tls import Pki, pki, secure_server  # noqa: F401 - the fixtures
from tests.tls_certificates import FAR_AHEAD, LONG_AGO, Authority, certificate

from polyglotic_desktop import main
from polyglotic_desktop.connection import sign_in
from polyglotic_desktop.connection.app import AppInfo


def test_the_session_opens_over_wss_with_a_root_this_copy_trusts(
    pki: Pki,  # noqa: F811 - the fixture
    secure_server: Callable[[list[str], Authority], FakeServer],  # noqa: F811
) -> None:
    leaf = Authority("leaf")
    server = secure_server(
        [
            certificate(leaf, pki.current, LONG_AGO, FAR_AHEAD, hosts=("localhost",)),
            pki.current_pem,
        ],
        leaf,
    )
    assert server.url.startswith("https://")
    assert main.session_reached(server.url, 5) == "opened"


def test_a_root_this_copy_doesnt_trust_is_said_not_opened(
    pki: Pki,  # noqa: F811 - the fixture
    secure_server: Callable[[list[str], Authority], FakeServer],  # noqa: F811
) -> None:
    """What 512's learners met on 0.1.7's Mac: no root to check the server
    by. The check names the failure; it never reads as opened."""
    stranger = Authority("Someone else's root")
    leaf = Authority("leaf")
    server = secure_server(
        [
            certificate(leaf, stranger, LONG_AGO, FAR_AHEAD, hosts=("localhost",)),
            certificate(stranger, stranger, LONG_AGO, FAR_AHEAD),
        ],
        leaf,
    )
    said = main.session_reached(server.url, 5)
    assert said.startswith("SSLCertVerificationError"), said


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """`check_tls` with its three reaches stood in for: /health, sign-in and
    the session, each as `said` says."""
    said: dict[str, Any] = {"health": 200, "sign_in": True, "session": "opened"}

    class Answer:
        status = 200

        def __enter__(self) -> Self:
            self.status = said["health"]
            return self

        def __exit__(self, *_: object) -> None:
            return None

    from polyglotic_desktop.connection import tls

    monkeypatch.setattr(tls, "urlopen", lambda _request, _timeout: Answer())
    monkeypatch.setattr(tls, "roots", lambda: 3)

    def redeem(*_: object) -> object:
        if said["sign_in"]:
            return sign_in.InviteNotValid()
        return sign_in.RedeemFailed("not_secure", None)

    monkeypatch.setattr(sign_in, "redeem", redeem)
    monkeypatch.setattr(main, "session_reached", lambda _server, _s: said["session"])
    yield said


def test_the_check_passes_only_when_the_session_opens_too(
    reached: dict[str, Any], tmp_path: Path
) -> None:
    report = tmp_path / "tls.json"
    app = AppInfo("0.1.9", "macos-26")
    assert main.check_tls(report, "https://api.example", app) == 0
    found = json.loads(report.read_text(encoding="utf-8"))
    assert (found["health"], found["sign_in"], found["session"]) == (
        200,
        "InviteNotValid",
        "opened",
    )
    reached["session"] = "SSLCertVerificationError: certificate verify failed"
    assert main.check_tls(report, "https://api.example", app) == 1
    found = json.loads(report.read_text(encoding="utf-8"))
    assert found["ok"] is False and found["session"].startswith("SSLCert")
