"""Capturing apps one by one where Windows doesn't promise it (polyglotic-hq
285, decision 0076): tried on Windows 10 from version 2004 (build 19041),
given up on this PC if Windows refuses or gives silence while the app
plainly plays - said once, remembered for this Windows update and this
version of the app, tried again after an update of either or from Home's
"Try apps again". Windows 11 (and the documented build 20348) as before.

Windows is a stand-in here: its support (yes, try, no), the trial's outcome
and the captures. Nothing here ran on a real Windows 10."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui.test_main_wiring import FakeCapture, FakePipeline

from polyglotic_desktop.main import (
    AppsOneByOne,
    Sources,
    app_capture_line,
    apps_one_by_one,
    fell_back_text,
)
from polyglotic_desktop.ports.capture import AppCaptureSupport, TrialOutcome
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui.theme import SOURCE_COLORS
from polyglotic_desktop.ui_next import home as home_module
from polyglotic_desktop.ui_next.home import PickerCard
from polyglotic_desktop.ui_next.os_words import on_linux, pc_mac_or_linux, pc_or_mac
from polyglotic_desktop.ui_next.views.home import (
    AppRow,
    AppStatus,
    Picker,
    PickerView,
)

YES, TRY, NO = AppCaptureSupport.YES, AppCaptureSupport.TRY, AppCaptureSupport.NO
HERE = {"windows": "19045.5131", "app": "0.5.0"}
REFUSED = TrialOutcome(False, "refused 0x88890008")


class StandInTrial:
    """Stands in for Windows' `Trial`: the captures' first outcome stands."""

    def __init__(self) -> None:
        self.outcome: TrialOutcome | None = None

    def tell(self, outcome: TrialOutcome) -> None:
        if self.outcome is None:
            self.outcome = outcome


class Trials:
    """Each trial made, in order."""

    def __init__(self) -> None:
        self.made: list[StandInTrial] = []

    def __call__(self) -> StandInTrial:
        self.made.append(StandInTrial())
        return self.made[-1]


def made(
    support: AppCaptureSupport,
    stored: dict[str, object] | None = None,
    build: str = HERE["windows"],
    app: str = HERE["app"],
) -> tuple[AppsOneByOne, Settings, Trials, MemorySettingsStore]:
    store = MemorySettingsStore(stored)
    settings = Settings(store)
    trials = Trials()
    return AppsOneByOne(support, settings, build, app, trials), settings, trials, store


# -- the rule --------------------------------------------------------------------


def test_promised_tried_or_not_by_windows_support() -> None:
    assert apps_one_by_one(YES, {}, HERE)
    assert apps_one_by_one(YES, {**HERE, "why": "silent"}, HERE)  # never given up
    assert apps_one_by_one(TRY, {}, HERE)
    assert not apps_one_by_one(NO, {}, HERE)


def test_failed_here_before_is_tried_again_after_an_update_of_windows_or_the_app() -> (
    None
):
    fell_back = {**HERE, "why": "refused 0x88890008"}
    assert not apps_one_by_one(TRY, fell_back, HERE)
    assert apps_one_by_one(TRY, fell_back, {**HERE, "windows": "19045.5247"})
    assert apps_one_by_one(TRY, fell_back, {**HERE, "app": "0.5.1"})


def test_the_logs_line_is_content_free_and_says_what_happened() -> None:
    """One line for the first Windows 10 tester's PC to answer the question:
    the build, whether it was tried, whether it worked or why not."""
    build = "19045.5131"
    start = f"capturing apps one by one: Windows build {build}, "
    assert app_capture_line(YES, "26200.7171", True).endswith("promised")
    assert app_capture_line(NO, "18363.1556", False).endswith(
        "not tried (Windows before version 2004)"
    )
    assert app_capture_line(TRY, build, True) == start + "trying"
    assert app_capture_line(TRY, build, True, TrialOutcome(True)) == (
        start + "tried: it worked"
    )
    assert app_capture_line(TRY, build, True, REFUSED) == (
        start + "tried: it failed (refused 0x88890008), everything the PC plays now"
    )
    assert app_capture_line(TRY, build, False, None, {"why": "silent"}) == (
        start + "not tried: it failed here before (silent)"
    )


# -- trying it --------------------------------------------------------------------


def test_windows_11_is_as_before(qapp: QApplication) -> None:
    """Promised: on, no trial (the captures do exactly what they did), and
    nothing changes whatever happens."""
    per_app, settings, trials, _ = made(YES, build="26200.7171")
    assert per_app.on and per_app.trial is None and trials.made == []
    assert not per_app.fell_back
    per_app.check()
    per_app.try_again()
    assert per_app.on and trials.made == [] and settings.value == AppSettings()
    assert per_app.line.endswith("promised")


def test_older_windows_10_is_as_before(qapp: QApplication) -> None:
    per_app, _, trials, _ = made(NO, build="18363.1556")
    assert not per_app.on and per_app.trial is None and trials.made == []
    assert not per_app.fell_back  # nothing to try again
    per_app.try_again()
    assert not per_app.on


def test_windows_10_tries_and_keeps_apps_when_it_works(qapp: QApplication) -> None:
    per_app, settings, trials, _ = made(TRY)
    changed: list[bool] = []
    per_app.changed.connect(lambda: changed.append(per_app.on))
    assert per_app.on and per_app.trial is trials.made[0]
    assert per_app.line.endswith("trying")
    per_app.check()  # nothing shown yet: still trying
    assert per_app.on and per_app.line.endswith("trying")
    trials.made[0].tell(TrialOutcome(True))
    per_app.check()
    assert per_app.on and changed == [] and per_app.line.endswith("tried: it worked")
    assert settings.value.app_capture_fell_back == {}


def test_windows_10_falls_back_says_so_once_and_remembers_it(
    qapp: QApplication,
) -> None:
    per_app, settings, trials, store = made(TRY)
    changed: list[bool] = []
    per_app.changed.connect(lambda: changed.append(per_app.on))
    trials.made[0].tell(REFUSED)
    trials.made[0].tell(TrialOutcome(True))  # later: the first outcome stands
    per_app.check()
    per_app.check()
    assert changed == [False]  # once
    assert not per_app.on and per_app.fell_back and per_app.trial is None
    record = {**HERE, "why": "refused 0x88890008"}
    assert settings.value.app_capture_fell_back == record
    assert per_app.line.endswith(
        "tried: it failed (refused 0x88890008), everything the PC plays now"
    )

    # the next start, on this Windows update and this app: not tried again
    again, _, trials_again, _ = made(TRY, store.values)
    assert not again.on and again.fell_back and trials_again.made == []
    assert again.line.endswith("not tried: it failed here before (refused 0x88890008)")
    # after a Windows update: tried again
    updated, _, trials_updated, _ = made(TRY, store.values, build="19045.5247")
    assert updated.on and len(trials_updated.made) == 1


def test_try_apps_again_tries_afresh(qapp: QApplication) -> None:
    per_app, settings, trials, store = made(
        TRY, {"app_capture_fell_back": {**HERE, "why": "silent"}}
    )
    changed: list[bool] = []
    per_app.changed.connect(lambda: changed.append(per_app.on))
    assert not per_app.on and per_app.fell_back
    per_app.try_again()
    assert per_app.on and changed == [True] and len(trials.made) == 1
    assert per_app.trial is trials.made[0] and per_app.line.endswith("trying")
    assert settings.value.app_capture_fell_back == {}
    assert store.values["app_capture_fell_back"] == {}
    per_app.try_again()  # it's on: nothing to try again
    assert len(trials.made) == 1


def test_the_record_holds_no_apps_name_and_survives_a_restart() -> None:
    record = {**HERE, "why": "silent"}
    value = AppSettings.from_stored({"app_capture_fell_back": record})
    assert value.app_capture_fell_back == record
    assert AppSettings.from_stored({"app_capture_fell_back": "silent"}) == AppSettings()
    assert AppSettings.from_stored({"app_capture_fell_back": {"why": "x" * 200}}) == (
        AppSettings()
    )  # not what this app writes: its default
    assert fell_back_text() == pc_mac_or_linux(
        "Windows on this PC couldn't caption one app alone, so Polyglotic"
        " captions everything the PC plays. You can try apps again on Home.",
        "This Mac couldn't caption one app alone, so Polyglotic"
        " captions everything the Mac plays. You can try apps again on Home.",
        "This PC couldn't caption one app alone, so Polyglotic"
        " captions everything the PC plays. You can try apps again on Home.",
    )


def test_the_sources_move_to_everything_the_pc_plays_when_it_falls_back() -> None:
    """`main`'s handler sets the sources' `per_app` and follows the settings:
    the app's source goes, everything the PC plays comes."""
    pipeline = FakePipeline()
    sources = Sources(
        pipeline,  # type: ignore[arg-type]
        FakeAppList(),
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture("system"),
        lambda: FakeCapture("mic"),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
    )
    value = AppSettings(whole_system=False, apps=("Web Browser",))
    sources.follow(value)
    assert sources.plan is not None and not sources.plan.whole_system
    sources.per_app = False
    sources.follow(value)
    assert sources.plan.whole_system and pipeline.calls[-1].startswith("system:system:")
    sources.per_app = True  # tried again
    sources.follow(value)
    assert not sources.plan.whole_system and pipeline.calls[-1].endswith("app 20:False")


# -- Home's note ----------------------------------------------------------------------


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def __getattr__(self, name: str) -> object:
        return lambda *args: self.calls.append((name, args))


SYSTEM_ROW = AppRow("system", "This PC", "#ff6e9c", AppStatus.EVERYTHING)


@pytest.fixture
def card(qapp: QApplication) -> Iterator[tuple[PickerCard, PickerView, Commands]]:
    commands = Commands()
    view = PickerView(Picker(), commands)  # type: ignore[arg-type]
    built = PickerCard(view, SOURCE_COLORS)
    yield built, view, commands
    built.deleteLater()


def test_homes_note_says_why_apps_are_off(
    card: tuple[PickerCard, PickerView, Commands],
) -> None:
    built, view, commands = card
    note, again = built.everything_note, built.apps_again
    # apps one by one (Windows 11, or a Windows 10 where it works): on hover
    assert note.isHidden() and again.isHidden()
    assert (
        built.pick_apps.accessibleDescription() == "Only caption the apps you choose."
    )
    assert built.pick_apps.isEnabled()
    # Windows 10 before version 2004
    view.follow(Picker(captioned=(SYSTEM_ROW,), whole_system=True, per_app=False))
    assert not note.isHidden() and again.isHidden()
    assert note.text() == (
        LINUX_NOTE
        if on_linux()
        else pc_or_mac(
            "instead of apps (the only choice on this version of Windows)",
            "instead of apps (the only choice on this version of macOS)",
        )
    )
    assert not built.pick_apps.isEnabled()
    # tried here and failed: said, with "Try apps again"
    failed = Picker(captioned=(SYSTEM_ROW,), per_app=False, fell_back=True)
    view.follow(failed)
    assert not note.isHidden() and not again.isHidden()
    assert note.text() == pc_mac_or_linux(
        "instead of apps: Windows on this PC couldn't caption one app alone",
        "instead of apps: this Mac couldn't caption one app alone",
        "instead of apps: this PC couldn't caption one app alone",  # 571
    )
    again.click()
    assert commands.calls == [("try_apps_again", ())]
    view.follow(Picker())  # it works now
    assert note.isHidden() and again.isHidden()
    PickerView(Picker(), commands).try_apps_again()  # type: ignore[arg-type]
    assert commands.calls == [("try_apps_again", ())]  # not where it didn't fail


LINUX_NOTE = "instead of apps (the only choice on Linux for now)"


def test_on_linux_homes_note_names_linux_not_windows(
    card: tuple[PickerCard, PickerView, Commands], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux's first build captions everything the PC plays only (one app at
    a time is 546's slice 2): Home says so in Linux's words, not "this
    version of Windows" (550)."""
    built, view, _ = card
    monkeypatch.setattr(home_module, "on_linux", lambda: True)
    view.follow(Picker(captioned=(SYSTEM_ROW,), whole_system=True, per_app=False))
    assert built.everything_note.text() == LINUX_NOTE


def test_the_logs_line_names_no_windows_build_where_there_is_none() -> None:
    """Linux (and a Mac) has no Windows build: the line said "Windows build ,
    not tried (Windows before version 2004)" on Linux's first run (550)."""
    assert app_capture_line(NO, "", False) == (
        "capturing apps one by one: not on this OS yet"
    )
    assert app_capture_line(YES, "", True) == "capturing apps one by one: promised"
