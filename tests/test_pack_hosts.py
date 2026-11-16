"""Which hosts learn the PC's address when a dictionary pack comes down
(decision 0122, checker's 3, 2026-11-14): only the storage's own, over
https; a redirect elsewhere is refused before it's followed; an installed
copy ignores the developer switches."""

from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from polyglotic_desktop import main
from polyglotic_desktop.connection import tls


class Redirecting:
    """A server on 127.0.0.1 answering `/go` with a redirect to `target`
    (a format string given the port), and `/here` with a body."""

    def __init__(self, target: str) -> None:
        self.asked: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                outer.asked.append(f"{self.headers.get('Host')}{self.path}")
                if self.path == "/go":
                    self.send_response(302)
                    self.send_header("Location", target.format(port=outer.port))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = b"here"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def elsewhere() -> Iterator[Redirecting]:
    server = Redirecting("http://localhost:{port}/here")  # another host's name
    yield server
    server.close()


@pytest.fixture
def same() -> Iterator[Redirecting]:
    server = Redirecting("/here")
    yield server
    server.close()


def request(server: Redirecting) -> urllib.request.Request:
    return urllib.request.Request(f"http://127.0.0.1:{server.port}/go")


def test_a_redirect_to_another_host_is_refused_before_its_followed(
    elsewhere: Redirecting,
) -> None:
    with pytest.raises(urllib.error.HTTPError) as refused:
        tls.urlopen(request(elsewhere), 10, same_host=True)
    assert refused.value.code == 302
    assert elsewhere.asked == [f"127.0.0.1:{elsewhere.port}/go"]  # never "localhost"


def test_a_redirect_on_the_same_host_is_followed(same: Redirecting) -> None:
    with tls.urlopen(request(same), 10, same_host=True) as response:
        assert response.read() == b"here"


def test_without_the_rule_redirects_are_followed_as_before(
    elsewhere: Redirecting,
) -> None:
    with tls.urlopen(request(elsewhere), 10) as response:
        assert response.read() == b"here"


def test_an_installed_copy_ignores_the_developer_switches(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    assert main.pack_storage("http://127.0.0.1:9/", ["a2V5"], packed=True) == (
        main.PACKS,
        main.FEED_KEYS,
    )
    assert "ignored in an installed copy" in caplog.text
    assert main.pack_storage(main.PACKS, [], packed=True) == (
        main.PACKS,
        main.FEED_KEYS,
    )


def test_from_source_a_stand_in_and_its_key_are_taken() -> None:
    assert main.pack_storage("http://127.0.0.1:9/", ["a2V5"], packed=False) == (
        "http://127.0.0.1:9/",
        (*main.FEED_KEYS, "a2V5"),
    )


def test_the_built_in_storage_is_https() -> None:
    assert main.PACKS.startswith("https://")
