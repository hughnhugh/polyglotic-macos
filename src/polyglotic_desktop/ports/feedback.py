"""Feedback: what the user sends us with "Report a problem" or "Suggest something".

A `Report` is the user's own words to us (protocol.md, Feedback): what
kind it is, their text, how to reply if they gave a way, the app's log if
they chose to attach it - shown to them before it goes - and the app and
Windows versions and the listening session it came from. Never a
screenshot: captions on screen can be other people's words.

Reports wait on this PC until the server has them (`WaitingReports`), so
one written while the server can't be reached is sent later. They're kept
apart from the outbox (`ports.outbox`), which holds only content-free
data: a report holds what the user wrote.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

ReportKind = Literal["problem", "suggestion", "question", "work_with_us"]
"""A problem, a suggestion, a question, or "I'd like to work on Polyglotic"."""


@dataclass(frozen=True)
class Report:
    id: str  # a UUID, so sending it twice stores it once
    at: str  # when the user sent it (protocol.md's time format)
    kind: ReportKind
    text: str
    reply_to: str | None  # an email address or a Discord name, as typed
    log: str | None  # the app's log as the user saw it, or None
    app_version: str
    os: str  # windows-10, windows-11
    os_version: str  # Windows' version number, e.g. 10.0.26200
    session_id: str | None  # the last listening session's, if one opened


class WaitingReports(Protocol):
    def add(self, report: Report) -> None:
        """Keeps `report` until it's sent; past a limit the oldest go."""
        ...

    def waiting(self) -> Sequence[Report]:
        """Every report not sent yet, oldest first."""
        ...

    def remove(self, report_id: str) -> None:
        """Forgets a report (the server has it, or refused it for good)."""
        ...

    def clear(self) -> int:
        """Forgets every report (signing out); returns how many."""
        ...
