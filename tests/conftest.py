"""The interface's compiled translations, built before any test runs
(they aren't committed: decision 0034); Windows' fonts for Qt in every
run (258); `windows_only` tests skipped off Windows (decision 0038); and
the budget tests' timings in pytest's summary and, in CI, on the run's
page (`tests/budget_judge.py`, polyglotic-hq project 140): every timed
action's median and longest run, so a slow moment that didn't fail is
still seen; and an English PC's languages first in the language lists,
whatever this PC's are (293). Off Windows: a machine whose Qt can't load
(no libEGL or libGL, and none can be installed) still runs every test that
needs no window, and the few tests that only hold on Windows are skipped
by name with the reason (`NOT_OFF_WINDOWS`). In a published copy of the
source, which has no `.github/`, the tests of CI's workflows are skipped.
On the user's PC, off CI, a run with a Qt test in it waits for the shared
Qt lock and 3.0 GB free, holds the lock to its end, and stops under 2.0 GB
free (`tools/qt_lock.py`, polyglotic-hq 563)."""

import os
import re
import sys
import threading
from collections.abc import Generator, Iterator
from pathlib import Path

import pytest

from tools import qt_lock

pytest_plugins = ("tests.known_flaky_plugin",)

# Windows' fonts for every test's Qt, whichever tests run (polyglotic-hq
# 258). Offscreen Qt on Windows has no fonts of its own: without this, a
# run of `tests/ui` alone drew text as boxes, and once a DesktopApp had
# added the theme's heading face, in that one Latin face, so Chinese drew
# nothing and 249's underline tests failed. A whole run had Windows' fonts
# only because collecting the UI lab's tests imports `tools.ui_lab.lab`,
# which sets the same folder. Set before any test makes the application.
WINDOWS_FONTS = Path("C:/Windows/Fonts")
if sys.platform == "win32" and WINDOWS_FONTS.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(WINDOWS_FONTS))


def _qt_loads() -> str:
    """Why Qt's windows can't load here, or "" when they can. PySide6's
    Linux wheels need the system's libEGL and libGL; a machine without them
    (and without the right to install them) can still test `core`,
    `adapters`, `connection` and the tools that draw nothing."""
    try:
        import PySide6.QtWidgets  # noqa: F401
    except ImportError as error:
        return str(error)
    return ""


QT_MISSING = _qt_loads()
NEEDS_QT = re.compile(
    r"^(?:from|import)\s+(?:PySide6|polyglotic_desktop\.(?:ui|ui_next|main|harness|perf)"
    r"|tools\.(?:ui_lab|learner_start))\b",
    re.MULTILINE,
)
"""A test file that imports Qt, the interface, or a tool that draws, at its
top (an import inside one test is that test's own: `NEEDS_QT_BY_NAME`)."""
NEEDS_QT_BY_NAME = (
    "test_layout.py::test_module_imports_and_has_a_docstring[polyglotic_desktop.ui",
    "test_layout.py::test_module_imports_and_has_a_docstring[polyglotic_desktop.main]",
    "test_start_imports.py::test_importing_main_leaves_the_connection_and_speech_libraries_for_later",
    "test_msix.py::test_the_logos_are_pngs_of_their_size",
    "test_package_build.py::test_the_icon_is_one_ico_at_windows_six_sizes",
    "test_package_build.py::test_the_installer_gives_the_app_and_its_shortcuts_one_taskbar_id",
)
"""Tests in files that otherwise need no Qt."""

NOT_OFF_WINDOWS = {
    "tests/ui_next/test_lookup_card.py::test_hover_shows_after_the_mouse_rests_and_lets_the_mouse_through": "",
    "tests/ui_next/test_lookup_card.py::test_the_hover_delay_starts_again_on_another_word": "",
    "tests/ui_next/test_lookup_card.py::test_a_click_on_a_word_pins_it_with_the_actions_above_its_row": "",
    "tests/ui_next/test_lookup_card.py::test_a_drag_across_a_phrase_within_its_row_pins_the_phrase": "",
    "tests/ui_next/test_lookup_card.py::test_esc_backspace_and_a_click_elsewhere_reach_it_without_the_focus": "",
    "tests/ui_next/test_lookup_card.py::test_its_buttons_keep_todays_tooltips": "",
    "tests/ui_next/test_lookup_card.py::test_it_closes_ten_seconds_after_the_mouse_leaves_it": "",
    "tests/ui_next/test_lookup_card.py::test_a_learning_action_repaints_only_the_captions_holding_its_entry": "",
    "tests/ui_next/test_lookup_card.py::test_its_text_is_never_under_12_px_and_faint_text_is_readable": "",
    "tests/ui_next/test_lookup_card.py::test_click_any_word_until_the_first_lookup_then_never_again": "",
    "tests/ui_next/test_lookup_card.py::test_its_own_words_are_in_the_interfaces_fonts_and_meanings_chinese_first": "",
    "tests/ui_next/test_lookup_card.py::test_the_dictionary_out_card_says_whats_wrong_and_how_to_fix_it": "",
    "tests/ui_next/test_lookup_card.py::test_a_word_in_a_language_not_learned_asks_to_learn_it_too": "",
    "tests/tools/test_ui_lab_checks.py::test_a_character_no_font_has_is_found_as_a_box": (
        "Linux's fallback fonts draw a box for every missing character"
    ),
    "tests/ui_next/test_words.py::test_an_export_that_cant_be_written_says_so_not_an_error": (
        "a read-only file is Windows' lock; Linux replaces it"
    ),
}
"""Tests that pass on CI's Linux runner (the "Checks (Linux)" job, with
`tools/linux_qt_libs.sh`) and on Windows, but failed in three other Ubuntu
24.04 containers (measured 2026-11-13, PySide6 6.12: fonts, the locale,
the user and `.git` were each ruled out; the cause isn't found). In CI
they run as any test. Elsewhere off Windows they may fail without failing
the run (`xfail`, not strict), so a copy of the source on another Linux
machine starts from a clean run. The lookup card's: there, a click or hover
sent to a caption window doesn't reach the card."""

IN_CI = bool(os.environ.get("GITHUB_ACTIONS"))
LINUX_DESKTOP = "POLYGLOTIC_LINUX_DESKTOP"
"""Set (to 1) by `.github/workflows/linux.yml` where a sound server and a
session bus run: only there do `linux_desktop` tests run (550)."""


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
"""CI's workflows. A published copy of the source leaves `.github/` out:
there, the tests that check the workflows themselves have nothing to read."""
READS_WORKFLOWS_AT_IMPORT = ("test_workflows.py", "test_release_check.py")


def pytest_report_header(config: pytest.Config) -> list[str]:
    said = []
    if QT_MISSING:
        said.append(
            f"Qt's windows can't load here ({QT_MISSING}): the interface's tests "
            "aren't collected; everything else runs"
        )
    if not WORKFLOWS.is_dir():
        said.append(
            "no .github/workflows in this copy: the tests of CI's workflows are skipped"
        )
    return said


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    """A test that reads a CI workflow is skipped in a copy without them,
    not failed: the file it asks for was left out on purpose."""
    try:
        return (yield)
    except FileNotFoundError as error:
        if not WORKFLOWS.is_dir() and ".github" in str(error):
            pytest.skip("this copy has no .github/workflows")
        raise


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Without Qt, leave out the interface's folders and any test file that
    imports Qt or the interface, instead of an error per file."""
    if not WORKFLOWS.is_dir() and collection_path.name in READS_WORKFLOWS_AT_IMPORT:
        return True
    if not QT_MISSING:
        return None
    if collection_path.is_dir():
        interface = collection_path.name in ("ui", "ui_next")
        return (interface and collection_path.parent.name == "tests") or None
    a_test = collection_path.suffix == ".py" and collection_path.name.startswith(
        "test_"
    )
    if a_test and NEEDS_QT.search(collection_path.read_text(encoding="utf-8")):
        return True
    return None


@pytest.fixture
def fill_the_width_on() -> Iterator[None]:
    """Fill the width's flag on for one test (polyglotic-hq 555: off in the
    app, its code kept): the tests of the pour itself."""
    from polyglotic_desktop.core.releases import flags

    flags.set_value(flags.FILL_THE_WIDTH, True)
    yield
    flags.set_value(flags.FILL_THE_WIDTH, None)


@pytest.fixture(autouse=True)
def _an_english_pc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The learner's own languages as an English Windows has them, whatever
    the machine's are (polyglotic-hq 293): the language lists put them
    first, and no test may follow the PC it runs on."""
    from polyglotic_desktop.ui_next import languages

    monkeypatch.setattr(languages, "own_languages", lambda: ["en"])


@pytest.fixture(autouse=True)
def _at_the_design_sizes() -> Iterator[None]:
    """Each test begins, and leaves the interface, at its design sizes: a
    text size factor of 1.0 - Windows' 100 % and the app's Smaller, which
    is 1.0 since decision 0244 made Normal, the default, 1.3 (polyglotic-hq
    524). The sizes tests name are the interface's own (13 px text, a 960 x
    680 window); a test of the default sets it (`use_app_text_size
    ("normal")`), and the UI lab runs every state at it. Only where the
    interface's style is loaded: a run without Qt never loads it."""
    _design_sizes()
    yield
    _design_sizes()


def _design_sizes() -> None:
    style = sys.modules.get("polyglotic_desktop.ui_next.style")
    if style is None:
        return
    style.use_text_scale(1.0)
    style.use_app_text_size("smaller")
    assert style.text_scale() == 1.0, "the app's Smaller isn't 1.0: change this"


@pytest.fixture(autouse=True)
def _pack_warm_ups_end() -> Iterator[None]:
    """A pack's word split reading its data on its own thread ("pack warm",
    `main.PackDelivery`) ends with the test that opened it: it runs in short
    turns at the interpreter (decision 0207), which would time the next
    test's slots differently - the watchdog's tests missed a slow slot
    beside one (polyglotic-hq 436). `QTest.qWait` keeps the interpreter, so
    one can still be reading when a test ends; it's waited for here."""
    yield
    for thread in threading.enumerate():
        if thread.name == "pack warm":
            thread.join(30)


TESTS = Path(__file__).resolve().parent
QT_LOCK_TAKEN = pytest.StashKey[bool]()


def _needs_qt(item: pytest.Item, files: dict[Path, bool]) -> bool:
    """Whether `item` is a Qt test: in `tests/ui` or `tests/ui_next`, in a
    file that imports Qt, the interface or a tool that draws (`NEEDS_QT`),
    or one of `NEEDS_QT_BY_NAME`. `files` keeps each file's answer."""
    path = item.path
    if any(p.parent == TESTS and p.name in ("ui", "ui_next") for p in path.parents):
        return True
    if any(name in item.nodeid for name in NEEDS_QT_BY_NAME):
        return True
    if path not in files:
        text = path.read_text(encoding="utf-8") if path.suffix == ".py" else ""
        files[path] = bool(NEEDS_QT.search(text))
    return files[path]


@pytest.hookimpl(wrapper=True)
def pytest_runtestloop(session: pytest.Session) -> Generator[None, object, object]:
    """On the user's PC (off CI), a run with a Qt test in it waits for the
    shared Qt lock and 3.0 GB free before its first test, and holds the
    lock until its last (`tools/qt_lock.py`, polyglotic-hq 563): two
    whole-suite runs started together took the PC to 0.5 GB free beside
    the live server on 2026-11-20. A run of no Qt test takes nothing."""
    files: dict[Path, bool] = {}
    if (
        session.config.option.collectonly
        or not qt_lock.applies()
        or not any(_needs_qt(item, files) for item in session.items)
    ):
        return (yield)
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")

    def say(text: str) -> None:
        if reporter is not None:
            reporter.write_line(text)
        else:
            print(text, flush=True)

    what = " ".join(["pytest", *session.config.invocation_params.args])[:120]
    try:
        with qt_lock.held(what, say=say) as took:
            session.stash[QT_LOCK_TAKEN] = took
            return (yield)
    except qt_lock.GaveUp as why:
        pytest.exit(str(why), returncode=pytest.ExitCode.INTERRUPTED)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, object, object]:
    """A run holding the Qt lock stops after a test that leaves the PC
    under 2.0 GB free, as the agents' wrappers stopped theirs (the run
    ends "interrupted", saying why)."""
    result = yield
    if item.session.stash.get(QT_LOCK_TAKEN, False):
        why = qt_lock.too_little_memory()
        if why:
            item.session.shouldstop = why
    return result


def pytest_configure(config: pytest.Config) -> None:
    """Each `.qm` from its `.ts`, before a test's application installs it."""
    from tools.i18n import __main__ as i18n

    i18n.build()


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """`windows_only` tests are skipped off Windows (decision 0038): the Linux
    checks run everything else; `macos_only` tests off macOS (409); and
    `linux_desktop` tests (a sound server, a session bus: 550) everywhere
    but a Linux desktop session that says it is one (`LINUX_DESKTOP`)."""
    if not (sys.platform.startswith("linux") and os.environ.get(LINUX_DESKTOP)):
        for item in items:
            if item.get_closest_marker("linux_desktop"):
                item.add_marker(pytest.mark.skip(reason="a Linux desktop session only"))
    if sys.platform != "darwin":
        for item in items:
            if item.get_closest_marker("macos_only"):
                item.add_marker(pytest.mark.skip(reason="macOS only"))
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="Windows only")
    no_qt = pytest.mark.skip(reason="Qt's windows can't load on this machine")
    for item in items:
        test = getattr(item, "nodeid", "")
        if item.get_closest_marker("windows_only"):
            item.add_marker(skip)
        elif test.split("[")[0] in NOT_OFF_WINDOWS and not IN_CI:
            why = NOT_OFF_WINDOWS[test.split("[")[0]]
            why = why or "the card isn't reached by a sent click or hover"
            item.add_marker(
                pytest.mark.xfail(
                    reason=f"fails on some Linux machines: {why}", strict=False
                )
            )
        elif QT_MISSING and any(name in test for name in NEEDS_QT_BY_NAME):
            item.add_marker(no_qt)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    budget_judge = sys.modules.get("tests.budget_judge")  # only if a budget test ran
    # a start that is recorded, not judged, has notes alone (322)
    if budget_judge is None or not (budget_judge.JUDGED or budget_judge.NOTES):
        return
    terminalreporter.section("budget tests")
    budget_judge.keep_mains_record()  # on CI's run of main (decision 0136)
    for line in budget_judge.summary_lines():
        terminalreporter.write_line(line)
    for note in budget_judge.NOTES:  # the start's parts beside main's (314)
        terminalreporter.write_line(note)
    page = os.environ.get("GITHUB_STEP_SUMMARY")
    if page:  # in CI: the table on the run's page
        with open(page, "a", encoding="utf-8") as out:
            if budget_judge.JUDGED:
                out.write(budget_judge.summary_markdown())
            for note in budget_judge.NOTES:
                out.write(f"\n```\n{note}\n```\n")
