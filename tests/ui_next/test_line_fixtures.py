"""Unit 0 caption-line fixtures and revision properties (projects 827/832)."""

import json
import random
from pathlib import Path

import pytest

from polyglotic_desktop.core.listening.caption_model import CaptionModel, caption_model
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.ui.recorded_captions import clause, live
from polyglotic_desktop.ui_next.views.flow import Flow, Flowed, FlowOptions

FIXTURES = Path(__file__).parents[1] / "fixtures" / "lines"
PAIRED = FlowOptions(share=True, split=True)
EN = Language("en")


def composer_fixtures(directory: Path) -> list[Path]:
    """Find Unit 3 fixtures without consuming Unit 0's event fixtures."""
    found: list[Path] = []
    for path in sorted(directory.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if "window" in fixture and "events" in fixture:
            continue
        if "width" not in fixture or "steps" not in fixture:
            raise ValueError(f"unrecognised caption-line fixture schema: {path.name}")
        if not all("expected_pairs" in step for step in fixture["steps"]):
            raise ValueError(f"composer fixture lacks expected pairs: {path.name}")
        found.append(path)
    return found


class UnitPitch:
    """One unit of width per character, including the real ellipsis."""

    ascent, below = 1.0, 0.0

    def font(self, side: RowKind, language: Language | None, text: str) -> "UnitPitch":
        return self

    def width(self, text: str) -> float:
        return float(len(text))


def model(original: str, translation: str) -> list[CaptionModel]:
    history = CaptionHistory()
    history.apply(live("fixture", clause(original, translation)))
    return [caption_model(history.captions[0], EN)]


def pairs(captions: list[CaptionModel], flowed: Flowed) -> list[list[str]]:
    found: list[list[str]] = []
    for pair in sorted({line.pair for line in flowed.lines}):
        pair_text: list[str] = []
        for side in (RowKind.ORIGINAL, RowKind.TRANSLATION):
            lines = [
                line for line in flowed.lines if line.pair == pair and line.side is side
            ]
            text = "".join(
                captions[run.caption].text(run.words)
                for line in lines
                for run in line.runs
            ).strip()
            if lines and lines[-1].joins:
                text += "…"
            pair_text.append(text)
        found.append(pair_text)
    return found


@pytest.mark.parametrize("path", composer_fixtures(FIXTURES), ids=lambda p: p.stem)
def test_each_revision_matches_its_expected_pairs(path: Path) -> None:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    flow = Flow(UnitPitch())
    frozen: tuple[tuple[int, int], ...] = ()
    for step in fixture["steps"]:
        captions = model(step["original"], step["translation"])
        composed = flow.compose(captions, fixture["width"], PAIRED, frozen=frozen)
        assert pairs(captions, composed) == step["expected_pairs"]
        frozen = composed.frozen


def test_random_live_revisions_preserve_text_breaks_and_measure_cache() -> None:
    """Four properties: coverage, order, frozen prefix, and linear measuring."""
    randomizer = random.Random(832)
    flow = Flow(UnitPitch())
    frozen: tuple[tuple[int, int], ...] = ()
    words = ["one", "two", "three", "four", "five", "six"]
    said: list[str] = []
    previous_closed: list[list[str]] = []
    for _ in range(80):
        said.append(randomizer.choice(words))
        # A recognizer may correct the still-open last unit; closed text stays put.
        changed = [*said[:-1], said[-1] + randomizer.choice(("", "s"))]
        original = " ".join(changed)
        translation = " ".join(f"fr-{word}" for word in changed)
        captions = model(original, translation)
        composed = flow.compose(captions, 16, PAIRED, frozen=frozen)

        for side, expected in (
            (RowKind.ORIGINAL, original),
            (RowKind.TRANSLATION, translation),
        ):
            shown = "".join(
                captions[run.caption].text(run.words)
                for line in composed.lines
                if line.side is side
                for run in line.runs
            )
            assert shown.replace(" ", "") == expected.replace(" ", "")
        assert all(line.end <= 16.5 for line in composed.lines)
        now = pairs(captions, composed)
        matching = min(len(previous_closed), len(composed.frozen))
        assert now[:matching] == previous_closed[:matching]
        previous_closed, frozen = now[: len(composed.frozen)], composed.frozen

    # Two clause sides per distinct revision: no quadratic remeasurement.
    assert flow.measured <= 160


def test_composer_fixture_discovery_coexists_with_unit_zero(tmp_path: Path) -> None:
    unit_zero = tmp_path / "a.json"
    unit_zero.write_text('{"window": {"width": 20}, "events": []}', encoding="utf-8")
    composer = tmp_path / "revision.json"
    composer.write_text(
        '{"width": 20, "steps": [{"expected_pairs": []}]}', encoding="utf-8"
    )

    assert composer_fixtures(tmp_path) == [composer]
