"""Every web request the app makes itself names the app (core/shared/client.py):
Python's default User-Agent got a 403 from Cloudflare's Browser Integrity
Check on 2026-11-11, so no installed copy could sign in or read the update
feed."""

from __future__ import annotations

import ast
import urllib.request
from pathlib import Path
from typing import Self

import pytest

from polyglotic_desktop.adapters import signed_feed
from polyglotic_desktop.core.shared.client import USER_AGENT

SRC = Path(__file__).resolve().parent.parent / "src" / "polyglotic_desktop"


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


def test_no_request_goes_out_under_pythons_default_name() -> None:
    """In the source: every `urlopen` is given a Request (never a bare
    address), and every Request built names its headers."""
    found = 0
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "urllib.request" not in text:
            continue
        tree = ast.parse(text)
        for call in _calls(tree, "urlopen"):
            found += 1
            first = call.args[0]
            bare = isinstance(first, ast.Name) and first.id in ("url", "address")
            assert not bare, f"{path.name}:{call.lineno}: urlopen of a bare address"
        for call in _calls(tree, "Request"):
            assert any(k.arg == "headers" for k in call.keywords), (
                f"{path.name}:{call.lineno}"
            )
        if _calls(tree, "urlopen"):
            assert "USER_AGENT" in text or "HEADERS" in text, path.name
    assert found >= 5  # sign-in, feedback, problem reports, the feed and its packages


def test_the_feed_is_fetched_under_the_apps_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[urllib.request.Request] = []

    class Answer:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, n: int = -1) -> bytes:
            return b"{}"

    def urlopen(request: urllib.request.Request, timeout: float) -> Answer:
        seen.append(request)
        return Answer()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert signed_feed.fetch("https://updates.example.invalid/feed.json") == b"{}"
    assert seen[0].get_header("User-agent") == USER_AGENT
    assert USER_AGENT and "python" not in USER_AGENT.lower()
