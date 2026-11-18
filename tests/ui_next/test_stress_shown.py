"""Stress marks over Russian (polyglotic-hq 511): its own switch in Settings
> Readings, a mark over the stressed vowel of what was said in Russian
and of a translation into Russian, from the Russian pack, once Russian is
learned. Offscreen, made-up captions and a made-up pack."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.lexicon.test_stress import RUSSIAN
from tests.ui.test_dictionaries_together import dictionaries
from tests.ui.test_dictionary_fallbacks import pack
from tests.ui_next.made_up import EN
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.lexicon.stress import MARK
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
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

RU = Language("ru")
STRESS = CaptionLook(reading_lines=("ru",))
SAID = "Молоко и руку"
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def tools_with(tmp_path: Path, learned: tuple[str, ...]) -> Iterator[LearningTools]:
    folder = dictionaries(tmp_path / "dictionaries")
    ru, ru_file = main.open_pack(pack(folder, "wiktru-en", "ru", RUSSIAN), "ru")
    data = tmp_path / "data"
    found, store = main.learner_tools(folder, True, data, {"ru": ru})
    languages = LearningLanguages.of("en", learned)
    beside = main.tools_beside(found, folder, data, languages)
    found.set_choices(LanguageChoices(), {c: LanguageChoices() for c in languages.all})
    yield found
    for each in (store, *(s for _, s in beside)):
        each.close()
    ru_file.close()


@pytest.fixture
def learner(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """English main; Russian learned, its pack here."""
    yield from tools_with(tmp_path, ("ru",))


@pytest.fixture
def looker(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """Russian's pack here, but only Chinese learned."""
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


def over(shown: CaptionWindow, kind: RowKind) -> list[str]:
    """The letters a mark is drawn over, in `kind`'s rows."""
    QApplication.processEvents()
    shown.canvas.repaint()
    return [
        row.row.text[placed.start]
        for _, laid, _ in shown.canvas.placed
        for row in laid.rows
        if row.row.kind is kind
        for placed in row.above
        if placed.text == MARK
    ]


def test_a_mark_over_each_stressed_vowel_of_what_was_said(
    learner: LearningTools,
) -> None:
    shown = window(learner, STRESS)
    for n in range(3):
        shown.view.apply(
            finished(f"r{n}", clause(SAID, "Milk and a hand"), language=RU)
        )
    shown.apply_changed(new_caption=True)
    assert over(shown, RowKind.ORIGINAL)[:2] == ["о", "у"]  # молоко́, ру́ку


def test_a_mark_over_a_translation_into_russian(learner: LearningTools) -> None:
    shown = window(learner, STRESS, translate_into=RU)
    for n in range(3):
        shown.view.apply(
            finished(f"e{n}", clause("The hand", "рука", into=RU), language=EN)
        )
    shown.apply_changed(new_caption=True)
    assert over(shown, RowKind.TRANSLATION)[:1] == ["а"]  # рука́


def test_no_marks_until_russian_is_learned(looker: LearningTools) -> None:
    assert reading_lines.reader(looker, "ru") is None


def test_its_own_switch_shares_the_scripts_choices(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    panel.russian.click()
    assert view.value.reading_lines == ("ru",)
    assert panel.reading_over.isEnabled() and not panel.respelling_over.isEnabled()


def test_the_switch_is_saved() -> None:
    stored = AppSettings.from_stored(look_settings(STRESS)).to_stored()
    assert caption_look(AppSettings.from_stored(stored)).reading_lines == ("ru",)


def test_a_mark_sits_on_its_letter_and_keeps_no_band(learner: LearningTools) -> None:
    """511's first look drew the mark in the reading line's small size over
    a band above the line: a dot, far from its vowel. It is an accent on
    the letter now, in the text's own size, and the row needs no band."""
    shown = window(learner, STRESS)
    for n in range(3):
        shown.view.apply(
            finished(f"r{n}", clause(SAID, "Milk and a hand"), language=RU)
        )
    shown.apply_changed(new_caption=True)
    over(shown, RowKind.ORIGINAL)
    rows = [
        row
        for _, laid, _ in shown.canvas.placed
        for row in laid.rows
        if row.row.kind is RowKind.ORIGINAL and row.above
    ]
    assert rows
    for row in rows:
        assert row.band == 0
        size = row.layout.font().pixelSize()
        for placed in row.above:
            assert placed.font is not None and placed.font.pixelSize() == size
            assert placed.y > 0  # inside the line, not above it
