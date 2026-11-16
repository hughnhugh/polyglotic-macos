"""Sending feedback: `POST /v1/feedback` (protocol.md, Feedback), and sending again what waits.

A report the user sends is kept (`WaitingReports`) before anything is
tried, then `FeedbackSender` sends what waits, one at a time, on a thread
of its own - plain HTTP from the standard library, like signing in, so it
works when no listening session can open (that may be the problem being
reported). With the device token as `Authorization: Bearer ...`; with no
token yet, reports wait until the user signs in.

What the server answers decides what happens to a report:
- **stored** (`202`): forgotten here;
- **refused for good** (`400`, `413`: it would be refused every time):
  forgotten, and the user told;
- **anything else** - unreachable, busy (`429`), the token refused (`401`,
  sign in again), a server error: kept, and tried again later (`main`
  asks every `RETRY_EVERY_SEC`, and at start). Sending stops at the first
  such answer: the rest would get the same.

Nothing a report holds - its text, reply address or log - is ever logged
or put in an error.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from enum import StrEnum

from polyglotic_desktop.connection import protocol, tls
from polyglotic_desktop.connection.addresses import server_address
from polyglotic_desktop.core.shared.client import USER_AGENT
from polyglotic_desktop.ports.credentials import CredentialStore
from polyglotic_desktop.ports.feedback import Report, WaitingReports

TIMEOUT_SEC = 30.0
RETRY_EVERY_SEC = 600
log = logging.getLogger(__name__)


class Outcome(StrEnum):
    SENT = "sent"
    REFUSED = "refused"  # never accepted as it is: forgotten
    WAITING = "waiting"  # kept, to try again later


def send_report(
    server: str, token: str, report: Report, timeout: float = TIMEOUT_SEC
) -> Outcome:
    """Sends one report to `server` (`https://<host>`, or a local test
    server). ValueError for a plain `http://` address to another machine:
    the token would travel in the clear (connection/addresses.py); also
    ProtocolError for a report the protocol can't carry - caught by
    `FeedbackSender`, which forgets it."""
    address = server_address(server)
    body = protocol.encode(protocol.validate(protocol.FeedbackRequest, asdict(report)))
    request = urllib.request.Request(
        f"{address}/v1/feedback",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with tls.urlopen(request, timeout) as response:
            protocol.validate(protocol.FeedbackResponse, json.load(response))
    except urllib.error.HTTPError as error:
        if error.code in (400, 413):
            log.warning("a report was refused by the server (%d)", error.code)
            return Outcome.REFUSED
        log.info("a report waits: the server answered %d", error.code)
        return Outcome.WAITING
    except (urllib.error.URLError, OSError) as error:
        log.info(
            "a report waits: the server couldn't be reached (%s)", type(error).__name__
        )
        return Outcome.WAITING
    except (ValueError, protocol.ProtocolError):
        log.info("a report waits: the server's answer couldn't be read")
        return Outcome.WAITING
    return Outcome.SENT


class FeedbackSender:
    """Sends the waiting reports on a thread of its own, one call at a
    time. `on_outcome(report, outcome)` is called on that thread for each
    report tried."""

    def __init__(
        self,
        server: str,
        credentials: CredentialStore,
        waiting: WaitingReports,
        on_outcome: Callable[[Report, Outcome], None] | None = None,
        send: Callable[[str, str, Report], Outcome] = send_report,
    ) -> None:
        self.server = server
        self.credentials = credentials
        self.waiting = waiting
        self.on_outcome = on_outcome
        self._send = send
        self._worker = ThreadPoolExecutor(1, thread_name_prefix="feedback")

    def send_waiting(self) -> "Future[None]":
        """Tries every waiting report, oldest first, off the caller's thread."""
        return self._worker.submit(self._send_all)

    def _send_all(self) -> None:
        saved = self.credentials.load()
        if saved is None:
            return  # sent once the user signs in
        for report in self.waiting.waiting():
            try:
                outcome = self._send(self.server, saved.device_token, report)
            except protocol.ProtocolError:  # e.g. text over the limit: never sendable
                outcome = Outcome.REFUSED
            except ValueError:  # an address the token mustn't go to
                outcome = Outcome.WAITING
            if outcome is not Outcome.WAITING:
                self.waiting.remove(report.id)
            if self.on_outcome is not None:
                self.on_outcome(report, outcome)
            if outcome is Outcome.WAITING:
                return

    def close(self) -> None:
        self._worker.shutdown(wait=False, cancel_futures=True)
