"""W3, the lookup card on the caption windows (`ui_next.lookup_card`,
`caption_window`, `caption_windows`): one painted card for every window
that never takes the focus; hover after the mouse rests, pinned by a click
or a drag across a phrase; Esc, Backspace, a click elsewhere and leaving
it; a Learning action repainting only the captions holding its entry; and
the hovered word's links. Offscreen, made-up captions, the sample
dictionary (today's `LearningTools`, which `main` hands over)."""

import time
from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget
from tests.lexicon.sample import english_sample
from tests.ui.fakes import MemorySettingsStore, chinese_tools, tools_for
from tests.ui_next.made_up import at_one_moment, finished_updates
from tests.ui_next.test_lookup_view import learner

from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.main import LearningOffer
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import (
    CJK_FAMILIES,
    LATIN_FAMILIES,
    cursor_x,
)
from polyglotic_desktop.ui_next.caption_window import (
    CaptionWindow,
    Marked,
    linked_with,
    word_hint,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.lookup_card import (
    ACCENT,
    FAINT,
    FOLLOW_MS,
    HIDE_MS,
    HOVER_MS,
    HOVER_WIDTHS,
    LEAVE_MS,
    SURFACE,
    WIDTH,
    LookupCard,
    _meanings,
    dictionary_out,
)
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, Notice
from polyglotic_desktop.ui_next.views.lookup import LookupContext
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = Rect(0, 0, 1920, 1040)


class Keys:
    """Windows' key state, made up: what's "held" until asked."""

    def __init__(self) -> None:
        self.held: set[str] = set()

    def __call__(self, name: str) -> bool:
        found = name in self.held
        self.held.discard(name)
        return found


@pytest.fixture
def keys() -> Keys:
    return Keys()


@pytest.fixture
def problem() -> DictionaryProblem | None:
    """The learner's dictionary is whole, unless a test says otherwise."""
    return None


@pytest.fixture
def windows(
    qapp: QApplication, keys: Keys, problem: DictionaryProblem | None
) -> Iterator[CaptionWindows]:
    tools = chinese_tools(problem=problem)
    found = CaptionWindows(None, MIC, lambda: [AREA], keys=keys, learner=tools)
    tools.changed.connect(found.learning_changed)
    found.set_captioned([("app", APP)])
    shown = found.windows["app"]
    at_one_moment(shown)  # never a slide begun by a busy runner's pause (578)
    for update in finished_updates(40):
        found.apply(update)
    # Detect, kept: the spoken-language question these captions raise would
    # take the top rows the cards' tests click (polyglotic-hq 350)
    shown.set_spoken_language(None)
    shown.setGeometry(480, 600, 960, 360)
    qapp.processEvents()
    shown.canvas.repaint()
    yield found
    found.close()


def window(windows: CaptionWindows) -> CaptionWindow:
    return windows.windows["app"]


def card(windows: CaptionWindows) -> LookupCard:
    assert windows.card is not None
    return windows.card


def tools(windows: CaptionWindows) -> LearningTools:
    found = windows.learner
    assert isinstance(found, LearningTools)
    return found


def find(shown: CaptionWindow, text: str) -> tuple[Marked, QPointF]:
    """`text` in the newest lines in view, and a point on its first character."""
    for line, laid, rect in reversed(shown.canvas.placed):
        for row in laid.rows:
            if rect.top() + row.top < shown.canvas.clear_top:
                continue
            at = row.row.text.find(text)
            if at < 0:
                continue
            text_line = row.layout.lineForTextPosition(at)
            x = cursor_x(text_line, at)
            point = QPointF(
                rect.x() + x + 3,
                rect.y() + row.top + text_line.y() + text_line.height() / 2,
            )
            return Marked(line.key, row.index, at, at + len(text)), point
    raise LookupError(text)


def mouse(shown: QWidget, kind: str, pos: QPointF, held: bool = True) -> None:
    types = {
        "press": QEvent.Type.MouseButtonPress,
        "move": QEvent.Type.MouseMove,
        "release": QEvent.Type.MouseButtonRelease,
    }
    buttons = (
        Qt.MouseButton.LeftButton
        if held and kind != "release"
        else Qt.MouseButton.NoButton
    )
    event = QMouseEvent(
        types[kind], pos, shown.mapToGlobal(pos), Qt.MouseButton.LeftButton,
        buttons, Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    if kind == "press":
        shown.mousePressEvent(event)
    elif kind == "move":
        shown.mouseMoveEvent(event)
    else:
        shown.mouseReleaseEvent(event)


def click(shown: CaptionWindow, pos: QPointF) -> None:
    mouse(shown, "press", pos)
    mouse(shown, "release", pos)


def test_one_card_for_every_window_and_it_never_takes_the_focus(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([("app", APP), ("other", SourceId("app-2"))])
    shared = card(windows)
    assert all(w.card is shared for w in windows.windows.values())
    assert shared.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert shared.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert shared.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_hover_shows_after_the_mouse_rests_and_lets_the_mouse_through(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    shown, shared = window(windows), card(windows)
    word, point = find(shown, "电脑")
    mouse(shown, "move", point, held=False)
    assert shown.canvas.hovered == word
    assert not shared.isVisible() and shared._hover.interval() == HOVER_MS
    shared._hover.timeout.emit()  # the mouse rested
    assert shared.isVisible() and not shared.pinned
    assert shared.model.card().word == "电脑" and not shared.model.card().actions
    assert shared.windowFlags() & Qt.WindowType.WindowTransparentForInput
    _, other = find(shown, "游戏")
    mouse(shown, "move", other, held=False)  # showing: it follows the mouse
    assert shared.model.word == "电脑"  # not in the mouse move itself (272)
    assert shared._follow.isActive() and shared._follow.interval() == FOLLOW_MS
    shared._follow.timeout.emit()
    assert shared.model.word == "游戏"
    mouse(shown, "move", QPointF(shown.width() - 30, shown.height() - 20), held=False)
    assert shown.canvas.hovered is None and shared._hide.isActive()
    assert shared._hide.interval() == HIDE_MS
    shared._hide.timeout.emit()
    assert not shared.isVisible()


def test_the_hover_delay_starts_again_on_another_word(
    windows: CaptionWindows, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shown 100 ms after the mouse rests on a word - not on the first
    word it crossed: the delay starts again on another word, and is kept
    on the same one. Counted, not timed: a real 60 ms sleep against the
    100 ms delay, then its time left read, let a busy PC decide (polyglotic-hq
    312: it failed on 3 of 3 Linux runs of two branches on 2026-11-13). Each
    word is found as the window draws it with the mouse over it."""
    shown, shared = window(windows), card(windows)
    started: list[str] = []
    start = shared._hover.start

    def counted(*args: int) -> None:
        assert shared._pending is not None
        started.append(shared._pending.word)
        start(*args)

    monkeypatch.setattr(shared._hover, "start", counted)
    _, first = find(shown, "电脑")
    mouse(shown, "move", first, held=False)
    shown.canvas.repaint()
    _, second = find(shown, "游戏")
    mouse(shown, "move", second, held=False)
    assert shared._pending is not None and shared._pending.word == "游戏"
    assert shared._hover.isActive() and shared._hover.interval() == HOVER_MS
    mouse(shown, "move", QPointF(second.x() + 1, second.y()), held=False)
    assert started == ["电脑", "游戏"]  # started again on another; the same: kept


def test_a_click_on_a_word_pins_it_with_the_actions_above_its_row(
    windows: CaptionWindows,
) -> None:
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    assert shared.pinned and shared.model.card().actions
    assert not shared.windowFlags() & Qt.WindowType.WindowTransparentForInput
    request = shared.request
    assert request is not None and request.word == "电脑"
    assert request.context.translation  # the row's translation, for the line
    assert shared.above and shared.geometry().bottom() < request.row.y
    # its centre, as a width's half: QRect.center() rounds down half a pixel
    # more, which with a word half a pixel off a whole one (a Mac's font) was
    # 1.5 px off (polyglotic-hq 420: the first Mac run of the suite)
    placed = shared.geometry()
    centre = placed.left() + placed.width() / 2
    word_centre = request.rect.x + request.rect.width / 2
    assert abs(centre - word_centre) <= 1 or placed.left() == 8
    assert shown._drag is None  # a press on a word doesn't move the window


def test_a_drag_across_a_phrase_within_its_row_pins_the_phrase(
    windows: CaptionWindows,
) -> None:
    shown, shared = window(windows), card(windows)
    _, start = find(shown, "画")
    _, end = find(shown, "很漂亮")  # under 4: no sentence (522)
    mouse(shown, "press", start)
    mouse(shown, "move", QPointF(end.x() + 4, end.y()))
    assert shown.canvas.selection is not None
    mouse(shown, "release", end)
    assert shared.pinned and shared.model.word.startswith("画面")
    assert shown.canvas.selection is None


def test_esc_backspace_and_a_click_elsewhere_reach_it_without_the_focus(
    windows: CaptionWindows, keys: Keys
) -> None:
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    shared.do("part:0")
    assert shared.model.word == "电"
    keys.held.add("backspace")
    shared._look_at_keys()
    assert shared.model.word == "电脑"
    keys.held.add("escape")
    shared._look_at_keys()
    assert not shared.isVisible()
    click(shown, point)
    QApplication.sendEvent(
        shown,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        ),
    )
    assert not shared.isVisible()  # Esc while this app has the keyboard
    click(shown, point)
    elsewhere = QWidget()
    QApplication.sendEvent(
        elsewhere,
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(-500, -500),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    assert not shared.isVisible()  # a click on another of this app's windows


def test_its_buttons_keep_todays_tooltips(windows: CaptionWindows) -> None:
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    assert shared.tip("known") == "I know this word - don't highlight it"
    assert shared.tip("deck") == "Put it in the words you're learning"
    assert shared.tip("part:0") == "Look up 电"
    assert shared.tip("save:saved") == "Save to Saved"


def test_it_closes_ten_seconds_after_the_mouse_leaves_it(
    windows: CaptionWindows,
) -> None:
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    assert shared._leave.isActive() and shared._leave.interval() == LEAVE_MS
    shared.enterEvent(None)  # type: ignore[arg-type]
    assert not shared._leave.isActive()
    shared.leaveEvent(QEvent(QEvent.Type.Leave))
    assert shared._leave.isActive()
    shared._leave.timeout.emit()
    assert not shared.isVisible()


def test_locked_or_hidden_closes_it(windows: CaptionWindows) -> None:
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    windows.set_locked(True)
    assert not shared.isVisible()
    windows.set_locked(False)
    click(shown, point)
    windows.set_hidden(True)
    assert not shared.isVisible()


def test_a_learning_action_repaints_only_the_captions_holding_its_entry(
    windows: CaptionWindows,
) -> None:
    shown, shared = window(windows), card(windows)
    marks = shown.marks
    holding = {
        line.key for line, _, _ in shown.canvas.placed if "电脑" in line.rows[0].text
    }
    others = {line.key for line, _, _ in shown.canvas.placed} - holding
    assert holding and others and set(marks._kept) >= holding | others
    _, point = find(shown, "电脑")
    click(shown, point)
    shared.do("deck")
    assert shared.model.card().in_deck
    assert not holding & set(marks._kept)  # forgotten: worked out again
    assert others <= set(marks._kept)  # kept: no other caption touched
    entry = tools(windows).lookup("电脑")[0]
    status = tools(windows).vocabulary.status(tools(windows).facts(entry)).status
    assert status is WordStatus.LEARNING
    windows.learning_changed("statuses")  # a change from elsewhere: all forgotten
    assert not marks._kept


def test_the_hovered_words_links_are_drawn_on_hover(windows: CaptionWindows) -> None:
    windows.set_look(CaptionLook(word_links=WordLinks.HOVER))
    shown = window(windows)
    shown.canvas.repaint()
    word, point = find(shown, "电脑")
    mouse(shown, "move", point, held=False)
    line = next(ln for ln, _, _ in shown.canvas.placed if ln.key == word.key)
    partners = linked_with(line, word)
    assert {line.rows[p.row].text[p.start : p.end] for p, _ in partners} == {
        "电脑",
        "computer",
    }
    assert not shown.marks(line, word.row)  # On hover: no underline otherwise


def test_no_learner_no_lookup(qapp: QApplication) -> None:
    shown = CaptionWindow(
        "app", APP, CaptionWindows(None).stored.for_new(0),
        SourceLabel("Discord", "#4dd0e1"), areas=lambda: [AREA],
    )  # fmt: skip
    for update in finished_updates(10):
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    shown.show()
    qapp.processEvents()
    shown.canvas.repaint()
    _, _, rect = shown.canvas.placed[-1]
    mouse(shown, "move", rect.center(), held=False)
    assert shown.canvas.hovered is None and shown.card is None
    shown.close()


def _contrast(a: QColor, b: QColor) -> float:
    def luminance(color: QColor) -> float:
        def channel(v: float) -> float:
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

        r, g, b_ = (channel(c) for c in (color.redF(), color.greenF(), color.blueF()))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_

    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_its_text_is_never_under_12_px_and_faint_text_is_readable(
    windows: CaptionWindows,
) -> None:
    """What the UI lab's checks found (project 119): the status chips, the
    parts' title and the Backspace hint were 11 px, and the faint grey
    (hints, counts, the parts' title) was 3.6:1 on the card."""
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    shared.do("part:0")  # a part: Back, and its Backspace hint
    painted = shared._painted
    assert any(run.color == QColor(FAINT) for run in painted.runs)
    sizes = [run.font.pixelSize() for run in painted.runs]
    sizes.append(shared._chip("new", "#ffd27a").font.pixelSize())
    assert min(sizes) >= 12
    assert _contrast(QColor(FAINT), QColor(SURFACE)) >= 4.5


def test_click_any_word_until_the_first_lookup_then_never_again(
    qapp: QApplication,
) -> None:
    """160: people didn't find that the words are clickable. 176: the first
    finished caption says "Click any word" on the notice line, until the
    first lookup on this PC - then never again, in any window."""
    store = MemorySettingsStore({})
    tools = chinese_tools()
    first = CaptionWindows(store, MIC, lambda: [AREA], keys=Keys(), learner=tools)
    first.set_captioned([("app", APP)])
    shown = first.windows["app"]
    now = time.monotonic()
    assert shown.notices.showing(now) == (None, None)  # nothing to click yet
    for update in finished_updates(40):
        first.apply(update)
    assert shown.notices.showing(now) == (None, word_hint())
    shown.set_connection(Notice.RECONNECTING, None)  # the state comes first
    assert shown.notices.showing(now)[0] is Notice.RECONNECTING
    shown.set_connection(None, None)
    shown.set_spoken_language(None)  # no question over the top rows (350)
    shown.setGeometry(480, 600, 960, 360)
    qapp.processEvents()
    shown.canvas.repaint()
    _, point = find(shown, "电脑")
    click(shown, point)  # the first lookup
    assert card(first).pinned
    assert shown.notices.showing(now) == (None, None)
    first.save_now()
    first.close()

    again = CaptionWindows(store, MIC, lambda: [AREA], keys=Keys(), learner=tools)
    again.set_captioned([("app", APP)])
    for update in finished_updates(6):
        again.apply(update)
    # never again - the line may say pinyin can go above Chinese, once (369)
    assert again.windows["app"].notices.showing(now)[1] != word_hint()
    again.close()


def test_no_hint_where_words_cant_be_looked_up(qapp: QApplication) -> None:
    plain = CaptionWindows(None, MIC, lambda: [AREA])  # no learning tools
    plain.set_captioned([("app", APP)])
    for update in finished_updates(3):
        plain.apply(update)
    assert plain.windows["app"].notices.showing(time.monotonic()) == (None, None)
    plain.close()


def test_the_hint_only_where_the_captions_words_can_be_looked_up(
    qapp: QApplication,
) -> None:
    """368: with nothing learned, a German PC's tools were English's alone,
    so a Chinese caption's words could be looked up nowhere - yet it said
    "Click any word". No hint then; with Chinese's dictionary open beside
    (as nothing learned now opens it), the hint and a lookup."""
    english = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    alone = CaptionWindows(None, MIC, lambda: [AREA], keys=Keys(), learner=english)
    alone.set_captioned([("app", APP)])
    for update in finished_updates(6):  # Chinese captions
        alone.apply(update)
    assert alone.windows["app"].notices.showing(time.monotonic()) == (None, None)
    alone.close()

    english.learn_beside(chinese_tools())
    both = CaptionWindows(None, MIC, lambda: [AREA], keys=Keys(), learner=english)
    both.set_captioned([("app", APP)])
    for update in finished_updates(40):
        both.apply(update)
    shown = both.windows["app"]
    assert shown.notices.showing(time.monotonic()) == (None, word_hint())
    shown.set_spoken_language(None)  # no question over the top rows (350)
    shown.setGeometry(480, 600, 960, 360)
    qapp.processEvents()
    shown.canvas.repaint()
    _, point = find(shown, "电脑")
    click(shown, point)
    assert card(both).pinned
    both.close()


def test_an_english_word_with_no_phonetic_shows_no_lone_dash(
    qapp: QApplication,
) -> None:
    """192, 198: an English entry with no phonetic (ECDICT's are sometimes
    empty) showed a lone blue "-" where the phonetic goes. Nothing now."""
    shown = LookupCard(learner(english=True))
    shown.model.show("keep", LookupContext("Keep going"), pinned=True)
    entry = shown.model.card()
    assert entry.readings and not entry.readings[0].reading  # no phonetic
    painted = shown._lay_out(entry, style.px(WIDTH))
    drawn = [(b.layout.text(), b.color) for b in painted.blocks]
    drawn += [(r.text, r.color) for r in painted.runs]
    assert ("-", QColor(ACCENT)) not in drawn
    assert any(text.startswith("1. ") for text, _ in drawn)  # its meaning still


def test_its_own_words_are_in_the_interfaces_fonts_and_meanings_chinese_first(
    windows: CaptionWindows,
) -> None:
    """176, 198: the card's buttons, chips and notes were in its Latin fonts,
    so in a Chinese interface their Chinese came from whatever face Windows
    found - MS UI Gothic, a Japanese one, in an English locale. They are in
    the interface's fonts (its Chinese face: YaHei UI, or JhengHei UI for
    zh_TW). Meanings hold Chinese too (an English word's are Chinese; "CL:
    台[tai2]"): Chinese first, in the word's script."""
    shown, shared = window(windows), card(windows)
    _, point = find(shown, "电脑")
    click(shown, point)
    shared.do("save")  # the categories open
    painted = shared._painted
    drawn = {run.text: run.font.families() for run in painted.runs}
    drawn |= {b.layout.text(): b.layout.font().families() for b in painted.blocks}
    for own in ("new", "Add to deck", "Known", "Save to ▴", "+ New category"):
        assert drawn[own] == style.UI_FAMILIES, own
    assert drawn["INSIDE THIS WORD"] == style.UI_FAMILIES
    (measure,) = (t for t in drawn if t.startswith("Measure word"))
    assert drawn[measure] == style.UI_FAMILIES
    (meaning,) = (t for t in drawn if t.startswith("1. "))
    zh, hant = CJK_FAMILIES["zh"], CJK_FAMILIES["zh-hant"]  # and an OS's own
    assert drawn[meaning][: len(zh)] == list(zh)
    entry = shared.model.card()
    assert _meanings(replace(entry, traditional=True))[: len(hant)] == hant
    assert _meanings(replace(entry, language="ja")) == LATIN_FAMILIES


def test_an_english_words_chinese_meanings_are_in_a_chinese_face(
    qapp: QApplication,
) -> None:
    """198: an English word's meanings are ECDICT's Chinese ("left": 左边的),
    drawn in the card's Latin fonts - MS UI Gothic on Windows in an
    English locale, for every English learner who reads Chinese."""
    shown = LookupCard(learner(english=True))
    shown.model.show("left", LookupContext("Turn left here"), pinned=True)
    painted = shown._lay_out(shown.model.card(), style.px(WIDTH))
    meanings = [b for b in painted.blocks if "左边的" in b.layout.text()]
    assert meanings
    for block in meanings:
        zh = CJK_FAMILIES["zh"]  # and an OS's own
        assert block.layout.font().families()[: len(zh)] == list(zh)
    shown.close()


@pytest.mark.parametrize("problem", [DictionaryProblem.DAMAGED])
def test_the_dictionary_out_card_says_whats_wrong_and_how_to_fix_it(
    windows: CaptionWindows,
) -> None:
    """Hovered or pinned, the card says the dictionary needs repairing and
    how - in full, at the hover card's widest (polyglotic-hq 199)."""
    shown, shared = window(windows), card(windows)
    what, fix = dictionary_out(DictionaryProblem.DAMAGED, chinese=True)
    _, point = find(shown, "电脑")
    mouse(shown, "move", point, held=False)
    shared._hover.timeout.emit()  # the mouse rested
    texts = [block.layout.text() for block in shared._painted.blocks]
    assert what in texts and fix in texts
    assert shared.width() == style.px(HOVER_WIDTHS[1])
    click(shown, point)
    texts = [block.layout.text() for block in shared._painted.blocks]
    assert shared.pinned and what in texts and fix in texts
    assert not shared.model.card().actions and shared._hits == [
        (shared._hits[0][0], "close")
    ]


def test_a_language_added_from_the_card_says_its_dictionarys_download(
    windows: CaptionWindows,
) -> None:
    """Learn it too for a language with a pack to download: the card says
    it's on Learning with its dictionary, and how big (polyglotic-hq 327)."""

    class WithAPack(LearningOffer):
        def pack_size(self, code: str) -> int:
            return 13_131_253 if code == "en" else 0

    settings = Settings(MemorySettingsStore({"learning": "zh"}))
    shown, shared = window(windows), card(windows)
    shared.model.offer = WithAPack(settings)
    _, point = find(shown, "computer")
    click(shown, point)
    shared.do("learn_too")
    texts = [block.layout.text() for block in shared._painted.blocks]
    assert (
        "English is on your Learning page now, with its dictionary to download "
        "there (13.1 MB)." in texts
    )


def test_a_word_in_a_language_not_learned_asks_to_learn_it_too(
    windows: CaptionWindows,
) -> None:
    """A click on an English word of a Chinese learner's caption: "Learning
    English?" - Learn English too adds it to Learning's list, kept in the
    settings, and the card says where it went (DECISIONS.md #65,
    polyglotic-hq 262)."""
    settings = Settings(MemorySettingsStore({"learning": "zh"}))
    shown, shared = window(windows), card(windows)
    shared.model.offer = LearningOffer(settings)
    _, point = find(shown, "computer")
    click(shown, point)
    assert shared.pinned and shared.model.card().offer == "en"
    assert [hit for _, hit in shared._hits][-2:] == ["learn_too", "not_now"]
    assert shared.tip("not_now") == "Don't ask about this language again"
    shared.do("learn_too")
    assert settings.value.also_learning == ("en",)
    texts = [block.layout.text() for block in shared._painted.blocks]
    assert "English is on your Learning page now." in texts
    assert "learn_too" not in [hit for _, hit in shared._hits]
    _, point = find(shown, "电脑")  # Chinese: learned, never asked
    click(shown, point)
    assert shared.model.card().offer == ""
