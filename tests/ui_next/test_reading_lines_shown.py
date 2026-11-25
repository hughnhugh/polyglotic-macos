"""Reading lines shown (polyglotic-hq 369, decision 0155): pinyin drawn
above Chinese, centred over its characters and never touching; on a
caption window's rows in Chinese - what was said or its translation -
from the learner's Chinese dictionary, once it is read; the switch per
language and its size in Settings > Captions, saved; the one-time hint;
and a resize step and a live update with it inside today's budgets.
Offscreen, made-up captions and the sample CC-CEDICT."""

import itertools
import time
from collections.abc import Iterator
from dataclasses import replace
from functools import partial

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget
from tests.budget_judge import sampled, within
from tests.ui.fakes import MemorySettingsStore, chinese_tools
from tests.ui_next.made_up import EN, ZH, finished_updates, live_update
from tests.ui_next.test_caption_window import areas
from tests.ui_next.test_flow import PAIRED, ROWS
from tests.ui_next.test_reading_lines import made_up

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    JapaneseReading,
    LongLines,
    ReadingSize,
    ReadingSystem,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.main import caption_look, look_changes, look_settings
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import (
    APP,
    CONTROLS,
    GAME,
    MIC,
    clause,
    finished,
)
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    Ink,
    char_under,
    cursor_x,
)
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.caption_window import (
    Canvas,
    CaptionWindow,
    Marked,
    caption_style,
    one_layout,
    reading_hint,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.flow import FlowOptions
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.transcript import Transcript, TranscriptChoices

PINYIN = CaptionLook(reading_lines=("zh",), japanese_reading=JapaneseReading.OFF)
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


# -- drawn -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flow", "fill"),
    [
        (None, Fill.CLAUSES),
        (ROWS, Fill.CLAUSES),
        (PAIRED, Fill.CLAUSES),
        (one_layout(PINYIN, LongLines.DISPLAY_NEW_LINES), Fill.CLAUSES),
        (None, Fill.STACKED),
        (None, Fill.PAIRED),
    ],
    ids=[
        "today",
        "rows",
        "paired",
        "display new lines",
        "poured stacked",
        "poured paired",
    ],
)
@pytest.mark.parametrize(
    "face", [None, "Ma Shan Zheng Captions"], ids=["plain", "brush"]
)
def test_readings_are_centred_over_their_characters_and_never_touch(
    qapp: QApplication, flow: FlowOptions | None, fill: Fill, face: str | None
) -> None:
    view = CaptionLines((APP,), EN, keep=20)
    view.set_models(flow is not None)
    view.apply(finished("a", GAME, CONTROLS))
    (line,) = view.lines
    style = CaptionStyle(
        flow=flow,
        fill=fill,
        reading_lines=frozenset({"zh"}),
        faces=(("zh", face),) if face is not None else (),
    )
    read = CaptionLayout(style, readings=made_up).laid(line, 420, 1.0)
    placed = 0
    for row in read.rows:
        if row.row.kind is not RowKind.ORIGINAL:
            assert not row.above
            continue
        assert row.above_font is not None
        metrics = QFontMetricsF(row.above_font)
        base = QFontMetricsF(row.layout.font())
        # The synthetic syllables depend on their indices in the source row.
        source_end = row.start + len(row.row.text)
        wanted = [
            reading
            for reading in made_up(line.rows[row.index].text, "zh")
            if row.start <= reading.start < source_end
        ]
        marks = [mark for mark in row.above if mark.start < len(row.row.text)]
        assert len(marks) == len(wanted)
        by_line: dict[float, list[tuple[float, float]]] = {}
        for reading, at in zip(wanted, marks, strict=True):
            start, end = reading.start - row.start, reading.end - row.start
            assert (at.start, at.end, at.text) == (start, end, reading.text)
            text_line = row.layout.lineForTextPosition(start)
            wide = metrics.horizontalAdvance(reading.text)
            under = base.horizontalAdvance(row.row.text[start:end])
            centre = cursor_x(text_line, start) + under / 2
            assert at.x + wide / 2 == pytest.approx(centre, abs=0.6)
            assert at.y < text_line.y()  # above its line's box
            assert at.x >= -0.6  # never cut by the window's edge
            by_line.setdefault(text_line.y(), []).append((at.x, at.x + wide))
            placed += 1
        for spans in by_line.values():
            spans.sort()
            for (_, left_end), (right_start, _) in itertools.pairwise(spans):
                assert right_start >= left_end + 1.0, "two readings touch"
    assert placed > 10


def test_medium_readings_are_bigger_than_small(qapp: QApplication) -> None:
    view = CaptionLines((APP,), EN, keep=20)
    view.apply(finished("a", GAME))
    (line,) = view.lines
    sizes = []
    for size in ReadingSize:
        style = caption_style(replace(PINYIN, reading_size=size))
        laid = CaptionLayout(style, readings=made_up).laid(line, 600, 1.0)
        font = laid.rows[0].above_font
        assert font is not None
        sizes.append(font.pixelSize())
    assert sizes[0] < sizes[1]


# -- a caption window ------------------------------------------------------------------

LABS = {
    "today": CaptionLab(),
    "translation below": CaptionLab(fill=Fill.STACKED),
    "line by line": CaptionLab(fill=Fill.PAIRED),
    "new, translation below": CaptionLab(flow=True, fill=Fill.STACKED),
    "new, line by line": CaptionLab(flow=True, fill=Fill.PAIRED),
    "run-on": CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True),
    "lined-up": CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True, aligned=True),
}


def read_window(
    qapp: QApplication,
    lab: CaptionLab,
    captions: int,
    look: CaptionLook = PINYIN,
    ready: bool = True,
    **choices: object,
) -> CaptionWindow:
    chosen = replace(WindowChoices(), **choices)  # type: ignore[arg-type]
    window = CaptionWindow(
        "Discord.exe", APP, chosen, SourceLabel("Discord", "#4dd0e1"), mic=MIC,
        areas=areas, learner=chinese_tools(ready),
    )  # fmt: skip
    MADE.append(window)
    window.set_look(replace(look, lab=lab))
    for update in finished_updates(captions):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.show()
    window.resize(900, 460)
    qapp.processEvents()
    window.canvas.repaint()
    return window


def drawn(window: CaptionWindow, kind: RowKind | None = None) -> int:
    return sum(
        len(row.above)
        for _, laid, _ in window.canvas.placed
        for row in laid.rows
        if kind is None or row.row.kind is kind
    )


@pytest.mark.parametrize("lab", list(LABS))
def test_a_caption_window_draws_pinyin_from_the_learners_dictionary(
    qapp: QApplication, lab: str
) -> None:
    window = read_window(qapp, LABS[lab], 8)
    assert drawn(window, RowKind.ORIGINAL) > 4
    assert drawn(window, RowKind.TRANSLATION) == 0  # English
    window.set_look(replace(PINYIN, reading_lines=(), lab=LABS[lab]))
    window.canvas.repaint()
    assert drawn(window) == 0


@pytest.mark.parametrize("lab", list(LABS))
@pytest.mark.parametrize("into", [ZH, Language("zh-hant")], ids=["zh", "zh-hant"])
def test_a_translation_into_chinese_carries_pinyin_too(
    qapp: QApplication, lab: str, into: Language
) -> None:
    """English heard, translated into Chinese: the translation's row is
    the one in Chinese, and the same switch reads it (en->zh) - in every
    layout (polyglotic-hq 395: the user's preview 1, "pinyin doesn't work
    over translations it seems"; Translation below and Line by line
    without the New layout drew none)."""
    window = read_window(qapp, LABS[lab], 0, translate_into=into)
    for n in range(3):
        window.view.apply(
            finished(
                f"e{n}", clause("I play games", "我打游戏", into=into), language=EN
            )
        )
    window.apply_changed(new_caption=True)
    window.canvas.repaint()
    assert drawn(window, RowKind.TRANSLATION) >= 3 * 2
    assert drawn(window, RowKind.ORIGINAL) == 0


@pytest.mark.parametrize("lab", list(LABS))
@pytest.mark.parametrize("system", list(ReadingSystem))
def test_a_second_language_translation_into_chinese_carries_its_reading(
    qapp: QApplication, lab: str, system: ReadingSystem
) -> None:
    """The user's settings (polyglotic-hq 427, preview 2: "translation
    lines still don't have pinyin/zhuyin"): English heard, the window's
    language English, Chinese its second - the server keeps the Chinese
    line under English, the target - so the row read as English and had
    no reading over it, in every layout, pinyin or Zhuyin."""
    look = replace(PINYIN, reading_system=system)
    window = read_window(qapp, LABS[lab], 0, look, translate_into=EN)
    window.set_second_languages({EN: ZH})
    for n in range(3):
        kept = clause("I play games", "我打游戏", (("play", "打"),), into=EN)
        window.view.apply(finished(f"e{n}", kept, language=EN))
    window.apply_changed(new_caption=True)
    window.canvas.repaint()
    assert drawn(window, RowKind.TRANSLATION) >= 3 * 2
    assert drawn(window, RowKind.ORIGINAL) == 0


@pytest.mark.parametrize("lab", list(LABS))
def test_a_chinese_line_of_an_english_clause_carries_its_reading(
    qapp: QApplication, lab: str
) -> None:
    """polyglotic-hq 497 (490's picture `e2e-2-after-pr329.png`): a
    caption labelled Mandarin, its English clause translated into Chinese,
    English's second language, the line kept under English - the server
    says it is Chinese (`written_in`), so it has its pinyin, in every
    layout. Read from the caption's label, it was English: none."""
    window = english_clauses_window(qapp, LABS[lab], {EN: ZH})
    assert drawn(window, RowKind.TRANSLATION) >= 3  # the sample's 我, at least
    assert drawn(window, RowKind.ORIGINAL) == 0  # English: nothing to read


def test_an_older_servers_line_is_read_as_the_captions_label_says(
    qapp: QApplication,
) -> None:
    """Without the server's word the line is taken for English, as before."""
    window = english_clauses_window(qapp, LABS["today"], {})
    assert drawn(window) == 0


def english_clauses_window(
    qapp: QApplication, lab: CaptionLab, written_in: dict[Language, Language]
) -> CaptionWindow:
    window = read_window(qapp, lab, 0, translate_into=EN)
    window.set_second_languages({EN: ZH})
    said = "It's not what I expected in the beginning,"
    for n in range(3):
        kept = clause(said, "这与我最初的预期不同。", (("expected", "预期"),), into=EN)
        window.view.apply(
            finished(f"m{n}", replace(kept, written_in=written_in), language=ZH)
        )
    window.apply_changed(new_caption=True)
    window.canvas.repaint()
    return window


def test_without_chinese_learned_no_empty_band_over_a_translation(
    qapp: QApplication,
) -> None:
    """Pinyin on, English learned and not Chinese - so no Chinese
    dictionary open - and English translated into Chinese: no pinyin, and
    no room left for it either (395: on real captions the translation rows
    had an empty band above them)."""
    from tests.lexicon.sample import english_sample
    from tests.ui.fakes import tools_for

    from polyglotic_desktop.core.lexicon.english import EnglishDictionary
    from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY

    english = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    window = CaptionWindow(
        "Discord.exe", APP, replace(WindowChoices(), translate_into=ZH),
        SourceLabel("Discord", "#4dd0e1"), mic=MIC, areas=areas, learner=english,
    )  # fmt: skip
    MADE.append(window)
    window.set_look(PINYIN)
    window.show()
    window.resize(900, 460)
    for n in range(3):
        window.view.apply(
            finished(f"e{n}", clause("I play games", "我打游戏", into=ZH), language=EN)
        )
    window.apply_changed(new_caption=True)
    qapp.processEvents()
    window.canvas.repaint()
    rows = [row for _, laid, _ in window.canvas.placed for row in laid.rows]
    assert rows and all(row.band == 0 and not row.above for row in rows)


def test_pinyin_comes_once_the_dictionary_is_read(qapp: QApplication) -> None:
    """Never read on the interface's thread: until the word split's data
    is read, rows are laid out without it, and laid out again after."""
    window = read_window(qapp, CaptionLab(), 8, ready=False)
    assert drawn(window) == 0
    learner = window.learner
    assert learner is not None
    learner.dictionary.prepare()  # type: ignore[union-attr]
    window.dictionary_ready()
    window.canvas.repaint()
    assert drawn(window) > 4


@pytest.mark.parametrize("lab", list(LABS))
def test_a_resize_step_with_pinyin_is_within_a_frame(
    qapp: QApplication, lab: str
) -> None:
    window = read_window(qapp, LABS[lab], 150)
    width, height = window.width(), window.height()

    def step(n: int) -> None:
        window.resize(width - 150 + n * 9, height + n)
        window.canvas.repaint()

    within(budgets.FRAME, lambda: sampled(qapp, [partial(step, n) for n in range(30)]))


@pytest.mark.parametrize("on", [True, False], ids=["pinyin", "no-pinyin"])
@pytest.mark.parametrize("lab", list(LABS))
def test_a_live_update_with_pinyin_is_within_a_new_captions_budget(
    qapp: QApplication, lab: str, on: bool
) -> None:
    """With pinyin off too: the same window and learner, what it costs."""
    window = read_window(qapp, LABS[lab], 150, PINYIN if on else CaptionLook())
    pool = finished_updates(8)
    grown = [
        replace(
            live_update("app-live"),
            clauses=tuple(
                Clause(
                    f"{c.original}{'还有更多' * n}",
                    {EN: f"{c.translations[EN]} {'and more ' * n}"},
                    c.links,
                )
                for c in pool[n % 8].clauses
            ),
        )
        for n in range(12)
    ]
    # as many as the tries take: 24 a try, and a busy PC's third ran out (437)
    updates = itertools.cycle(grown)

    def arrive() -> None:
        window.view.apply(next(updates))
        window.apply_changed(new_caption=False)
        window.canvas.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 12))


# -- the setting -----------------------------------------------------------------------


def test_pinyin_is_off_until_switched_on_and_saved() -> None:
    chinese_only = CaptionLook(japanese_reading=JapaneseReading.OFF)
    assert chinese_only.reading_lines == ()
    assert not caption_style(chinese_only).reading_lines
    view = LookView(chinese_only)
    panel = ReadingLinesPanel(view, notes=True)
    try:
        assert not panel.chinese.isChecked() and not panel.reading_size.isEnabled()
        panel.chinese.setChecked(True)
        assert view.value.reading_lines == ("zh",)
        assert panel.reading_size.isEnabled()
        view.set_reading_size(ReadingSize.MEDIUM)
        assert caption_style(view.value).reading_lines == frozenset({"zh"})
        # saved as the app saves it - a choice now, not the default (511) -
        # and read back as it was
        stored = {
            **AppSettings().to_stored(),
            **look_changes(AppSettings(), view.value),
        }
        back = caption_look(AppSettings.from_stored(stored))
        assert (back.reading_lines, back.reading_size) == (("zh",), ReadingSize.MEDIUM)
        view.set_reading_line("zh", False)
        assert view.value.reading_lines == ()
    finally:
        shiboken6.delete(panel)


def test_a_reading_line_stored_wrongly_is_off() -> None:
    for wrong in ("zh", ["xx"], [1], None):
        found = AppSettings.from_stored(
            {"reading_lines": wrong, "reading_size": "huge"}
        )
        assert found.reading_lines == () and found.reading_size == "small"


# -- the one-time hint -----------------------------------------------------------------


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, areas, learner=chinese_tools())
    found.set_captioned([("app", APP)])
    yield found
    found.close()


def hinted(windows: CaptionWindows) -> bool:
    _, text = windows.windows["app"].notices.showing(time.monotonic())
    return text == reading_hint()


def test_the_pinyin_hint_is_said_once_after_the_first_lookup(
    windows: CaptionWindows,
) -> None:
    windows.apply(finished("a", GAME))
    assert not hinted(windows)  # "Click any word" first
    windows.stored.looked_up = True
    windows.apply(finished("b", GAME))
    assert hinted(windows) and windows.stored.reading_hinted
    assert windows.stored.to_stored()["reading_hinted"] is True
    windows.windows["app"].notices.brief("", 0.0, 0.0)  # it went
    windows.apply(finished("c", GAME))
    assert not hinted(windows)


def test_no_pinyin_hint_with_pinyin_on_or_no_chinese(windows: CaptionWindows) -> None:
    windows.stored.looked_up = True
    windows.set_look(PINYIN)
    windows.apply(finished("a", GAME))
    assert not hinted(windows)
    windows.set_look(CaptionLook())
    windows.apply(finished("b", clause("hello", "bonjour", into=EN), language=EN))
    assert not hinted(windows) and not windows.stored.reading_hinted


# -- only over the words past what the learner knows -----------------------------------


def over(window: CaptionWindow, word: str) -> int:
    """Readings drawn over `word` in the window's rows in Chinese."""
    found = 0
    for _, laid, _ in window.canvas.placed:
        for row in laid.rows:
            at = row.row.text.find(word)
            if at < 0 or not row.above:
                continue
            ruby = window.canvas.engine._ruby(row.row, row.layout.font())
            assert ruby is not None
            found += sum(at <= r.start < at + len(word) for r in ruby.readings)
    return found


def test_with_past_what_i_know_a_known_words_pinyin_goes_and_comes_back(
    qapp: QApplication,
) -> None:
    look = replace(PINYIN, reading_past=True)
    window = read_window(qapp, CaptionLab(), 0, look=look)
    window.view.apply(finished("g", GAME))
    window.apply_changed(new_caption=True)
    window.canvas.repaint()
    assert over(window, "游戏") == 2
    learner = window.learner
    assert learner is not None
    game = learner.lookup("游戏")[0].entry_id
    learner.vocabulary.set_status(game, WordStatus.KNOWN)
    window.learning_changed(Changed.STATUSES.value)
    window.canvas.repaint()
    assert over(window, "游戏") == 0
    assert drawn(window, RowKind.ORIGINAL) > 0  # the words they don't know: still
    learner.vocabulary.set_status(game, WordStatus.NEW)
    window.learning_changed(Changed.STATUSES.value)
    window.canvas.repaint()
    assert over(window, "游戏") == 2


def test_every_word_keeps_a_known_words_pinyin(qapp: QApplication) -> None:
    window = read_window(qapp, CaptionLab(), 0)
    window.view.apply(finished("g", GAME))
    window.apply_changed(new_caption=True)
    learner = window.learner
    assert learner is not None
    learner.vocabulary.set_status(learner.lookup("游戏")[0].entry_id, WordStatus.KNOWN)
    window.learning_changed(Changed.STATUSES.value)
    window.canvas.repaint()
    assert over(window, "游戏") == 2


def test_past_what_i_know_is_a_choice_saved_with_the_switch() -> None:
    view = LookView(PINYIN)
    panel = ReadingLinesPanel(view, notes=True)
    try:
        assert panel.reading_over.isEnabled()
        view.set_reading_past(True)
        assert caption_style(view.value).reading_past
        store = MemorySettingsStore({})
        Settings(store).update(**look_settings(view.value))  # as main saves it
        assert caption_look(AppSettings.from_stored(store.values)).reading_past
        view.set_reading_line("zh", False)
        assert not panel.reading_over.isEnabled()
    finally:
        shiboken6.delete(panel)


# -- the hover band, arrows and the transcript -----------------------------------------


def en_zh(flow: FlowOptions | None) -> tuple[CaptionLayout, Line]:
    """English heard, translated into Chinese with pinyin, words linked."""
    view = CaptionLines(
        (APP,), ZH, keep=20, options=DisplayOptions(word_links=WordLinks.ARROWS)
    )
    view.set_models(flow is not None)
    view.apply(
        finished(
            "e",
            clause("I play games every day", "我每天打游戏", (("games", "游戏"),), ZH),
            language=EN,
        )
    )
    (line,) = view.lines
    style = CaptionStyle(
        flow=flow, arrows=True, link_room=True, reading_lines=frozenset({"zh"})
    )
    return CaptionLayout(style, readings=made_up), line


@pytest.mark.parametrize("flow", [None, ROWS, PAIRED], ids=["today", "rows", "paired"])
def test_an_arrow_ends_over_its_counterparts_pinyin_not_through_it(
    qapp: QApplication, flow: FlowOptions | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, line = en_zh(flow)
    tips: list[QPointF] = []
    draw = QPainter.drawPath

    def noted(painter: QPainter, path: QPainterPath) -> None:
        tips.append(path.pointAtPercent(1.0))
        draw(painter, path)

    monkeypatch.setattr(QPainter, "drawPath", noted)
    laid = engine.laid(line, 600, 1.0)
    image = QImage(640, int(laid.height) + 40, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    marks = CaptionMarks(None)
    marks.set_look(WordLinks.ARROWS, WordIntroductions.OFF)
    engine.paint(painter, line, laid, QPointF(10, 10), Ink(), marks)
    painter.end()
    meant = next(r for r in laid.rows if r.row.kind is RowKind.TRANSLATION)
    assert meant.above and meant.band > 0
    pinyin_top = 10 + meant.top + meant.layout.lineAt(0).y() - meant.band
    assert tips, "no arrow drawn"
    for tip in tips:
        assert tip.y() <= pinyin_top + 2.0


@pytest.mark.parametrize("scrolling", [False, True])
def test_video_paints_readings_and_word_links_in_the_same_rows(
    qapp: QApplication, scrolling: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polyglotic_desktop.ui_next.video import Video

    engine, line = en_zh(None)
    ready = False
    engine.readings = lambda text, lang: made_up(text, lang) if ready else None
    tips = []
    draw = QPainter.drawPath

    def note(painter: QPainter, path: QPainterPath) -> None:
        tips.append(path.pointAtPercent(1.0) + painter.worldTransform().map(QPointF()))
        draw(painter, path)

    monkeypatch.setattr(QPainter, "drawPath", note)
    marks = CaptionMarks(None)
    marks.set_look(WordLinks.ARROWS, WordIntroductions.OFF)
    video = Video()

    def grab(now: float):
        image = QImage(240, 160, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        try:
            return video.paint(
                painter,
                engine,
                Ink(),
                marks,
                lambda *_: None,
                [line],
                1.0,
                image.width(),
                image.height(),
                now,
                scrolling=scrolling,
                languages=(EN, ZH),
            )
        finally:
            painter.end()

    before = grab(0)
    before_y = before[0][1].rows[-1].top + before[0][2].y()
    ready = True
    # A dictionary becoming ready replaces the caption window's engine.
    engine = CaptionLayout(engine.style, readings=made_up)
    after = grab(0.1)
    _, laid, rect = after[0]
    meant = laid.rows[-1]
    assert meant.top + rect.y() + meant.layout.lineAt(0).y() == pytest.approx(before_y)
    assert meant.above and tips
    origin = rect.topLeft() + QPointF(0, meant.top)
    assert meant.above_font is not None
    metrics = QFontMetricsF(meant.above_font)
    for mark in meant.above:
        assert mark.y < meant.layout.lineAt(0).y()
        at = origin + QPointF(mark.x + metrics.horizontalAdvance(mark.text) / 2, mark.y)
        found = char_under([(meant, origin)], at)
        assert found is not None and found[2] == meant.start + mark.start


def test_video_lookup_can_find_the_later_wrap_of_the_same_clause(
    qapp: QApplication,
) -> None:
    from polyglotic_desktop.ui_next.video import Video

    engine, line = en_zh(None)
    window = read_window(qapp, CaptionLab(), 0, translate_into=ZH)
    video = Video()
    image = QImage(132, 275, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        window.canvas.placed = video.paint(
            painter, engine, Ink(), None, lambda *_: None, [line],
            1.0, image.width(), image.height(), 0.0, languages=(EN, ZH),
            lines_shown=3,
        )  # fmt: skip
    finally:
        painter.end()

    _, laid, _ = window.canvas.placed[0]
    wraps = [row for row in laid.rows if row.row.kind is RowKind.ORIGINAL]
    assert len(wraps) > 1 and wraps[-1].start > 0
    last = wraps[-1]
    found = window.word_at(Marked(line.key, last.index, last.start, last.start + 3))
    assert found is not None and found.word == last.row.text[:3]


@pytest.mark.parametrize("flow", [None, PAIRED], ids=["today", "paired"])
def test_a_point_over_a_reading_is_over_its_character(
    qapp: QApplication, flow: FlowOptions | None
) -> None:
    view = CaptionLines((APP,), EN, keep=20)
    view.set_models(flow is not None)
    view.apply(finished("a", GAME))
    (line,) = view.lines
    style = CaptionStyle(flow=flow, reading_lines=frozenset({"zh"}))
    laid = CaptionLayout(style, readings=made_up).laid(line, 600, 1.0)
    said = next(r for r in laid.rows if r.row.kind is RowKind.ORIGINAL)
    origin = QPointF(10, 10 + said.top)
    for at in said.above[:4]:
        index = next(
            r.start
            for r in made_up(said.row.text, "zh")
            if r.text == at.text
            and said.above.index(at) == made_up(said.row.text, "zh").index(r)
        )
        text_line = said.layout.lineForTextPosition(index)
        middle = (cursor_x(text_line, index) + cursor_x(text_line, index + 1)) / 2
        over = QPointF(origin.x() + middle, origin.y() + at.y - 2)  # in the pinyin
        found = char_under([(said, origin)], over)
        assert found is not None and found[2] == index


def test_a_hovered_words_highlight_covers_its_pinyin(qapp: QApplication) -> None:
    view = CaptionLines((APP,), EN, keep=20)
    view.apply(finished("a", GAME))
    (line,) = view.lines
    style = CaptionStyle(reading_lines=frozenset({"zh"}))
    laid = CaptionLayout(style, readings=made_up).laid(line, 600, 1.0)
    said = next(r for r in laid.rows if r.row.kind is RowKind.ORIGINAL)
    image = QImage(640, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    Canvas._fill(
        painter, laid, QPointF(0, 0), Marked(0, said.index, 2, 4), QColor("#ff0000")
    )
    painter.end()
    text_line = said.layout.lineAt(0)
    middle = (cursor_x(text_line, 2) + cursor_x(text_line, 4)) / 2
    in_band = said.top + text_line.y() - said.band / 2
    assert image.pixelColor(int(middle), int(in_band)).red() > 200


def test_a_transcript_shows_pinyin_with_the_caption_windows(
    qapp: QApplication,
) -> None:
    transcript = Transcript(APP, EN, mic=MIC)
    for update in finished_updates(6):
        transcript.apply(update)
    window = TranscriptWindow(
        "Discord.exe", transcript, SourceLabel("Discord", "#4dd0e1"),
        TranscriptChoices(), style.current(), chinese_tools(),
    )  # fmt: skip
    MADE.append(window)
    shown = window.list
    shown.set_reading(PINYIN)
    assert shown.engine.style.reading_lines == frozenset({"zh"})
    laid = shown._laid(transcript.lines[-1])
    assert any(row.above for row in laid.rows)
    shown.set_reading(CaptionLook())
    laid = shown._laid(transcript.lines[-1])
    assert not any(row.above for row in laid.rows)
