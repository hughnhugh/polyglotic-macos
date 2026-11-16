"""The install's milestones, kept between runs and sent as usage statistics (polyglotic-hq project 134).

`core.releases.milestones` decides; this keeps its `Kept` as one note in
the outbox (`milestones`, JSON: times, versions, names - nothing else)
and sends what's due through the `DataExchange`, which keeps a usage event
only with consent to usage statistics. Until then a milestone waits here,
and goes when the app next starts or listens with consent given.

`app_installed` and `app_updated` carry the app's version, Windows's
`os` and the update channel (the plan's types); `first_caption_shown` the
seconds since the install. Any thread.
"""

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.core.releases import milestones
from polyglotic_desktop.core.releases.milestones import INSTALLED, UPDATED, Kept
from polyglotic_desktop.ports.outbox import Outbox

log = logging.getLogger(__name__)

NOTE = "milestones"


def _now() -> datetime:
    return datetime.now(UTC)


class Milestones:
    def __init__(
        self,
        outbox: Outbox,
        exchange: DataExchange,
        app: AppInfo,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._outbox = outbox
        self._exchange = exchange
        self._app = app
        self._clock = clock
        self._lock = threading.Lock()
        self._kept = _load(outbox.note(NOTE))

    def started(self, fresh: bool) -> None:
        """The app started; `fresh`: this PC has never connected (a new install)."""
        with self._lock:
            self._kept, update = milestones.started(
                self._kept, self._app.app_version, fresh, self._clock()
            )
            self._save()
        if update is not None:
            self._exchange.usage(
                UPDATED, {**update.props, "channel": self._app.channel}, update.at
            )
        self.send_due()

    def caption_shown(self) -> None:
        """A finished caption arrived: the first one is a milestone."""
        with self._lock:
            kept = milestones.caption_shown(self._kept, self._clock())
            if kept == self._kept:
                return
            self._kept = kept
            self._save()
        self.send_due()

    def send_due(self) -> None:
        """Hands what's due to the exchange; what it keeps (with consent) is sent."""
        with self._lock:
            for milestone in milestones.due(self._kept):
                props = dict(milestone.props)
                if milestone.name == INSTALLED:
                    props.update(
                        app_version=self._app.app_version,
                        os_version=self._app.os,
                        channel=self._app.channel,
                    )
                if self._exchange.usage(milestone.name, props, milestone.at):
                    self._kept = replace(
                        self._kept, sent=self._kept.sent | {milestone.name}
                    )
                    log.info("milestone kept to send: %s", milestone.name)
            self._save()

    def _save(self) -> None:
        kept = self._kept
        self._outbox.save_note(
            NOTE,
            json.dumps(
                {
                    "installed_at": _iso(kept.installed_at),
                    "version_run": kept.version_run,
                    "first_caption_at": _iso(kept.first_caption_at),
                    "sent": sorted(kept.sent),
                }
            ),
        )


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at is not None else None


def _time(value: object) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def _load(note: str | None) -> Kept:
    """The note as `Kept`; nothing (or something unreadable) is a new one."""
    try:
        found = json.loads(note) if note else {}
        version = found.get("version_run")
        return Kept(
            installed_at=_time(found.get("installed_at")),
            version_run=version if isinstance(version, str) else None,
            first_caption_at=_time(found.get("first_caption_at")),
            sent=frozenset(n for n in found.get("sent", []) if isinstance(n, str)),
        )
    except (ValueError, AttributeError, TypeError):
        return Kept()
