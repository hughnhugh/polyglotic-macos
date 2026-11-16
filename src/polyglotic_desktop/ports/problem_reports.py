"""Problem reports: "Report a problem" for alpha testers (polyglotic-hq 275; decision 0067).

A `ProblemReport` is feedback with everything attached that the tester
left ticked (protocol.md, Problem reports): their words, the app's log, its
settings, facts about the app, Windows and the audio devices, and - for
the alpha cohort only - the captions as shown and each source's last 2
minutes of speech, as sent for captioning.

Reports wait on this PC until the server has them (`WaitingProblemReports`),
each kept as the request it will be - its body, built once - so one
written while the server can't be reached goes later. They're kept apart
from the outbox (content-free) and from feedback (`ports.feedback`): a
report can hold what people said.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ReportedSpeech:
    """One finished caption's audio as it was sent: one Ogg Opus stream;
    `speech_start` and `speech_end` on the app's clock."""

    caption_id: str
    source_id: str
    category: str
    speech_start: float
    speech_end: float
    audio: bytes


@dataclass(frozen=True)
class ProblemReport:
    """A report as the tester sent it. A part they unticked is None (no
    speech: empty)."""

    id: str  # a UUID, so sending it twice keeps it once
    at: str  # when the tester sent it (protocol.md's time format)
    text: str
    app_version: str
    os: str
    os_version: str
    session_id: str | None
    log: str | None
    settings: Mapping[str, object] | None
    facts: Mapping[str, object] | None
    captions: Sequence[Mapping[str, object]] | None
    speech: tuple[ReportedSpeech, ...] = ()


class WaitingProblemReports(Protocol):
    def add(self, report_id: str, body: bytes) -> None:
        """Keeps a report's request body until it's sent; past a limit the
        oldest go."""
        ...

    def waiting(self) -> Sequence[tuple[str, bytes]]:
        """Every report not sent yet, oldest first: (id, body)."""
        ...

    def remove(self, report_id: str) -> None:
        """Forgets a report (the server has it, or refused it for good)."""
        ...

    def clear(self) -> int:
        """Forgets every report (signing out, deleting listening data);
        returns how many."""
        ...
