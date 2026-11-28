"""The live window's ink at 60 Hz through revisions, withdrawals and arrivals."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication
from tests.ui_next.line_replay import glyphs
from tests.ui_next.test_arrivals import FRAME, Clock, opened

from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.continuations import CaptionGroups
from polyglotic_desktop.core.listening.display import (
    JapaneseReading,
    LongLines,
    RowKind,
)
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

EN = Language("en")
FR = Language("fr")
LONG = "One " + "clear lake beyond the mountain and the town " * 3
SHORT = "One"
type Glyph = tuple[int, RowKind, int, int, int | str]


def ink(window: CaptionWindow) -> dict[Glyph, float]:
    result: dict[Glyph, float] = {}
    for canvas in (window.canvas, window.zone):
        if canvas.isHidden():
            continue
        page = [(ln, laid, rect, 1.0) for ln, laid, rect in canvas.placed]
        page.extend(canvas.turning)
        for line, laid, rect, scale in page:
            for row in laid.rows:
                if getattr(row, "opacity", 1.0) <= 0:
                    continue
                for cursor, glyph, box in glyphs(row.layout):
                    y = rect.y() + scale * (row.top + box.top())
                    if canvas.clear_top <= y < canvas.height():
                        key: Glyph = (
                            line.key,
                            row.row.kind,
                            row.row.clause,
                            row.source_index(cursor),
                            glyph,
                        )
                        result[key] = canvas.y() + y
                for reading in (*row.above, *row.below):
                    y = rect.y() + scale * (row.top + reading.y)
                    if canvas.clear_top <= y < canvas.height():
                        key = (
                            line.key,
                            row.row.kind,
                            row.row.clause,
                            row.start + reading.start,
                            reading.text,
                        )
                        result[key] = canvas.y() + y
    return result


def update(
    key: str, text: str, translation: str = "", *, kind: CaptionKind = CaptionKind.LIVE
) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(key),
        APP,
        kind,
        (Clause(text, {EN: translation} if translation else {}),),
        FR,
        (FR,),
    )


class Film:
    def __init__(self, window: CaptionWindow, clock: Clock):
        self.window = window
        self.clock = clock
        self.previous: dict[Glyph, float] = {}

    def frames(self, count: int = 120, *, still: bool = False) -> dict[Glyph, float]:
        for _ in range(count):
            self.window._tick()
            self.window.canvas.repaint()
            if not self.window.zone.isHidden():
                self.window.zone.repaint()
            current = ink(self.window)
            for key in current.keys() & self.previous.keys():
                assert current[key] <= self.previous[key] + 1e-6, (
                    key,
                    self.previous[key],
                    current[key],
                )
            if still:
                assert current == self.previous
            self.previous = current
            self.clock.now += FRAME
        return self.previous


@pytest.fixture
def film(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[Film]:
    monkeypatch.setattr(caption_window, "reduced_motion", lambda: False)
    clock = Clock()
    look = CaptionLook(preview=True)
    window = opened(
        qapp,
        clock,
        captions=0,
        look=replace(look, lab=replace(look.lab, arrival_gap=0, line_gap=0)),
        show_mic=True,
    )
    window.view.set_settle_after(120)
    window.resize(360, 690)
    qapp.processEvents()
    try:
        yield Film(window, clock)
    finally:
        window.close()
        shiboken6.delete(window)


@pytest.mark.parametrize(
    "mode", ["grouped", "paired", "own", "preview", "zone", "cards", "video", "large"]
)
def test_shorter_caption_leaves_ink_in_place(film: Film, mode: str) -> None:
    window = film.window
    long = update(
        "live", LONG[:48] if mode in ("zone", "cards", "video") else LONG, "Here."
    )
    if mode == "paired":
        window.set_presets(
            replace(window.preset_menu, long_lines=LongLines.DISPLAY_NEW_LINES)
        )
    elif mode == "own":
        long = replace(long, source_id=MIC)
    elif mode in ("zone", "cards"):
        window.set_cards(mode == "cards")
        window.set_timing(CaptionMode.STEADY)
    elif mode == "video":
        window.set_video(True)
    elif mode == "large":
        window.set_text_size(2.0)
    if mode == "preview":
        window.receive(
            update("earlier", "Earlier.", "Before.", kind=CaptionKind.FINISHED)
        )
        film.frames()
        long = replace(long, clauses=(Clause(LONG, {EN: LONG}),))
    window.receive(long)
    before = film.frames()
    assert before
    if mode == "zone":
        assert window.zone.placed
    if mode == "cards":
        assert window.deck is not None
    if mode == "preview":
        draft = window.view.lines[-1]
        assert draft.provisional and any(key[0] == draft.key for key in before)
    short = replace(
        long,
        kind=CaptionKind.FINISHED if mode == "preview" else long.kind,
        clauses=(Clause(SHORT, {EN: "Here."}),),
    )
    window.receive(short)
    after = film.frames()
    assert before.keys() & after.keys()
    window.receive(replace(short, clauses=(Clause("One clear lake.", {EN: "Here."}),)))
    assert film.frames()


@pytest.mark.parametrize(
    "operation", ["retract", "translate", "late", "join", "continues", "burst"]
)
def test_revisions_above_and_below_surviving_glyphs(film: Film, operation: str) -> None:
    window = film.window
    first = update("first", "First", kind=CaptionKind.FINISHED)
    window.receive(first)
    film.frames()
    second = update("second", "B", "" if operation == "late" else LONG)
    window.receive(second)
    before = film.frames()
    assert len({key[0] for key in before}) == 2
    if operation == "retract":
        window.receive(replace(second, kind=CaptionKind.WITHDRAWN, clauses=()))
    elif operation in ("late", "translate"):
        window.receive(replace(second, clauses=(Clause("B", {EN: "One"}),)))
    elif operation == "join":
        window.receive(
            replace(
                first,
                caption_id=CaptionId("joined"),
                replaces=(first.caption_id, second.caption_id),
                clauses=(Clause("First B"),),
            )
        )
    elif operation == "continues":
        window.receive(
            replace(second, clauses=(Clause("B"),), kind=CaptionKind.FINISHED)
        )
        groups = CaptionGroups(window.view._history, lambda _cid: None)
        continuation = replace(
            update("continued", "B next.", kind=CaptionKind.FINISHED),
            continues=second.caption_id,
        )
        for packet in groups.project(continuation):
            window.receive(packet)
    else:
        for i in range(16):
            window.receive(
                update(f"burst-{i}", f"Further words {i}", kind=CaptionKind.FINISHED)
            )
    after = film.frames()
    assert after
    if operation == "burst":
        assert window.bursts
    else:
        assert before.keys() & after.keys()
    window.receive(update("next", "More.", kind=CaptionKind.FINISHED))
    assert film.frames()


@pytest.mark.parametrize(("code", "ruby"), [("zh", "shan1"), ("ja", "\u3084\u307e")])
def test_readings_can_appear_and_disappear(film: Film, code: str, ruby: str) -> None:
    window = film.window
    lang = Language(code)
    text = "\u5c71"
    packet = replace(
        update("reading", text, "Hill."), language=lang, languages_heard=(lang,)
    )
    window.receive(packet)
    before = film.frames()
    assert before
    look = window.look
    window.set_look(
        replace(look, reading_lines=(code,), japanese_reading=JapaneseReading.BOTH)
    )
    readings = [Reading(0, 1, ruby)]
    if code == "ja":
        readings.append(Reading(0, 1, "yama", below=True))
    window.canvas.engine.readings = lambda text, language: readings
    window.receive(replace(packet, clauses=(Clause(text + text, {EN: "Hill."}),)))
    shown = film.frames()
    assert {key[-1] for key in shown if isinstance(key[-1], str)} == {
        r.text for r in readings
    }
    window.set_look(look)
    window.receive(packet)
    cleared = film.frames()
    assert before.keys() & cleared.keys()
    assert all(isinstance(key[-1], int) for key in cleared)


@pytest.mark.parametrize("video", [False, True], ids=["panel", "video"])
def test_scrolled_page_stays_still_through_a_revision_and_arrival(
    film: Film, video: bool
) -> None:
    window = film.window
    window.set_video(video)
    packets = [
        update(str(i), f"{i} land", kind=CaptionKind.FINISHED) for i in range(24)
    ]
    for packet in packets:
        window.receive(packet)
    film.frames()
    window.canvas.scroll_by(400)
    film.previous = {}
    held = film.frames(1)
    assert held and not window.view.scroll.following
    visible = window.canvas.placed[len(window.canvas.placed) // 2][0]
    window.receive(
        replace(
            next(p for p in packets if p.caption_id == visible.caption_id),
            clauses=(Clause(LONG),),
        )
    )
    window.receive(update("tail", "Next."))
    film.frames(still=True)
    window.go_live()
    assert window.view.scroll.following


def test_an_arrival_uses_the_vacated_rows_before_lifting_earlier_text(
    film: Film,
) -> None:
    window = film.window
    window.set_language("")
    first = update("anchor", "Anchor.", kind=CaptionKind.FINISHED)
    second = update("tail", LONG)
    window.receive(first)
    film.frames()
    window.receive(second)
    before = film.frames(300)
    anchor, tail = (line.key for line in window.view.lines)
    first_y = min(y for key, y in before.items() if key[0] == anchor)
    marker = next(key for key in before if key[0] == tail and key[3] == 0)
    old_top = before[marker]
    old_bottom = max(y for key, y in before.items() if key[0] == tail)
    window.receive(replace(second, clauses=(Clause(SHORT),)))
    shortened = film.frames()
    assert shortened[marker] <= old_top + 1e-6
    window.receive(update("fills", "More.", kind=CaptionKind.FINISHED))
    after = film.frames()
    latest = window.view.lines[-1].key
    assert min(y for key, y in after.items() if key[0] == anchor) == pytest.approx(
        first_y
    )
    assert old_top < min(y for key, y in after.items() if key[0] == latest) < old_bottom


def test_grouped_wrap_is_immediate_with_reduced_motion(
    film: Film, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(caption_window, "reduced_motion", lambda: True)
    window = film.window
    window.receive(update("caption", SHORT, "Here."))
    film.frames(1)
    window.receive(update("caption", LONG, "Here."))
    film.frames(1)
    rows = [row for _, laid, _ in window.canvas.placed for row in laid.rows]
    assert any(row.visual_line for row in rows)
    assert all(getattr(row, "opacity", 1.0) == 1 for row in rows)
    assert not window.arriving


@pytest.mark.parametrize("edit", ["split", "join"])
@pytest.mark.parametrize("mode", LongLines)
def test_a_surviving_word_keeps_its_height_across_clause_boundaries(
    film: Film, edit: str, mode: LongLines
) -> None:
    window = film.window
    window.set_presets(replace(window.preset_menu, long_lines=mode))
    first = update("first", "First Quartz", "Here.")
    window.receive(first)
    film.frames()
    if edit == "join":
        window.receive(update("second", "Last.", "Last."))
        film.frames()

    def marker() -> float | None:
        return next(
            (
                rect.y() + row.top + box.top()
                for _, laid, rect in window.canvas.placed
                for row in laid.rows
                if row.row.kind is RowKind.ORIGINAL
                for i, _, box in glyphs(row.layout)
                if row.row.text[i : i + 1] == "Q"
            ),
            None,
        )

    before = marker()
    assert before is not None
    changed = replace(
        first, clauses=(Clause("First", {EN: "Here."}), Clause("Quartz", {EN: "Last."}))
    )
    if edit == "join":
        changed = replace(
            changed,
            caption_id=CaptionId("joined"),
            kind=CaptionKind.FINISHED,
            replaces=(first.caption_id, CaptionId("second")),
        )
    window.receive(changed)
    for _ in range(120):
        film.frames(1)
        current = marker()
        if current is None:  # its new row waits for the text in its place (984)
            continue
        assert current <= before + 1e-6
        before = current
    assert marker() is not None
