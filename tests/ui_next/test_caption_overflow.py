"""Overflow on the caption and Video paint paths, at the reported window width."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import areas
from tests.ui_next.test_card_stack import Clock

from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.display import (
    JapaneseReading,
    LongLines,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.core.listening.timing import (
    OFFERED_MODES,
    CaptionId,
    CaptionMode,
)
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_layout import char_under
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows

JA = "山道を歩いて川沿いの橋を渡ると、街道の先は小さな町の終着駅。"
EN = "Follow the path down the hill, cross the bridge over the river and walk to the station in the little town."
TARGET = Language("en")


def readings(text: str, language: str | None) -> list[Reading]:
    pronunciations = {
        "山": ("やま", "yama"),
        "道": ("みち", "michi"),
        "川": ("かわ", "kawa"),
        "橋": ("はし", "hashi"),
        "町": ("まち", "machi"),
        "駅": ("えき", "eki"),
    }
    return (
        [
            Reading(i, i + 1, value, below=below)
            for i, char in enumerate(text)
            if char in pronunciations
            for value, below in zip(pronunciations[char], (False, True), strict=True)
        ]
        if language == "ja"
        else []
    )


@pytest.mark.parametrize(
    ("mode", "video"),
    [
        *(
            pytest.param(mode, False, id=f"{mode.value}-caption")
            for mode in OFFERED_MODES
        ),
        *(
            pytest.param(mode, True, id=f"{mode.value}-subtitle")
            for mode in OFFERED_MODES
        ),
        pytest.param(CaptionMode.SCROLLING, True, id="scrolling-subtitle"),
    ],
)
@pytest.mark.parametrize("choice", LongLines)
def test_each_continuation_is_linked_and_slides(
    qapp: QApplication,
    mode: CaptionMode,
    video: bool,
    choice: LongLines,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = CaptionWindows(None, MIC, areas)
    clock = Clock()
    monkeypatch.setattr(
        "polyglotic_desktop.ui_next.caption_window.reduced_motion", lambda: False
    )
    try:
        windows.set_cards(False)
        windows.set_two_zones(False)
        windows.set_captioned([("app", APP)])
        windows.set_timing(mode)
        if video:
            windows.set_subtitles((0.045, 0.8))
        shown = windows.windows["app"]
        shown.clock = clock
        shown.set_language("en")
        monkeypatch.setattr(shown, "_readings", lambda *_: readings)
        shown.set_look(
            replace(
                shown.look,
                japanese_reading=JapaneseReading.BOTH,
                reading_lines=("ja",),
                word_links=WordLinks.COLOURS,
                show_source=False,
                show_language=False,
            )
        )
        shown.set_text_size(1.4)
        shown.set_translation_size(1.4)
        shown.resize(600, 520)
        shown.set_presets(
            replace(shown.preset_menu, video_lines_shown=6, long_lines=choice)
        )
        update = CaptionUpdate(
            CaptionId("walk"),
            APP,
            CaptionKind.FINISHED,
            (Clause("山", {TARGET: "Walk."}),),
            Language("ja"),
        )
        shown.receive(update)
        shown.grab()
        clock.now += 3
        shown.grab()
        link = WordLink((0, len(JA)), (0, len(EN)), True, 1.0)
        shown.receive(
            replace(update, clauses=(Clause(JA, {TARGET: EN}, {TARGET: (link,)}),))
        )
        entries: dict[tuple[bool, int], float] = {}
        first_tops: dict[tuple[RowKind, int], float] = {}
        final_tops: dict[tuple[RowKind, int], float] = {}
        for _ in range(140 if video else 2):
            shown.grab()
            if video:
                flow = shown.canvas.video.flow
                assert flow is not None
                for painted in flow.rows():
                    if painted.start:
                        entries.setdefault(
                            (painted.translation, painted.start),
                            painted.y - flow.slots[painted.key].row.y,
                        )
            for _, item, box in shown.canvas.placed:
                for row in item.rows:
                    if row.start:
                        key = row.row.kind, row.start
                        top = box.y() + row.top + row.layout.lineAt(0).y()
                        first_tops.setdefault(key, top)
                        final_tops[key] = top
            clock.now += 0.05 if video else 3
        assert shown.video_enabled == video
        assert bool(shown.canvas.tracks_visible) == video
        rows = [r for _, item, _ in shown.canvas.placed for r in item.rows]
        if mode is CaptionMode.SCROLLING and choice is LongLines.GROUPED:
            # Scrolling pans a single row per language; there is no break to mark.
            flow = shown.canvas.video.flow
            assert flow is not None
            assert {r.translation: r.text for r in flow.rows()} == {False: JA, True: EN}
            assert rows and all(r.layout.lineCount() == 1 for r in rows)
            assert all(not r.layout.text().endswith("...") for r in rows)
            return
        if choice is LongLines.GROUPED:
            ordered = sorted(
                (box.y() + row.top + row.layout.lineAt(0).y(), row.row.kind)
                for _, item, box in shown.canvas.placed
                for row in item.rows
            )
            kinds = [kind for _, kind in ordered]
            assert kinds == sorted(kinds, key=lambda kind: kind is RowKind.TRANSLATION)
        for kind, source in ((RowKind.ORIGINAL, JA), (RowKind.TRANSLATION, EN)):
            side = sorted(
                (r for r in rows if r.row.kind is kind), key=lambda r: r.start
            )
            assert len(side) > 1
            assert "".join(r.row.text for r in side) == source
            for i, row in enumerate(side):
                marked = choice is LongLines.DISPLAY_NEW_LINES and i + 1 < len(side)
                assert row.layout.lineCount() == 1
                assert row.layout.textOption().wrapMode() is QTextOption.WrapMode.NoWrap
                assert row.layout.text() == (
                    row.row.text.rstrip() + "..." if marked else row.row.text
                )
                qt = row.layout.lineAt(0)
                assert qt.naturalTextRect().right() <= shown.canvas.width() + 0.5
                assert (
                    len(row.row.links) == 1
                    and row.row.links[0].link == side[0].row.links[0].link
                )
                if kind is RowKind.ORIGINAL:
                    for band in (row.above, row.below):
                        assert band and (band[-1].text == "...") == marked, (
                            row.row.text,
                            band,
                            marked,
                        )
                if marked:
                    point = qt.naturalTextRect().center()
                    point.setX(qt.naturalTextRect().right() - 1)
                    assert char_under([(row, QPointF())], point) is None
                if i:
                    key = kind, row.start
                    assert first_tops[key] > final_tops[key] + 0.5, (
                        key,
                        first_tops,
                        final_tops,
                    )
                    if video:
                        assert entries[kind is RowKind.TRANSLATION, row.start] > 0.5
    finally:
        windows.close()


@pytest.mark.parametrize("mode", [*OFFERED_MODES, CaptionMode.SCROLLING])
@pytest.mark.parametrize("english_original", [False, True], ids=["ja-en", "en-ja"])
@pytest.mark.parametrize("video", [False, True], ids=["caption", "subtitle"])
def test_painted_pairs_follow_their_word_links(
    qapp: QApplication, mode: CaptionMode, english_original: bool, video: bool
) -> None:
    # Uneven phrase lengths make independently wrapping the two tracks disagree.
    phrases = [
        ("駅", "the railway station"),
        ("橋", "the wooden bridge"),
        ("川", "the river"),
        ("山", "the highest mountain"),
        ("谷", "the valley"),
        ("池", "the pond"),
        ("森", "the forest"),
        ("道", "the winding path"),
        ("村", "the village"),
        ("寺", "the old temple"),
    ]
    ja = "".join(word for word, _ in phrases)
    en = " ".join(phrase for _, phrase in phrases)
    original, meaning = (en, ja) if english_original else (ja, en)
    source, target = (
        (Language("en"), Language("ja"))
        if english_original
        else (Language("ja"), Language("en"))
    )
    links = []
    for i, (_, phrase) in enumerate(phrases):
        pos = en.index(phrase)
        japanese, english = (i, i + 1), (pos, pos + len(phrase))
        a, b = (english, japanese) if english_original else (japanese, english)
        links.append(WordLink(a, b, True, 1.0))

    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_cards(False)
        windows.set_two_zones(False)
        windows.set_captioned([("app", APP)])
        windows.set_timing(mode)
        if video:
            windows.set_subtitles((0.045, 0.8))
        shown = windows.windows["app"]
        clock = Clock()
        shown.clock = clock
        shown.set_language(target)
        shown.set_look(
            replace(
                shown.look,
                show_source=False,
                show_language=False,
                word_links=WordLinks.OFF,
            )
        )
        shown.set_text_size(1.25)
        shown.set_translation_size(1.25)
        shown.resize(600, 560)
        shown.set_presets(replace(shown.preset_menu, video_lines_shown=6))
        update = CaptionUpdate(
            CaptionId("places"),
            APP,
            CaptionKind.FINISHED,
            (Clause(original, {target: meaning}, {target: tuple(links)}),),
            source,
        )
        shown.receive(replace(update, clauses=(Clause(original, {}),)))
        shown.grab()
        clock.now += 2
        shown.receive(update)
        shown.grab()
        shown.set_presets(
            replace(shown.preset_menu, long_lines=LongLines.DISPLAY_NEW_LINES)
        )
        for _ in range(45 if video else 2):
            clock.now += 0.5
            shown.grab()
        rows = sorted(
            (
                (box.y() + row.top + row.layout.lineAt(0).y(), row)
                for _, item, box in shown.canvas.placed
                for row in item.rows
            ),
            key=lambda pair: pair[0],
        )
        assert len(rows) >= 4 and len(rows) % 2 == 0
        assert all(row.layout.lineCount() == 1 for _, row in rows)
        for (_, upper), (_, lower) in zip(rows[::2], rows[1::2], strict=True):
            assert (upper.row.kind, lower.row.kind) == (
                RowKind.ORIGINAL,
                RowKind.TRANSLATION,
            )
            said, translated = upper.row.text.strip(), lower.row.text.strip()
            glyphs, words = (
                (translated, said) if english_original else (said, translated)
            )
            assert " ".join(dict(phrases)[char] for char in glyphs) == words
        assert "".join(row.row.text for _, row in rows[::2]) == original
        assert "".join(row.row.text for _, row in rows[1::2]) == meaning
    finally:
        windows.close()


@pytest.mark.parametrize("choice", LongLines)
@pytest.mark.parametrize("video", [False, True], ids=["caption", "subtitle"])
def test_paced_cards_follow_long_lines(
    qapp: QApplication, video: bool, choice: LongLines
) -> None:
    windows = CaptionWindows(None, MIC, areas)
    clock = Clock()
    try:
        windows.set_captioned([("app", APP)])
        windows.set_timing(CaptionMode.STEADY)
        if video:
            windows.set_subtitles((0.045, 0.8))
        shown = windows.windows["app"]
        shown.clock = clock
        shown.set_language("en")
        shown.resize(600, 520)
        shown.set_text_size(1.4)
        shown.set_translation_size(1.4)
        shown.set_look(replace(shown.look, show_source=False, show_language=False))
        shown.set_presets(replace(shown.preset_menu, long_lines=choice))
        assert shown.deck is not None
        shown.receive(
            CaptionUpdate(
                CaptionId("walk"),
                APP,
                CaptionKind.FINISHED,
                (Clause(JA, {TARGET: EN}),),
                Language("ja"),
            )
        )
        painted = {}
        for _ in range(180):
            shown.check_card_room()
            shown.grab()
            for line, item, _ in shown.canvas.placed:
                for row in item.rows:
                    painted[line.key, row.row.kind, row.start] = row
            clock.now += 0.05
        for kind, source in ((RowKind.ORIGINAL, JA), (RowKind.TRANSLATION, EN)):
            rows = [
                row
                for (key, side, start), row in sorted(painted.items())
                if side is kind
            ]
            assert len(rows) > 1
            assert "".join(row.row.text for row in rows).replace(
                " ", ""
            ) == source.replace(" ", "")
            assert [row.layout.text().endswith("...") for row in rows] == [
                choice is LongLines.DISPLAY_NEW_LINES and i < len(rows) - 1
                for i in range(len(rows))
            ]
    finally:
        windows.close()
