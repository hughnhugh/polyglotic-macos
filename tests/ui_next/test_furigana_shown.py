"""Furigana above Japanese (polyglotic-hq 511, 383's brief): its own switch
in Settings > Readings, drawn over what was said in Japanese and over a
translation into Japanese, from the Japanese pack's word split, once
Japanese is learned - with pinyin's size, words and colour; and the
one-time hint tells a Japanese learner of it. Offscreen, made-up captions
and a made-up pack (its word split is the real one, Sudachi small)."""

import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget
from tests.lexicon.sample import FakeDictionaryFile
from tests.ui.test_dictionaries_together import dictionaries
from tests.ui.test_dictionary_fallbacks import pack
from tests.ui_next.made_up import EN
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, reading_hint
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.panels import LookView

JA = Language("ja")
FURIGANA = CaptionLook(reading_lines=("ja",))
JAPANESE = FakeDictionaryFile(
    [
        EntryRecord("jmdict:1", "友達", "", "ともだち", ("friend",), 300),
        EntryRecord("jmdict:2", "飲む", "", "のむ", ("to drink",), 400),
        EntryRecord("jmdict:3", "東京", "", "とうきょう", ("Tokyo",), 200),
    ],
    {"友達": ["jmdict:1"], "飲む": ["jmdict:2"], "東京": ["jmdict:3"]},
)
"""A Japanese pack's entries, as `tools.dictionaries.packs` writes them."""
SAID = "友達と東京で飲みました"
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
    ja, ja_file = main.open_pack(pack(folder, "jmdict-en", "ja", JAPANESE), "ja")
    data = tmp_path / "data"
    found, store = main.learner_tools(folder, True, data, {"ja": ja})
    languages = LearningLanguages.of("en", learned)
    beside = main.tools_beside(found, folder, data, languages)
    found.set_choices(LanguageChoices(), {c: LanguageChoices() for c in languages.all})
    yield found
    for each in (store, *(s for _, s in beside)):
        each.close()
    ja_file.close()


@pytest.fixture
def learner(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """English main; Japanese learned, its pack here."""
    yield from tools_with(tmp_path, ("ja",))


@pytest.fixture
def looker(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """Japanese's pack here, but only Chinese learned."""
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


def said_in_japanese(shown: CaptionWindow) -> None:
    for n in range(3):
        shown.view.apply(
            finished(
                f"j{n}", clause(SAID, "I drank with a friend in Tokyo"), language=JA
            )
        )
    shown.apply_changed(new_caption=True)


def test_furigana_over_what_was_said_in_japanese(learner: LearningTools) -> None:
    shown = window(learner, FURIGANA)
    said_in_japanese(shown)
    # kana over the kanji only: 飲み's み is written, so only の over 飲
    assert readings(shown, RowKind.ORIGINAL)[:3] == ["ともだち", "とうきょう", "の"]


def test_furigana_over_a_translation_into_japanese(learner: LearningTools) -> None:
    shown = window(learner, FURIGANA, translate_into=JA)
    for n in range(3):
        shown.view.apply(
            finished(f"e{n}", clause("My friend", "友達", into=JA), language=EN)
        )
    shown.apply_changed(new_caption=True)
    assert readings(shown, RowKind.TRANSLATION)[:1] == ["ともだち"]


def test_no_line_until_japanese_is_learned(looker: LearningTools) -> None:
    """As pinyin needs Chinese learned: the pack alone reads nothing."""
    assert reading_lines.reader(looker, "ja") is None
    shown = window(looker, FURIGANA)
    said_in_japanese(shown)
    assert readings(shown, RowKind.ORIGINAL) == []


def test_furigana_has_its_own_switch_and_shares_the_rest(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    assert not panel.reading_size.isEnabled()
    panel.japanese.click()
    assert view.value.reading_lines == ("ja",)
    assert panel.reading_size.isEnabled() and panel.reading_over.isEnabled()
    assert not panel.reading_system.isEnabled()  # pinyin or zhuyin: Chinese's


def test_the_switch_is_saved() -> None:
    stored = AppSettings.from_stored(look_settings(FURIGANA)).to_stored()
    assert caption_look(AppSettings.from_stored(stored)).reading_lines == ("ja",)


def test_a_japanese_learner_is_told_of_furigana_once(learner: LearningTools) -> None:
    windows = CaptionWindows(None, MIC, areas, learner=learner)
    windows.set_captioned([("app", APP)])
    try:
        windows.stored.looked_up = True
        windows.apply(finished("a", clause(SAID, "I drank"), language=JA))
        _, text = windows.windows["app"].notices.showing(time.monotonic())
        assert text == reading_hint("ja") != reading_hint()
        assert windows.stored.reading_hinted
    finally:
        windows.close()


def test_past_what_you_know_leaves_the_known_words_plain(
    learner: LearningTools,
) -> None:
    """383's "Past what you know": with the learner's line at 250 words,
    東京 (200th) is known and goes plain; 友達 (300th) and 飲む (400th)
    keep theirs."""
    learner.set_choices(LanguageChoices(), {"ja": LanguageChoices(links_from=250)})
    shown = window(learner, replace(FURIGANA, reading_past=True))
    said_in_japanese(shown)
    assert readings(shown, RowKind.ORIGINAL)[:2] == ["ともだち", "の"]


def test_furigana_reaches_over_the_kana_after_its_kanji(qapp: QApplication) -> None:
    """511's real captions read 必 ずしも: かなら, wider than 必, pushed the
    kana away. It reaches over half the kana now, as Japanese ruby does -
    and still takes its whole room before a kanji (not kana)."""
    font = QFont()
    font.setPixelSize(28)
    over_kana = reading_lines.ruby("必ずしも", [Reading(0, 1, "かなら")], font)
    alone = reading_lines.ruby("必要", [Reading(0, 1, "かなら")], font)
    assert 0.0 <= over_kana.after[0] < alone.after[0]
