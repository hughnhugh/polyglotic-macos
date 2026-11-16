"""A drag of the look's slider (Settings > Captions, "Panel: how solid")
shows in the caption windows at once and is saved once it settles - no
save, no file read, nothing following the settings on any mouse move
(polyglotic-hq 273: in the user's log each move ran everything that
follows the settings, reading the other language's level file and
looking for the sample, and held the interface up to 410 ms)."""

from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.budget_judge import sampled, within
from tests.ui.fakes import Built, MemorySettingsStore
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop import main
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui_next.panels import LookPanel

DRAG_STEP_MS = 16
"""A mouse move a frame, as a drag sends them (60 a second)."""


class Reads:
    """What the app read from files while it ran: each other language's
    level, and whether there's a sample."""

    def __init__(self) -> None:
        self.levels: list[str] = []
        self.samples: list[str | None] = []


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> Reads:
    found = Reads()

    def sample_file(learning: str | None) -> Path | None:
        found.samples.append(learning)
        return None

    monkeypatch.setattr(main, "sample_file", sample_file)
    return found


def built_learning_two(reads: Reads) -> tuple[Built, MemorySettingsStore]:
    """The app, learning Chinese and English (Learning's page shows the
    other one's level from its file), with the sample offered on Home."""
    store = MemorySettingsStore({"learning": "zh", "also_learning": ["en"]})
    built = Built(store)
    built.hub.level_of = lambda code: reads.levels.append(code)
    built.hub.sample = lambda on: None
    built.hub.show_learning()
    reads.levels.clear()
    built.hub.follow()
    reads.samples.clear()
    return built, store


def test_a_drag_saves_once_it_settles_and_reads_no_file(
    qapp: QApplication, reads: Reads
) -> None:
    built, store = built_learning_two(reads)
    panel = LookPanel(built.panels.look)
    saves = store.saves
    for step in range(60):  # a second of dragging, a move a frame
        panel.background.setValue(20 + step)
        QTest.qWait(DRAG_STEP_MS)
        # shown in the caption windows at once
        assert built.windows.look.opacity == (20 + step) / 100
        assert store.saves == saves  # not saved on a mouse move
    assert built.panels.look_waiting
    assert (reads.levels, reads.samples) == ([], [])
    QTest.qWait(main.SETTLE_MS + 100)
    assert store.saves == saves + 1  # once, with the last value
    assert built.desktop.settings.value.opacity == 0.79
    assert not built.panels.look_waiting
    # nothing Learning's page or the sample come from changed: no file read
    assert (reads.levels, reads.samples) == ([], [])
    panel.deleteLater()
    built.close()


def test_learnings_page_still_follows_a_change_to_the_languages_learned(
    qapp: QApplication, reads: Reads
) -> None:
    built, _ = built_learning_two(reads)
    built.desktop.settings.update(opacity=0.5)
    assert reads.levels == []
    built.desktop.settings.update(also_learning=[])
    assert reads.levels  # shown again, its levels read
    built.close()


def test_another_setting_changed_mid_drag_keeps_the_dragged_look(
    qapp: QApplication, reads: Reads
) -> None:
    built, _ = built_learning_two(reads)
    panel = LookPanel(built.panels.look)
    panel.background.setValue(33)
    built.desktop.settings.update(spoken_language="ja")  # saved meanwhile
    assert panel.background.value() == 33  # not back to the saved look
    assert built.panels.look.value.opacity == 0.33
    built.panels.save_look()  # at quit, before it settles
    assert built.desktop.settings.value.opacity == 0.33
    assert built.desktop.settings.value.spoken_language == "ja"
    panel.deleteLater()
    built.close()


def test_a_step_of_a_look_drag_within_a_frame(qapp: QApplication, reads: Reads) -> None:
    """Each mouse move of the drag with three caption windows full of
    captions: within a frame (`budgets.FRAME`, 8 ms)."""
    built, _ = built_learning_two(reads)
    sources = [SourceId(f"app-{n}") for n in (1, 2, 3)]
    built.windows.set_captioned([(f"app{n}", s) for n, s in enumerate(sources)])
    for source in sources:
        for update in finished_updates(150, source=source):
            built.windows.apply(update)
    panel = LookPanel(built.panels.look)
    panel.show()
    qapp.processEvents()
    values = iter(range(10, 100))

    def step() -> None:
        panel.background.setValue(next(values))

    within(budgets.FRAME, lambda: sampled(qapp, [step] * 8))
    panel.close()
    panel.deleteLater()
    built.close()
