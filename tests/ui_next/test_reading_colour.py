"""Pinyin's colour, and linked words in their link's colour (polyglotic-hq
395; the user's preview-1 feedback, 2026-11-16: "pinyin should have the
option of matching the word link colour (maybe it should be a word link
feature allowing all three pinyin, caption, translation to match the arrow
link colour) ... There should be option to customise pinyin colour").

Settings > Look's Pinyin group: "Pinyin colour: Same as its line / Its
word link's colour / Custom"; the Word links group: "Colour the linked
words too". Each saved; drawn in the link's colour, readable on every
preset's panel. Offscreen, made-up captions and the sample CC-CEDICT."""

from collections.abc import Iterator
from dataclasses import replace
from itertools import cycle

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QTextCharFormat,
    QTextLayout,
)
from PySide6.QtWidgets import QApplication, QWidget
from tests.budget_judge import sampled, within
from tests.ui.fakes import chinese_tools
from tests.ui.test_learning_load_view import LINE, SPANS
from tests.ui.test_marks_on_poured_captions import AT, count
from tests.ui_next.made_up import EN, finished_updates, live_update
from tests.ui_next.test_caption_window import areas
from tests.ui_next.test_reading_lines import made_up
from tests.ui_next.test_reading_lines_shown import LABS, PINYIN, read_window

from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.display import ReadingColour, WordLinks
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_layout import (
    LINK_MARK,
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidRow,
    Mark,
    _coloured_words,
    _reading_colours,
    link_ink,
    span_rects,
)
from polyglotic_desktop.ui_next.caption_marks import LINK_COLORS
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, look_ink
from polyglotic_desktop.ui_next.panels import ReadingLinesPanel, WordLinksPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, WindowChoices
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.views.flow import flow_options
from polyglotic_desktop.ui_next.views.lab import Fill
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    LARGE_TEXT,
    PRESETS,
    VIDEOS,
    _mix,
    contrast,
)

MADE: list[QWidget] = []
ORANGE, VIOLET = QColor(LINK_COLORS[0]), QColor(LINK_COLORS[1])


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def placed(*starts: int) -> tuple[reading_lines.Placed, ...]:
    return tuple(
        reading_lines.Placed(10.0 * n, 0.0, "yóu", start)
        for n, start in enumerate(starts)
    )


# -- the colours -----------------------------------------------------------------------


def test_pinyin_is_its_lines_colour_by_default() -> None:
    row = QColor("#ffd76e")
    links = [(0, 2, ORANGE, 0)]
    assert _reading_colours(placed(0, 1), links, Ink(), row) == []


def test_in_its_word_links_colour_where_a_link_joins_it_else_its_lines() -> None:
    """游戏 linked in orange, 的 not linked, 画面 in violet."""
    ink = Ink(reading_colour=ReadingColour.LINK)
    row = QColor("#ffd76e")
    links = [(0, 2, ORANGE, 0), (3, 5, VIOLET, 1)]
    found = _reading_colours(placed(0, 1, 2, 3, 4), links, ink, row)
    assert [c.name() if c else None for c in found] == [
        ORANGE.name(), ORANGE.name(), None, VIOLET.name(), VIOLET.name(),
    ]  # fmt: skip


def test_with_no_links_shown_its_lines_colour() -> None:
    ink = Ink(reading_colour=ReadingColour.LINK)
    assert _reading_colours(placed(0, 1), [], ink, QColor("#ffffff")) == []


def _is_grey(colour: QColor) -> bool:
    return (
        max(colour.red(), colour.green(), colour.blue())
        - min(colour.red(), colour.green(), colour.blue())
        <= 6
    )


def test_grey_where_no_link_joins_it_and_its_links_colour_where_one_does() -> None:
    """Polyglotic-hq 532 (the user, 2026-11-19: "the default pinyin/
    alternate reading font colour ... (maybe even arrowlink default)
    should be greyish"): 游戏 linked in orange, 的 not linked - its
    reading grey, under the gold of its line, not the line's gold."""
    ink = Ink(reading_colour=ReadingColour.GREY, panel="#0a0c10")
    row = QColor("#ffd76e")
    found = _reading_colours(placed(0, 1, 2), [(0, 2, ORANGE, 0)], ink, row)
    assert [c.name() for c in found[:2] if c] == [ORANGE.name(), ORANGE.name()]
    assert found[2] is not None and _is_grey(found[2])
    assert found[2].lightness() < QColor("#ffffff").lightness()
    # word links off: every reading grey
    plain = _reading_colours(placed(0, 1), [], ink, QColor("#ffffff"))
    assert len(plain) == 2 and all(c is not None and _is_grey(c) for c in plain)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_the_grey_is_quieter_than_its_text_and_still_reads_on_every_panel(
    preset: object,
) -> None:
    """Between the panel and what was said - light on dark panels, dark on
    Paper's cream - and drawn at a reading's ink, 4.5:1 on its panel."""
    from polyglotic_desktop.ui_next.views.presets import ColourPreset
    from polyglotic_desktop.ui_next.views.tone import reading_grey

    assert isinstance(preset, ColourPreset)
    grey = reading_grey(preset.background, preset.original)
    assert _is_grey(QColor(grey))
    assert contrast(grey, preset.background) < contrast(
        preset.original, preset.background
    )
    ink = Ink(
        QColor(preset.original),
        QColor(preset.translation),
        reading_colour=ReadingColour.GREY,
        panel=preset.background,
        panel_opacity=preset.opacity,
    )
    (drawn,) = _reading_colours(placed(0), [], ink, QColor(preset.original))
    assert drawn is not None
    seen = _mix(preset.background, drawn.name(), reading_lines.ALPHA)
    assert contrast(seen, preset.background) >= AA_TEXT - 0.05, preset.key


def test_a_custom_colour_for_every_reading_as_faint_as_its_line() -> None:
    ink = Ink(reading_colour=ReadingColour.CUSTOM, reading=QColor("#9ad0ff"))
    row = QColor("#ffffff")
    row.setAlphaF(0.5)  # an older caption
    found = _reading_colours(placed(0, 1, 2), [(0, 1, ORANGE, 0)], ink, row)
    assert {c.name() for c in found if c} == {"#9ad0ff"}
    assert all(
        c is not None and c.alphaF() == pytest.approx(0.5, abs=0.01) for c in found
    )


def test_linked_words_take_their_links_colour() -> None:
    ink = Ink()
    words = _coloured_words([(3, 5, VIOLET, 1), (0, 2, ORANGE, 0)], ink, QColor("#fff"))
    assert [(start, end, c.name()) for start, end, c in words] == [
        (0, 2, ORANGE.name()),
        (3, 5, VIOLET.name()),
    ]


LAYOUTS = {
    "rows": CaptionStyle(),
    "stacked": CaptionStyle(fill=Fill.STACKED),
    "paired": CaptionStyle(fill=Fill.PAIRED),
    "new-paired": CaptionStyle(flow=flow_options(Fill.PAIRED)),
    "new-run-on": CaptionStyle(flow=flow_options(Fill.PAIRED, run_on=True)),
    "new-lined-up": CaptionStyle(flow=flow_options(Fill.PAIRED, aligned=True)),
    "new-stacked": CaptionStyle(flow=flow_options(Fill.STACKED)),
}


WORDS = ["研究", "电脑", "游戏", "足球"]
COLOURS = [QColor(c) for c in LINK_COLORS[: len(WORDS)]]


def side_by_side(
    layout: str, width: int, pinyin: bool, readings: ReadingColour | None = None
) -> tuple[QImage, LaidRow]:
    """`WORDS` linked side by side, each in its link's colour (`COLOURS`),
    painted in `layout` at `width` (0: narrow, poured or wrapped over two
    lines), the readings' colour `readings` (None: Ink's own): the picture
    and the row they're in."""
    view = CaptionLines((APP,), Language("en"), keep=10)
    view.set_models(True)
    view.apply(finished("a", clause(LINE, "This person studies computer games.")))
    line = view.lines[0]

    def marks(_line: object, row: int) -> list[Mark]:
        found: list[Mark] = []
        if row != 0:
            return found
        for n, word in enumerate(WORDS):
            format_ = QTextCharFormat()
            format_.setUnderlineColor(COLOURS[n])
            format_.setProperty(LINK_MARK, n)
            found.append((*SPANS[word], format_))
        return found

    style = replace(LAYOUTS[layout], reading_lines=frozenset({"zh"} if pinyin else ()))
    engine = CaptionLayout(style, readings=made_up)
    if not width:  # narrow: poured or wrapped over two lines
        widest = engine.laid(line, 4000, 1.0).rows[0].layout.lineAt(0)
        width = max(40, int(widest.naturalTextWidth() * 0.6))
    laid = engine.laid(line, width, 1.0)
    image = QImage(width + 20, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("#101014"))
    painter = QPainter(image)
    ink = Ink(
        QColor("#ffffff"),
        QColor("#ffd76e"),
        said_in_link_colours=True,
        panel="#101014",
    )
    if readings is not None:
        ink = replace(ink, reading_colour=readings)
    engine.paint(painter, line, laid, AT, ink, marks)
    painter.end()
    return image, next(row for row in laid.rows if row.index == 0)


@pytest.mark.parametrize("pinyin", [False, True], ids=["plain", "pinyin"])
@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("width", [4000, 0], ids=["one-line", "narrow"])
def test_linked_words_side_by_side_are_each_in_their_links_colour(
    qapp: QApplication, layout: str, width: int, pinyin: bool
) -> None:
    """Every word linked (Chinese has no spaces between them): 研究, 电脑,
    游戏 and 足球 side by side, each in its own link's colour, in every
    layout. Qt skipped a coloured range touching one drawn already, so with
    pinyin above (the characters spread out to fit it) a word after a
    linked word was drawn plain - 摄影师 after 撞倒 in 395's own picture of
    real captions - until each range was drawn whole (#796's
    `drawn_whole`)."""
    image, row = side_by_side(layout, width, pinyin)
    for word, colour in zip(WORDS, COLOURS, strict=True):
        rects = span_rects(row.layout, *SPANS[word])
        assert count(image, rects, row.top, colour) > 8, (word, colour.name(), width)


@pytest.mark.parametrize("pinyin", [False, True], ids=["plain", "pinyin"])
@pytest.mark.parametrize("layout", LAYOUTS)
def test_coloured_words_are_drawn_once_not_a_format_range_each(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, layout: str, pinyin: bool
) -> None:
    """Each glyph drawn once, in its word's colour, and the readings each
    in theirs (437). Qt's `QTextLayout.draw` with a format range a word
    draws the word's line again under a clip of its own, a word at a time:
    with both sides coloured and pinyin in its links' colours, a run-on
    live update went over a new caption's 4 ms on CI (median 6.0 ms, the
    PC 32 % busy, 2026-11-17)."""
    ranges: list[int] = []
    draw = QTextLayout.draw

    def counted(layout: QTextLayout, *args: object) -> None:
        if len(args) > 2 and args[2]:  # (painter, at, selections, ...)
            ranges.append(len(args[2]))  # type: ignore[arg-type]
        draw(layout, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(QTextLayout, "draw", counted)
    image, row = side_by_side(layout, 4000, pinyin, ReadingColour.LINK)
    assert ranges == []
    for word, colour in zip(WORDS, COLOURS, strict=True):  # and drawn
        rects = span_rects(row.layout, *SPANS[word])
        assert count(image, rects, row.top, colour) > 8, (word, colour.name())


SAID_WORDS = {"研究": 0, "电脑": 1}
TRANSLATION_WORDS = {"studies": 0, "computer": 1}


@pytest.mark.parametrize("layout", ["rows", "new-paired", "new-run-on"])
@pytest.mark.parametrize(
    ("said", "translation"),
    [(False, False), (True, False), (False, True), (True, True)],
    ids=["neither", "said-only", "translation-only", "both"],
)
def test_each_side_is_coloured_on_its_own(
    qapp: QApplication, layout: str, said: bool, translation: bool
) -> None:
    """Polyglotic-hq 431 (the user, 2026-11-17: "toggleable separately"):
    what was said's linked words in their link's colour, the
    translation's, both or neither - the other side's in its own row's
    colour, its underline still the link's."""
    text = "This person studies computer games."
    view = CaptionLines((APP,), Language("en"), keep=10)
    view.set_models(True)
    view.apply(finished("a", clause(LINE, text)))
    line = view.lines[0]
    colours = [ORANGE, VIOLET]
    spans = {
        0: {w: (*SPANS[w], n) for w, n in SAID_WORDS.items()},
        1: {
            w: (text.index(w), text.index(w) + len(w), n)
            for w, n in TRANSLATION_WORDS.items()
        },
    }

    def marks(_line: object, row: int) -> list[Mark]:
        found: list[Mark] = []
        for start, end, n in spans.get(row, {}).values():
            format_ = QTextCharFormat()
            format_.setUnderlineColor(colours[n])
            format_.setProperty(LINK_MARK, n)
            found.append((start, end, format_))
        return found

    engine = CaptionLayout(LAYOUTS[layout])
    laid = engine.laid(line, 900, 1.0)
    image = QImage(920, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor("#101014"))
    painter = QPainter(image)
    ink = Ink(
        QColor("#ffffff"),
        QColor("#ffd76e"),
        said_in_link_colours=said,
        translation_in_link_colours=translation,
        panel="#101014",
    )
    engine.paint(painter, line, laid, AT, ink, marks)
    painter.end()
    rows = {row.index: row for row in laid.rows}
    for index, on, own in ((0, said, "#ffffff"), (1, translation, "#ffd76e")):
        row = rows[index]
        for word, (start, end, n) in spans[index].items():
            rects = [
                r.adjusted(0, 0, 0, -r.height() * 0.25)  # the glyphs, not the line
                for r in span_rects(row.layout, start, end)
            ]
            coloured = count(image, rects, row.top, colours[n])
            plain = count(image, rects, row.top, QColor(own))
            if on:
                assert coloured > 8 and plain < coloured, (word, coloured, plain)
            else:
                assert plain > 8 and coloured < plain, (word, coloured, plain)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
@pytest.mark.parametrize("alpha", [1.0, 0.6], ids=["newest", "older"])
def test_every_link_colour_reads_on_every_presets_panel(
    preset: object, alpha: float
) -> None:
    """Readable over a game: a link's colour as a word or its pinyin is
    drawn in it - as faint as it's drawn (an older caption, a reading's
    own faintness) - reaches 4.5:1 on the panel drawn solid, on Paper's
    cream too, where the colours (picked for dark panels) are darkened.
    The lab's contrast check found 2.9:1 on Paper before (395)."""
    background = preset.background  # type: ignore[attr-defined]
    ink = Ink(panel=background)
    row = QColor("#ffffff")
    row.setAlphaF(alpha)
    for colour in LINK_COLORS:
        for faint in (1.0, reading_lines.ALPHA):
            drawn = link_ink(QColor(colour), ink, row, faint)
            seen = _mix(background, drawn.name(), drawn.alphaF() * faint)
            assert contrast(seen, background) >= AA_TEXT, (colour, background, faint)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
@pytest.mark.parametrize("alpha", [1.0, 0.6], ids=["newest", "older"])
@pytest.mark.parametrize("video", VIDEOS, ids=["light-video", "black-video"])
def test_every_link_colour_reads_through_every_presets_panel(
    preset: object, alpha: float, video: str
) -> None:
    """Polyglotic-hq 431: a linked word, or its pinyin, in its link's
    colour reads at large text's 3:1 on its panel at the panel's own
    opacity over a light or a black video (284's videos). On Classic's
    72 % over a light video, #e040fb was at 2.4:1 before."""
    background = preset.background  # type: ignore[attr-defined]
    opacity = preset.opacity  # type: ignore[attr-defined]
    seen = _mix(video, background, opacity)
    ink = Ink(panel=background, panel_opacity=opacity)
    row = QColor("#ffffff")
    row.setAlphaF(alpha)
    for faint in (1.0, reading_lines.ALPHA):
        for colour in LINK_COLORS:
            drawn = link_ink(QColor(colour), ink, row, faint)
            found = contrast(_mix(seen, drawn.name(), alpha * faint), seen)
            assert found >= LARGE_TEXT, (colour, faint, found)


def test_a_solid_panel_keeps_the_shades_it_had() -> None:
    """At 100 % there is no video behind it: the shades are 395's."""
    ink = Ink(panel="#000000", panel_opacity=1.0)
    assert all(
        link_ink(QColor(c), ink, QColor("#ffffff")).name() == c for c in LINK_COLORS
    )


def test_on_a_dark_panel_the_link_colours_are_as_they_are() -> None:
    ink = Ink(panel="#0a0c10")
    assert all(
        link_ink(QColor(c), ink, QColor("#ffffff")).name() == c for c in LINK_COLORS
    )


def test_readings_are_drawn_in_their_own_colours(qapp: QApplication) -> None:
    """`reading_lines.draw` with a colour per reading: the first in orange,
    the second in its row's white."""
    font = QFont()
    font.setPixelSize(20)
    readings = (
        reading_lines.Placed(4.0, 24.0, "hé", 0),
        reading_lines.Placed(60.0, 24.0, "hé", 1),
    )
    image = QImage(120, 32, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    reading_lines.draw(
        painter, readings, font, QPointF(0, 0), QColor("#ffffff"), [ORANGE, None]
    )
    painter.end()

    def hues(x0: int, x1: int) -> set[str]:
        found = set()
        for x in range(x0, x1):
            for y in range(32):
                c = image.pixelColor(x, y)
                if c.red() > 200 and c.green() > 120:
                    found.add("orange" if c.blue() < 120 else "white")
        return found

    assert hues(0, 50) == {"orange"}
    assert hues(56, 120) == {"white"}


# -- in a caption window ---------------------------------------------------------------


def test_a_caption_windows_ink_follows_the_look(qapp: QApplication) -> None:
    look = CaptionLook(
        word_links=WordLinks.COLOURS,
        reading_lines=("zh",),
        reading_colour=ReadingColour.LINK,
        said_in_link_colours=True,
        translation_in_link_colours=False,
    )
    window = CaptionWindow(
        "Discord.exe", APP, WindowChoices(), SourceLabel("Discord", "#4dd0e1"),
        mic=MIC, areas=areas, learner=chinese_tools(),
    )  # fmt: skip
    MADE.append(window)
    window.set_look(look)
    window.view.apply(finished("a"))
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    window.canvas.repaint()  # drawn with it, no error
    ink = window.canvas.ink
    assert ink.reading_colour is ReadingColour.LINK and ink.said_in_link_colours
    assert not ink.translation_in_link_colours
    assert ink.panel_opacity == look.opacity  # shades read through the panel (431)
    assert ink.panel == look.background
    assert look_ink(Ink(), replace(look, reading_colour=ReadingColour.CUSTOM)).reading


# -- the settings ----------------------------------------------------------------------


def test_the_choices_are_saved_and_come_back() -> None:
    for said, translation in ((True, False), (False, True)):
        look = CaptionLook(
            reading_colour=ReadingColour.CUSTOM,
            reading_custom="#a5f28a",
            said_in_link_colours=said,
            translation_in_link_colours=translation,
        )
        stored = AppSettings.from_stored(look_settings(look)).to_stored()
        back = caption_look(AppSettings.from_stored(stored))
        assert (
            back.reading_colour,
            back.reading_custom,
            back.said_in_link_colours,
            back.translation_in_link_colours,
        ) == (ReadingColour.CUSTOM, "#a5f28a", said, translation)


def test_the_previews_one_switch_comes_back_as_both() -> None:
    """0.1.7's previews saved one switch for both sides (395): on, it's
    both on; once either is saved, that wins."""
    look = caption_look(AppSettings.from_stored({"link_words_coloured": True}))
    assert look.said_in_link_colours and look.translation_in_link_colours
    off = caption_look(AppSettings.from_stored({"link_words_coloured": False}))
    assert not off.said_in_link_colours and not off.translation_in_link_colours
    chosen = AppSettings.from_stored(
        {"link_words_coloured": True, "translation_in_link_colours": False}
    )
    assert chosen.said_in_link_colours and not chosen.translation_in_link_colours


def test_on_and_its_link_colour_until_chosen_and_wrong_values_are_the_default() -> None:
    """A new install's: linked words and pinyin in their link's colour, so
    word links turned on show a word, its pinyin and its translation alike
    (the user, 2026-11-17, polyglotic-hq 446: "default this setting to be
    on"); with word links off they change nothing."""
    assert caption_look(AppSettings()).reading_colour is ReadingColour.GREY  # 532
    assert caption_look(AppSettings()).said_in_link_colours
    assert caption_look(AppSettings()).translation_in_link_colours
    found = AppSettings.from_stored(
        {"reading_colour": "rainbow", "reading_custom_color": "blue"}
    )
    assert found.reading_colour == "grey" and found.reading_custom_color == "#9ad0ff"


def test_the_pinyin_group_offers_the_three_and_custom_shows_its_colour(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook(reading_lines=("zh",)))
    panel = ReadingLinesPanel(view, notes=True)
    MADE.append(panel)
    assert panel.custom_row.isHidden()
    panel.reading_colour.changed.emit(ReadingColour.LINK.value)
    assert view.value.reading_colour is ReadingColour.LINK
    assert panel.custom_row.isHidden()
    panel.reading_colour.changed.emit(ReadingColour.CUSTOM.value)
    assert not panel.custom_row.isHidden()
    panel.reading_custom.chosen.emit("#ff9ecf")  # a swatch, typed or picked
    assert view.value.reading_custom == "#ff9ecf"
    assert view.value.reading_colour is ReadingColour.CUSTOM
    view.set_reading_line("zh", False)
    assert not panel.reading_colour.isEnabled()  # pinyin off: nothing to colour


UNCOLOURED = CaptionLook(said_in_link_colours=False, translation_in_link_colours=False)
"""Linked words in their line's colour, both sides (each on by default
since 446)."""


def test_the_word_links_group_colours_the_linked_words(qapp: QApplication) -> None:
    view = LookView(replace(UNCOLOURED, word_links=WordLinks.COLOURS))
    panel = WordLinksPanel(view, notes=True)
    MADE.append(panel)
    said, translation = panel.said_in_link_colours, panel.translation_in_link_colours
    assert not said.isChecked() and not translation.isChecked()
    translation.click()  # the translation's alone (431)
    assert view.value.translation_in_link_colours
    assert not view.value.said_in_link_colours
    said.click()
    translation.click()
    assert view.value.said_in_link_colours
    assert not view.value.translation_in_link_colours
    view.set_word_links(WordLinks.OFF)
    assert not said.isEnabled() and not translation.isEnabled()  # nothing to colour


# -- the cost --------------------------------------------------------------------------


def test_a_live_update_with_both_sides_coloured_is_within_a_new_captions_budget(
    qapp: QApplication,
) -> None:
    """431: run on, with pinyin and word links as colours, both sides'
    linked words in their links' colours, within today's budget for a new
    caption. Qt's format range a word cost about 1 ms more than off, and
    went over on CI (2026-11-17); each glyph drawn once costs about 0.3 ms
    (437: medians 1.8-2.3 ms here, 2.9-3.2 before)."""
    look = replace(
        PINYIN,
        word_links=WordLinks.COLOURS,
        said_in_link_colours=True,
        translation_in_link_colours=True,
        reading_colour=ReadingColour.LINK,
    )
    window = read_window(qapp, LABS["run-on"], 150, look)
    MADE.append(window)
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
    updates = cycle(grown)

    def arrive() -> None:
        window.view.apply(next(updates))
        window.apply_changed(new_caption=False)
        window.canvas.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 12))


def test_an_untouched_reading_colour_follows_the_new_grey_and_a_choice_stays() -> None:
    """Every 0.1.8 and 0.1.9 settings file holds "link", chosen or not: one
    whose record of changes doesn't name it takes today's default, Grey
    (532, decision 0220); one that names it keeps the choice."""
    untouched = AppSettings.from_stored({"reading_colour": "link", "changed": []})
    assert untouched.reading_colour == ReadingColour.GREY.value
    chosen = AppSettings.from_stored(
        {"reading_colour": "link", "changed": ["reading_colour"]}
    )
    assert chosen.reading_colour == ReadingColour.LINK.value
