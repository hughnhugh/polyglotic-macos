"""Telling the learner their dictionary is out (polyglotic-hq 199): one
notice on Home's banner - after what's happening now, in 176's
one-message order - and a line in Help's check, both in the lookup card's
words, from the start or from when a query finds the file damaged.
Made-up apps, the sample dictionary, offscreen."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore, chinese_tools

from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.main import Hub, Panels
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.caption_window import notice_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.lookup_card import dictionary_out
from polyglotic_desktop.ui_next.views.caption_window import Notice
from polyglotic_desktop.ui_next.views.placement import Rect

WHAT, FIX = dictionary_out(DictionaryProblem.DAMAGED, chinese=True)
BANNER = f"{WHAT}. {FIX}"


class Problem:
    """The learner's dictionary file's problem, as the tests set it."""

    def __init__(self, problem: DictionaryProblem | None = None) -> None:
        self.problem = problem

    def __call__(self) -> DictionaryProblem | None:
        return self.problem


def built(qapp: QApplication, problem: Problem) -> tuple[Hub, LearningTools]:
    tools = chinese_tools(problem=problem)  # as `main` hands the file's over
    desktop = DesktopApp(MemorySettingsStore(), tools, FakeAppList())
    windows = CaptionWindows(None, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    panels = Panels(desktop.settings, windows)
    assert desktop.apps is not None
    hub = Hub(desktop, windows, panels, desktop.apps, True)
    return hub, tools


@pytest.fixture
def problem() -> Problem:
    return Problem()


@pytest.fixture
def hub(qapp: QApplication, problem: Problem) -> Iterator[Hub]:
    found, _ = built(qapp, problem)
    yield found
    found.close()
    found.windows.close()
    found.desktop.close()


def banner(hub: Hub) -> str | None:
    notice = hub.home.state.notice
    return notice.text() if not notice.isHidden() else None


def test_out_from_the_start_home_says_so_and_how_to_fix_it(
    qapp: QApplication,
) -> None:
    hub, _ = built(qapp, Problem(DictionaryProblem.DAMAGED))
    assert banner(hub) == BANNER
    hub.close()
    hub.windows.close()
    hub.desktop.close()


def test_whole_no_notice(hub: Hub) -> None:
    assert banner(hub) is None


def test_out_later_home_says_so_once_its_found(
    qapp: QApplication, hub: Hub, problem: Problem
) -> None:
    tools = hub.desktop.tools
    assert tools is not None
    problem.problem = DictionaryProblem.DAMAGED
    tools.dictionary_out.emit()  # from the thread whose query failed: queued
    qapp.processEvents()
    assert banner(hub) == BANNER


def test_it_comes_after_whats_happening_now(
    qapp: QApplication, problem: Problem
) -> None:
    """176's one-message order: captions failing, then a brief notice,
    then today's minutes used, then an unstable connection (165), then the
    dictionary - lookups only, and it stays until it's repaired."""
    problem.problem = DictionaryProblem.MISSING
    hub, _ = built(qapp, problem)
    state = hub.home.state
    missing = dictionary_out(DictionaryProblem.MISSING, chinese=True)
    assert banner(hub) == f"{missing[0]}. {missing[1]}"
    state.set_failing(True)
    assert banner(hub) == notice_text(Notice.FAILING, None)
    state.set_failing(False)
    state.set_notice("Settings were reset")
    assert banner(hub) == "Settings were reset"
    state.set_notice(None)
    state.set_minutes(60, 0)
    assert banner(hub) == notice_text(Notice.MINUTES_USED, None)
    state.set_minutes(10, 50)
    state.set_unstable(True)
    assert banner(hub) == notice_text(Notice.UNSTABLE, None)
    state.set_unstable(False)
    assert banner(hub) == f"{missing[0]}. {missing[1]}"
    hub.close()
    hub.windows.close()
    hub.desktop.close()


def test_helps_check_says_whats_wrong_and_reports_its_kind(
    hub: Hub, problem: Problem
) -> None:
    help_page = hub.help
    help_page.refresh()
    assert help_page.dictionary.isHidden()
    problem.problem = DictionaryProblem.DAMAGED
    reported: list[str] = []
    help_page.report_wanted.connect(reported.append)

    help_page.refresh()

    assert not help_page.dictionary.isHidden()
    assert help_page.dictionary.text().endswith(WHAT)
    assert help_page.dictionary_fix.text() == FIX
    help_page._report()
    assert reported[-1].endswith("\ndictionary: damaged")
