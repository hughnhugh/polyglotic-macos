"""Furigana above Japanese (polyglotic-hq 511, 383's brief): its own switch
in Settings > Readings, drawn over what was said in Japanese and over a
translation into Japanese, from the Japanese pack's word split, once
Japanese is learned - with pinyin's size, words and colour; and the
one-time hint tells a Japanese learner of it. Offscreen, made-up captions
and a made-up pack (its word split is the real one, Sudachi small)."""

import shutil
import time
from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QGlyphRun
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from tests.lexicon.sample import FakeDictionaryFile
from tests.ui.fakes import MemorySettingsStore
from tests.ui.test_dictionaries_together import dictionaries
from tests.ui.test_dictionary_fallbacks import pack
from tests.ui_next.made_up import EN, at_one_moment
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Step
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import JapaneseReading, RowKind
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import Panels, caption_look, look_settings
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, reading_hint
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.controls import SwitchRow
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill
from polyglotic_desktop.ui_next.views.panels import (
    JapaneseReadings,
    JapaneseReadingsView,
    LookView,
)

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
    import sudachidict_small

    folder = dictionaries(tmp_path / "dictionaries")
    installed_dictionary = (
        Path(sudachidict_small.__file__).parent / "resources" / "system.dic"
    )
    shutil.copyfile(installed_dictionary, folder / main.JAPANESE_DICTIONARY)
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


def readings_below(shown: CaptionWindow, kind: RowKind) -> list[str]:
    QApplication.processEvents()
    shown.canvas.repaint()
    return [
        placed.text
        for _, laid, _ in shown.canvas.placed
        for row in laid.rows
        if row.row.kind is kind
        for placed in row.below
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
    assert panel.reading_size.isEnabled()  # Kana is an effective reading line
    panel.japanese.changed.emit(JapaneseReading.ROMAJI.value)
    assert view.value.reading_lines == ()  # the retired flag is not rewritten
    assert view.value.japanese_reading is JapaneseReading.ROMAJI
    assert panel.reading_size.isEnabled() and panel.reading_over.isEnabled()
    assert panel.reading_colour.isEnabled()
    assert not panel.reading_system.isEnabled()  # pinyin or zhuyin: Chinese's
    panel.japanese.changed.emit(JapaneseReading.OFF.value)
    assert not panel.reading_size.isEnabled() and not panel.reading_over.isEnabled()
    assert not panel.reading_colour.isEnabled()


def test_migrated_japanese_line_does_not_keep_shared_controls_on(
    qapp: QApplication,
) -> None:
    old = AppSettings().to_stored()
    old.pop("japanese_reading")
    old["reading_lines"] = ["ja"]
    old["changed"] = ["reading_lines"]
    store = MemorySettingsStore(old)
    settings = Settings(store)
    view = LookView(
        caption_look(settings.value),
        lambda look: settings.update(**main.look_changes(settings.value, look)),
    )
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)

    def enabled() -> tuple[bool, bool, bool]:
        return (
            panel.reading_size.isEnabled(),
            panel.reading_over.isEnabled(),
            panel.reading_colour.isEnabled(),
        )

    assert view.value.reading_lines == ("ja",)
    assert panel.japanese.value() is JapaneseReading.KANA
    assert enabled() == (True, True, True)
    panel.japanese.choose(JapaneseReading.OFF)
    assert view.value.reading_lines == ("ja",)  # stale migration input is ignored
    assert enabled() == (False, False, False)
    for choice in (
        JapaneseReading.KANA,
        JapaneseReading.ROMAJI,
        JapaneseReading.BOTH,
    ):
        panel.japanese.choose(choice)
        assert enabled() == (True, True, True)
        panel.japanese.choose(JapaneseReading.OFF)

    view.set_reading_line("en", True)
    assert enabled() == (True, False, True)  # respelling has its own placement
    view.set_reading_line("en", False)
    view.set_reading_line("zh", True)
    assert enabled() == (True, True, True)


@pytest.mark.parametrize(
    ("status", "present", "absent"),
    [
        (
            "missing",
            "Shows once the Japanese dictionary is here.",
            "aren't in this version",
        ),
        (
            "failed",
            "Japanese readings aren't in this version yet.",
            "dictionary is here",
        ),
        ("ready", "Both keeps kana above and adds romaji below.", "dictionary is here"),
    ],
)
def test_japanese_row_explains_its_actual_readiness(
    qapp: QApplication, status: str, present: str, absent: str
) -> None:
    panel = ReadingLinesPanel(
        LookView(CaptionLook()),
        notes=True,
        japanese_readings=JapaneseReadingsView(
            JapaneseReadings(
                supported=status != "failed", dictionary_here=status == "ready"
            )
        ),
    )
    MADE.append(panel)
    notes = next(
        label.text()
        for label in panel.findChildren(QLabel)
        if "Both keeps kana" in label.text()
    )
    notes += " " + panel.japanese_note.text()
    assert present in notes
    assert absent not in notes


@pytest.mark.parametrize(
    "japanese_readings",
    [
        JapaneseReadings(dictionary_here=True),
        JapaneseReadings(),
        JapaneseReadings(supported=False),
    ],
)
def test_readings_keeps_the_inset_chinese_note_to_the_readable_measure(
    qapp: QApplication, japanese_readings: JapaneseReadings
) -> None:
    """The shared note that failed the native lab is not either Japanese note."""
    panel = ReadingLinesPanel(
        LookView(FURIGANA),
        notes=True,
        japanese_readings=JapaneseReadingsView(japanese_readings),
    )
    MADE.append(panel)
    chinese_row = panel.chinese.parentWidget()
    assert isinstance(chinese_row, SwitchRow)
    assert chinese_row.detail.text().startswith(
        "A small syllable over each Chinese character"
    )
    assert chinese_row.detail.maximumWidth() == round(
        chinese_row.detail.measure() * 1.2
    )


@pytest.mark.parametrize(
    ("state", "words"),
    [
        (
            JapaneseReadings(supported=False),
            "Japanese readings aren't in this version yet.",
        ),
        (
            JapaneseReadings(),
            "Shows once the Japanese dictionary is here.",
        ),
        (
            JapaneseReadings(progress=PackProgress("ja", Step.DOWNLOADING, 25, 100)),
            "The Japanese dictionary is downloading: 25%.",
        ),
    ],
)
def test_furigana_switch_explains_when_readings_are_unavailable(
    qapp: QApplication, state: JapaneseReadings, words: str
) -> None:
    panel = ReadingLinesPanel(
        LookView(FURIGANA),
        notes=True,
        japanese_readings=JapaneseReadingsView(state),
    )
    MADE.append(panel)
    assert panel.japanese.value() is JapaneseReading.KANA
    assert panel.japanese_note.text() == words


def test_furigana_switch_is_quiet_when_the_dictionary_is_here(
    qapp: QApplication,
) -> None:
    panel = ReadingLinesPanel(
        LookView(FURIGANA),
        notes=True,
        japanese_readings=JapaneseReadingsView(JapaneseReadings(dictionary_here=True)),
    )
    MADE.append(panel)
    assert panel.japanese_note.text() == ""


def test_the_switch_is_saved() -> None:
    chosen = replace(FURIGANA, japanese_reading=JapaneseReading.BOTH)
    stored = AppSettings.from_stored(look_settings(chosen)).to_stored()
    restored = caption_look(AppSettings.from_stored(stored))
    assert restored.reading_lines == ("ja",)
    assert restored.japanese_reading is JapaneseReading.BOTH


def test_the_switch_survives_an_app_restart() -> None:
    stored = look_settings(replace(FURIGANA, japanese_reading=JapaneseReading.ROMAJI))
    first_run = AppSettings.from_stored(stored)
    restarted = AppSettings.from_stored(first_run.to_stored())
    assert caption_look(restarted).japanese_reading is JapaneseReading.ROMAJI


@pytest.mark.parametrize(
    ("old_lines", "changed", "choice"),
    [
        ([], [], JapaneseReading.KANA),
        ([], None, JapaneseReading.KANA),
        ([], ["reading_lines"], JapaneseReading.OFF),
        (["zh"], ["reading_lines"], JapaneseReading.OFF),
        (["ja"], ["reading_lines"], JapaneseReading.KANA),
    ],
)
def test_the_old_furigana_switch_migrates_and_reopens_consistently(
    old_lines: list[str], changed: list[str] | None, choice: JapaneseReading
) -> None:
    # A real pre-choice file contained every setting, not merely the two
    # migration inputs.  No `changed` key represents the oldest format.
    old = AppSettings().to_stored()
    old.pop("japanese_reading")
    old["reading_lines"] = old_lines
    if changed is None:
        old.pop("changed")
    else:
        old["changed"] = changed
    value = AppSettings.from_stored(old)
    stored = value.to_stored()
    reopened = AppSettings.from_stored(stored)
    assert JapaneseReading(value.japanese_reading) is choice
    assert JapaneseReading(reopened.japanese_reading) is choice
    assert reopened.to_stored() == stored


def test_a_compound_look_edit_keeps_every_nonreading_change_on_reopen() -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    edited = replace(caption_look(settings.value), opacity=0.50, background="#123456")

    settings.update(**main.look_changes(settings.value, edited))

    assert {"opacity", "background_color"} <= set(settings.value.changed)
    reopened = Settings(store)
    assert reopened.value.opacity == 0.50
    assert reopened.value.background_color == "#123456"
    assert reopened.value.to_stored() == settings.value.to_stored()


def test_a_real_japanese_choice_click_puts_the_saved_default_back(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    original = settings.value.to_stored()
    view = LookView(
        caption_look(settings.value),
        lambda look: settings.update(**main.look_changes(settings.value, look)),
    )
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)

    assert panel.japanese.value() is JapaneseReading.KANA
    panel.japanese.choose(JapaneseReading.OFF)
    assert settings.value.japanese_reading == JapaneseReading.OFF.value
    panel.japanese.choose(JapaneseReading.KANA)

    assert settings.value.to_stored() == original
    reopened = Settings(store)
    assert reopened.value.to_stored() == original
    assert caption_look(reopened.value).japanese_reading is JapaneseReading.KANA


def test_a_real_nondefault_choice_click_survives_reopen_and_restore(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    view = LookView(
        caption_look(settings.value),
        lambda look: settings.update(**main.look_changes(settings.value, look)),
    )
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    panel.japanese.choose(JapaneseReading.BOTH)
    chosen = settings.value.to_stored()
    assert chosen["japanese_reading"] == "both"
    assert chosen["reading_lines"] == []  # legacy input stays untouched
    changed = chosen["changed"]
    assert isinstance(changed, list)
    assert "japanese_reading" in changed

    panel.japanese.choose(JapaneseReading.OFF)
    panel.japanese.choose(JapaneseReading.BOTH)
    assert settings.value.to_stored() == chosen
    assert Settings(store).value.to_stored() == chosen


@pytest.mark.parametrize("edit", ["opacity", "japanese"])
def test_panels_keep_an_explicit_default_script_list_on_other_edits(
    qapp: QApplication, edit: str
) -> None:
    original = AppSettings()
    explicit = main.readings_by_default(original)
    filed = replace(
        original, reading_lines=explicit, changed=("reading_lines",)
    ).to_stored()
    store = MemorySettingsStore(filed)
    settings = Settings(store)
    windows = CaptionWindows(None, MIC, areas)
    panels = Panels(settings, windows)
    try:
        if edit == "opacity":
            panels.look.set_opacity(0.50)
        else:
            panels.look.set_japanese_reading(JapaneseReading.ROMAJI)
        panels.save_look()

        reopened = Settings(store).value
        assert reopened.reading_lines == explicit
        assert "reading_lines" in reopened.changed
        assert reopened.opacity == (0.50 if edit == "opacity" else original.opacity)
        assert reopened.japanese_reading == (
            JapaneseReading.ROMAJI.value
            if edit == "japanese"
            else JapaneseReading.KANA.value
        )
    finally:
        windows.close()


def test_panels_leave_an_implicit_script_list_following_language_defaults(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    windows = CaptionWindows(None, MIC, areas)
    panels = Panels(settings, windows)
    try:
        panels.look.set_opacity(0.50)
        panels.look.set_japanese_reading(JapaneseReading.ROMAJI)
        panels.save_look()
        reopened = Settings(store)
        assert reopened.value.reading_lines == ()
        assert "reading_lines" not in reopened.value.changed

        before = caption_look(reopened.value).reading_lines
        reopened.update(targets=("zh",))
        after = caption_look(Settings(store).value).reading_lines
        assert "zh" in before and "zh" not in after
    finally:
        windows.close()


def test_panels_keep_an_explicit_list_after_a_real_script_off_on_cycle(
    qapp: QApplication,
) -> None:
    original = AppSettings()
    explicit = main.readings_by_default(original)
    store = MemorySettingsStore(
        replace(
            original, reading_lines=explicit, changed=("reading_lines",)
        ).to_stored()
    )
    settings = Settings(store)
    windows = CaptionWindows(None, MIC, areas)
    panels = Panels(settings, windows)
    try:
        panels.look.set_reading_line("zh", False)
        panels.save_look()
        panels.look.set_reading_line("zh", True)
        panels.save_look()

        reopened = Settings(store).value
        assert reopened.reading_lines == explicit
        assert "reading_lines" in reopened.changed
        reopened_settings = Settings(store)
        reopened_settings.update(targets=("zh",))
        assert caption_look(reopened_settings.value).reading_lines == explicit
    finally:
        windows.close()


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        (JapaneseReading.KANA, ["はは", "お", "み"]),
        (JapaneseReading.ROMAJI, ["haha", "wa", "o", "o"]),
        (JapaneseReading.BOTH, ["はは", "お", "み"]),
    ],
)
def test_each_japanese_choice_reads_particles_in_a_caption(
    learner: LearningTools,
    choice: JapaneseReading,
    expected: list[str],
) -> None:
    shown = window(learner, replace(FURIGANA, japanese_reading=choice))
    for n in range(3):
        shown.view.apply(
            finished(f"p{n}", clause("母は尾を見た", "I saw a tail"), language=JA)
        )
    shown.apply_changed(new_caption=True)
    assert readings(shown, RowKind.ORIGINAL)[: len(expected)] == expected
    if choice is JapaneseReading.BOTH:
        assert readings_below(shown, RowKind.ORIGINAL)[:4] == ["haha", "wa", "o", "o"]


def test_both_places_kana_above_and_smaller_romaji_below_each_word(
    learner: LearningTools,
) -> None:
    shown = window(learner, replace(FURIGANA, japanese_reading=JapaneseReading.BOTH))
    for n in range(3):
        shown.view.apply(
            finished(f"b{n}", clause("母は尾を見た", "I saw a tail"), language=JA)
        )
    shown.apply_changed(new_caption=True)
    QApplication.processEvents()
    laid = next(laid for _, laid, _ in shown.canvas.placed)
    row = next(row for row in laid.rows if row.row.kind is RowKind.ORIGINAL)
    assert [item.text for item in row.above][:3] == ["はは", "お", "み"]
    assert [item.text for item in row.below][:4] == ["haha", "wa", "o", "o"]
    assert row.above_font is not None and row.below_font is not None
    assert row.below_font.pixelSize() < row.above_font.pixelSize()
    assert min(item.y for item in row.below) > max(item.y for item in row.above)


def glyph_rects(runs: Iterable[QGlyphRun], origin: QPointF) -> Iterator[QRectF]:
    for run in runs:
        raw = run.rawFont()
        for glyph, position in zip(run.glyphIndexes(), run.positions(), strict=True):
            rect = raw.pathForGlyph(glyph).boundingRect()
            if not rect.isEmpty():
                yield rect.translated(origin + position)


@pytest.mark.parametrize("size", [1.0, 2.0], ids=["100%", "200%"])
@pytest.mark.parametrize(
    "choice", [JapaneseReading.BOTH, JapaneseReading.ROMAJI, JapaneseReading.KANA]
)
def test_japanese_readings_clear_the_next_row_and_window_edge(
    learner: LearningTools, choice: JapaneseReading, size: float
) -> None:
    shown = window(learner, replace(FURIGANA, japanese_reading=choice))
    at_one_moment(shown)
    shown.set_text_size(size)
    shown.set_translation_size(size)
    for n, (said, meaning) in enumerate(
        (
            ("ここは東京の映画館です", "This is a cinema in Tokyo."),
            ("友達と東京で飲みました", "I drank with a friend in Tokyo."),
        )
    ):
        shown.view.apply(finished(f"reading-{n}", clause(said, meaning), language=JA))
    shown.apply_changed(new_caption=True)
    QApplication.processEvents()
    shown.canvas.grab()

    assert len(shown.canvas.placed) == 2
    assert_reading_geometry(shown, choice, RowKind.ORIGINAL)


@pytest.mark.parametrize("fill", list(Fill))
def test_wrapped_japanese_translation_keeps_its_last_reading_inside_the_window(
    learner: LearningTools, fill: Fill
) -> None:
    choice = JapaneseReading.BOTH
    look = replace(FURIGANA, japanese_reading=choice, lab=CaptionLab(fill=fill))
    shown = window(learner, look, translate_into=JA)
    at_one_moment(shown)
    shown.resize(280, 530)
    shown.view.apply(
        finished("wrap", clause("We went to Tokyo.", SAID * 3, into=JA), language=EN)
    )
    shown.apply_changed(new_caption=True)
    QApplication.processEvents()
    shown.canvas.grab()
    rows = [
        row
        for _, laid, _ in shown.canvas.placed
        for row in laid.rows
        if row.row.kind is RowKind.TRANSLATION
    ]
    assert len({row.top + mark.y for row in rows for mark in row.below}) > 1
    # A kana-only continuation has no furigana. Count only the caption's own
    # readings across the wrap, skipping its display-only ellipses.
    kana = [mark.text for row in rows for mark in row.above if mark.end >= 0]
    romaji = [mark.text for row in rows for mark in row.below if mark.end >= 0]
    assert kana == ["ともだち", "とうきょう", "の"] * 3
    assert romaji == ["tomodachi", "to", "tōkyō", "de", "nomi", "mashi", "ta"] * 3
    assert_reading_geometry(shown, choice, RowKind.TRANSLATION)


def test_video_tracks_keep_both_japanese_readings(learner: LearningTools) -> None:
    choice = JapaneseReading.BOTH
    shown = window(
        learner, replace(FURIGANA, japanese_reading=choice), translate_into=JA
    )
    at_one_moment(shown)
    shown.set_video(True)
    shown.receive(finished("video", clause("My friend", "友達", into=JA), language=EN))
    QApplication.processEvents()
    shown.canvas.grab()
    now = shown.clock()
    shown.clock = lambda: now + 1.0
    shown.canvas.grab()
    assert shown.canvas.placed
    assert_reading_geometry(shown, choice, RowKind.TRANSLATION)


def assert_reading_geometry(
    shown: CaptionWindow, choice: JapaneseReading, kind: RowKind
) -> None:
    viewport = QRectF(shown.canvas.rect())
    base_glyphs: list[QRectF] = []
    readings: list[QRectF] = []
    for _, laid, rect in shown.canvas.placed:
        assert {row.row.kind for row in laid.rows} == set(RowKind)
        target = [row for row in laid.rows if row.row.kind is kind]
        assert any(row.above for row in target)
        assert any(row.below for row in target) == (choice is JapaneseReading.BOTH)
        for row in laid.rows:
            origin = rect.topLeft() + QPointF(0, row.top)
            for box in glyph_rects(
                row.layout.glyphRuns(), origin + row.layout.position()
            ):
                assert viewport.contains(box)
                base_glyphs.append(box)
            for marks, font in (
                (row.above, row.above_font),
                (row.below, row.below_font),
            ):
                if font is None:
                    continue
                for mark in marks:
                    word = QRectF()
                    for glyph in glyph_rects(
                        reading_lines.glyphs((mark,), font), origin
                    ):
                        word = word.united(glyph)
                    assert not word.isEmpty() and viewport.contains(word)
                    readings.append(word)
    for n, ink in enumerate(readings):
        assert all(not ink.intersects(box) for box in base_glyphs), ink
        assert all(not ink.intersects(other) for other in readings[n + 1 :])


def test_romaji_over_japanese_uses_each_sudachi_word(learner: LearningTools) -> None:
    shown = window(learner, replace(FURIGANA, japanese_reading=JapaneseReading.ROMAJI))
    said_in_japanese(shown)
    assert readings(shown, RowKind.ORIGINAL)[:3] == ["tomodachi", "to", "tōkyō"]


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
