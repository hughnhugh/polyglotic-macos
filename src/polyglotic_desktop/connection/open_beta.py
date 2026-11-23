"""HTTPS adapter for email verification, account status, prices, codes,
plan changes and checkout (the server's `docs/open-beta-contract.md`, with
round 2: polyglotic-hq 683's CONTRACT-ROUND-2.md).

Call from a worker thread. Device tokens only travel to the configured API
and are saved in the OS credential store after a successful verification.
"""

import json
import re
import ssl
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from http.client import HTTPException
from typing import Annotated
from urllib.parse import unquote, urlsplit

from pydantic import Field, StrictBool, StringConstraints

from polyglotic_desktop.connection import protocol, tls
from polyglotic_desktop.connection.addresses import server_address
from polyglotic_desktop.connection.sign_in import TIMEOUT_SEC, narrow_code
from polyglotic_desktop.core.shared.client import USER_AGENT
from polyglotic_desktop.core.shared.open_beta import (
    PLAN_CHANGE_TIMEOUT,
    Account,
    Allowance,
    ChangePreview,
    CodeOffer,
    Money,
    Offer,
    PriceList,
    ScheduledSwitch,
    Subscription,
)
from polyglotic_desktop.ports.credentials import CredentialStore, DeviceCredentials
from polyglotic_desktop.ports.open_beta import CODE_LENGTH, AccountError, Region

PIPL_WORDING = "pipl_cross_border_v1"
MARKETING_WORDING = "marketing_v1"
CHECKOUT_URL_MAX = (
    2048  # ASCII bytes; fits the checkout QR at its normal correction level
)
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]
Nonempty = Annotated[str, StringConstraints(min_length=1)]
Amount = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,12}(\.[0-9]{1,4})?$")]
"""A decimal string in major currency units (the contract's wire format)."""
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
PercentOff = Annotated[int, Field(strict=True, ge=1, le=100)]
# Wire format at /v1/codes/check and /v1/checkout (server accounts/offers.py).
OFFER_CODE = re.compile(r"[a-zA-Z0-9_-]{6,80}")


def _offer_code(text: str) -> str:
    code = narrow_code(text)
    if OFFER_CODE.fullmatch(code) is None:
        raise AccountError("malformed_code")
    return code


class _Region(protocol.Message):
    country: str = "XX"
    pipl_cross_border_required: StrictBool = False


class _Challenge(protocol.Message):
    challenge_id: Nonempty


class _ScheduledSwitch(protocol.Message):
    plan: Nonempty
    period: Nonempty
    effective_at: datetime


class _Subscription(protocol.Message):
    status: Nonempty
    period: str | None = None
    period_end: datetime | None = None
    renews_at: datetime | None = None
    renewal_amount: Amount | None = None
    currency: Currency | None = None
    scheduled: _ScheduledSwitch | None = None
    plan: str | None = None

    def subscription(self) -> Subscription:
        scheduled = self.scheduled
        return Subscription(
            self.status,
            self.period,
            self.period_end,
            self.renews_at,
            _money(self.renewal_amount, self.currency)
            if self.renewal_amount is not None and self.currency is not None
            else None,
            ScheduledSwitch(scheduled.plan, scheduled.period, scheduled.effective_at)
            if scheduled is not None
            else None,
            self.plan,
        )


class _View(protocol.Message):
    account_id: Nonempty
    cohort: Nonempty
    registered: StrictBool
    plan: Nonempty
    percent_left: Percent | None = None
    allowance_percent: Percent | None = None  # the name before round 2
    resets_at: datetime | None = None
    renews_at: datetime | None = None
    provider: str | None = None
    subscription: _Subscription | None = None
    email: str | None = None

    def account(self) -> Account:
        allowance = None
        percent = (
            self.percent_left
            if self.percent_left is not None
            else self.allowance_percent
        )
        if percent is not None:
            allowance = Allowance(percent, self.resets_at)
        return Account(
            self.account_id,
            self.cohort,
            self.registered,
            self.plan,
            allowance,
            self.renews_at,
            self.provider,
            self.subscription.subscription() if self.subscription is not None else None,
            self.email,
        )


class _Verified(_View):
    device_token: Nonempty = Field(repr=False)


def _money(amount: str, currency: str) -> Money:
    return Money(Decimal(amount), currency)


class _Price(protocol.Message):
    plan: Nonempty
    period: Nonempty
    currency: Currency
    amount: Amount
    renewal_amount: Amount | None = None
    renewal_at: datetime | None = None
    pass_ends_at: datetime | None = None
    mode: str | None = None

    def offer(self) -> Offer:
        return Offer(
            self.plan,
            self.period,
            _money(self.amount, self.currency),
            _money(self.renewal_amount, self.currency)
            if self.renewal_amount is not None
            else None,
            self.renewal_at,
            self.pass_ends_at,
            self.mode,
        )


class _CodeOffer(protocol.Message):
    kind: Nonempty
    percent_off: PercentOff | None = None


class _Prices(protocol.Message):
    prices: list[_Price]
    offer: _CodeOffer | None = None

    def price_list(self) -> PriceList:
        return PriceList(
            tuple(price.offer() for price in self.prices),
            CodeOffer(self.offer.kind, self.offer.percent_off)
            if self.offer is not None
            else None,
        )


class _Preview(protocol.Message):
    preview_id: Nonempty
    plan: Nonempty
    period: Nonempty
    mode: Nonempty
    currency: Currency
    amount: Amount
    renewal_amount: Amount | None = None
    renewal_at: datetime | None = None
    effective_at: datetime | None = None
    pass_ends_at: datetime | None = None

    resumes_renewal: StrictBool = False

    def preview(self) -> ChangePreview:
        return ChangePreview(
            self.preview_id,
            self.plan,
            self.period,
            self.mode,
            _money(self.amount, self.currency),
            _money(self.renewal_amount, self.currency)
            if self.renewal_amount is not None
            else None,
            self.renewal_at,
            self.effective_at,
            self.pass_ends_at,
            self.resumes_renewal,
        )


class _Changed(protocol.Message):
    checkout_url: Nonempty | None = None


class _Checkout(protocol.Message):
    checkout_url: Nonempty


class _Portal(protocol.Message):
    manage_url: Nonempty


class Accounts:
    def __init__(self, server: str, store: CredentialStore) -> None:
        self._server = server
        self._store = store

    def region(self) -> Region:
        region = self._request("GET", "/v1/accounts/marketing-default", _Region)
        return Region(region.country, region.pipl_cross_border_required)

    def start(
        self,
        email: str,
        *,
        marketing: bool,
        cross_border: bool,
        timezone: str,
    ) -> str:
        current = self._store.load()
        install = self._store.install_id()
        if install is None:
            install = str(uuid.uuid4())
            self._store.save(DeviceCredentials(install, ""))
        body: dict[str, object] = {
            "email": email,
            "install_id": install,
            "marketing_opt_in": marketing,
            "time_zone": timezone,
        }
        if marketing:
            body["marketing_opt_in_version"] = MARKETING_WORDING
        if cross_border:
            body["pipl_cross_border"] = True
            body["pipl_cross_border_version"] = PIPL_WORDING
        return self._request(
            "POST",
            "/v1/accounts/email/start",
            _Challenge,
            current,
            body,
        ).challenge_id

    def verify(
        self,
        challenge: str,
        code: str,
        before_save: Callable[[Account], None] | None = None,
    ) -> Account:
        install = self._store.install_id()
        code = narrow_code(code)
        if re.fullmatch(rf"[0-9]{{{CODE_LENGTH}}}", code) is None:
            raise AccountError("malformed_code")
        if install is None:
            raise AccountError("code_not_valid")
        answer = self._request(
            "POST",
            "/v1/accounts/email/verify",
            _Verified,
            self._store.load(),
            {"install_id": install, "challenge_id": challenge, "code": code},
        )
        if not answer.registered:
            raise AccountError("registration_required")
        account = answer.account()
        if before_save is not None:
            before_save(account)
        self._store.save(DeviceCredentials(install, answer.device_token))
        return account

    def current(self, device: DeviceCredentials, *, billing: bool = False) -> Account:
        if billing:
            return self._request(
                "GET",
                "/v1/accounts/me?billing=1",
                _View,
                device,
                timeout=PLAN_CHANGE_TIMEOUT.value,
            ).account()
        return self._request("GET", "/v1/accounts/me", _View, device).account()

    def allow_cross_border(self, device: DeviceCredentials) -> Account:
        return self._request(
            "PUT",
            "/v1/accounts/cross-border",
            _View,
            device,
            {"pipl_cross_border": True, "pipl_cross_border_version": PIPL_WORDING},
        ).account()

    def prices(self, device: DeviceCredentials, *, billing: bool = False) -> PriceList:
        """What this account may buy, in its local currency, under the code
        offer it holds (if any)."""
        path = "/v1/checkout/prices?billing=1" if billing else "/v1/checkout/prices"
        return self._request("GET", path, _Prices, device).price_list()

    def check_code(self, device: DeviceCredentials, code: str) -> PriceList:
        """The offer a typed code gives and the prices under it. Checking
        claims nothing; the code itself is never kept or logged here."""
        found = self._request(
            "POST", "/v1/codes/check", _Prices, device, {"code": _offer_code(code)}
        ).price_list()
        if found.code_offer is None:
            raise AccountError("offer_not_available")
        return found

    def checkout(
        self,
        device: DeviceCredentials,
        account: Account,
        offer: Offer,
        code: str | None = None,
    ) -> str:
        body: dict[str, object] = {
            "account_id": account.id,
            "plan": offer.plan,
            "period": offer.period,
        }
        if code is not None:
            body["code"] = _offer_code(code)
        try:
            answer = self._request("POST", "/v1/checkout", _Checkout, device, body)
        except AccountError as error:
            if code is None and error.code == "offer_not_available":
                raise AccountError(
                    "plan_offer_not_available", status=error.status
                ) from None
            raise
        return self._checkout_url(answer.checkout_url, device)

    def preview_change(
        self, device: DeviceCredentials, offer: Offer, *, allow_resume: bool = False
    ) -> ChangePreview:
        """What changing to `offer` costs: the charge now, the next charge
        and its date. Nothing changes until `change`."""
        body: dict[str, object] = {"plan": offer.plan, "period": offer.period}
        if allow_resume:
            body["allow_resume"] = True
        return self._request(
            "POST", "/v1/checkout/change/preview", _Preview, device, body
        ).preview()

    def change(self, device: DeviceCredentials, preview: ChangePreview) -> str | None:
        """Confirm a previewed change. A pass upgrade returns its checkout
        link (it takes effect when paid); a subscription change returns None."""
        body: dict[str, object] = {"preview_id": preview.id}
        if preview.resumes_renewal:
            body["resume_renewal"] = True
        try:
            answer = self._request(
                "POST",
                "/v1/checkout/change",
                _Changed,
                device,
                body,
                timeout=PLAN_CHANGE_TIMEOUT.value,
            )
        except AccountError as error:
            if (
                error.code == "request_timed_out"
                or error.status == HTTPStatus.GATEWAY_TIMEOUT
                or (error.code == "checkout_unavailable" and not preview.needs_checkout)
            ):
                raise AccountError("change_confirmation_pending") from None
            raise
        if answer.checkout_url is None:
            if preview.needs_checkout:
                raise AccountError("checkout_unavailable")
            return None
        return self._checkout_url(answer.checkout_url, device)

    def _checkout_url(self, value: str, device: DeviceCredentials) -> str:
        if len(value) > CHECKOUT_URL_MAX or not value.isascii():
            raise AccountError("checkout_unavailable")
        return self._payment_url(value, device)

    def resume_renewal(self, device: DeviceCredentials) -> None:
        self._request(
            "POST",
            "/v1/billing/resume-renewal",
            protocol.Message,
            device,
            timeout=PLAN_CHANGE_TIMEOUT.value,
        )

    def subscription_portal(self, device: DeviceCredentials) -> str:
        answer = self._request("POST", "/v1/billing/portal", _Portal, device)
        return self._payment_url(answer.manage_url, device)

    @staticmethod
    def _payment_url(value: str, device: DeviceCredentials) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or device.device_token in unquote(value)
        ):
            raise AccountError("checkout_unavailable")
        return value

    def revoke(self, device: DeviceCredentials) -> None:
        self._request(
            "POST",
            "/v1/accounts/sign-out",
            protocol.Message,
            device,
        )

    def _request[M: protocol.Message](
        self,
        method: str,
        path: str,
        model: type[M],
        device: DeviceCredentials | None = None,
        body: dict[str, object] | None = None,
        *,
        timeout: float = TIMEOUT_SEC,
    ) -> M:
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if device is not None:
            headers["Authorization"] = f"Bearer {device.device_token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            address = server_address(self._server)
        except ValueError:
            raise AccountError("unavailable", diagnostic="invalid_address") from None
        try:
            address = (
                address.replace("wss://", "https://", 1)
                if address.startswith("wss://")
                else address.replace("ws://", "http://", 1)
            )
            request = urllib.request.Request(
                address + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers=headers,
                method=method,
            )
            with tls.urlopen(request, timeout, same_host=True) as response:
                data: object = {} if response.status == 204 else json.load(response)
                return protocol.validate(model, data)
        except urllib.error.HTTPError as error:
            with error:
                try:
                    failed = protocol.validate(protocol.HttpError, json.load(error))
                except ValueError:
                    raise AccountError("unavailable", status=error.code) from None
            retry_after = failed.retry_after
            if retry_after is None:
                retry = error.headers.get("Retry-After", "")
                if retry.isascii() and retry.isdecimal() and len(retry) <= 10:
                    retry_after = int(retry)
            raise AccountError(failed.error, retry_after, status=error.code) from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise AccountError("request_timed_out") from None
            diagnostic = (
                "tls_failed"
                if isinstance(error.reason, ssl.SSLError)
                else "network_failed"
            )
            raise AccountError("unavailable", diagnostic=diagnostic) from None
        except TimeoutError:
            raise AccountError("request_timed_out") from None
        except ssl.SSLError:
            raise AccountError("unavailable", diagnostic="tls_failed") from None
        except (OSError, HTTPException):
            raise AccountError("unavailable", diagnostic="network_failed") from None
        except ValueError:
            raise AccountError("unavailable", diagnostic="invalid_response") from None
