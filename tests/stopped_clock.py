"""A wall clock stopped at one instant, for tests whose words or names
depend on the day, the hour or the time zone (polyglotic-hq 344).

A test that read `datetime.now()` itself, after the code under test had
read it, failed when the PC's midnight fell in between: the maintenance
test named Sunday in the app and not in the test (2026-11-14, #622). Put
`stopped_at(...)` in place of `datetime` in each module that reads the
clock, and work out what's expected from the same instant.
"""

from datetime import UTC, datetime, tzinfo

from PySide6.QtCore import QDate, QDateTime

AFTER_MIDNIGHT_IN_MELBOURNE = datetime(2026, 11, 14, 13, 30, tzinfo=UTC)
"""ENGINEERING.md 9b's 13:30 UTC: still Saturday in UTC, already Sunday
00:30 in Melbourne (daylight saving's +11)."""


def stopped_at(instant: datetime) -> type[datetime]:
    """`datetime`, whose `now` is always `instant` (in the zone asked for;
    this PC's time, without a zone, if none is)."""

    class Stopped(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> "Stopped":
            return cls.fromtimestamp(instant.timestamp(), tz)

    return Stopped


def qt_stopped_at(instant: datetime) -> tuple[type[QDate], type[QDateTime]]:
    """Qt's `QDate` and `QDateTime`, whose current date and time are
    `instant` on this PC's clock: for modules that read Qt's clock."""
    local = instant.astimezone()

    class StoppedDate(QDate):
        @staticmethod
        def currentDate() -> QDate:
            return QDate(local.year, local.month, local.day)

    class StoppedDateTime(QDateTime):
        @staticmethod
        def currentDateTime(*_: object) -> QDateTime:
            # this PC's zone only: the app reads it no other way
            return QDateTime.fromSecsSinceEpoch(int(instant.timestamp()))

    return StoppedDate, StoppedDateTime
