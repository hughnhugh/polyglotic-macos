"""A stand-in for the update storage over HTTP on 127.0.0.1, for the packs'
download tests (decision 0122): serves a folder laid out as the bucket
is, with `Range` as R2 answers it, and faults on demand - a connection cut
after so many bytes, a stall, a slow trickle, an error status."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Self


@dataclass
class Faults:
    cut_after: list[int] = field(default_factory=list)
    """Each request for a pack's file sends at most the next of these many
    bytes, then closes (taken in turn; none left: whole)."""
    stall_after: int | None = None
    """Sends this many bytes of a pack's file, then nothing for `stall_for`."""
    stall_for: float = 5.0
    slow: float = 0.0
    """Seconds between 64 KB blocks of a pack's file."""
    status: dict[str, int] = field(default_factory=dict)
    """A path's status instead of its file (`packs/files/x.sqlite`: 503)."""
    swap: dict[str, bytes] = field(default_factory=dict)
    """A path served with other bytes than its file's."""


class StandIn:
    """`with StandIn(folder) as server:` - `server.base` is its address."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.faults = Faults()
        self.requests: list[tuple[str, str, int]] = []
        """Each request: its path, its Range header, the status sent."""
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                stand_in._serve(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self._server.server_address[1]}/"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _serve(self, request: BaseHTTPRequestHandler) -> None:
        path = request.path.lstrip("/")
        asked = request.headers.get("Range", "")
        faults = self.faults
        if path in faults.status:
            code = faults.status[path]
            self.requests.append((path, asked, code))
            request.send_response(code)
            request.send_header("Content-Length", "0")
            request.end_headers()
            return
        file = self.folder / path
        if path in faults.swap:
            data = faults.swap[path]
        elif file.is_file():
            data = file.read_bytes()
        else:
            self.requests.append((path, asked, 404))
            request.send_response(404)
            request.send_header("Content-Length", "0")
            request.end_headers()
            return
        start = 0
        found = re.fullmatch(r"bytes=(\d+)-", asked)
        if found and int(found.group(1)) < len(data):
            start = int(found.group(1))
        code = 206 if found and start else 200
        if found and int(found.group(1)) >= len(data):
            code = 416
        self.requests.append((path, asked, code))
        request.send_response(code)
        if code == 416:
            request.send_header("Content-Length", "0")
            request.end_headers()
            return
        if code == 206:
            request.send_header(
                "Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}"
            )
        request.send_header("Content-Length", str(len(data) - start))
        request.end_headers()
        body = data[start:]
        is_pack = path.startswith("packs/files/")
        if is_pack and faults.cut_after:
            body = body[: faults.cut_after.pop(0)]
        try:
            sent = 0
            for at in range(0, len(body), 64 * 1024):
                block = body[at : at + 64 * 1024]
                if (
                    is_pack
                    and faults.stall_after is not None
                    and sent >= faults.stall_after
                ):
                    faults.stall_after = None
                    time.sleep(faults.stall_for)
                    return
                request.wfile.write(block)
                request.wfile.flush()
                sent += len(block)
                if is_pack and faults.slow:
                    time.sleep(faults.slow)
        except (ConnectionError, OSError):
            return
        request.close_connection = True
