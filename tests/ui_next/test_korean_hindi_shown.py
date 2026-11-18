"""Romanization above Korean and Latin letters above Hindi (polyglotic-hq
511): each its own switch in Settings > Readings, drawn over what was said
and over a translation, by rule - no dictionary, so for any learner who
turns them on. Offscreen, made-up captions."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import chinese_tools
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.panels import LookView

KO, HI, EN = Language("ko"), Language("hi"), Language("en")
LINES = CaptionLook(reading_lines=("hi", "ko"))
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def window(look: CaptionLook, **choices: object) -> CaptionWindow:
    shown = CaptionWindow(
        "Discord.exe", APP, replace(WindowChoices(), **choices),  # type: ignore[arg-type]
        SourceLabel("Discord", "#4dd0e1"), mic=MIC, areas=areas, learner=chinese_tools(),
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


def test_korean_romanized_over_what_was_said(qapp: QApplication) -> None:
    shown = window(LINES)
    for n in range(3):
        shown.view.apply(
            finished(f"k{n}", clause("한국어 국물", "Korean soup"), language=KO)
        )
    shown.apply_changed(new_caption=True)
    assert readings(shown, RowKind.ORIGINAL)[:2] == ["hangugeo", "gungmul"]


def test_hindi_over_a_translation_into_hindi(qapp: QApplication) -> None:
    shown = window(LINES, translate_into=HI)
    for n in range(3):
        shown.view.apply(
            finished(f"e{n}", clause("The room", "कमरा", into=HI), language=EN)
        )
    shown.apply_changed(new_caption=True)
    assert readings(shown, RowKind.TRANSLATION)[:1] == ["kamrā"]


def test_off_by_default_each_its_own_switch(qapp: QApplication) -> None:
    assert not CaptionLook().reading_lines
    view = LookView(CaptionLook())
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    panel.korean.click()
    panel.hindi.click()
    assert view.value.reading_lines == ("hi", "ko")
    stored = AppSettings.from_stored(look_settings(view.value)).to_stored()
    assert caption_look(AppSettings.from_stored(stored)).reading_lines == ("hi", "ko")
