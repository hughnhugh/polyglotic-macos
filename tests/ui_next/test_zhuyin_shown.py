"""Zhuyin as a reading choice (polyglotic-hq 395): "Readings above Chinese:
Pinyin / Zhuyin" in Settings > Look's Pinyin group, saved; drawn over what
was said in Chinese and over translations into Chinese, like pinyin.
Offscreen, made-up captions and the sample CC-CEDICT."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import EN, ZH, finished_updates
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop.core.listening.display import ReadingSystem, RowKind
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill
from polyglotic_desktop.ui_next.views.panels import LookView

ZHUYIN = CaptionLook(reading_lines=("zh",), reading_system=ReadingSystem.ZHUYIN)
MADE: list[QWidget] = []
BOPOMOFO = range(0x3105, 0x3130)


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def window(qapp: QApplication, look: CaptionLook, **choices: object) -> CaptionWindow:
    shown = CaptionWindow(
        "Discord.exe", APP, replace(WindowChoices(), **choices),  # type: ignore[arg-type]
        SourceLabel("Discord", "#4dd0e1"), mic=MIC, areas=areas,
        learner=chinese_tools(),
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


def zhuyin_only(texts: list[str]) -> bool:
    return bool(texts) and all(
        any(ord(c) in BOPOMOFO for c in text) and text.isascii() is False
        for text in texts
    )


@pytest.mark.parametrize(
    "lab",
    [CaptionLab(), CaptionLab(flow=True, fill=Fill.PAIRED, aligned=True)],
    ids=["today", "new, line by line, lined up"],
)
def test_zhuyin_over_what_was_said(qapp: QApplication, lab: CaptionLab) -> None:
    shown = window(qapp, replace(ZHUYIN, lab=lab))
    for update in finished_updates(6):
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    found = readings(shown, RowKind.ORIGINAL)
    assert zhuyin_only(found), found
    assert "ㄧㄡˊ" in found  # 游 of 游戏


def test_zhuyin_over_a_translation_into_chinese(qapp: QApplication) -> None:
    shown = window(qapp, ZHUYIN, translate_into=ZH)
    for n in range(3):
        shown.view.apply(
            finished(f"e{n}", clause("I play games", "我打游戏", into=ZH), language=EN)
        )
    shown.apply_changed(new_caption=True)
    found = readings(shown, RowKind.TRANSLATION)
    assert zhuyin_only(found), found


def test_back_to_pinyin(qapp: QApplication) -> None:
    shown = window(qapp, ZHUYIN)
    for update in finished_updates(4):
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    assert zhuyin_only(readings(shown, RowKind.ORIGINAL))
    shown.set_look(replace(ZHUYIN, reading_system=ReadingSystem.PINYIN))
    found = readings(shown, RowKind.ORIGINAL)
    assert found and not any(ord(c) in BOPOMOFO for t in found for c in t)


def test_the_choice_is_saved_and_pinyin_until_chosen() -> None:
    assert caption_look(AppSettings()).reading_system is ReadingSystem.PINYIN
    stored = AppSettings.from_stored(look_settings(ZHUYIN)).to_stored()
    assert caption_look(AppSettings.from_stored(stored)).reading_system is (
        ReadingSystem.ZHUYIN
    )
    wrong = AppSettings.from_stored({"reading_system": "cangjie"})
    assert wrong.reading_system == "pinyin"


def test_the_pinyin_group_offers_zhuyin(qapp: QApplication) -> None:
    view = LookView(CaptionLook(reading_lines=("zh",)))
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    panel.reading_system.changed.emit(ReadingSystem.ZHUYIN.value)
    assert view.value.reading_system is ReadingSystem.ZHUYIN
    view.set_reading_line("zh", False)
    assert not panel.reading_system.isEnabled()
