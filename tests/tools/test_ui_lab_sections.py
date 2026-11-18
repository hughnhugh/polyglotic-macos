"""Settings' section switch in the UI lab (polyglotic-hq 381): a section's
first show is timed as its own action, held to a first show's budget, and
`section_switch` - held to a warm switch's 8 ms - times only switches to a
section already shown (twice round the sections). Timed together, 5 of
its 12 samples were first shows (9-45 ms), and its median was in effect
the slowest warm switches'."""

import itertools
from collections.abc import Callable
from pathlib import Path

import pytest
from tools.ui_lab import lab, pages

from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from tools import busy_pc


@pytest.mark.parametrize(
    "state_name", ["ui_next.w4_settings", "ui_next.w4_settings_lab"]
)
def test_a_sections_first_show_is_timed_apart_from_its_warm_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_name: str
) -> None:
    timing: list[str] = []  # the action being timed, if any
    switched: list[tuple[str, str, bool]] = []  # (action, section, shown before)
    seen: set[str] = set()
    show_section = SettingsPage.show_section
    time = lab.Lab.time

    def recorded_show(page: SettingsPage, key: str) -> None:
        switched.append((timing[-1] if timing else "", key, key in seen))
        seen.add(key)
        show_section(page, key)

    def recorded_time(
        lab_: lab.Lab,
        action: str,
        do: Callable[[], object],
        repeat: int = 1,
        budget: budgets.Budget | None = None,
    ) -> list[float]:
        timing.append(action)
        try:
            return time(lab_, action, do, repeat, budget)
        finally:
            timing.pop()

    monkeypatch.setattr(SettingsPage, "show_section", recorded_show)
    monkeypatch.setattr(lab.Lab, "time", recorded_time)
    # one try: a slow PC's first try over budget runs the state again, its
    # sections shown already (polyglotic-hq 420: GitHub's Mac, run 43827502097)
    monkeypatch.setattr(busy_pc, "MOST_TRIES", 1)
    state = next(s for s in pages.STATES if s.name == state_name)
    (result,) = lab.run([state], tmp_path)

    first_shows = [
        (key, before) for a, key, before in switched if a == "section_first_show"
    ]
    warm = [(key, before) for a, key, before in switched if a == "section_switch"]
    assert [key for key, _ in first_shows] != [] and not any(b for _, b in first_shows)
    assert {key for key, _ in first_shows} | {switched[0][1]} == set(SECTIONS)
    assert len(warm) == 2 * len(SECTIONS) and all(before for _, before in warm)
    timed = [key for a, key, _ in switched if a]
    assert all(a != b for a, b in itertools.pairwise(timed))  # each a switch
    assert result.actions["section_first_show"].budget == budgets.PAGE_SWITCH_COLD
    assert len(result.actions["section_first_show"].samples) == len(SECTIONS) - 1
    assert result.actions["section_switch"].budget == budgets.PAGE_SWITCH_WARM
    assert len(result.actions["section_switch"].samples) == 2 * len(SECTIONS)
    section = state_name.removeprefix("ui_next.w4_settings").removeprefix("_") or "look"
    assert switched[-1][1] == section  # photographed on its own section
