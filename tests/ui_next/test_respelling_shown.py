"""A respelling above English (polyglotic-hq 511; 471's table, DECISIONS
#200: KAY-oss, TYME, uu, ee): how each English word sounds, from the
English dictionary's form readings, over what was said in English and a
translation into English, once English is learned - past what the learner
knows at first, its own choice. Offscreen, made-up captions and a
made-up dictionary."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.lexicon.sample import english_sample
from tests.ui.fakes import chinese_tools, tools_for
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import JapaneseReading, RowKind
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

EN = Language("en")
ZH = Language("zh")
RESPELLING = CaptionLook(reading_lines=("en",), japanese_reading=JapaneseReading.OFF)
SAID = "They keep running, awkward"  # ranks 35, 250, 202 (run), 2,500
SOUNDS = {"they": "DHAY", "keep": "KEEP", "running": "RUN-ing", "awkward": "AWK-werd"}
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def english_tools(known_line: int = 1000) -> LearningTools:
    """An English learner whose dictionary respells its words, knowing the
    commonest `known_line` words."""
    file = english_sample()
    file.form_readings.update(SOUNDS)
    tools = tools_for(EnglishDictionary(file), ENGLISH_FREQUENCY.id)
    tools.set_choices(LanguageChoices(links_from=known_line), {})
    return tools


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


def said_in_english(shown: CaptionWindow) -> None:
    for n in range(3):
        shown.view.apply(
            finished(f"e{n}", clause(SAID, "他们一直跑，尴尬", into=ZH), language=EN)
        )
    shown.apply_changed(new_caption=True)


def test_a_respelling_over_each_english_word(qapp: QApplication) -> None:
    shown = window(english_tools(), replace(RESPELLING, respelling_past=False))
    said_in_english(shown)
    assert readings(shown, RowKind.ORIGINAL)[:4] == list(SOUNDS.values())


def test_at_first_only_over_the_words_past_what_the_learner_knows(
    qapp: QApplication,
) -> None:
    """DECISIONS #200: "only over new words" at first - they, keep and
    running are within the 1,000 the learner knows, awkward isn't - and
    the script readings' own choice (every word) leaves it as it is."""
    assert RESPELLING.respelling_past and not RESPELLING.reading_past
    shown = window(english_tools(), RESPELLING)
    said_in_english(shown)
    assert readings(shown, RowKind.ORIGINAL)[:1] == ["AWK-werd"]
    assert "DHAY" not in readings(shown, RowKind.ORIGINAL)


def test_a_respelling_over_a_translation_into_english(qapp: QApplication) -> None:
    shown = window(english_tools(), replace(RESPELLING, respelling_past=False))
    for n in range(3):
        shown.view.apply(
            finished(
                f"z{n}", clause("他们跑", "They keep running", into=EN), language=ZH
            )
        )
    shown.apply_changed(new_caption=True)
    assert readings(shown, RowKind.TRANSLATION)[:3] == ["DHAY", "KEEP", "RUN-ing"]


def test_hyphens_and_curly_apostrophes() -> None:
    file = english_sample()
    file.form_readings.update({"well": "WEL", "known": "NOHN", "don't": "DOHNT"})
    english = EnglishDictionary(file)
    text = "Well-known, don’t"
    found = [(text[r.start : r.end], r.text) for r in english.readings(text)]
    assert found == [("Well", "WEL"), ("known", "NOHN"), ("don’t", "DOHNT")]


def test_no_line_until_english_is_learned(qapp: QApplication) -> None:
    """As pinyin needs Chinese learned: a Chinese learner's English rows
    have none."""
    assert reading_lines.reader(chinese_tools(), "en") is None


def test_its_own_switch_and_its_own_choice_of_words(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    assert not panel.respelling_over.isEnabled()
    assert panel.reading_size.isEnabled() and panel.reading_over.isEnabled()
    panel.english.click()
    assert view.value.reading_lines == ("en",)
    assert panel.respelling_over.isEnabled() and panel.reading_over.isEnabled()
    panel.japanese.choose(JapaneseReading.OFF)
    # the scripts' "Readings over" isn't English's
    assert panel.respelling_over.isEnabled() and not panel.reading_over.isEnabled()
    assert panel.reading_size.isEnabled()
    panel.respelling_over.set_value(False)
    panel.respelling_over.changed.emit(False)
    assert view.value.respelling_past is False


def test_the_switch_and_its_choice_are_saved() -> None:
    look = replace(RESPELLING, respelling_past=False)
    stored = AppSettings.from_stored(look_settings(look)).to_stored()
    again = caption_look(AppSettings.from_stored(stored))
    assert again.reading_lines == ("en",) and again.respelling_past is False
    assert caption_look(AppSettings()).respelling_past is True
