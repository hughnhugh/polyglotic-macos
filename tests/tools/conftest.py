"""The tools' tests. The UI lab's fonts are set up before any test draws
text (polyglotic-hq 198): Qt doesn't take Windows' fonts registered late in
a long run, after many other tests have drawn (`pytest tests/ui_next
tests/tools`), and the lab sets them up first, as it starts.

Main's timing records are each test's own (polyglotic-hq 367)."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _records_of_the_tests_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Main's timing records (decision 0136) in the test's own folder, never
    this PC's: the lab's gate, run in a test on CI's run of main, kept its
    made-up timings as main's record, and every pull request after it was
    judged against an empty one (polyglotic-hq 367, 2026-11-15). A test
    that keeps or reads a record points it at its own folder too."""
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path / "timing-records"))


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    if any("test_ui_lab" in item.nodeid for item in items):
        from tools.ui_lab import lab

        lab.application()
