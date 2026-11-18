"""The quiet view's strip names what its source is talking about now
(polyglotic-hq 491, decision 0227): after the source's label, dim, the
theme's few keyest words - asked of the window's own language's learning
data for its own source when the strip shows; nothing with the quiet view
off. Offscreen, made-up captions, the sample dictionary (the naming itself
is `tests/learning/test_theme.py`'s)."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools

from polyglotic_desktop.core.learning.theme import Said
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = Rect(0, 0, 1920, 1040)
QUIET = CaptionLook(quiet=True, reading_lines=("zh",))
AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def said(form: str) -> Said:
    return Said(EntryFacts(EntryId(f"test:{form}"), None, 20000, False), form, 3, 4, AT)


@pytest.fixture
def shown(qapp: QApplication) -> Iterator[CaptionWindows]:
    tools = chinese_tools()
    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=tools)
    windows.set_look(QUIET)
    windows.set_captioned([("app", APP)])
    windows.apply(finished("c1", clause("业主说小区的物业很好。", "Owners say ...")))
    window = windows.windows["app"]
    window.setGeometry(100, 150, 900, 420)
    window.show()
    qapp.processEvents()
    yield windows
    windows.close()


def test_the_quiet_views_strip_names_what_its_source_is_talking_about(
    shown: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = shown.learner
    assert tools is not None
    asked: list[str] = []

    def theme_name(source: str) -> list[Said]:
        asked.append(source)
        return [said("业主"), said("小区"), said("物业")]

    monkeypatch.setattr(tools.vocabulary.curriculum, "theme_name", theme_name)
    window = shown.windows["app"]
    window._show_band(True)
    qapp.processEvents()
    assert asked and asked[-1] == APP
    assert window.tag.note == "业主 · 小区 · 物业"
    assert "业主 · 小区 · 物业" in window.tag.toolTip()
    window._show_band(False)


def test_nothing_is_named_with_the_quiet_view_off_or_before_enough_is_said(
    shown: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = shown.learner
    assert tools is not None
    window = shown.windows["app"]
    window._show_band(True)
    assert window.tag.note == ""  # nothing said enough yet
    window._show_band(False)
    monkeypatch.setattr(
        tools.vocabulary.curriculum, "theme_name", lambda source: [said("业主")]
    )
    shown.set_look(replace(QUIET, quiet=False))
    qapp.processEvents()
    window._show_band(True)
    assert window.tag.note == ""
    window._show_band(False)
