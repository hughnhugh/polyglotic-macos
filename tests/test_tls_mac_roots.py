"""A Mac's secure connections trust macOS's own roots (connection.tls, decision 0236).

polyglotic-hq 512 (2026-11-18): a Mac tester couldn't sign in - "Something
on this network is in the way" - and no try reached our server. Python's
OpenSSL in the packed Mac app looks for its roots in places of its own
build that don't exist on a Mac, so its store was empty and every secure
connection failed verification. Here a Mac is one whose OpenSSL finds no
roots of its own (`nothing_found`), with macOS's root list (`MAC_ROOTS`)
holding the test's root; a TLS server on 127.0.0.1 serves a leaf from it.
"""

from __future__ import annotations

import logging
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from tests.fakes import MemoryCredentialStore
from tests.tls_certificates import (
    FAR_AHEAD,
    LONG_AGO,
    Authority,
    certificate,
    https_server,
    server_context,
)

from polyglotic_desktop.connection import tls
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.sign_in import RedeemFailed, redeem

CODE = "7KQM-X2PD-9VHT-C4RA"


def nothing_found() -> ssl.SSLContext:
    """`ssl.create_default_context()` as the packed Mac app's OpenSSL
    makes it: the host name and the path checked, and no roots."""
    return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


@pytest.fixture
def mac_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Authority:
    """A Mac: OpenSSL finds no roots; macOS's list holds the test's root."""
    root = Authority("Mac Root")
    roots = tmp_path / "cert.pem"
    roots.write_bytes(certificate(root, root, LONG_AGO, FAR_AHEAD).encode())
    monkeypatch.setattr(ssl, "create_default_context", nothing_found)
    monkeypatch.setattr(tls, "MAC_ROOTS", roots, raising=False)
    tls._said.clear()
    return root


def served_by(root: Authority, tmp_path: Path) -> ssl.SSLContext:
    leaf = Authority("leaf")
    chain = [certificate(leaf, root, LONG_AGO, FAR_AHEAD, hosts=("localhost",))]
    return server_context(tmp_path, leaf, chain)


def test_a_mac_trusts_the_roots_macos_ships(mac_root: Authority) -> None:
    assert tls.trusted().cert_store_stats()["x509_ca"] == 1


def test_a_mac_connects_securely(mac_root: Authority, tmp_path: Path) -> None:
    with https_server(served_by(mac_root, tmp_path)) as server:
        request = urllib.request.Request(server.url + "/health")
        with tls.urlopen(request, 5) as response:
            assert response.status == 200


def test_a_mac_signs_in(mac_root: Authority, tmp_path: Path) -> None:
    """Sign-in's own path reaches the server: what comes back is its
    answer, not a failure to connect (`{}` isn't a token)."""
    with https_server(served_by(mac_root, tmp_path)) as server:
        result = redeem(
            server.url, CODE, MemoryCredentialStore(), AppInfo("0.1.8", "macos-26")
        )
        assert server.requests == ["/v1/redeem"]
        assert isinstance(result, RedeemFailed) and result.unreachable is None


def test_a_mac_without_its_root_list_still_connects_where_it_can(
    mac_root: Authority,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(tls, "MAC_ROOTS", tmp_path / "not-there.pem", raising=False)
    caplog.set_level(logging.WARNING, logger=tls.__name__)
    made = tls.trusted()
    assert made.cert_store_stats()["x509_ca"] == 0
    assert made.verify_mode is ssl.CERT_REQUIRED and made.check_hostname
    assert "macOS's roots couldn't be read" in caplog.text


def test_off_a_mac_only_the_oss_own_roots() -> None:
    """Windows (and Linux) as before (decision 0104): OpenSSL's defaults -
    on Windows, its stores."""
    assert (tls.MAC_ROOTS is None) is (sys.platform != "darwin")


def test_no_roots_at_all_is_logged_as_the_apps_fault(
    mac_root: Authority,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """0.1.7 on a Mac: nothing trusted, every connection refused - the log
    says it's the app, not the learner's network."""
    monkeypatch.setattr(tls, "MAC_ROOTS", None, raising=False)
    caplog.set_level(logging.WARNING, logger=tls.__name__)
    with https_server(served_by(mac_root, tmp_path)) as server:
        request = urllib.request.Request(server.url + "/health")
        with pytest.raises(urllib.error.URLError):
            tls.urlopen(request, 5)
    assert "trusts no roots at all: the app's fault" in caplog.text
