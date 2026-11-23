"""A word saved, moved or un-saved takes - or loses - its category's colour
at once on every caption already showing it (the user, 2026-11-14: "they
don't get immediately highlight. Only subsequent or future ones show the
highlight I believe"; polyglotic-hq 305): the line it was saved from, the
same word in other lines of the window, another caption window, the app's
transcript, a live line - and the provisional line (Steady's at the
longest wait for text, Quick preview's), which drew no saved colour at all
until its finished caption came: the failing case, on `main` and 0.1.4.

The windows are left to paint themselves (`processEvents`), as on screen:
no repaint is forced, and what each paint drew is read from the layout's
own paint. Nothing is laid out again. Offscreen, made-up captions, the
sample dictionary."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools
from tests.ui.test_caption_marks import EN, dashed, dotted
from tests.ui_next.made_up import SEPARATE

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.listening.display import DisplayOptions
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished, live
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, cursor_x
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = Rect(0, 0, 1920, 1040)
WORD = "电脑"
LINES = (
    ("我的电脑又卡了，", "My computer froze again,"),
    ("这个游戏的画面很漂亮。", "This game's graphics are beautiful."),
    ("电脑坏了怎么办？", "What if the computer breaks?"),
)


@dataclass
class Painted:
    """What each paint drew since `clear`: per surface and line, the
    colours the word was drawn in (saved words' only)."""

    seen: dict[tuple[int, int], frozenset[str]] = field(default_factory=dict)

    def clear(self) -> None:
        self.seen.clear()


@pytest.fixture
def painted(monkeypatch: pytest.MonkeyPatch) -> Painted:
    found = Painted()
    paint = CaptionLayout.paint

    def recorded(self, painter, line, laid, at, ink, marks=None):
        colours: set[str] = set()
        for index, row in enumerate(line.rows):
            for start, end, format_ in marks(line, index) if marks else ():
                assert isinstance(format_, QTextCharFormat)
                if WORD in row.text[start:end] and (
                    format_.foreground().style() is not Qt.BrushStyle.NoBrush
                ):
                    colours.add(format_.foreground().color().name())
        found.seen[(id(painter.device()), line.key)] = frozenset(colours)
        return paint(self, painter, line, laid, at, ink, marks)

    monkeypatch.setattr(CaptionLayout, "paint", recorded)
    return found


@dataclass
class Shown:
    tools: LearningTools
    windows: CaptionWindows
    transcripts: Transcripts

    @property
    def window(self) -> CaptionWindow:
        return self.windows.windows["app"]

    @property
    def other(self) -> CaptionWindow:
        return self.windows.windows["other"]


def showing(qapp: QApplication, look: CaptionLook, last: str = "") -> Shown:
    """Two caption windows (an app's, and the mic's in a second), the
    app's transcript, three finished captions each - two with the word -
    and with `last` "live", a live update holding it too."""
    tools = chinese_tools()
    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=tools)
    windows.stored.joined = SEPARATE  # on their own: windows start joined (554)
    tools.changed.connect(windows.learning_changed)
    transcripts = Transcripts(windows, None, learner=tools, areas=lambda: [AREA])
    tools.changed.connect(transcripts.learning_changed)
    windows.set_look(look)
    windows.set_captioned([("app", APP), ("other", MIC)])
    for n, (said, meant) in enumerate(LINES):
        for source, key in ((APP, "c"), (MIC, "m")):
            update = finished(f"{key}{n}", clause(said, meant), source=source)
            windows.apply(update)
            transcripts.apply(update)
    if last == "live":
        windows.apply(live("c9", clause("我的电脑又", "My computer")))
    windows.windows["app"].setGeometry(100, 150, 900, 420)
    windows.windows["other"].setGeometry(1000, 150, 800, 420)
    for each in windows.windows.values():
        each.show()
    transcripts.show("app")
    transcripts.shown["app"].resize(900, 500)
    qapp.processEvents()
    for each in windows.windows.values():
        each.canvas.repaint()
    transcripts.shown["app"].list.repaint()
    return Shown(tools, windows, transcripts)


@pytest.fixture
def shown(qapp: QApplication, request: pytest.FixtureRequest) -> Iterator[Shown]:
    look, last = (
        request.param
        if hasattr(request, "param")
        else (CaptionLook(arrival=Arrival.STEP), "")
    )
    found = showing(qapp, look, last)
    yield found
    found.transcripts.close()
    found.windows.close()


def holding(window: CaptionWindow) -> set[int]:
    return {
        line.key
        for line, _, _ in window.canvas.placed
        if any(WORD in row.text for row in line.rows)
    }


def pin(shown: Shown, qapp: QApplication) -> None:
    """A click on the word in the newest line holding it: the card pinned."""
    window = shown.window
    for _, laid, rect in reversed(window.canvas.placed):
        for row in laid.rows:
            at = row.row.text.find(WORD)
            if at < 0 or rect.top() + row.top < window.canvas.clear_top:
                continue
            text_line = row.layout.lineForTextPosition(at)
            pos = QPointF(
                rect.x() + cursor_x(text_line, at) + 3,
                rect.y() + row.top + text_line.y() + text_line.height() / 2,
            )
            for kind, held in (
                (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
            ):
                event = QMouseEvent(
                    kind, pos, window.mapToGlobal(pos), Qt.MouseButton.LeftButton,
                    held, Qt.KeyboardModifier.NoModifier,
                )  # fmt: skip
                if kind is QEvent.Type.MouseButtonPress:
                    window.mousePressEvent(event)
                else:
                    window.mouseReleaseEvent(event)
            qapp.processEvents()
            assert shown.windows.card is not None and shown.windows.card.pinned
            return
    raise LookupError(WORD)


def drawn_at_once(
    shown: Shown,
    painted: Painted,
    qapp: QApplication,
    action: Callable[[], object],
    colour: Callable[[], str | None],
) -> None:
    """`action`, then the windows left to paint themselves: every line
    showing the word, on every surface, painted again in `colour` (None:
    none) - with nothing laid out again."""
    laid = [w.canvas.engine.laid_out for w in shown.windows.windows.values()]
    painted.clear()
    action()
    for _ in range(3):
        qapp.processEvents()
    wanted = colour()
    surfaces = [(id(w.canvas), holding(w)) for w in (shown.window, shown.other)]
    transcript = shown.transcripts.shown["app"].list
    surfaces.append(
        (
            id(transcript),
            {
                line.key
                for line in transcript.transcript.lines
                if any(WORD in row.text for row in line.rows)
            },
        )
    )
    for device, keys in surfaces:
        assert keys
        for key in keys:
            got = painted.seen.get((device, key))
            assert got is not None, ("not painted again", device, key)
            assert got == (frozenset({wanted}) if wanted else frozenset()), (key, got)
    assert [w.canvas.engine.laid_out for w in shown.windows.windows.values()] == laid


PREVIEW = (CaptionLook(preview=True, arrival=Arrival.STEP), "live")
"""The provisional line: Quick preview's, and Steady's at the longest wait
for text."""
CASES = [
    (CaptionLook(arrival=Arrival.STEP), ""),
    (CaptionLook(arrival=Arrival.STEP), "live"),
    PREVIEW,
]
IDS = ["finished", "a live line", "a provisional line"]


@pytest.mark.parametrize("shown", CASES, ids=IDS, indirect=True)
def test_saving_from_the_card_colours_every_showing_line_at_once(
    shown: Shown, painted: Painted, qapp: QApplication
) -> None:
    pin(shown, qapp)
    card = shown.windows.card
    assert card is not None
    vocabulary = shown.tools.vocabulary

    def colour_of(category: str) -> Callable[[], str]:
        return lambda: vocabulary.category(category).color  # type: ignore[union-attr]

    drawn_at_once(
        shown, painted, qapp, lambda: card.do("save:saved"), colour_of("saved")
    )
    drawn_at_once(
        shown, painted, qapp, lambda: card.do("save:tricky"), colour_of("tricky")
    )
    drawn_at_once(shown, painted, qapp, lambda: card.do("remove"), lambda: None)
    drawn_at_once(
        shown,
        painted,
        qapp,
        lambda: card.do("new_category"),
        lambda: vocabulary.categories[-1].color,
    )


@pytest.mark.parametrize("shown", CASES, ids=IDS, indirect=True)
def test_saving_or_unsaving_elsewhere_colours_every_showing_line_at_once(
    shown: Shown, painted: Painted, qapp: QApplication
) -> None:
    """From Words, another device's sync: any Learning change but the
    card's own repaints what shows."""
    entry = shown.tools.lookup(WORD)[0]
    vocabulary = shown.tools.vocabulary
    drawn_at_once(
        shown,
        painted,
        qapp,
        lambda: vocabulary.save(
            entry.entry_id,
            entry.headword,
            entry.traditional,
            entry.reading,
            "",
            "saved",
            LookupContext(""),
        ),
        lambda: vocabulary.category("saved").color,  # type: ignore[union-attr]
    )
    drawn_at_once(
        shown, painted, qapp, lambda: vocabulary.unsave(entry.entry_id), lambda: None
    )


def test_joined_columns_take_the_colour_at_once(
    qapp: QApplication, painted: Painted
) -> None:
    shown = showing(qapp, CaptionLook(preview=True, arrival=Arrival.STEP), "live")
    try:
        shown.windows.join()
        joined = shown.windows.joined_window
        assert joined is not None
        joined.setGeometry(100, 150, 1500, 420)
        joined.show()
        qapp.processEvents()
        for each in shown.windows.windows.values():
            each.canvas.repaint()
        pin(shown, qapp)
        card = shown.windows.card
        assert card is not None
        drawn_at_once(
            shown,
            painted,
            qapp,
            lambda: card.do("save:saved"),
            lambda: shown.tools.vocabulary.category("saved").color,  # type: ignore[union-attr]
        )
    finally:
        shown.transcripts.close()
        shown.windows.close()


def test_a_provisional_line_changing_with_saved_words_within_its_budget(
    qapp: QApplication,
) -> None:
    """Saved words on the provisional line are worked out each time it
    changes: with 30 captions in a window of the default size, saved words
    in them, still within NEW_CAPTION, timed as the other budget tests are.
    What they add is small: a change and a whole repaint took a median
    0.86 ms without them and 0.87 ms with them here (a 1,000 px window 1.5
    and 1.6 ms - whose repaint alone went past 4 ms on the Linux runner,
    so the window is the default's, as in the other new-caption tests)."""
    from tests.budget_judge import sampled, within
    from tests.ui_next.made_up import finished_updates

    from polyglotic_desktop.perf import budgets

    tools = chinese_tools()
    for word in ("电脑", "游戏"):  # the sample dictionary's
        entry = tools.lookup(word)[0]
        tools.vocabulary.save(
            entry.entry_id, entry.headword, entry.traditional, entry.reading, "",
            "saved", LookupContext(""),
        )  # fmt: skip
    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=tools)
    windows.set_look(CaptionLook(preview=True, arrival=Arrival.STEP))
    windows.set_captioned([("app", APP)])
    window = windows.windows["app"]
    window.setGeometry(100, 100, 960, 300)
    for update in finished_updates(30):
        windows.apply(update)
    window.show()
    qapp.processEvents()
    window.canvas.repaint()
    assert len(window.view.lines) >= 30
    texts = iter(
        [f"我的电脑又卡了，我们周末一起玩游戏吧{'。' * (n % 5)}" for n in range(60)]
    )

    def changes() -> None:
        windows.apply(live("p1", clause(next(texts), "My computer froze again")))
        window.canvas.repaint()

    try:
        within(budgets.NEW_CAPTION, lambda: sampled(qapp, [changes] * 10))
        provisional = window.view.lines[-1]
        assert provisional.provisional
        assert any(
            f.foreground().style() is not Qt.BrushStyle.NoBrush
            for f in (m[2] for m in window.marks(provisional, 0))
        )
    finally:
        windows.close()


def test_the_provisional_line_shows_saved_words_and_nothing_else(
    qapp: QApplication,
) -> None:
    """Steady's line at the longest wait for text and Quick preview's
    (polyglotic-hq 305): a saved word in its colour there too - the line
    being read, where a word is looked up and saved - but no dots, dashes
    or links: it keeps changing."""
    tools = chinese_tools()
    computer = tools.lookup("电脑")[0]
    tools.vocabulary.save(
        computer.entry_id, computer.headword, computer.traditional,
        computer.reading, "", "saved", LookupContext(""),
    )  # fmt: skip
    tools.vocabulary.set_status(tools.lookup("游戏")[0].entry_id, WordStatus.LEARNING)
    view = CaptionLines((APP,), EN, keep=10, options=DisplayOptions(preview=True))
    view.apply(live("a", clause("我的电脑又卡了，打游戏", "My computer froze")))
    line = view.lines[0]
    assert line.provisional
    marks = CaptionMarks(tools)
    found = marks(line, 0)
    saved = tools.vocabulary.category("saved")
    assert saved is not None
    assert [(s, e, f.foreground().color().name()) for s, e, f in found] == [
        (2, 4, saved.color)
    ]
    assert dashed(found) == [] and dotted(found) == []
