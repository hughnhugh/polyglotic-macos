"""A Linux PC's secure connections trust the distribution's own roots
(connection.tls, polyglotic-hq 550): the packed app's OpenSSL looks for
them only where the build's Python was configured to (/etc/ssl), and
Fedora keeps them under /etc/pki - so, as on the Mac (512), it would have
trusted nothing and no one could sign in. Here a Linux PC is one whose
OpenSSL finds no roots of its own, with the distribution's bundle holding
the test's root; a TLS server on 127.0.0.1 serves a leaf from it."""

from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path

import pytest
from tests.fakes import MemoryCredentialStore
from tests.test_tls_mac_roots import CODE, nothing_found, served_by
from tests.tls_certificates import (
    FAR_AHEAD,
    LONG_AGO,
    Authority,
    certificate,
    https_server,
)

from polyglotic_desktop.connection import tls
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.sign_in import RedeemFailed, redeem


@pytest.fixture
def fedora_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Authority:
    """Fedora: OpenSSL finds no roots; /etc/pki's bundle holds the test's."""
    root = Authority("Fedora Root")
    bundle = tmp_path / "ca-bundle.crt"
    bundle.write_bytes(certificate(root, root, LONG_AGO, FAR_AHEAD).encode())
    monkeypatch.setattr(ssl, "create_default_context", nothing_found)
    monkeypatch.setattr(tls, "MAC_ROOTS", None, raising=False)
    monkeypatch.setattr(tls, "linux_roots", lambda: bundle)
    tls._said.clear()
    return root


def test_the_first_bundle_the_pc_has_is_the_one(tmp_path: Path) -> None:
    debian, fedora = tmp_path / "debian.crt", tmp_path / "fedora.crt"
    fedora.write_text("x")
    assert tls.linux_roots((debian, fedora), "linux") == fedora
    debian.write_text("x")
    assert tls.linux_roots((debian, fedora), "linux") == debian
    assert tls.linux_roots((debian, fedora), "win32") is None
    assert tls.linux_roots((tmp_path / "none.crt",), "linux") is None


def test_every_distributions_place_is_tried() -> None:
    places = {str(p).replace("\\", "/") for p in tls.LINUX_BUNDLES}
    assert "/etc/ssl/certs/ca-certificates.crt" in places  # Debian, Ubuntu
    assert "/etc/pki/tls/certs/ca-bundle.crt" in places  # Fedora


def test_linux_trusts_the_distributions_roots(fedora_root: Authority) -> None:
    assert tls.trusted().cert_store_stats()["x509_ca"] == 1


def test_linux_connects_and_signs_in(fedora_root: Authority, tmp_path: Path) -> None:
    with https_server(served_by(fedora_root, tmp_path)) as server:
        request = urllib.request.Request(server.url + "/health")
        with tls.urlopen(request, 5) as response:
            assert response.status == 200
        result = redeem(
            server.url, CODE, MemoryCredentialStore(), AppInfo("0.1.8", "linux-6")
        )
        assert isinstance(result, RedeemFailed) and result.unreachable is None
