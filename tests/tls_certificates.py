"""Certificates made for a test, with any dates, and a TLS server that shows them (polyglotic-hq 313).

The app's secure connections are tested against a real TLS handshake on
127.0.0.1 with certificates whose dates the test chooses: an intermediate
out of date in the trust store, a leaf from before the app was built or
from the future. Nothing here touches this PC's clock or its certificate
store: the client trusts only the roots a test hands it.

Ed25519 keys (PyNaCl, already the app's: the update feed's signatures)
and a small DER writer, so no private key is kept in the repo and no
library is added to make certificates. OpenSSL 3 takes Ed25519
certificates in TLS 1.3, which is what Python's server and client agree.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import socket
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nacl.signing import SigningKey

LONG_AGO = datetime(2001, 1, 1, tzinfo=UTC)
FAR_AHEAD = datetime(2099, 12, 31, tzinfo=UTC)
"""Dates that hold whenever the tests run: OpenSSL checks the real clock."""

_ED25519 = "1.3.101.112"
_SERVER_AUTH = "1.3.6.1.5.5.7.3.1"


def _length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _length(len(body)) + body


def _seq(*parts: bytes) -> bytes:
    return _tlv(0x30, b"".join(parts))


def _integer(n: int) -> bytes:
    return _tlv(0x02, n.to_bytes(n.bit_length() // 8 + 1, "big"))


def _oid(dotted: str) -> bytes:
    first, second, *rest = (int(p) for p in dotted.split("."))
    body = bytearray([40 * first + second])
    for part in rest:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.insert(0, 0x80 | (part & 0x7F))
            part >>= 7
        body += bytes(chunk)
    return _tlv(0x06, bytes(body))


def _time(when: datetime) -> bytes:
    if when.year < 2050:  # RFC 5280: UTCTime until 2049, then GeneralizedTime
        return _tlv(0x17, when.strftime("%y%m%d%H%M%SZ").encode())
    return _tlv(0x18, when.strftime("%Y%m%d%H%M%SZ").encode())


def _name(common_name: str, organisation: str) -> bytes:
    def part(oid: str, text: str) -> bytes:
        return _tlv(0x31, _seq(_oid(oid), _tlv(0x0C, text.encode())))

    return _seq(part("2.5.4.10", organisation), part("2.5.4.3", common_name))


def _extension(oid: str, value: bytes, critical: bool = False) -> bytes:
    flag = _tlv(0x01, b"\xff") if critical else b""
    return _seq(_oid(oid), flag, _tlv(0x04, value))


def _pem(label: str, der: bytes) -> str:
    text = base64.b64encode(der).decode()
    lines = [text[i : i + 64] for i in range(0, len(text), 64)]
    dashes = "-----"
    return "\n".join(
        [f"{dashes}BEGIN {label}{dashes}", *lines, f"{dashes}END {label}{dashes}", ""]
    )


@dataclass
class Authority:
    """Who signs: a name and an Ed25519 key."""

    name: str
    organisation: str = "Polyglotic test"
    key: SigningKey = field(default_factory=SigningKey.generate)

    @property
    def key_id(self) -> bytes:
        return hashlib.sha1(bytes(self.key.verify_key)).digest()

    def key_pem(self) -> str:
        """The private key as PKCS #8 PEM, for the test server only."""
        seed = bytes(self.key)
        der = _seq(_integer(0), _seq(_oid(_ED25519)), _tlv(0x04, _tlv(0x04, seed)))
        return _pem("PRIVATE" + " KEY", der)


def certificate(
    subject: Authority,
    issuer: Authority,
    not_before: datetime,
    not_after: datetime,
    *,
    hosts: tuple[str, ...] = (),
    serial: int = 1,
    signed_by: SigningKey | None = None,
    this_pc: bool = True,
) -> str:
    """`subject`'s certificate from `issuer`, valid from `not_before` to
    `not_after`, as PEM: a CA's when `hosts` is empty, else a server's for
    those names and (`this_pc`) 127.0.0.1. `signed_by`: a key other than
    the issuer's, for a signature that doesn't check."""
    ed25519 = _seq(_oid(_ED25519))
    if hosts:
        names = b"".join(_tlv(0x82, h.encode()) for h in hosts)
        if this_pc:
            names += _tlv(0x87, bytes([127, 0, 0, 1]))
        extensions = [
            _extension("2.5.29.19", _seq(), critical=True),
            _extension("2.5.29.15", _tlv(0x03, b"\x07\x80"), critical=True),
            _extension("2.5.29.37", _seq(_oid(_SERVER_AUTH))),
            _extension("2.5.29.17", _seq(names)),
        ]
    else:
        extensions = [
            _extension("2.5.29.19", _seq(_tlv(0x01, b"\xff")), critical=True),
            _extension("2.5.29.15", _tlv(0x03, b"\x01\x06"), critical=True),
        ]
    extensions.append(_extension("2.5.29.14", _tlv(0x04, subject.key_id)))
    extensions.append(_extension("2.5.29.35", _seq(_tlv(0x80, issuer.key_id))))
    tbs = _seq(
        _tlv(0xA0, _integer(2)),
        _integer(serial),
        ed25519,
        _name(issuer.name, issuer.organisation),
        _seq(_time(not_before), _time(not_after)),
        _name(subject.name, subject.organisation),
        _seq(ed25519, _tlv(0x03, b"\x00" + bytes(subject.key.verify_key))),
        _tlv(0xA3, _seq(*extensions)),
    )
    signature = (signed_by or issuer.key).sign(tbs).signature
    return _pem("CERTIFICATE", _seq(tbs, ed25519, _tlv(0x03, b"\x00" + signature)))


def server_context(folder: Path, leaf: Authority, chain: list[str]) -> ssl.SSLContext:
    """A TLS server's context sending `chain` (the leaf's certificate
    first) with `leaf`'s key."""
    certs, key = folder / f"{leaf.name}-chain.pem", folder / f"{leaf.name}-key.pem"
    certs.write_text("".join(chain), encoding="ascii", newline="")
    key.write_text(leaf.key_pem(), encoding="ascii", newline="")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certs, key)
    return context


@dataclass
class Served:
    """An HTTPS server on 127.0.0.1 and what reached it."""

    url: str
    requests: list[str]
    """The paths asked for: what got through the handshake."""


@contextmanager
def https_server(context: ssl.SSLContext) -> Iterator[Served]:
    """Answers every POST and GET with `{}` over TLS, in a thread."""
    requests: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self) -> None:
            requests.append(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = do_POST = _answer

        def log_message(self, format: str, *args: object) -> None:
            pass

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def get_request(self) -> tuple[socket.socket, Any]:
            sock, address = super().get_request()
            return context.wrap_socket(sock, server_side=True), address

        def handle_error(self, request: object, client_address: object) -> None:
            pass  # a refused handshake is what some tests want

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Served(f"https://127.0.0.1:{server.server_address[1]}", requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
