"""Jyutping above Cantonese (polyglotic-hq 450, decision 0160; the user,
2026-11-17: "a script assistance similar level to english phonology / zhu
yin / pinyin"): its own switch in Settings > Look's Readings, drawn over
what was said in Cantonese and over a translation into Cantonese, from the
Cantonese pack, once Cantonese is learned - with pinyin's size, words and
colour. Offscreen, made-up captions and a made-up pack."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.test_cantonese_cards import tools_with
from tests.ui_next.made_up import EN
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import ReadingSystem, RowKind
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.panels import LookView

YUE = Language("yue")
JYUTPING = CaptionLook(reading_lines=("yue",))
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


@pytest.fixture
def learner(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """English main; Chinese and Cantonese learned, Cantonese's pack here."""
    yield from tools_with(tmp_path, ("zh", "yue"))


@pytest.fixture
def looker(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """Cantonese's pack here, but only Chinese learned."""
    yield from tools_with(tmp_path, ("zh",))


def window(tools: LearningTools, look: CaptionLook, **choices: object) -> CaptionWindow:
    shown = CaptionWindow(
        "Discord.exe", APP, replace(WindowChoices(), **choices),  # type: ignore[arg-type]
        SourceLabel("Discord", "#4dd0e1"), mic=MIC, areas=areas, learner=tools,
    )  # fmt: skip
    MADE.append(shown)
    shown.set_look(look)
    shown.show()
    shown.resize(900, 460)
    return shown


def readings(shown: CaptionWindow, kind: RowKind) -> list[str]:
    QApplication.processEvents()
    shown.canvas.repaint()
    return [
        placed.text
        for _, laid, _ in shown.canvas.placed
        for row in laid.rows
        if row.row.kind is kind
        for placed in row.above
    ]


def said_in_cantonese(shown: CaptionWindow) -> None:
    for n in range(3):
        shown.view.apply(
            finished(f"y{n}", clause("佢哋而家係", "They are now"), language=YUE)
        )
    shown.apply_changed(new_caption=True)


def test_jyutping_over_what_was_said_in_cantonese(learner: LearningTools) -> None:
    shown = window(learner, JYUTPING)
    said_in_cantonese(shown)
    found = readings(shown, RowKind.ORIGINAL)
    # a syllable a character, by the pack's words, tones raised
    assert found[:5] == ["keoi⁵", "dei⁶", "ji⁴", "gaa¹", "hai⁶"], found


def test_zhuyin_is_chinese_only(learner: LearningTools) -> None:
    """Zhuyin is how Chinese is read in Taiwan: Cantonese stays Jyutping."""
    shown = window(learner, replace(JYUTPING, reading_system=ReadingSystem.ZHUYIN))
    said_in_cantonese(shown)
    assert readings(shown, RowKind.ORIGINAL)[:2] == ["keoi⁵", "dei⁶"]


def test_jyutping_over_a_translation_into_cantonese(learner: LearningTools) -> None:
    shown = window(learner, JYUTPING, translate_into=YUE)
    for n in range(3):
        shown.view.apply(
            finished(f"e{n}", clause("They are", "佢哋係", into=YUE), language=EN)
        )
    shown.apply_changed(new_caption=True)
    assert readings(shown, RowKind.TRANSLATION)[:3] == ["keoi⁵", "dei⁶", "hai⁶"]


def test_no_line_until_cantonese_is_learned(looker: LearningTools) -> None:
    """As pinyin needs Chinese learned: Cantonese's pack alone (a lookup
    only) reads nothing, and keeps no room for a line."""
    assert reading_lines.reader(looker, "yue") is None
    shown = window(looker, JYUTPING)
    said_in_cantonese(shown)
    assert readings(shown, RowKind.ORIGINAL) == []


def test_each_language_has_its_own_switch_and_the_rest_are_shared(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    assert not panel.reading_size.isEnabled()
    panel.cantonese.click()
    assert view.value.reading_lines == ("yue",)
    # its size, words and colour are pinyin's; pinyin's or zhuyin isn't its
    assert panel.reading_size.isEnabled() and panel.reading_colour.isEnabled()
    assert not panel.reading_system.isEnabled()
    panel.chinese.click()
    assert view.value.reading_lines == ("yue", "zh")
    assert panel.reading_system.isEnabled()


def test_the_switch_is_saved() -> None:
    stored = AppSettings.from_stored(look_settings(JYUTPING)).to_stored()
    assert caption_look(AppSettings.from_stored(stored)).reading_lines == ("yue",)
