"""What a caption window marks (`ui_next.caption_marks`): Learning's
highlights and word links, as today's overlay - drawn at paint time, kept
per line, forgotten on a Learning change. Made-up captions, the sample
dictionary. (Here rather than in tests/ui_next: the learning tools are
today's `ui.learning.LearningTools`, which `main` hands over.)"""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import english_sample
from tests.ui.fakes import chinese_tools, tools_for

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.captions import (
    Clause,
    Language,
    WordClass,
    WordLink,
)
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished, live
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_layout import LINK_MARK
from polyglotic_desktop.ui_next.caption_marks import (
    IN_DECK,
    LINK_COLORS,
    CaptionMarks,
    Panel,
    link_colour,
    link_colours,
)
from polyglotic_desktop.ui_next.caption_window import marks_panel
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.views.presets import (
    BY_KEY,
    LOOKS,
    PRESETS,
    _mix,
    ciede2000,
    contrast,
    with_look,
)
from polyglotic_desktop.ui_next.views.tone import caption_text_colour
from polyglotic_desktop.ui_next.word_classes import (
    APART_FROM_TEXT,
    CLASS_ALTERNATES,
    CLASS_COLOURS,
    CLASS_CONTRAST,
    class_backing,
    class_colour,
)

EN = Language("en")


def marked(
    marks: object, style: QTextCharFormat.UnderlineStyle
) -> list[tuple[int, int, str]]:
    assert isinstance(marks, list | tuple)
    found = []
    for start, end, format_ in marks:
        assert isinstance(format_, QTextCharFormat)
        if format_.underlineStyle() is style:
            found.append((start, end, format_.underlineColor().name()))
    return found


def dotted(marks: object) -> list[tuple[int, int, str]]:
    """Dots: words new to the learner."""
    return marked(marks, QTextCharFormat.UnderlineStyle.DotLine)


def dashed(marks: object) -> list[tuple[int, int, str]]:
    """Dashes: words in the deck - a shape of their own, so a colour-blind
    learner tells them from new words (135, 2026-11-07)."""
    return marked(marks, QTextCharFormat.UnderlineStyle.DashUnderline)


def test_words_in_the_deck_are_dashed_on_finished_captions_only(
    qapp: QApplication,
) -> None:
    tools = chinese_tools()
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑又卡了，", "My computer froze,")))
    marks = CaptionMarks(tools)
    line = view.lines[0]
    assert (2, 4, IN_DECK) in dashed(marks(line, 0))
    assert (2, 4, IN_DECK) not in dotted(marks(line, 0))  # not dots in green
    view.apply(live("b", clause("电脑")))
    assert dashed(marks(view.lines[-1], 0)) == []  # a live update keeps changing


def test_word_introductions_off_dots_no_word_and_a_change_marks_again(
    qapp: QApplication,
) -> None:
    """Learning's word introductions (polyglotic-hq 262): Off dots no new
    word - the deck's dashes stay - and a change of choice works the
    line's marks out again (none kept from before)."""
    tools = chinese_tools()
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑又卡了，", "My computer froze,")))
    marks = CaptionMarks(tools)
    line = view.lines[0]
    marks.set_look(WordLinks.OFF, WordIntroductions.EVERY)
    assert dotted(marks(line, 0))  # every new word: some dots
    marks.set_look(WordLinks.OFF, WordIntroductions.OFF)
    assert dotted(marks(line, 0)) == []
    assert (2, 4, IN_DECK) in dashed(marks(line, 0))
    marks.set_look(WordLinks.OFF, WordIntroductions.EVERY)
    assert dotted(marks(line, 0))


def test_a_learning_change_forgets_the_marks_but_exposures_dont(
    qapp: QApplication,
) -> None:
    tools = chinese_tools()
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑又卡了，", "My computer froze,")))
    marks = CaptionMarks(tools)
    line = view.lines[0]
    before = dotted(marks(line, 0)), dashed(marks(line, 0))
    assert not marks.learning_changed(Changed.EXPOSURES.value)
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    assert (dotted(marks(line, 0)), dashed(marks(line, 0))) == before  # kept until told
    assert marks.learning_changed(Changed.STATUSES.value)
    assert (2, 4, IN_DECK) in dashed(marks(line, 0))


def test_word_links_are_underlined_in_their_links_colour(qapp: QApplication) -> None:
    view = CaptionLines(
        (APP,), EN, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    view.apply(
        finished("a", clause("我的电脑", "My computer", (("电脑", "computer"),)))
    )
    marks = CaptionMarks(None)  # no learner: links only
    line = view.lines[0]
    assert all(not marks(line, row) for row in range(len(line.rows)))  # links off
    marks.set_look(WordLinks.COLOURS, WordIntroductions.A_FEW)
    linked = [m for row in range(len(line.rows)) for m in marks(line, row)]
    # the layout underlines them below the descenders (249, F14), not Qt
    assert all(
        f.hasProperty(LINK_MARK)
        and f.underlineStyle() is QTextCharFormat.UnderlineStyle.NoUnderline
        for _, _, f in linked
    )
    assert len(linked) == sum(len(row.links) for row in line.rows) == 2


def test_a_word_class_link_uses_one_colour_clear_of_both_sides_in_every_look(
    qapp: QApplication,
) -> None:
    """Mismatched taggers still produce one safe colour in every shipped look."""
    link = WordLink(
        (0, 11),
        (0, 2),
        True,
        0.9,
        original_pos=WordClass.ADVERB,
        translation_pos=WordClass.VERB,
    )
    linked = Clause("discoveries", {EN: "发现"}, {EN: (link,)})
    view = CaptionLines(
        (APP,), EN, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    view.apply(finished("class-pair", linked))
    base = caption_look(AppSettings())
    looks = [base, *(with_look(base, look.key) for look in LOOKS)]
    looks.extend(
        replace(
            base,
            original=preset.original,
            translation=preset.translation,
            background=preset.background,
            opacity=preset.opacity,
        )
        for preset in PRESETS
    )
    for look in looks:
        marks = CaptionMarks(None)
        panel = replace(marks_panel(look), colour_links_by_word_class=True)
        marks.set_look(WordLinks.COLOURS, WordIntroductions.A_FEW, panel)
        colours = [
            format_.underlineColor().name()
            for row in range(len(view.lines[0].rows))
            for _, _, format_ in marks(view.lines[0], row)
        ]
        assert len(colours) == 2 and len(set(colours)) == 1
        for row, colour in zip(view.lines[0].rows, colours, strict=True):
            text = caption_text_colour(
                panel.own(row.kind), panel.background, panel.vibrance
            )
            assert ciede2000(colour, text) >= APART_FROM_TEXT, (look, row.kind)


def test_hover_pairing_colours_skip_classics_gold_neighbours() -> None:
    classic = BY_KEY["classic"]
    panel = Panel(classic.background, classic.original, classic.translation)
    assert link_colours(panel) == tuple(
        c for c in LINK_COLORS if c not in ("#ff9f43", "#acbf60")
    )


@pytest.mark.parametrize(
    "preset", [use_presets.EVERYDAY, use_presets.LEARNING, use_presets.VIDEO]
)
@pytest.mark.parametrize("vibrance", [-100, 0, 100])
def test_a_links_colour_is_never_its_lines_own(preset: str, vibrance: int) -> None:
    look = caption_look(use_presets.chosen(AppSettings(), preset))
    looks = [look, *(with_look(look, recommended.key) for recommended in LOOKS)]
    looks.extend(
        replace(
            look,
            original=p.original,
            translation=p.translation,
            background=p.background,
            opacity=p.opacity,
        )
        for p in PRESETS
    )
    for chosen in looks:
        panel = marks_panel(replace(chosen, vibrance=vibrance))
        for row in (RowKind.ORIGINAL, RowKind.TRANSLATION):
            text = caption_text_colour(panel.own(row), panel.background, vibrance)
            swatches = {
                pos: class_colour(pos, panel.background, panel.opacity, text)
                for pos in CLASS_COLOURS
            }
            assert ciede2000(swatches[WordClass.NOUN], swatches[WordClass.NUMBER]) >= 20
            assert ciede2000(swatches[WordClass.PRONOUN], swatches[None]) >= 25
            for pos, swatch in swatches.items():
                assert swatch in (CLASS_COLOURS[pos], *CLASS_ALTERNATES[pos]), (
                    panel,
                    row,
                    pos,
                )
                assert ciede2000(swatch, text) >= APART_FROM_TEXT, (panel, row, pos)
                backing = class_backing(swatch, panel.background, panel.opacity)
                if panel.opacity == 0:
                    assert backing is not None
                backdrops = (
                    [backing]
                    if backing is not None
                    else [
                        _mix(scene, panel.background, panel.opacity)
                        for scene in ("#000000", "#ffffff")
                    ]
                )
                assert all(
                    contrast(swatch, under) >= CLASS_CONTRAST for under in backdrops
                )


@pytest.mark.parametrize("style", [WordLinks.COLOURS, WordLinks.ARROWS])
def test_classified_and_unclassified_links_keep_every_endpoint(
    qapp: QApplication, style: WordLinks
) -> None:
    pairs = (("Il", "He"), ("mange", "eats"), ("vite", "quickly"), ("pommes", "apples"))
    plain = clause("Il mange vite des pommes", "He eats apples quickly", pairs)
    classes = (WordClass.PRONOUN, WordClass.VERB, WordClass.ADVERB, WordClass.NOUN)
    tagged = replace(
        plain,
        links={
            EN: tuple(
                replace(link, original_pos=pos, translation_pos=pos)
                for link, pos in zip(plain.links[EN], classes, strict=True)
            )
        },
    )
    view = CaptionLines((APP,), EN, keep=10, options=DisplayOptions(word_links=style))
    view.apply(finished("plain", plain, language=Language("fr")))
    view.apply(finished("tagged", tagged, language=Language("fr")))
    marks = CaptionMarks(None)
    panel = panel_of("classic")
    marks.set_look(style, WordIntroductions.A_FEW, panel)
    first, second = view.lines
    for index, row in enumerate(first.rows):
        missing, present = marks(first, index), marks(second, index)
        expected = [(link.start, link.end, link.link) for link in row.links]
        assert len(expected) == len(pairs)
        for drawn in (missing, present):
            assert [
                (start, end, fmt.property(LINK_MARK)) for start, end, fmt in drawn
            ] == expected
        expected_colours = [link_colour(panel, link.link) for link in row.links]
        for drawn in (missing, present):
            assert [
                fmt.underlineColor().name() for _, _, fmt in drawn
            ] == expected_colours


def test_a_new_caption_with_highlights_within_its_budget(qapp: QApplication) -> None:
    """Marks are worked out for a line when it's first painted: a new
    caption, highlights and all, still within NEW_CAPTION (8 ms), timed as
    the other budget tests are (`tests/budget_judge.py`)."""
    from tests.budget_judge import sampled, within
    from tests.ui_next.made_up import finished_updates

    from polyglotic_desktop.core.listening.sources import SourceLabel
    from polyglotic_desktop.perf import budgets
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow
    from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
    from polyglotic_desktop.ui_next.views.placement import Rect

    window = CaptionWindow(
        "lab",
        APP,
        WindowChoices(),
        SourceLabel("Discord", "#4dd0e1"),
        areas=lambda: [Rect(0, 0, 1920, 1040)],
        learner=chinese_tools(),
    )
    for update in finished_updates(150):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    window.canvas.repaint()
    arriving = iter(finished_updates(40, start=150))  # 10, warmed up, twice

    def arrive() -> None:
        window.view.apply(next(arriving))
        window.apply_changed(new_caption=True)
        window.canvas.repaint()

    try:
        within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 10))
    finally:
        window.close()


def test_no_learning_marks_until_the_dictionary_is_ready(qapp: QApplication) -> None:
    """Before the word split's data is read (a thread at start), a line is
    drawn without highlights rather than reading it on the Qt thread - and
    not kept, so it's marked at the first paint after `dictionary_ready`."""
    tools = chinese_tools(ready=False)
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.set_status(computer, WordStatus.LEARNING)
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑又卡了，", "My computer froze,")))
    marks = CaptionMarks(tools)
    line = view.lines[0]
    assert dashed(marks(line, 0)) == [] and not tools.ready
    tools.dictionary.prepare()  # type: ignore[union-attr]
    assert tools.ready
    assert (2, 4, IN_DECK) in dashed(marks(line, 0))


def test_only_rows_in_the_language_being_learned_are_marked(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 174: a learner of English hearing Spanish got English
    "unfamiliar" marks on the Spanish row - the English dictionary claims
    de, el, que (here "he", Spanish for "I have"). The Spanish row has none
    now; the English translation row keeps its marks."""
    tools = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    he = tools.lookup("he")[0].entry_id
    tools.vocabulary.set_status(he, WordStatus.LEARNING)  # in the deck: dashes
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(
        finished("a", clause("Yo he comido.", "He has eaten."), language=Language("es"))
    )
    marks = CaptionMarks(tools)
    line = view.lines[0]
    assert [row.language for row in line.rows] == ["es", "en"]
    assert dashed(marks(line, 0)) == []  # the Spanish row: nothing
    assert [(s, e) for s, e, _ in dashed(marks(line, 1))] == [(0, 2)]  # "He"


def saved_in(tools: LearningTools, word: str, category: str = "saved") -> str:
    """`word` saved into `category`: its category's colour."""
    entry = tools.lookup(word)[0]
    tools.vocabulary.save(
        entry.entry_id, entry.headword, entry.traditional, entry.reading, "",
        category, LookupContext(""),
    )  # fmt: skip
    found = tools.vocabulary.category(category)
    assert found is not None
    return found.color


def colours(marks: object) -> list[tuple[int, int, str, QColor | None]]:
    """The marks drawn in a colour of their own - saved words - with the
    tint behind any (None: none)."""
    assert isinstance(marks, list | tuple)
    return [
        (
            start,
            end,
            format_.foreground().color().name(),
            format_.background().color()
            if format_.background().style() is not Qt.BrushStyle.NoBrush
            else None,
        )
        for start, end, format_ in marks
        if format_.foreground().style() is not Qt.BrushStyle.NoBrush
    ]


def test_a_saved_word_is_in_its_category_colour_on_classic(qapp: QApplication) -> None:
    """Classic (the default): exactly the category's colour, nothing behind
    it - as before 305."""
    tools = chinese_tools()
    blue = saved_in(tools, "电脑")
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑又卡了，", "My computer froze,")))
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, panel_of("classic"))
    assert colours(marks(view.lines[0], 0)) == [(2, 4, blue, None)]


def test_saved_words_and_dots_are_readable_on_papers_cream(qapp: QApplication) -> None:
    """Polyglotic-hq 305: the categories' colours are picked for dark
    panels, and on Paper's cream a saved word showed at 1.4-2.2:1 - "Saved"
    a pale blue that hardly read as a word, let alone a saved one. Now as
    readable as text (4.5:1), the dots under new words as a mark (3:1)."""
    tools = chinese_tools()
    saved_in(tools, "电脑")
    saved_in(tools, "游戏", "tricky")
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑又卡了，", "My computer froze,")))
    view.apply(finished("b", clause("我们打游戏吧", "Let's play games")))
    paper = panel_of("paper")
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.EVERY, paper)
    shown = [c for line in view.lines for c in colours(marks(line, 0))]
    assert len(shown) == 2
    assert all(contrast(colour, paper.background) >= 4.5 for _, _, colour, _ in shown)
    dots = [d for line in view.lines for d in dotted(marks(line, 0))]
    assert dots and all(contrast(c, paper.background) >= 3.0 for _, _, c in dots)


def test_a_saved_word_in_its_rows_own_colour_gets_a_tint_behind_it(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 305: on Teletext a Chinese translation row is cyan, and
    a word saved in "Saved" (blue) in it looked like the rest of the row. A
    tint of its colour behind it says it's saved; in the white row above,
    its colour alone does."""
    tools = chinese_tools()
    blue = saved_in(tools, "电脑")
    hant = Language("zh-hant")
    view = CaptionLines((APP,), hant, keep=10)
    view.apply(
        finished(
            "a",
            clause("My computer froze again.", "我的電腦又當機了。", into=hant),
            language=EN,
        )
    )
    view.apply(
        finished("b", clause("我的电脑又卡了，", "我的電腦又當機了，", into=hant))
    )
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, panel_of("teletext"))
    english, chinese = view.lines
    assert [row.kind for row in english.rows] == [RowKind.ORIGINAL, RowKind.TRANSLATION]
    (start, end, colour, tint), *_ = colours(marks(english, 1))
    assert (start, end, colour) == (2, 4, blue)
    assert tint is not None and tint.name() == blue and 0 < tint.alphaF() < 1
    assert colours(marks(chinese, 0)) == [(2, 4, blue, None)]  # white "said" row


def test_a_caption_windows_marks_follow_its_look(qapp: QApplication) -> None:
    """The window hands its marks the look's panel and rows' colours, and
    a preset chosen while it's open reaches them."""
    from polyglotic_desktop.core.listening.sources import SourceLabel
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow
    from polyglotic_desktop.ui_next.views.caption_window import (
        CaptionLook,
        WindowChoices,
    )
    from polyglotic_desktop.ui_next.views.placement import Rect

    window = CaptionWindow(
        "lab",
        APP,
        WindowChoices(),
        SourceLabel("Discord", "#4dd0e1"),
        areas=lambda: [Rect(0, 0, 1920, 1040)],
        learner=chinese_tools(),
    )
    try:
        assert window.marks.panel == panel_of("classic")
        paper = BY_KEY["paper"]
        window.set_look(
            CaptionLook(
                background=paper.background,
                original=paper.original,
                translation=paper.translation,
                opacity=paper.opacity,
            )
        )
        assert window.marks.panel == panel_of("paper")
    finally:
        window.close()
        window.deleteLater()


def panel_of(key: str) -> Panel:
    preset = BY_KEY[key]
    return Panel(
        preset.background, preset.original, preset.translation, opacity=preset.opacity
    )
