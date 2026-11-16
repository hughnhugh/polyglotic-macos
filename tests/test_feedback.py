"""Feedback (project 053): reports kept on the PC until sent, sent to a stand-in for
`POST /v1/feedback`, and the log as a report attaches it.

Made-up reports and log lines only.
"""

import json
import threading
from collections.abc import Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests.fakes import MemoryCredentialStore
from tests.test_protocol import example

from polyglotic_desktop.adapters.app_log import hide_home, read_log
from polyglotic_desktop.adapters.feedback_files import KEEP, FeedbackFolder
from polyglotic_desktop.connection.feedback import (
    FeedbackSender,
    Outcome,
    send_report,
)
from polyglotic_desktop.ports.credentials import DeviceCredentials
from polyglotic_desktop.ports.feedback import Report

TOKEN = "pgd_" + "A" * 43
REPORT = Report(
    id="2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e",
    at="2026-11-05T10:02:00.000Z",
    kind="problem",
    text="The overlay stayed empty after I switched to the mic.",
    reply_to=None,
    log="2026-11-05 10:01:12 INFO connection: session opened\n",
    app_version="0.1.0",
    os="windows-11",
    os_version="10.0.26200",
    session_id="9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b",
)


def report(n: int, **changes: Any) -> Report:
    return replace(
        REPORT,
        id=f"{n:08d}-6f7a-4b8c-9d0e-1f2a3b4c5d6e",
        at=f"2026-11-05T10:{n:02d}:00.000Z",
        **changes,
    )


# --- Kept until sent -------------------------------------------------------------


def test_reports_wait_in_files_until_removed(tmp_path: Path) -> None:
    folder = FeedbackFolder(tmp_path / "feedback")
    assert folder.waiting() == []
    folder.add(report(2))
    folder.add(report(1, reply_to="tester@example.com"))
    again = FeedbackFolder(tmp_path / "feedback")  # the next start
    assert [r.id[:8] for r in again.waiting()] == ["00000001", "00000002"]
    assert again.waiting()[0].reply_to == "tester@example.com"
    again.remove(report(1).id)
    assert [r.id[:8] for r in again.waiting()] == ["00000002"]
    assert again.clear() == 1 and again.waiting() == []


def test_past_the_limit_the_oldest_reports_go(tmp_path: Path) -> None:
    folder = FeedbackFolder(tmp_path)
    for n in range(KEEP + 2):
        folder.add(report(n))
    kept = folder.waiting()
    assert len(kept) == KEEP
    assert kept[0].id[:8] == "00000002"


def test_a_report_file_that_cant_be_read_is_set_aside(tmp_path: Path) -> None:
    folder = FeedbackFolder(tmp_path)
    folder.add(report(1))
    (tmp_path / "broken.json").write_text("{not json", "utf-8")
    assert [r.id[:8] for r in folder.waiting()] == ["00000001"]
    assert not (tmp_path / "broken.json").exists()


# --- The log, as attached --------------------------------------------------------


def test_the_log_attached_is_the_newest_part_from_a_whole_line(tmp_path: Path) -> None:
    (tmp_path / "polyglotic.log.1").write_text("older line\n" * 10, "utf-8")
    (tmp_path / "polyglotic.log").write_text("newer line\n" * 3, "utf-8")
    assert read_log(tmp_path, limit=1000) == "older line\n" * 10 + "newer line\n" * 3
    tail = read_log(tmp_path, limit=50)
    assert tail is not None and tail.endswith("newer line\n" * 3)
    assert len(tail) <= 50 and tail.startswith(("older line", "newer line"))


def test_no_log_file_is_no_log(tmp_path: Path) -> None:
    assert read_log(tmp_path / "logs") is None


@pytest.mark.windows_only  # Windows' paths
def test_the_users_folder_is_hidden_in_the_log(tmp_path: Path) -> None:
    home = Path("C:/Users/Tester")
    text = (
        'File "C:\\Users\\Tester\\AppData\\Local\\Polyglotic\\x.py", line 3\n'
        "and c:/users/tester/AppData too\n"
    )
    (tmp_path / "polyglotic.log").write_text(text, "utf-8")
    shown = read_log(tmp_path, home=home)
    assert shown is not None
    assert "Tester" not in shown and "tester" not in shown
    assert shown.count("%USERPROFILE%") == 2
    assert hide_home("C:\\x", Path("C:\\")) == "C:\\x"  # a drive alone: nothing to hide


@pytest.mark.windows_only  # Windows' paths
def test_the_users_folder_is_hidden_where_velopack_escapes_it(tmp_path: Path) -> None:
    """Velopack's own log line at every update check writes the verified
    feed's path with each backslash doubled - the user's name went into a
    report's log there (polyglotic-hq 336)."""
    home = Path("C:/Users/Tester")
    line = (
        "INFO velopack.sources.file: Reading releases from file: "
        '"C:\\\\Users\\\\Tester\\\\AppData\\\\Local\\\\Polyglotic\\\\verified-feed'
        '\\\\win-x64-alpha\\\\releases.win-x64-alpha.json"\n'
    )
    (tmp_path / "polyglotic.log").write_text(line, "utf-8")
    shown = read_log(tmp_path, home=home)
    assert shown is not None
    assert "tester" not in shown.lower()
    assert shown.count("%USERPROFILE%") == 1
    assert "%USERPROFILE%\\\\AppData\\\\Local" in shown


# --- Sending -----------------------------------------------------------------------


class FeedbackServer:
    """Answers `POST /v1/feedback` with `status` (202 with the example's body)."""

    def __init__(self) -> None:
        self.requests: list[tuple[dict[str, Any], str]] = []
        self.status = 202
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((body, self.headers["Authorization"]))
                if outer.status == 202:
                    answer: dict[str, Any] = {"id": body["id"]}
                elif outer.status == 429:
                    answer = example("http/feedback.error")
                else:
                    answer = {"error": "request_not_valid"}
                data = json.dumps(answer).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"


@pytest.fixture
def server() -> Iterator[FeedbackServer]:
    stand_in = FeedbackServer()
    thread = threading.Thread(target=stand_in.http.serve_forever, daemon=True)
    thread.start()
    yield stand_in
    stand_in.http.shutdown()
    stand_in.http.server_close()


def test_a_report_is_sent_as_protocol_md_says(server: FeedbackServer) -> None:
    assert send_report(server.url, TOKEN, REPORT) is Outcome.SENT
    ((body, authorization),) = server.requests
    assert authorization == f"Bearer {TOKEN}"
    expected = {
        k: v for k, v in example("http/feedback.request").items() if v is not None
    }
    assert body.keys() == expected.keys()
    assert body["kind"] == "problem" and body["text"] == REPORT.text


def test_what_the_server_answers_decides_what_happens(server: FeedbackServer) -> None:
    for status, outcome in (
        (400, Outcome.REFUSED),
        (413, Outcome.REFUSED),
        (429, Outcome.WAITING),
        (401, Outcome.WAITING),
        (500, Outcome.WAITING),
    ):
        server.status = status
        assert send_report(server.url, TOKEN, REPORT) is outcome, status


def test_an_unreachable_server_keeps_the_report() -> None:
    assert send_report("http://127.0.0.1:9", TOKEN, REPORT) is Outcome.WAITING


def test_the_token_never_goes_in_the_clear_to_another_machine() -> None:
    with pytest.raises(ValueError):
        send_report("http://example.com", TOKEN, REPORT)


def signed_in() -> MemoryCredentialStore:
    return MemoryCredentialStore(DeviceCredentials("install", TOKEN))


def test_the_sender_sends_what_waits_and_forgets_what_arrived(
    server: FeedbackServer, tmp_path: Path
) -> None:
    folder = FeedbackFolder(tmp_path)
    folder.add(report(1))
    folder.add(report(2, kind="suggestion", log=None))
    heard: list[tuple[str, Outcome]] = []
    sender = FeedbackSender(
        server.url, signed_in(), folder, lambda r, o: heard.append((r.id[:8], o))
    )
    sender.send_waiting().result(timeout=10)
    assert heard == [("00000001", Outcome.SENT), ("00000002", Outcome.SENT)]
    assert folder.waiting() == []
    assert [b["kind"] for b, _ in server.requests] == ["problem", "suggestion"]
    sender.close()


def test_the_sender_stops_at_the_first_report_that_must_wait(tmp_path: Path) -> None:
    folder = FeedbackFolder(tmp_path)
    for n in (1, 2, 3):
        folder.add(report(n))
    answers = iter([Outcome.REFUSED, Outcome.WAITING, Outcome.SENT])
    tried: list[str] = []

    def send(server: str, token: str, sent: Report) -> Outcome:
        tried.append(sent.id[:8])
        return next(answers)

    sender = FeedbackSender("https://server.invalid", signed_in(), folder, send=send)
    sender.send_waiting().result(timeout=10)
    assert tried == ["00000001", "00000002"]  # the third would wait too
    assert [r.id[:8] for r in folder.waiting()] == ["00000002", "00000003"]
    sender.close()


def test_without_a_token_reports_wait_for_signing_in(tmp_path: Path) -> None:
    folder = FeedbackFolder(tmp_path)
    folder.add(report(1))
    tried: list[Report] = []

    def send(server: str, token: str, sent: Report) -> Outcome:
        tried.append(sent)
        return Outcome.SENT

    sender = FeedbackSender(
        "https://server.invalid", MemoryCredentialStore(), folder, send=send
    )
    sender.send_waiting().result(timeout=10)
    assert tried == [] and len(folder.waiting()) == 1
    sender.close()


def test_a_report_the_protocol_cant_carry_is_forgotten(tmp_path: Path) -> None:
    folder = FeedbackFolder(tmp_path)
    folder.add(report(1, text="x" * 5001))
    heard: list[Outcome] = []
    sender = FeedbackSender(
        "http://127.0.0.1:9", signed_in(), folder, lambda r, o: heard.append(o)
    )
    sender.send_waiting().result(timeout=10)
    assert heard == [Outcome.REFUSED] and folder.waiting() == []
    sender.close()
