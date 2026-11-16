"""Planned maintenance in the interface's words (polyglotic-hq 319, decision 0110).

One place for every line about a planned maintenance window, so Home's
banner, its state line, the tray (Home's title) and the caption windows
say it alike. Times are the learner's: their PC's time zone, written as
the app writes times (`QLocale()`: Windows' regional format when it's in
the interface's language). "Today" and "tomorrow" are the real day - the
server's time, corrected for a PC whose clock is off - in that zone. The
window's times are shown as they are; only "now" is corrected.
"""

from datetime import datetime, tzinfo

from PySide6.QtCore import QLocale, QTime
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.maintenance import Maintenance, Phase, phase


def _tr(text: str) -> str:
    return QApplication.translate("Maintenance", text)


def clock_time(at: datetime, zone: tzinfo | None = None) -> str:
    """`at` on this PC's clock face: its zone (`zone`: another, for tests),
    the learner's time format."""
    local = at.astimezone(zone)
    return QLocale().toString(
        QTime(local.hour, local.minute), QLocale.FormatType.ShortFormat
    )


def time_on(at: datetime, beside: datetime, zone: tzinfo | None = None) -> str:
    """`at`'s time, with its day's name when it falls on another day than
    `beside` in this PC's zone ("Sunday 00:30")."""
    local, other = at.astimezone(zone), beside.astimezone(zone)
    if local.date() == other.date():
        return clock_time(at, zone)
    day = QLocale().dayName(local.isoweekday(), QLocale.FormatType.LongFormat)
    #: a weekday's name and a time on it: "Sunday 00:30"
    return _tr("{day} {time}").format(day=day, time=clock_time(at, zone))


def state_title(
    window: Maintenance | None, pc_now: datetime, zone: tzinfo | None = None
) -> str:
    """Home's title (and so the tray's) while the server is away for it."""
    if window is None:
        return _tr("Planned maintenance")
    now = window.server_now(pc_now)
    #: Home's title and the tray's while Polyglotic's server is in it
    return _tr("Planned maintenance until {time}").format(
        time=time_on(window.ends_at, now, zone)
    )


def state_detail() -> str:
    """Home's line under the title: whose it is, and that nothing's to do -
    never "down": the title says it's planned, and until when (329's QA,
    330). A fragment, as Home's other details are; Help makes it a
    sentence (`home.unreachable_words`)."""
    #: Home's line under "Planned maintenance until 15:30"
    return _tr("not your internet - captions come back by themselves when it's over")


def banner(
    window: Maintenance | None, pc_now: datetime, zone: tzinfo | None = None
) -> str | None:
    """Home's quiet line: from a day before the start, when it is; during
    it, until when (when the state line doesn't say it already); None
    otherwise."""
    if window is None:
        return None
    now = window.server_now(pc_now)
    shown = phase(window, pc_now)
    if shown is Phase.DURING:
        return _tr(
            "Planned maintenance until {time}: captions pause until then, and "
            "come back by themselves."
        ).format(time=time_on(window.ends_at, now, zone))
    if shown is not Phase.AHEAD:
        return None
    start = clock_time(window.starts_at, zone)
    end = time_on(window.ends_at, window.starts_at, zone)
    if window.starts_at.astimezone(zone).date() == now.astimezone(zone).date():
        return _tr(
            "Planned maintenance today, {start}-{end}: captions pause then, "
            "and come back by themselves."
        ).format(start=start, end=end)
    return _tr(
        "Planned maintenance tomorrow, {start}-{end}: captions pause then, "
        "and come back by themselves."
    ).format(start=start, end=end)


def soon_line(window: Maintenance, zone: tzinfo | None = None) -> str:
    """The caption windows' one line, once, a few minutes before the start."""
    return _tr("Captions pause at {start} for planned maintenance, until {end}").format(
        start=clock_time(window.starts_at, zone),
        end=time_on(window.ends_at, window.starts_at, zone),
    )
