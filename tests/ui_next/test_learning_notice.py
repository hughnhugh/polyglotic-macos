"""Telling the learner their learning data was set aside at the start
(polyglotic-hq 206): one notice on Home's banner - last in 176's
one-message order, as there's nothing to do - and a line in Help's check
with where the old file is. "Report a problem" carries the kind only,
never the path. Made-up apps and data, offscreen."""

from pathlib import Path

from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore, chinese_tools

from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.main import Hub, Panels
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ports.learning import LearningDataProblem, SetAsideLearningData
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.caption_window import notice_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.home import (
    learning_set_aside_notice,
    learning_unsaved_notice,
)
from polyglotic_desktop.ui_next.lookup_card import dictionary_out
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.caption_window import Notice
from polyglotic_desktop.ui_next.views.placement import Rect

ASIDE = SetAsideLearningData(
    Path("C:/Users/someone/AppData/Roaming/Polyglotic")
    / "learning.sqlite.damaged-20261108T063000Z",
    LearningDataProblem.DAMAGED,
)


def built(
    aside: SetAsideLearningData | None,
    problem: DictionaryProblem | None = None,
) -> Hub:
    tools = chinese_tools(problem=problem)
    tools.learning_set_aside = aside  # as `main` hands the store's over
    desktop = DesktopApp(MemorySettingsStore(), tools, FakeAppList())
    windows = CaptionWindows(None, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    panels = Panels(desktop.settings, windows)
    assert desktop.apps is not None
    return Hub(desktop, windows, panels, desktop.apps, True)


def closed(hub: Hub) -> None:
    hub.close()
    hub.windows.close()
    hub.desktop.close()


def banner(hub: Hub) -> str | None:
    notice = hub.home.state.notice
    return notice.text() if not notice.isHidden() else None


def test_set_aside_at_the_start_home_says_so_and_names_the_file(
    qapp: QApplication,
) -> None:
    hub = built(ASIDE)
    text = banner(hub)
    assert text == learning_set_aside_notice(ASIDE)
    assert text is not None
    assert "learning.sqlite.damaged-20261108T063000Z" in text
    assert "someone" not in text  # its name: the folder is in Help
    assert "coming back from your account" in text
    closed(hub)


def test_whole_no_notice(qapp: QApplication) -> None:
    hub = built(None)
    assert banner(hub) is None
    closed(hub)


def test_it_comes_last(qapp: QApplication) -> None:
    """Captions failing, a brief notice, today's minutes used, an unstable
    connection and the dictionary being out all come first: each is
    happening now, or needs the learner; this needs nothing."""
    hub = built(ASIDE, DictionaryProblem.MISSING)
    state = hub.home.state
    missing = dictionary_out(DictionaryProblem.MISSING, chinese=True)
    assert banner(hub) == f"{missing[0]}. {missing[1]}"
    state.set_dictionary_out(None, True)
    assert banner(hub) == learning_set_aside_notice(ASIDE)
    state.set_unstable(True)
    assert banner(hub) == notice_text(Notice.UNSTABLE, None)
    state.set_unstable(False)
    state.set_failing(True)
    assert banner(hub) == notice_text(Notice.FAILING, None)
    state.set_failing(False)
    state.set_notice("Settings were reset")
    assert banner(hub) == "Settings were reset"
    state.set_notice(None)
    assert banner(hub) == learning_set_aside_notice(ASIDE)
    closed(hub)


def test_helps_check_says_where_the_file_is_and_reports_its_kind(
    qapp: QApplication,
) -> None:
    hub = built(ASIDE)
    help_page = hub.help
    reported: list[str] = []
    help_page.report_wanted.connect(reported.append)

    help_page.refresh()

    assert not help_page.learning.isHidden()
    assert help_page.learning.text().endswith(
        f"Your learning data on this {pc_or_mac('PC', 'Mac')} was damaged and has"
        " been set aside"
    )
    assert str(ASIDE.path) in help_page.learning_then.text()
    help_page._report()
    assert reported[-1].endswith("\nlearning data: set aside (damaged)")
    assert "someone" not in reported[-1] and "damaged-2026" not in reported[-1]
    closed(hub)


def test_whole_helps_check_has_no_line(qapp: QApplication) -> None:
    hub = built(None)
    hub.help.refresh()
    assert hub.help.learning.isHidden() and hub.help.learning_then.isHidden()
    closed(hub)


def test_found_damaged_later_home_says_restart_once_its_found(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 206 item 4: from the store's thread, once."""
    hub = built(None)
    tools = hub.desktop.tools
    assert tools is not None
    assert banner(hub) is None

    tools.learning_damaged.emit(ASIDE)
    qapp.processEvents()

    assert banner(hub) == learning_unsaved_notice()
    assert "restart Polyglotic" in learning_unsaved_notice()
    help_page = hub.help
    reported: list[str] = []
    help_page.report_wanted.connect(reported.append)
    help_page.refresh()
    assert not help_page.learning.isHidden()
    then = help_page.learning_then.text()
    assert then.startswith(
        f"Changes aren't kept on this {pc_or_mac('PC', 'Mac')} until you restart"
    )
    assert str(ASIDE.path) in then
    help_page._report()
    assert reported[-1].endswith(
        "\nlearning data: set aside (damaged), after the start"
    )
    closed(hub)


def test_found_damaged_later_but_not_set_aside_home_still_says_so(
    qapp: QApplication,
) -> None:
    """The file couldn't be renamed: nothing is saved all the same, and
    Help has no file to name."""
    hub = built(None)
    tools = hub.desktop.tools
    assert tools is not None
    tools.learning_damaged.emit(None)
    qapp.processEvents()
    assert banner(hub) == learning_unsaved_notice()
    hub.help.refresh()
    assert hub.help.learning.isHidden()
    closed(hub)


def test_deleted_on_this_pc_home_and_help_stop_naming_the_file(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Polyglotic-hq 213 (207): after "Delete learning data... also from
    this PC" the file set aside is gone, but Home's banner and Help's check
    still named it, for the rest of that run."""
    file = tmp_path / "learning.sqlite.damaged-20261108T063000+1100"
    file.write_bytes(b"made up")
    aside = SetAsideLearningData(file, LearningDataProblem.DAMAGED)
    hub = built(aside)
    tools = hub.desktop.tools
    assert tools is not None
    assert banner(hub) == learning_set_aside_notice(aside)

    file.unlink()  # as the store's delete does, on its thread
    tools.learning_deleted.emit()
    qapp.processEvents()

    assert banner(hub) is None
    hub.help.refresh()
    assert hub.help.learning.isHidden() and hub.help.learning_then.isHidden()
    closed(hub)


def test_deleted_but_kept_in_use_its_still_named(
    qapp: QApplication, tmp_path: Path
) -> None:
    """One that couldn't be deleted (in use) is still there: still named."""
    file = tmp_path / "learning.sqlite.damaged-20261108T063000+1100"
    file.write_bytes(b"made up")
    aside = SetAsideLearningData(file, LearningDataProblem.DAMAGED)
    hub = built(aside)
    tools = hub.desktop.tools
    assert tools is not None
    tools.learning_deleted.emit()
    qapp.processEvents()
    assert banner(hub) == learning_set_aside_notice(aside)
    closed(hub)


def test_found_damaged_later_then_deleted_home_still_says_restart(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Nothing is kept on this PC until a restart all the same; only the
    file's name goes."""
    file = tmp_path / "learning.sqlite.damaged-20261108T063000+1100"
    file.write_bytes(b"made up")
    hub = built(None)
    tools = hub.desktop.tools
    assert tools is not None
    tools.learning_damaged.emit(SetAsideLearningData(file, LearningDataProblem.DAMAGED))
    qapp.processEvents()
    file.unlink()
    tools.learning_deleted.emit()
    qapp.processEvents()
    assert banner(hub) == learning_unsaved_notice()
    assert tools.learning_unsaved and tools.learning_set_aside is None
    hub.help.refresh()
    assert hub.help.learning.isHidden()
    closed(hub)
