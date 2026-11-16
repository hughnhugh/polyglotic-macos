"""The user's consent choices, kept on this PC.

The first-run consent screen asks once (project 012, agreed 2026-11-04):
usage statistics, crash reports, and sharing how often they hear words
(exposure counts) - each off until the user says yes, and changeable in
settings. What the service needs (the account, minutes, connection data)
is explained there but isn't optional, so it isn't a choice here.

Each choice is kept with its id and time; the connection sends it to the
server as protocol.md's `consent` message (the record of the choice) and
sends usage events and exposure counts only while it says yes.

With each choice goes the tester agreement this PC accepted - its version
and when - asked on the same screen before anything else (polyglotic-hq
project 185): a later choice carries the same acceptance, so the server's
latest record always says which agreement the tester is under.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Agreement:
    """The tester agreement accepted on this PC: its version
    (`tester-2026-11-11`, core.shared.papers) and when (UTC)."""

    version: str
    at: datetime


@dataclass(frozen=True)
class ConsentChoice:
    """`usage`: usage statistics. `crashes`: crash reports. `exposures`:
    sharing how often the learner hears words. `id` is a UUID; `at` is
    when they chose (UTC). `agreement`: the tester agreement accepted on
    this PC, if any yet."""

    id: str
    at: datetime
    usage: bool
    crashes: bool
    exposures: bool
    agreement: Agreement | None = None


class ConsentStore(Protocol):
    def consent(self) -> ConsentChoice | None:
        """The latest choice, or None if the user hasn't chosen yet (show
        the consent screen)."""
        ...

    def save_consent(self, choice: ConsentChoice) -> None: ...
