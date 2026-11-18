"""Signing in (connection.sign_in) against a stand-in for `POST /v1/redeem`.

A small HTTP server in a thread answers as protocol.md says, with the
server's example bodies; the token lands in an in-memory credential store.
"""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from tests.fakes import MemoryCredentialStore
from tests.test_protocol import example

from polyglotic_desktop.connection.app import AppInfo, source_version
from polyglotic_desktop.connection.sign_in import (
    InviteNotValid,
    NotACode,
    PlusAlready,
    RedeemFailed,
    SignedIn,
    SignInAgain,
    SignOutFirst,
    SubscriptionEnded,
    TooManyAttempts,
    invite_code,
    redeem,
)
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.ports.credentials import DeviceCredentials

APP = AppInfo("0.1.0", "windows-11")
GOOD_CODE = "7KQM-X2PD-9VHT-C4RA"
LIMIT = "1111-1111-1111-1111"  # the stand-in answers 429
BROKEN = "2222-2222-2222-2222"  # the stand-in answers 500 with no JSON
RUNNING = "4444-4444-4444-4444"  # a subscription pays already: 409 (193, 185)
NEW_ACCOUNT = "5555-5555-5555-5555"  # an invite code: with a token, 409 (208)
ENDED = "6666-6666-6666-6666"  # its subscription ended before it was used (258)
NEWER = "7777-7777-7777-7777"  # not valid, for a reason this app doesn't know


class RedeemServer:
    """Answers `POST /v1/redeem`: the good code once, then 400; `LIMIT` 429."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.tokens: list[str | None] = []
        self.used = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                outer.tokens.append(self.headers.get("Authorization"))
                if self.path != "/v1/redeem":
                    self._answer(404, {"error": "not_found"})
                elif body["invite_code"] == LIMIT:
                    self._answer(429, example("http/redeem.error.too_many_attempts"))
                elif body["invite_code"] == BROKEN:
                    self._answer(500, None)
                elif self.headers.get("Authorization") == "Bearer pgd_revoked":
                    self._answer(401, {"error": "token_not_valid"})
                elif body["invite_code"] == NEW_ACCOUNT and self.headers.get(
                    "Authorization"
                ):
                    self._answer(
                        409, example("http/redeem.error.code_starts_new_account")
                    )
                elif body["invite_code"] == ENDED:
                    self._answer(400, example("http/redeem.error.subscription_ended"))
                elif body["invite_code"] == NEWER:
                    self._answer(
                        400, {"error": "invite_code_not_valid", "reason": "newer"}
                    )
                elif body["invite_code"] == RUNNING:
                    self._answer(409, example("http/redeem.error.subscription_running"))
                elif body["invite_code"] == GOOD_CODE and not outer.used:
                    outer.used = True
                    self._answer(200, example("http/redeem.response"))
                else:
                    self._answer(400, example("http/redeem.error"))

            def _answer(self, status: int, body: dict[str, Any] | None) -> None:
                data = json.dumps(body).encode() if body is not None else b"oops"
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"


@pytest.fixture
def server() -> Iterator[RedeemServer]:
    stand_in = RedeemServer()
    thread = threading.Thread(target=stand_in.http.serve_forever, daemon=True)
    thread.start()
    yield stand_in
    stand_in.http.shutdown()
    stand_in.http.server_close()


def test_redeeming_saves_the_token_with_a_new_install_id(server: RedeemServer) -> None:
    store = MemoryCredentialStore()
    assert redeem(server.url, f" {GOOD_CODE}\n", store, APP) == SignedIn("alpha")
    assert store.saved is not None
    assert store.saved.device_token == example("http/redeem.response")["device_token"]
    (sent,) = server.requests
    assert sent.keys() == example("http/redeem.request").keys()
    assert sent["invite_code"] == GOOD_CODE
    assert sent["install_id"] == store.saved.install_id
    assert (sent["app_version"], sent["channel"], sent["os"]) == (
        "0.1.0",
        "win-x64-alpha",
        "windows-11",
    )


def test_a_new_code_keeps_the_install_id(server: RedeemServer) -> None:
    store = MemoryCredentialStore(DeviceCredentials("3c5e7a9b-old", "pgd_revoked"))
    assert isinstance(redeem(server.url, GOOD_CODE, store, APP), SignedIn)
    assert store.saved is not None and store.saved.install_id == "3c5e7a9b-old"
    assert store.saved.device_token != "pgd_revoked"


def test_after_signing_out_the_code_goes_with_the_same_install_id(
    server: RedeemServer,
) -> None:
    """polyglotic-hq 288: signing out (or a refused token) deleted the install
    id with the token, so the same code came from a "new PC" and the server
    refused it. The install id stays (decision 0080); the server signs that
    install in again with its code (server decision 0057)."""
    store = MemoryCredentialStore(DeviceCredentials("3c5e7a9b-mine", "pgd_mine"))
    store.forget()  # signed out
    assert store.load() is None
    assert isinstance(redeem(server.url, GOOD_CODE, store, APP), SignedIn)
    assert server.requests[0]["install_id"] == "3c5e7a9b-mine"
    assert store.saved is not None and store.saved.install_id == "3c5e7a9b-mine"
    assert server.tokens == [None]  # signed out: no token sent


def test_signed_in_the_code_goes_onto_this_account_with_its_token(
    server: RedeemServer,
) -> None:
    """polyglotic-hq 185 (server #192): the code from a Plus email, typed
    while signed in, carries the device token; signing in never does."""
    saved = DeviceCredentials("3c5e7a9b-mine", "pgd_mine")
    store = MemoryCredentialStore(saved)
    assert isinstance(
        redeem(server.url, GOOD_CODE, store, APP, signed_in=True), SignedIn
    )
    server.used = False
    redeem(server.url, GOOD_CODE, MemoryCredentialStore(saved), APP)
    assert server.tokens == ["Bearer pgd_mine", None]
    assert server.requests[0]["install_id"] == "3c5e7a9b-mine"


def test_a_subscription_already_and_a_sign_in_run_out_are_said_plainly(
    server: RedeemServer,
) -> None:
    mine = DeviceCredentials("3c5e7a9b-mine", "pgd_mine")
    store = MemoryCredentialStore(mine)
    assert redeem(server.url, RUNNING, store, APP, signed_in=True) == PlusAlready()
    assert store.saved == mine  # nothing changes: the code wasn't used
    gone = MemoryCredentialStore(DeviceCredentials("3c5e7a9b-old", "pgd_revoked"))
    assert redeem(server.url, GOOD_CODE, gone, APP, signed_in=True) == SignInAgain()


def test_signed_in_an_invite_code_never_changes_the_account(
    server: RedeemServer,
) -> None:
    """203's item 1: "I have a code" with an invite code opened a new
    account and the app carried on as it. The server refuses it now
    (#205); this PC keeps its sign-in and says to sign out first."""
    mine = DeviceCredentials("3c5e7a9b-mine", "pgd_mine")
    store = MemoryCredentialStore(mine)
    assert redeem(server.url, NEW_ACCOUNT, store, APP, signed_in=True) == (
        SignOutFirst()
    )
    assert store.saved == mine


def test_a_used_code_is_not_valid_and_nothing_is_saved(server: RedeemServer) -> None:
    redeem(server.url, GOOD_CODE, MemoryCredentialStore(), APP)
    store = MemoryCredentialStore()
    assert redeem(server.url, GOOD_CODE, store, APP) == InviteNotValid()
    assert store.saved is None


def test_an_ended_subscriptions_code_says_so(server: RedeemServer) -> None:
    """`invite_code_not_valid` with `reason` `subscription_ended`: the code's
    subscription was cancelled before it was used (server #252, polyglotic-hq
    256, 258). Any other reason is read as none."""
    store = MemoryCredentialStore()
    assert redeem(server.url, ENDED, store, APP) == SubscriptionEnded()
    assert redeem(server.url, NEWER, store, APP) == InviteNotValid()
    assert store.saved is None


def test_too_many_attempts_says_when_to_try_again(server: RedeemServer) -> None:
    assert redeem(server.url, LIMIT, MemoryCredentialStore(), APP) == (
        TooManyAttempts(600)
    )


def test_an_unreadable_answer_fails_without_the_code(server: RedeemServer) -> None:
    result = redeem(server.url, BROKEN, MemoryCredentialStore(), APP)
    assert isinstance(result, RedeemFailed) and "500" in result.why
    assert BROKEN not in result.why and "2222" not in result.why
    # a 500 that isn't our server's answer: the server is down (251)
    assert result.unreachable is Unreachable.DOWN


def test_no_server() -> None:
    result = redeem("http://127.0.0.1:9", GOOD_CODE, MemoryCredentialStore(), APP, 2)
    assert isinstance(result, RedeemFailed) and GOOD_CODE not in result.why
    # refused - or no answer, if Windows takes longer than the timeout (251)
    assert result.unreachable in (Unreachable.DOWN, Unreachable.NO_ANSWER)


def test_no_internet_is_said_as_the_learners_side() -> None:
    """A name that never resolves (`.invalid`, RFC 6761): DNS failing, or
    no network at all - "check your internet" (polyglotic-hq 251)."""
    result = redeem(
        "https://polyglotic-251.invalid", GOOD_CODE, MemoryCredentialStore(), APP, 5
    )
    assert isinstance(result, RedeemFailed)
    assert result.unreachable is Unreachable.OFFLINE


def test_plain_http_to_another_machine_is_refused_before_anything_is_sent() -> None:
    """The token would come back over the network in the clear. `.invalid`
    never resolves, so without the check this would be a RedeemFailed, not
    a ValueError - and nothing must leave the PC either way."""
    store = MemoryCredentialStore()
    with pytest.raises(ValueError, match="https://"):
        redeem("http://server.invalid:8080", GOOD_CODE, store, APP, 2)
    assert store.saved is None


@pytest.mark.parametrize(
    "typed",
    [
        "7kqm-x2pd-9vht-c4ra",
        " 7KQM X2PD 9VHT C4RA ",
        "7KQMX2PD9VHTC4RA",
        "7KQM-X2PD-9VHT-C4RA",
    ],
)
def test_case_spaces_and_dashes_dont_matter(typed: str) -> None:
    assert invite_code(typed) == GOOD_CODE


def test_look_alikes_read_as_digits() -> None:
    assert invite_code("OOOO-IIII-LLLL-oil0") == "0000-1111-1111-0110"


@pytest.mark.parametrize(
    "typed", ["", "7KQM-X2PD-9VHT", "7KQM-X2PD-9VHT-C4RA-1", "7KQM-X2PD-9VHT-C4RU"]
)
def test_what_cant_be_a_code(typed: str) -> None:
    assert invite_code(typed) is None  # U isn't in Crockford's alphabet


def test_what_cant_be_a_code_is_answered_without_a_request(
    server: RedeemServer,
) -> None:
    assert redeem(server.url, "hello", MemoryCredentialStore(), APP) == NotACode()
    assert server.requests == []


def test_the_code_goes_in_four_groups(server: RedeemServer) -> None:
    redeem(server.url, "7kqmx2pd9vhtc4ra", MemoryCredentialStore(), APP)
    assert server.requests[0]["invite_code"] == GOOD_CODE


def test_this_app_says_the_os_it_was_given() -> None:
    """Its name and version number come from the OS's adapters
    (`main.os_adapters`, decision 0038), not from asking Windows here."""
    app = AppInfo.this_app("windows-11", "10.0.26200")
    assert (app.os, app.os_version, app.app_version) == (
        "windows-11",
        "10.0.26200",
        source_version(),  # from source: the newest release its notes name (0224)
    )
