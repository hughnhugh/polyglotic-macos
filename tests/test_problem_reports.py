"""Report a problem (polyglotic-hq 275): what listening offers (captions as shown,
each source's held speech), the request as protocol.md's example, kept on
the PC until sent, and sent to a stand-in for `POST /v1/problem-reports`.

Made-up captions, log lines and bytes only - never anyone's speech.
"""

import base64
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from tests.fakes import MemoryCredentialStore
from tests.test_protocol import example

from polyglotic_desktop.adapters.problem_report_files import (
    KEEP,
    ProblemReportFolder,
)
from polyglotic_desktop.connection.feedback import Outcome
from polyglotic_desktop.connection.problem_reports import (
    ProblemReportSender,
    request_body,
    send_problem_report,
)
from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.problem_report import (
    captions_as_shown,
    speech_by_source,
)
from polyglotic_desktop.core.listening.recent_speech import HeldSpeech, RecentSpeech
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ports.credentials import DeviceCredentials
from polyglotic_desktop.ports.problem_reports import ProblemReport, ReportedSpeech

TOKEN = "pgd_" + "A" * 43
NOW = datetime(2026, 11, 11, 13, 30, tzinfo=UTC)
EXAMPLE = example("http/problem_report.request")


def caption(n: int, minutes_ago: float, source: str = "app-1") -> Caption:
    at = NOW - timedelta(minutes=minutes_ago)
    return Caption(
        key=n,
        caption_id=CaptionId(f"0a1b2c3d-4e5f-4a6b-8c7d-{n:012d}"),
        source_id=SourceId(source),
        by_you=False,
        live=False,
        clauses=(
            Clause(
                "车票在柜台上。", {Language("en"): "The tickets are on the counter."}
            ),
        ),
        language=Language("zh"),
        languages_heard=(Language("zh"),),
        started_at=at,
        updated_at=at + timedelta(seconds=2),
    )


def held(n: int, source: str, category: SourceCategory, end: float) -> HeldSpeech:
    return HeldSpeech(
        CaptionId(f"0a1b2c3d-4e5f-4a6b-8c7d-{n:012d}"),
        SourceId(source),
        category,
        end - 2.0,
        end,
        b"OggS" + bytes(96),
    )


def test_the_captions_of_the_last_few_minutes_as_shown_oldest_first() -> None:
    shown = captions_as_shown([caption(2, 1.0), caption(1, 3.0), caption(0, 9.0)], NOW)
    assert [c["caption_id"] for c in shown] == [
        "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
        "0a1b2c3d-4e5f-4a6b-8c7d-000000000002",
    ]
    assert shown[1] == {
        "caption_id": "0a1b2c3d-4e5f-4a6b-8c7d-000000000002",
        "source_id": "app-1",
        "by_you": False,
        "live": False,
        "language": "zh",
        "started_at": "2026-11-11T13:29:00.000Z",
        "updated_at": "2026-11-11T13:29:02.000Z",
        "original": "车票在柜台上。",
        "translations": {"en": "The tickets are on the counter."},
        "checked": False,
    }


def test_held_speech_comes_as_one_part_per_source_and_says_whose_voices() -> None:
    clock = [100.0]
    store = RecentSpeech(lambda: clock[0])
    store.add(held(1, "app-1", SourceCategory.VIDEO, 10.0))
    store.add(held(2, "discord", SourceCategory.CALL, 20.0))
    store.add(held(3, "app-1", SourceCategory.VIDEO, 30.0))
    store.add(held(4, "mic", SourceCategory.MIC, 95.0))
    clock[0] = 140.0  # the first is past 2 minutes now
    video, call, mic = speech_by_source(store.held())
    assert [str(c.caption_id)[-1] for c in video.clips] == ["3"]
    assert (video.others_voices, call.others_voices, mic.others_voices) == (
        False,
        True,
        True,
    )
    assert (call.seconds, call.size) == (2.0, 100)


def test_a_report_is_sent_as_protocol_md_s_example() -> None:
    sent = EXAMPLE["speech"][0]
    report = ProblemReport(
        id=EXAMPLE["id"],
        at=EXAMPLE["at"],
        text=EXAMPLE["text"],
        app_version=EXAMPLE["app_version"],
        os=EXAMPLE["os"],
        os_version=EXAMPLE["os_version"],
        session_id=EXAMPLE["session_id"],
        log=EXAMPLE["log"],
        settings=EXAMPLE["settings"],
        facts=EXAMPLE["facts"],
        captions=EXAMPLE["captions"],
        speech=(
            ReportedSpeech(
                sent["caption_id"],
                sent["source_id"],
                sent["category"],
                sent["speech_start"],
                sent["speech_end"],
                base64.b64decode(sent["data"]),
            ),
        ),
    )
    assert json.loads(request_body(report)) == EXAMPLE


def test_unticked_parts_are_left_out() -> None:
    report = ProblemReport(
        "5d6e7f80-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
        "2026-11-11T03:10:00.000Z",
        "",
        "0.4.0",
        "windows-11",
        "10.0.26200",
        None,
        None,
        None,
        {"app": {}},
        None,
    )
    body = json.loads(request_body(report))
    assert set(body) == {"id", "at", "text", "app_version", "os", "os_version", "facts"}


def test_waiting_reports_are_kept_whole_until_sent(tmp_path: Path) -> None:
    folder = ProblemReportFolder(tmp_path / "problem-reports")
    for n in range(KEEP + 2):
        folder.add(f"id-{n}", f"body {n}".encode())
    assert [i for i, _ in folder.waiting()] == [f"id-{n}" for n in range(2, KEEP + 2)]
    folder.remove("id-2")
    assert folder.waiting()[0] == ("id-3", b"body 3")
    assert folder.clear() == KEEP - 1 and folder.waiting() == []


class Stand_in(BaseHTTPRequestHandler):
    answers: ClassVar[list[int]] = []
    bodies: ClassVar[list[Any]] = []

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        type(self).bodies.append(json.loads(self.rfile.read(length)))
        code = type(self).answers.pop(0)
        body = json.dumps(
            {"id": self.bodies[-1]["id"]} if code == 202 else {"error": "x"}
        ).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def stand_in() -> Iterator[str]:
    Stand_in.answers, Stand_in.bodies = [], []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stand_in)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.mark.parametrize(
    ("code", "outcome"),
    [
        (202, Outcome.SENT),
        (403, Outcome.REFUSED),  # captions or audio from outside the alpha
        (413, Outcome.REFUSED),
        (400, Outcome.REFUSED),
        (404, Outcome.WAITING),  # a server before 275
        (429, Outcome.WAITING),
        (500, Outcome.WAITING),
    ],
)
def test_what_the_server_answers_decides(
    stand_in: str, code: int, outcome: Outcome
) -> None:
    Stand_in.answers = [code]
    body = json.dumps(EXAMPLE).encode()
    assert send_problem_report(stand_in, TOKEN, body) is outcome


def test_the_sender_keeps_then_sends_off_the_callers_thread(
    stand_in: str, tmp_path: Path
) -> None:
    credentials = MemoryCredentialStore()
    waiting = ProblemReportFolder(tmp_path)
    told: list[tuple[str, Outcome, str]] = []
    sender = ProblemReportSender(
        stand_in,
        credentials,
        waiting,
        lambda i, o: told.append((i, o, threading.current_thread().name)),
    )
    report = ProblemReport(
        EXAMPLE["id"],
        EXAMPLE["at"],
        "it froze",
        "0.4.0",
        "windows-11",
        "10",
        None,
        None,
        None,
        None,
        None,
    )
    sender.keep_and_send(report).result(5)
    assert waiting.waiting() != [] and told == []  # not signed in: it waits
    credentials.save(DeviceCredentials("6f1c2d3e-4a5b-4c6d-8e7f-8091a2b3c4d5", TOKEN))
    Stand_in.answers = [500]
    sender.send_waiting().result(5)
    assert told[-1][1] is Outcome.WAITING and waiting.waiting() != []
    Stand_in.answers = [202]
    sender.send_waiting().result(5)
    assert told[-1][:2] == (EXAMPLE["id"], Outcome.SENT)
    assert told[-1][2].startswith("problem-reports")
    assert waiting.waiting() == []
    assert Stand_in.bodies[-1]["text"] == "it froze"
    sender.close()
