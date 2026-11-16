"""Sending problem reports: `POST /v1/problem-reports` (protocol.md, Problem reports; polyglotic-hq 275).

"Report a problem" for alpha testers. Like feedback (`connection.feedback`),
plain HTTP from the standard library on a thread of its own, so it works
when no listening session can open - and so nothing here ever runs on the
interface's thread: `ProblemReportSender.keep_and_send` builds the request
(base64 of the audio, a few hundred KB a source), keeps it on disk, then
sends what waits, one at a time.

What the server answers decides what happens to a report:
- **kept** (`202`): forgotten here;
- **refused for good** (`400`, `403` - captions or audio from outside the
  alpha -, `413`): forgotten, and the tester told;
- **anything else** - unreachable, busy (`429`), an older server without
  the endpoint (`404`), the token refused (`401`), a server error: kept,
  and tried again later. Sending stops at the first such answer.

Nothing a report holds is ever logged or put in an error.
"""

import base64
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from polyglotic_desktop.connection import protocol, tls
from polyglotic_desktop.connection.addresses import server_address
from polyglotic_desktop.connection.feedback import TIMEOUT_SEC, Outcome
from polyglotic_desktop.core.shared.client import USER_AGENT
from polyglotic_desktop.ports.credentials import CredentialStore
from polyglotic_desktop.ports.problem_reports import (
    ProblemReport,
    WaitingProblemReports,
)

REFUSED_FOR_GOOD = (400, 403, 413)
log = logging.getLogger(__name__)


def request_body(report: ProblemReport) -> bytes:
    """The report as protocol.md's request body. ProtocolError for one the
    protocol can't carry (e.g. text over the limit): never sendable."""
    message = protocol.validate(
        protocol.ProblemReportRequest,
        {
            "id": report.id,
            "at": report.at,
            "text": report.text,
            "app_version": report.app_version,
            "os": report.os,
            "os_version": report.os_version,
            "session_id": report.session_id,
            "log": report.log,
            "settings": report.settings,
            "facts": report.facts,
            "captions": report.captions,
            "speech": [
                {
                    "caption_id": s.caption_id,
                    "source_id": s.source_id,
                    "category": s.category,
                    "speech_start": round(s.speech_start, 3),
                    "speech_end": round(s.speech_end, 3),
                    "codec": "ogg_opus",
                    "data": base64.b64encode(s.audio).decode("ascii"),
                }
                for s in report.speech
            ]
            or None,
        },
    )
    return protocol.encode(message).encode("utf-8")


def send_problem_report(
    server: str, token: str, body: bytes, timeout: float = TIMEOUT_SEC * 4
) -> Outcome:
    """Sends one report's body to `server`. ValueError for a plain
    `http://` address to another machine (connection/addresses.py)."""
    address = server_address(server)
    request = urllib.request.Request(
        f"{address}/v1/problem-reports",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with tls.urlopen(request, timeout) as response:
            protocol.validate(protocol.ProblemReportResponse, json.load(response))
    except urllib.error.HTTPError as error:
        if error.code in REFUSED_FOR_GOOD:
            log.warning("a problem report was refused by the server (%d)", error.code)
            return Outcome.REFUSED
        log.info("a problem report waits: the server answered %d", error.code)
        return Outcome.WAITING
    except (urllib.error.URLError, OSError) as error:
        log.info(
            "a problem report waits: the server couldn't be reached (%s)",
            type(error).__name__,
        )
        return Outcome.WAITING
    except (ValueError, protocol.ProtocolError):
        log.info("a problem report waits: the server's answer couldn't be read")
        return Outcome.WAITING
    return Outcome.SENT


class ProblemReportSender:
    """Keeps and sends problem reports on a thread of its own, one call at a
    time. `on_outcome(report_id, outcome)` is called on that thread for
    each report tried (and `REFUSED` for one that can't be built)."""

    def __init__(
        self,
        server: str,
        credentials: CredentialStore,
        waiting: WaitingProblemReports,
        on_outcome: Callable[[str, Outcome], None] | None = None,
        send: Callable[[str, str, bytes], Outcome] = send_problem_report,
    ) -> None:
        self.server = server
        self.credentials = credentials
        self.waiting = waiting
        self.on_outcome = on_outcome
        self._send = send
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="problem-reports")

    def keep_and_send(self, report: ProblemReport) -> "Future[None]":
        """Builds the report's request and keeps it, then sends what waits -
        all off the caller's thread."""
        return self._worker.submit(self._keep_and_send, report)

    def send_waiting(self) -> "Future[None]":
        """Tries every waiting report, oldest first, off the caller's thread."""
        return self._worker.submit(self._send_all)

    def _keep_and_send(self, report: ProblemReport) -> None:
        try:
            body = request_body(report)
        except protocol.ProtocolError:
            self._tell(report.id, Outcome.REFUSED)
            return
        self.waiting.add(report.id, body)
        log.info("a problem report kept to send (%d KiB)", len(body) // 1024)
        self._send_all()

    def _send_all(self) -> None:
        saved = self.credentials.load()
        if saved is None:
            return  # sent once the tester signs in
        for report_id, body in self.waiting.waiting():
            try:
                outcome = self._send(self.server, saved.device_token, body)
            except ValueError:  # an address the token mustn't go to
                outcome = Outcome.WAITING
            if outcome is not Outcome.WAITING:
                self.waiting.remove(report_id)
            self._tell(report_id, outcome)
            if outcome is Outcome.WAITING:
                return

    def _tell(self, report_id: str, outcome: Outcome) -> None:
        if self.on_outcome is not None:
            self.on_outcome(report_id, outcome)

    def close(self) -> None:
        self._worker.shutdown(wait=False, cancel_futures=True)
