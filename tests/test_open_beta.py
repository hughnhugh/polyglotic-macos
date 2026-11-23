"""The public account and checkout requests, with a fake HTTPS response."""

import json
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

import pytest
from tests.fakes import MemoryCredentialStore

from polyglotic_desktop.connection import open_beta, tls
from polyglotic_desktop.core.shared.open_beta import (
    Account,
    Allowance,
    Money,
    Offer,
    PriceList,
)
from polyglotic_desktop.ports.credentials import DeviceCredentials
from polyglotic_desktop.ports.open_beta import AccountError, Region

VIEW = {
    "account_id": "beta-account",
    "cohort": "open_beta",
    "registered": True,
    "plan": "beta_free",
    "allowance_percent": 42,
    "resets_at": "2026-11-22T13:00:00Z",
}


class Reply(BytesIO):
    status = 200


@pytest.mark.parametrize("consent_required", [False, True])
def test_region_needs_no_token_or_country_field(
    monkeypatch: pytest.MonkeyPatch, consent_required: bool
) -> None:
    def send(request: urllib.request.Request, timeout: float, same_host: bool) -> Reply:
        assert request.full_url == "https://example.test/v1/accounts/marketing-default"
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") is None
        assert same_host and timeout > 0
        return Reply(
            json.dumps({"pipl_cross_border_required": consent_required}).encode()
        )

    monkeypatch.setattr(tls, "urlopen", send)
    device = DeviceCredentials("test-install", "test-device")
    accounts = open_beta.Accounts("https://example.test", MemoryCredentialStore(device))
    assert accounts.region() == Region(pipl_cross_border_required=consent_required)


def test_registration_keeps_install_id_and_waits_to_save_the_device_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryCredentialStore(None)
    calls: list[tuple[urllib.request.Request, dict[str, object]]] = []

    def send(request: urllib.request.Request, timeout: float, same_host: bool) -> Reply:
        assert same_host and timeout > 0
        assert store.load() is None  # An install ID alone cannot start listening.
        assert store.install_id() is not None
        assert isinstance(request.data, bytes)
        calls.append((request, json.loads(request.data)))
        data = (
            {"challenge_id": "challenge"}
            if request.full_url.endswith("/start")
            else {**VIEW, "device_token": "test-device"}
        )
        return Reply(json.dumps(data).encode())

    monkeypatch.setattr(tls, "urlopen", send)
    accounts = open_beta.Accounts("https://example.test", store)
    for _ in range(2):
        challenge = accounts.start(
            "learner@example.test",
            marketing=False,
            cross_border=True,
            timezone="Australia/Melbourne",
        )
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1]
    install = store.install_id()
    assert install is not None and UUID(install).version == 4
    assert calls[0][1]["pipl_cross_border"] is True
    assert calls[0][1]["pipl_cross_border_version"] == "pipl_cross_border_v1"
    assert calls[0][1]["time_zone"] == "Australia/Melbourne"
    for malformed in ("12345", "01 2345", "01.2345", "0123456"):
        with pytest.raises(AccountError, match="malformed_code"):
            accounts.verify(challenge, malformed)
    assert len(calls) == 2

    account = accounts.verify(challenge, "　０１２３４５　")
    assert store.load() == DeviceCredentials(install, "test-device")
    assert calls[-1][1] == {
        "install_id": install,
        "challenge_id": challenge,
        "code": "012345",
    }
    assert account.allowance == Allowance(42, datetime(2026, 11, 22, 13, tzinfo=UTC))


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://checkout.example.test/pay", True),
        ("http://checkout.example.test/pay", False),
        ("https://checkout.example.test/?x=test-device", False),
        ("https://name@checkout.example.test/pay", False),
    ],
)
def test_checkout_keeps_the_device_credential_inside_https_api(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    allowed: bool,
) -> None:
    device = DeviceCredentials("test-install", "test-device")
    account = Account("beta-account", "open_beta", True, "beta_free", Allowance(42))
    offer = Offer("premium", "pass_3", Money(Decimal("126.66"), "CNY"))

    def send(request: urllib.request.Request, timeout: float, same_host: bool) -> Reply:
        assert request.full_url == "https://example.test/v1/checkout"
        assert request.headers["Authorization"] == "Bearer test-device"
        assert same_host and timeout > 0
        assert isinstance(request.data, bytes)
        assert json.loads(request.data) == {
            "account_id": account.id,
            "plan": "premium",
            "period": "pass_3",
        }
        return Reply(json.dumps({"checkout_url": url}).encode())

    monkeypatch.setattr(tls, "urlopen", send)
    accounts = open_beta.Accounts("wss://example.test", MemoryCredentialStore(device))
    if allowed:
        assert accounts.checkout(device, account, offer) == url
    else:
        with pytest.raises(AccountError, match="checkout_unavailable"):
            accounts.checkout(device, account, offer)


def test_upgrade_displays_only_the_server_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = DeviceCredentials("test-install", "test-device")

    def send(request: urllib.request.Request, timeout: float, same_host: bool) -> Reply:
        assert request.get_method() == "GET"
        assert request.full_url == "https://example.test/v1/checkout/prices"
        assert request.headers["Authorization"] == "Bearer test-device"
        return Reply(
            b'{"prices":[{"plan":"plus","period":"year","currency":"AUD",'
            b'"amount":"149.00","renewal_amount":"179.00",'
            b'"renewal_at":"2027-11-22T00:00:00Z"}],"offer":null}'
        )

    monkeypatch.setattr(tls, "urlopen", send)
    accounts = open_beta.Accounts("https://example.test", MemoryCredentialStore(device))
    assert accounts.prices(device) == PriceList(
        (
            Offer(
                "plus",
                "year",
                Money(Decimal("149.00"), "AUD"),
                Money(Decimal("179.00"), "AUD"),
                datetime(2027, 11, 22, tzinfo=UTC),
            ),
        )
    )
