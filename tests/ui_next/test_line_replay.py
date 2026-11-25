"""The permanent motion gate. The same streams are inputs for the Rust replay."""

import string

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.line_replay import FIXTURES, load, measure

from polyglotic_desktop.ui_next.views.cards import GLIDE_FASTEST

CASES = [*string.ascii_lowercase[:14], "motion"]


def test_shared_contract_is_input_only_and_has_a_to_n_plus_ten_moments() -> None:
    for case in CASES:
        events = load(FIXTURES / f"{case}.json")["events"]
        assert events and [e["t"] for e in events] == sorted(e["t"] for e in events)
        for event in events:
            assert set(event) >= {"t", "key", "source", "live", "clauses"}
            for clause in event["clauses"]:
                assert set(clause) == {
                    "said",
                    "words",
                    "reading",
                    "translation",
                    "links",
                }
    motion = load(FIXTURES / "motion.json")
    assert len({e["moment"] for e in motion["events"] if e.get("moment")}) == 10


@pytest.mark.parametrize("case", CASES)
def test_real_window_has_no_line_discontinuity(qapp: QApplication, case: str) -> None:
    result = measure(load(FIXTURES / f"{case}.json"), qapp)
    assert result.jump == result.vanished == result.orphaned == 0, result
    assert result.peak_speed <= GLIDE_FASTEST.value + 1e-6, result
    assert result.bursts <= int(case == "m")


@pytest.mark.parametrize("case", ["a", "b"])
def test_planted_old_step_fault_jumps_at_least_60_px(
    qapp: QApplication, case: str
) -> None:
    assert measure(load(FIXTURES / f"{case}.json"), qapp, planted_step=True).jump >= 60


@pytest.mark.xfail(
    strict=True,
    reason="Unit 4 switches caption windows to the frozen line pairs from Unit 3",
)
def test_shown_characters_keep_their_horizontal_place(qapp: QApplication) -> None:
    assert measure(load(FIXTURES / "motion.json"), qapp).x_shift == 0


@pytest.mark.xfail(
    strict=True, reason="Unit 4 preserves Unit 3's frozen breaks through a final split"
)
def test_a_final_split_keeps_shown_characters_on_their_line(qapp: QApplication) -> None:
    assert measure(load(FIXTURES / "a.json"), qapp).rewrap == 0
