"""The built app's own requests through Cloudflare, before a release is
published (`--check-release`, polyglotic-hq 563): on 2026-11-11 Cloudflare's
edge refused Python's own user agent with a 403, curl passed, and every
installed copy failed to sign in. The check reads the update feed and sends
a report as the app does - its own name in each request - with a token
that's no one's, and passes only on our servers' own answers: never on
Cloudflare's refusal, nor a network failure. Every request here is the
test's own; nothing leaves the PC."""

import base64
import io
import json
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Self

import pytest
from nacl.signing import SigningKey

from polyglotic_desktop import main
from polyglotic_desktop.adapters import signed_feed
from polyglotic_desktop.connection import tls
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.core.shared.client import USER_AGENT

KEY = SigningKey(b"\x07" * 32)
CHANNEL = "win-x64-alpha"
UPDATES = "https://updates.example/"
FEED = json.dumps(
    {
        "Assets": [
            {
                "Type": "Full",
                "Version": "0.1.9",
                "FileName": "Polyglotic-0.1.9-win-x64-alpha-full.nupkg",
                "Size": 100,
                "SHA256": "ab" * 32,
            }
        ]
    }
).encode()
CLOUDFLARE = b"<!DOCTYPE html><title>Attention Required! | Cloudflare</title>"
APP = AppInfo("0.1.9", "windows-11")


class Answer:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def read(self, limit: int = -1) -> bytes:
        return self._body.read(limit)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def refused(url: str, code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "refused", {}, io.BytesIO(body))  # type: ignore[arg-type]


@pytest.fixture
def edge(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Our servers behind a stand-in for Cloudflare's edge: it answers as
    our servers do, unless `refuse` names a path it refuses as the edge
    did on 2026-11-11. Every request it sees is kept, with its headers."""
    seen: list[Any] = []
    state: dict[str, Any] = {"seen": seen, "refuse": ()}
    signature = KEY.sign(signed_feed.signed_message(CHANNEL, FEED)).signature

    def answer(request: Any, timeout: float = 0.0) -> Answer:
        seen.append(request)
        url = request.full_url
        if any(part in url for part in state["refuse"]):
            raise refused(url, 403, CLOUDFLARE)
        if url.endswith(f"releases.{CHANNEL}.json"):
            return Answer(200, FEED)
        if url.endswith(".json.sig"):
            return Answer(200, base64.b64encode(signature))  # as served
        if url.endswith(".nupkg"):
            return Answer(206, b"P")
        if url.endswith("/v1/feedback"):
            raise refused(url, 401, b'{"error": "token_not_valid"}')
        raise AssertionError(f"not asked for: {url}")

    monkeypatch.setattr(tls, "urlopen", answer)
    monkeypatch.setattr(main, "_open_url", answer)
    public = base64.b64encode(bytes(KEY.verify_key)).decode()
    monkeypatch.setattr(main, "FEED_KEYS", (public,))
    monkeypatch.setattr(
        main, "tls_found", lambda _server, _app: {"health": 200, "ok": True}
    )
    yield state


def test_it_passes_on_our_servers_own_answers(
    edge: dict[str, Any], tmp_path: Path
) -> None:
    report = tmp_path / "release.json"
    code = main.check_release(report, "https://api.example", UPDATES, CHANNEL, APP)
    assert code == 0, report.read_text(encoding="utf-8")
    found = json.loads(report.read_text(encoding="utf-8"))
    assert found["feed"] == {"signature": "verified", "newest": "0.1.9", "package": 206}
    assert found["report"] == "token_not_valid"
    assert found["ok"] is True
    # each as the app asks: its own name, never Python's; the report with a
    # token that's no one's, and the package's first byte only
    assert all(r.get_header("User-agent") == USER_AGENT for r in edge["seen"])
    sent = next(r for r in edge["seen"] if r.full_url.endswith("/v1/feedback"))
    assert sent.get_header("Authorization") == f"Bearer {main.NOT_ANYONES_TOKEN}"
    package = next(r for r in edge["seen"] if r.full_url.endswith(".nupkg"))
    assert package.get_header("Range") == "bytes=0-0"


@pytest.mark.parametrize("refused_path", ["/v1/feedback", ".json", ".nupkg"])
def test_the_edges_refusal_of_any_part_fails_it(
    edge: dict[str, Any], tmp_path: Path, refused_path: str
) -> None:
    """2026-11-11's 403: the release stops instead of reaching testers."""
    edge["refuse"] = (refused_path,)
    report = tmp_path / "release.json"
    assert main.check_release(report, "https://api.example", UPDATES, CHANNEL, APP) == 1
    found = json.loads(report.read_text(encoding="utf-8"))
    assert found["ok"] is False
    said = json.dumps(found)
    assert "403" in said, said


def test_a_feed_signed_by_another_key_fails_it(
    edge: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stranger = base64.b64encode(bytes(SigningKey(b"\x08" * 32).verify_key)).decode()
    monkeypatch.setattr(main, "FEED_KEYS", (stranger,))
    report = tmp_path / "release.json"
    assert main.check_release(report, "https://api.example", UPDATES, CHANNEL, APP) == 1
    found = json.loads(report.read_text(encoding="utf-8"))
    assert found["feed"]["error"].startswith("FeedNotTrusted")


def test_the_secure_connections_part_still_counts(
    edge: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        main, "tls_found", lambda _server, _app: {"health": 403, "ok": False}
    )
    report = tmp_path / "release.json"
    assert main.check_release(report, "https://api.example", UPDATES, CHANNEL, APP) == 1


def test_a_report_answered_by_anyone_but_our_server_isnt_its_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cloudflare(request: Any, timeout: float = 0.0) -> Answer:
        raise refused(request.full_url, 403, CLOUDFLARE)

    monkeypatch.setattr(tls, "urlopen", cloudflare)
    said = main.report_answered("https://api.example", APP)
    assert said == "HTTP 403, not our server's answer"
