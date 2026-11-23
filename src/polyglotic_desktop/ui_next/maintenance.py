"""Planned maintenance in the interface's words (polyglotic-hq 319, decision 0110).

One place for every line about a planned maintenance window, so Home's
banner, its state line, the tray (Home's title) and the caption windows
say it alike. Times are the learner's: their PC's time zone, written as
the app writes times (`QLocale()`: Windows' regional format when it's in
the interface's language). "Today" and "tomorrow" are the real day - the
server's time, corrected for a PC whose clock is off - in that zone. The
window's times are shown as they are; only "now" is corrected.

Each line names that zone once, after its last time - "06:00-07:30
(AEDT)" - so testers in other countries needn't guess whose 06:00 it is
(polyglotic-hq 542): the short name the learner's locale gives it at that
moment ("AEDT" in Melbourne's summer, "AEST" in its winter, "MEZ" in a
German Berlin), or its offset from UTC ("UTC+11") where the locale has
only an offset or nothing. A window with daylight saving starting or
ending inside it names the zone after both times: "01:30 (AEDT)-02:30
(AEST)".
"""

from datetime import UTC, datetime

from PySide6.QtCore import QDateTime, QLocale, QTime, QTimeZone
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.maintenance import Maintenance, Phase, phase


def _tr(text: str) -> str:
    return QApplication.translate("Maintenance", text)


_held: list[Maintenance | None] = [None]
"""The window the app holds now (`hold`)."""


def hold(window: Maintenance | None) -> None:
    """The planned maintenance window the app holds now (None: none), as
    Home is told it (`main.Hub.set_maintenance`): the caption windows'
    notice during it says until when from it (`notice_until`)."""
    _held[0] = window


def wall_clock() -> datetime:
    """This PC's time now, for the caption windows' notice (the UI lab and
    the tests put a fixed one in its place)."""
    return datetime.now(UTC)


def pc_zone() -> QTimeZone:
    """This PC's time zone, as Windows (or macOS) has it: every time here
    is written in it, unless a test (or the UI lab) gives another."""
    return QTimeZone.systemTimeZone()


def _on_clock(at: datetime, zone: QTimeZone | None) -> QDateTime:
    """`at` on `zone`'s clock (None: this PC's)."""
    return QDateTime.fromMSecsSinceEpoch(
        round(at.timestamp() * 1000), pc_zone() if zone is None else zone
    )


def clock_time(at: datetime, zone: QTimeZone | None = None) -> str:
    """`at` on this PC's clock face: its zone (`zone`: another, for tests),
    the learner's time format."""
    local = _on_clock(at, zone).time()
    return QLocale().toString(
        QTime(local.hour(), local.minute()), QLocale.FormatType.ShortFormat
    )


def utc_offset(seconds: int) -> str:
    """An offset from UTC as a zone's name: "UTC+11", "UTC+5:30", "UTC-3"."""
    if seconds == 0:
        return "UTC"
    sign = "+" if seconds > 0 else "-"
    hours, minutes = divmod(abs(seconds) // 60, 60)
    return f"UTC{sign}{hours}:{minutes:02d}" if minutes else f"UTC{sign}{hours}"


def zone_name(at: datetime, zone: QTimeZone | None = None) -> str:
    """The name of the PC's zone (`zone`: another) at `at`: the learner's
    locale's short name for it then ("AEDT", "AEST", "JST", "MEZ"), or its
    offset ("UTC+11") where the locale gives only an offset ("GMT+11") or
    nothing."""
    zone = pc_zone() if zone is None else zone
    moment = _on_clock(at, zone)
    name = zone.displayName(moment, QTimeZone.NameType.ShortName, QLocale())
    if name and not any(c.isdigit() for c in name):
        return name
    return utc_offset(zone.offsetFromUtc(moment))


def _zoned(time: str, at: datetime, zone: QTimeZone | None) -> str:
    #: a time and the time zone of the learner's PC it's in, said once in a
    #: line about planned maintenance: "07:30 (AEDT)", "Sunday 07:30 (UTC+11)"
    return _tr("{time} ({zone})").format(time=time, zone=zone_name(at, zone))


def time_on(at: datetime, beside: datetime, zone: QTimeZone | None = None) -> str:
    """`at`'s time, with its day's name when it falls on another day than
    `beside` in this PC's zone ("Sunday 00:30")."""
    local = _on_clock(at, zone).date()
    if local == _on_clock(beside, zone).date():
        return clock_time(at, zone)
    day = QLocale().dayName(local.dayOfWeek(), QLocale.FormatType.LongFormat)
    #: a weekday's name and a time on it: "Sunday 00:30"
    return _tr("{day} {time}").format(day=day, time=clock_time(at, zone))


def _until(window: Maintenance, now: datetime, zone: QTimeZone | None) -> str:
    """The window's end, and its zone: "07:30 (AEDT)"."""
    return _zoned(time_on(window.ends_at, now, zone), window.ends_at, zone)


def _span(window: Maintenance, zone: QTimeZone | None) -> tuple[str, str]:
    """The window's start and end, the zone named after the end - and
    after the start too when it's another there: daylight saving starting
    or ending inside the window ("01:30 (AEDT)", "02:30 (AEST)")."""
    start = clock_time(window.starts_at, zone)
    if zone_name(window.starts_at, zone) != zone_name(window.ends_at, zone):
        start = _zoned(start, window.starts_at, zone)
    return start, _until(window, window.starts_at, zone)


def state_title(
    window: Maintenance | None, pc_now: datetime, zone: QTimeZone | None = None
) -> str:
    """Home's title (and so the tray's) while the server is away for it."""
    if window is None:
        return _tr("Planned maintenance")
    #: Home's title and the tray's while Polyglotic's server is in it
    return _tr("Planned maintenance until {time}").format(
        time=_until(window, window.server_now(pc_now), zone)
    )


def state_detail() -> str:
    """Home's line under the title: whose it is, and that nothing's to do -
    never "down": the title says it's planned, and until when (329's QA,
    330). A fragment, as Home's other details are; Help makes it a
    sentence (`home.unreachable_words`)."""
    #: Home's line under "Planned maintenance until 15:30"
    return _tr("not your internet - captions come back by themselves when it's over")


def banner(
    window: Maintenance | None, pc_now: datetime, zone: QTimeZone | None = None
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
        ).format(time=_until(window, now, zone))
    if shown is not Phase.AHEAD:
        return None
    start, end = _span(window, zone)
    if _on_clock(window.starts_at, zone).date() == _on_clock(now, zone).date():
        return _tr(
            "Planned maintenance today, {start}-{end}: captions pause then, "
            "and come back by themselves."
        ).format(start=start, end=end)
    return _tr(
        "Planned maintenance tomorrow, {start}-{end}: captions pause then, "
        "and come back by themselves."
    ).format(start=start, end=end)


def notice_until(
    pc_now: datetime | None = None, zone: QTimeZone | None = None
) -> str | None:
    """The caption windows' notice while the server is away for planned
    maintenance, with until when - the end Home's title says, in the PC's
    zone, named: "Planned maintenance until 07:30 (AEDT) - captions come
    back by themselves" (polyglotic-hq 563, 542's proposal: it said only
    that it was planned). None with no window held: the notice then says
    only that (`caption_window.notice_text`)."""
    window = _held[0]
    if window is None:
        return None
    now = window.server_now(wall_clock() if pc_now is None else pc_now)
    #: the caption windows' line while Polyglotic's server is in it
    return _tr(
        "Planned maintenance until {time} - captions come back by themselves"
    ).format(time=_until(window, now, zone))


def soon_line(window: Maintenance, zone: QTimeZone | None = None) -> str:
    """The caption windows' one line, once, a few minutes before the start."""
    start, end = _span(window, zone)
    return _tr("Captions pause at {start} for planned maintenance, until {end}").format(
        start=start, end=end
    )
