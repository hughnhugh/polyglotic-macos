"""Per app vs whole system, what the learner did, and the install's milestones (polyglotic-hq project 134).

The session's summary says how long it captioned apps on their own or
everything the PC plays, at each number of apps, and what the learner did
- numbers and yes/no only; the install's milestones wait for consent and
go once; with usage statistics off nothing behavioural is kept.
"""

import itertools
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection import listening
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.exchange import USAGE, DataExchange
from polyglotic_desktop.connection.milestones import Milestones
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import (
    Capture,
    CaptureMode,
    SourceId,
    capture_of,
)
from polyglotic_desktop.core.listening.summary import SessionAction, SessionSummary
from polyglotic_desktop.core.releases import milestones
from polyglotic_desktop.core.shared import LearningEvent
from polyglotic_desktop.ports.capture import SourceCategory

APPS_1 = Capture(CaptureMode.APPS, 1, my_speech=False)
APPS_3 = Capture(CaptureMode.APPS, 3, my_speech=True)
EVERYTHING = Capture(CaptureMode.WHOLE_SYSTEM, 0, my_speech=False)
NOTHING = Capture(CaptureMode.NONE, 0, my_speech=False)
AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)


def test_time_in_each_mode_and_at_each_number_of_apps() -> None:
    summary = SessionSummary(None, capture=APPS_1, started=0.0)
    summary.captured(APPS_3, at=60.0)  # two more apps, and my speech
    summary.captured(EVERYTHING, at=90.0)  # a switch
    summary.captured(APPS_1, at=150.0)  # and back
    props = listening.session_ended(summary.ended(170.0))
    assert props["capture_mode"] == "apps"  # 110s of apps, 60s of everything
    assert (props["apps_seconds"], props["whole_system_seconds"]) == (110.0, 60.0)
    assert props["mode_switches"] == 2
    assert props["apps_max"] == 3
    assert [props[f"apps_{n}_seconds"] for n in range(4)] == [60.0, 80.0, 0.0, 30.0]
    assert props["my_speech_seconds"] == 30.0


def test_an_app_and_everything_else_is_a_mode_of_its_own() -> None:
    """polyglotic-hq DECISIONS.md #59 (project 139): one app beside
    everything else the PC plays is `apps_plus_rest` - its time apart from
    apps on their own and everything the PC plays, at 1 app."""
    rest = capture_of(True, False, 1, False, everything_else=True)
    assert rest == Capture(CaptureMode.APPS_PLUS_REST, 1, my_speech=False)
    assert capture_of(False, False, 0, False, everything_else=True).mode is (
        CaptureMode.NONE
    )
    summary = SessionSummary(None, capture=APPS_1, started=0.0)
    summary.captured(rest, at=20.0)  # everything else turned on: a switch
    props = listening.session_ended(summary.ended(100.0))
    assert props["capture_mode"] == "apps_plus_rest"
    assert props["apps_plus_rest_seconds"] == 80.0 and props["apps_seconds"] == 20.0
    assert props["whole_system_seconds"] == 0.0 and props["mode_switches"] == 1
    assert props["apps_1_seconds"] == 100.0
    selected = listening.source_selected(rest)
    assert selected == {"capture_mode": "apps_plus_rest", "apps": 1, "my_speech": False}


def test_choosing_for_the_first_time_is_not_a_switch() -> None:
    summary = SessionSummary(None, capture=NOTHING, started=0.0)
    summary.captured(EVERYTHING, at=5.0)
    ended = summary.ended(65.0)
    assert ended.mode_switches == 0 and ended.capture_mode == "whole_system"
    only_nothing = SessionSummary(None, capture=NOTHING, started=0.0).ended(9.0)
    assert only_nothing.capture_mode == "none"
    assert only_nothing.apps_0_seconds == 9.0


def test_what_was_captured_is_left_out_when_never_told() -> None:
    props = listening.session_ended(SessionSummary(None).ended(10.0))
    assert "capture_mode" not in props and "apps_0_seconds" not in props
    late = SessionSummary(None)
    late.captured(APPS_1, at=4.0)  # known from here on only
    assert late.ended(10.0).apps_1_seconds == 6.0


def test_what_the_learner_did_is_counted_never_described() -> None:
    summary = SessionSummary(None, capture=APPS_1, started=0.0)
    for action in (
        SessionAction.TRANSCRIPT_OPENED,
        SessionAction.TRANSCRIPT_OPENED,
        SessionAction.LINE_FLAGGED,
        SessionAction.JOINED_WINDOW,
        SessionAction.JOINED_WINDOW,
    ):
        summary.did(action)
    props = listening.session_ended(summary.ended(1.0))
    assert props["transcripts_opened"] == 2 and props["lines_flagged"] == 1
    assert props["joined_window"] is True and props["original_only"] is False
    for value in props.values():  # counts, yes/no and the plan's fixed lists
        assert isinstance(value, int | float | bool | str | dict)
        assert not isinstance(value, str) or value.replace("_", "").isalnum()


def test_the_capture_mode_comes_from_the_plan_of_sources() -> None:
    assert capture_of(False, False, 0, mic=True) == Capture(CaptureMode.NONE, 0, True)
    assert capture_of(True, False, 0, mic=False).mode is CaptureMode.APPS  # none open
    assert capture_of(True, True, 0, mic=False) == EVERYTHING
    assert capture_of(True, False, 2, mic=False) == Capture(CaptureMode.APPS, 2, False)


def test_source_selected_names_a_category_never_an_app() -> None:
    props = listening.source_selected(APPS_3, SourceCategory.CALL)
    assert props == {
        "capture_mode": "apps",
        "apps": 3,
        "my_speech": True,
        "source_category": "call",
    }
    assert "source_category" not in listening.source_selected(
        EVERYTHING, SourceCategory.SYSTEM
    )


def test_original_only_is_a_source_without_a_translation() -> None:
    zh = Language("zh")
    assert not ListeningSettings(targets=(zh,)).original_only
    assert ListeningSettings(targets=()).original_only
    own = ListeningSettings(targets=(zh,), source_targets={SourceId("app-1"): ()})
    assert own.original_only


# --- the install's milestones ---------------------------------------------------------


class Heard:
    def learning_arrived(self, events: Sequence[LearningEvent]) -> None:
        pass

    def learning_deleted(self) -> None:
        pass


class Rig:
    def __init__(self) -> None:
        self.outbox = SqliteOutbox(":memory:")
        ids = (f"00000000-0000-4000-8000-{n:012d}" for n in itertools.count(1))
        self.now = AT
        self.exchange = DataExchange(
            self.outbox,
            self.outbox,
            Heard(),
            "cedict",
            new_id=lambda: next(ids),
            clock=lambda: self.now,
        )
        self.app = AppInfo("0.5.0", "windows-11", "win-x64-alpha")

    def milestones(self, version: str = "0.5.0") -> Milestones:
        app = AppInfo(version, self.app.os, self.app.channel)
        return Milestones(self.outbox, self.exchange, app, clock=lambda: self.now)

    def usage(self) -> list[str]:
        return [w.body for w in self.outbox.waiting() if w.kind == USAGE]


def test_the_install_waits_for_consent_and_goes_once() -> None:
    rig = Rig()
    first = rig.milestones()
    first.started(fresh=True)  # before the consent screen
    assert rig.usage() == []
    rig.now = AT + timedelta(minutes=2)
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    first.send_due()
    (installed,) = rig.usage()
    assert '"name":"app_installed"' in installed
    assert '"at":"2026-11-07T09:00:00.000Z"' in installed  # when it was installed
    assert '"os_version":"windows-11"' in installed
    rig.now = AT + timedelta(minutes=5)
    first.caption_shown()
    first.caption_shown()  # only the first
    assert sum('"first_caption_shown"' in u for u in rig.usage()) == 1
    assert '"seconds_since_install":300.0' in rig.usage()[-1]
    again = rig.milestones()  # the next run
    again.started(fresh=False)
    assert len(rig.usage()) == 2


def test_with_usage_statistics_off_no_milestone_is_kept() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=False, crashes=True, exposures=True)
    run = rig.milestones()
    run.started(fresh=True)
    run.caption_shown()
    assert rig.usage() == []
    rig.exchange.choose_consent(usage=True, crashes=True, exposures=True)
    run.send_due()  # said yes later: the install, dated when it was
    assert len(rig.usage()) == 2


def test_an_update_is_a_milestone_and_an_old_install_never_guesses() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.milestones("0.4.0").started(fresh=False)  # installed before this existed
    assert rig.usage() == []
    rig.milestones("0.5.0").started(fresh=False)
    (updated,) = rig.usage()
    assert '"from_version":"0.4.0"' in updated and '"to_version":"0.5.0"' in updated


def test_an_unreadable_note_is_an_old_install() -> None:
    rig = Rig()
    rig.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    rig.outbox.save_note("milestones", "[not, json")
    rig.milestones().started(fresh=False)
    assert rig.usage() == []  # nothing guessed
    note = rig.outbox.note("milestones")
    assert note is not None and '"version_run": "0.5.0"' in note
    assert milestones.due(milestones.Kept()) == []
