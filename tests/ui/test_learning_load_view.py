"""The learning load's viewing mode in a caption window (polyglotic-hq
324): with the Lab's switch on, a finished caption's words that are in
the load are in their stage's colour over their stage's line; known words
are plain; new-word dots, deck dashes and word links' colours aren't
drawn; and off, nothing changes. Made-up captions, the sample dictionary
with made-up ranks."""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import Built, MemorySettingsStore, tools_for
from tests.ui.test_caption_marks import colours, dashed, dotted, saved_in

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.load import Counting, LoadRules, Stage
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import DisplayOptions, WordLinks
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished, live
from polyglotic_desktop.ui.settings import load_rules_changes, load_rules_from
from polyglotic_desktop.ui_next.caption_layout import LINK_MARK
from polyglotic_desktop.ui_next.caption_marks import (
    RARE_ALPHA,
    STAGE_COLOURS,
    STAGE_LINES,
    CaptionMarks,
    Panel,
)
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.lab import CaptionLab, LoadRare
from polyglotic_desktop.ui_next.views.presets import (
    PRESETS,
    colour_difference,
    contrast,
)

EN = Language("en")
RANKS = {"人": 5, "这个": 20, "电脑": 1200, "游戏": 1300, "研究": 1400, "足球": 1500}
LINE = "这个人研究电脑游戏足球"
#       0 1 2 3 4 5 6 7 8 9 10: 这个 人 研究 电脑 游戏 足球
SPANS = {"这个": (0, 2), "人": (2, 3), "研究": (3, 5), "电脑": (5, 7)}
SPANS |= {"游戏": (7, 9), "足球": (9, 11)}


def learner(size: int = 3) -> LearningTools:
    """A learner of 1,000 words with a load of the next `size`: 电脑, 游戏
    and 研究; 足球 is past it, 这个 and 人 known."""
    tools = tools_for(
        ChineseDictionary(chinese_sample(frequency_ranks=RANKS)), "hsk-2025"
    )
    tools.vocabulary.set_known_words(1000)
    tools.vocabulary.set_load_rules(LoadRules(size=size))
    return tools


def entry(tools: LearningTools, word: str) -> EntryId:
    return tools.lookup(word)[0].entry_id


def hear(tools: LearningTools, text: str, caption_id: str = "") -> None:
    hear.count = getattr(hear, "count", 0) + 1  # type: ignore[attr-defined]
    tools.vocabulary.caption_finished(
        caption_id or f"heard-{hear.count}",  # type: ignore[attr-defined]
        tools.words_in(text),
        by_you=False,
    )


def shown(text: str = LINE) -> Line:
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause(text, "This person studies computer games.")))
    return view.lines[0]


def on(key: str = "classic", dim_rare: bool = False) -> Panel:
    preset = next(p for p in PRESETS if p.key == key)
    return Panel(
        preset.background,
        preset.original,
        preset.translation,
        load=True,
        dim_rare=dim_rare,
    )


def lines_under(marks: object) -> dict[tuple[int, int], QTextCharFormat.UnderlineStyle]:
    assert isinstance(marks, list | tuple)
    return {
        (start, end): format_.underlineStyle()
        for start, end, format_ in marks
        if format_.underlineStyle() is not QTextCharFormat.UnderlineStyle.NoUnderline
    }


def test_the_sample_line_splits_as_the_tests_say(qapp: QApplication) -> None:
    tools = learner()
    assert {
        LINE[w.start : w.end]: (w.start, w.end) for w in tools.words_in(LINE)
    } == SPANS


def test_words_in_the_load_are_in_their_stages_colour_over_its_line(
    qapp: QApplication,
) -> None:
    tools = learner()
    hear(tools, "电脑 电脑 电脑")  # orange
    hear(tools, " ".join(["游戏"] * 6))  # yellow
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    found = marks(shown(), 0)
    red, orange, yellow, _green = STAGE_COLOURS
    assert colours(found) == [
        (*SPANS["研究"], red, None),
        (*SPANS["电脑"], orange, None),
        (*SPANS["游戏"], yellow, None),
    ]
    # the line under each fills in as the word is learned: never hue alone
    assert lines_under(found) == {
        SPANS["研究"]: STAGE_LINES[Stage.RED],
        SPANS["电脑"]: STAGE_LINES[Stage.ORANGE],
        SPANS["游戏"]: STAGE_LINES[Stage.YELLOW],
    }
    assert len(set(STAGE_LINES)) == 5  # a shape for each stage, and for ready


def test_green_then_ready_to_check_then_plain_once_known(qapp: QApplication) -> None:
    tools = learner()
    computer = entry(tools, "电脑")
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    line = shown()
    green = STAGE_COLOURS[Stage.GREEN]

    hear(tools, " ".join(["电脑"] * 9))
    marks.load_changed(None)
    assert (*SPANS["电脑"], green, None) in colours(marks(line, 0))
    assert lines_under(marks(line, 0))[SPANS["电脑"]] is STAGE_LINES[Stage.GREEN]

    hear(tools, " ".join(["电脑"] * 3))
    marks.load_changed(None)
    assert tools.vocabulary.load.stage(computer) is Stage.READY
    assert (*SPANS["电脑"], green, None) in colours(marks(line, 0))
    assert lines_under(marks(line, 0))[SPANS["电脑"]] is STAGE_LINES[Stage.READY]

    tools.vocabulary.check_word(computer, knows=True)  # graduated: plain text
    marks.load_changed(None)
    assert SPANS["电脑"] not in {(s, e) for s, e, *_ in colours(marks(line, 0))}
    assert SPANS["电脑"] not in lines_under(marks(line, 0))
    # and the next word by frequency took its place, in red
    assert (*SPANS["足球"], STAGE_COLOURS[Stage.RED], None) in colours(marks(line, 0))


def test_known_words_and_words_outside_the_load_are_plain(qapp: QApplication) -> None:
    tools = learner()
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.EVERY, on())
    marked = {(s, e) for s, e, _ in marks(shown(), 0)}
    assert marked == {SPANS["研究"], SPANS["电脑"], SPANS["游戏"]}


def test_words_outside_the_load_can_be_dimmed_but_known_ones_never(
    qapp: QApplication,
) -> None:
    tools = learner()
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on(dim_rare=True))
    dimmed = [
        (start, end, format_.foreground().color())
        for start, end, format_ in marks(shown(), 0)
        if format_.foreground().style() is not Qt.BrushStyle.NoBrush
        and format_.foreground().color().alphaF() < 1.0
    ]
    assert [(s, e) for s, e, _ in dimmed] == [SPANS["足球"]]  # not 这个, 人
    colour = dimmed[0][2]
    assert colour.name() == "#ffffff"  # its row's own colour
    assert abs(colour.alphaF() - RARE_ALPHA) < 0.01


def test_the_mode_replaces_the_dots_and_the_dashes_and_keeps_word_links(
    qapp: QApplication,
) -> None:
    tools = learner()
    tools.vocabulary.set_status(entry(tools, "足球"), WordStatus.LEARNING)
    view = CaptionLines(
        (APP,), EN, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    view.apply(finished("a", clause(LINE, "Computer games", (("电脑", "Computer"),))))
    line = view.lines[0]
    marks = CaptionMarks(tools)
    off = replace(on(), load=False)
    marks.set_look(WordLinks.COLOURS, WordIntroductions.EVERY, off)
    before = [m for row in range(len(line.rows)) for m in marks(line, row)]
    assert dotted(marks(line, 0)) and dashed(marks(line, 0))  # as it always was
    assert any(f.hasProperty(LINK_MARK) for _, _, f in before)  # links underlined
    assert not colours(marks(line, 0))  # nothing in a stage's colour

    marks.set_look(WordLinks.COLOURS, WordIntroductions.EVERY, on())
    stages = {(s, e) for s, e, *_ in colours(marks(line, 0))}
    assert stages == {SPANS["研究"], SPANS["电脑"], SPANS["游戏"]}
    # only the load's own lines under words: no dot under a new word that
    # isn't in it, no dash under the deck's 足球
    assert set(lines_under(marks(line, 0))) == stages
    # word links as ever (340; the user, 2026-11-15: "Word links stop
    # working with learning load"): 电脑 is in the load and linked - its
    # stage's colour and line, and its link's bar - and so is its counterpart
    linked = [
        [(s, e) for s, e, f in marks(line, row) if f.hasProperty(LINK_MARK)]
        for row in range(len(line.rows))
    ]
    assert linked == [[SPANS["电脑"]], [(0, len("Computer"))]]


def test_a_saved_word_in_the_load_shows_its_stage_and_one_outside_its_category(
    qapp: QApplication,
) -> None:
    tools = learner()
    saved_in(tools, "电脑")
    blue = saved_in(tools, "足球")
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    found = colours(marks(shown(), 0))
    assert (*SPANS["电脑"], STAGE_COLOURS[Stage.RED], None) in found
    assert (*SPANS["足球"], blue, None) in found
    assert len(found) == 4


def test_a_live_caption_shows_no_stage(qapp: QApplication) -> None:
    tools = learner()
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(live("b", clause(LINE)))
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    assert marks(view.lines[-1], 0) == []


@pytest.mark.parametrize("preset", [p.key for p in PRESETS])
def test_the_four_stages_read_on_every_preset(qapp: QApplication, preset: str) -> None:
    """As text on the panel (4.5:1), apart from each other, and with a tint
    behind where a stage's colour is the row's own (Classic's yellow
    translation and the yellow stage)."""
    tools = learner(size=4)
    hear(tools, "电脑 电脑 电脑")
    hear(tools, " ".join(["游戏"] * 6))
    hear(tools, " ".join(["足球"] * 9))
    panel = on(preset)
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, panel)
    found = colours(marks(shown(), 0))
    assert len(found) == 4
    shades = [colour for _, _, colour, _ in found]
    assert all(contrast(colour, panel.background) >= 4.5 for colour in shades)
    apart = [
        colour_difference(a, b) for i, a in enumerate(shades) for b in shades[i + 1 :]
    ]
    assert min(apart) >= 30
    assert all(tint is None for *_, tint in found)  # white or dark "said" rows
    # the same words in a translation row, in the translation's colour
    zh = Language("zh")
    view = CaptionLines((APP,), zh, keep=10)
    view.apply(finished("a", clause("Computer games.", LINE, into=zh), language=EN))
    for _, _, colour, tint in colours(marks(view.lines[0], 1)):
        near = colour_difference(colour, panel.translation) < 30
        assert (tint is not None) == near


def test_only_the_lines_holding_a_word_that_changed_stage_are_marked_again(
    qapp: QApplication,
) -> None:
    tools = learner()
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("这个人研究电脑", "This person studies computers")))
    view.apply(finished("b", clause("这个人打游戏", "This person plays games")))
    first, second = view.lines
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    marks(first, 0), marks(second, 0)
    assert not marks.learning_changed(Changed.LOAD.value)  # `load_changed` says
    assert marks.load_changed(frozenset()) == set()  # meetings only: nothing
    assert marks.load_changed(frozenset({entry(tools, "电脑")})) == {first.key}
    assert marks.load_changed(None) is None  # any word: every line
    off = CaptionMarks(tools)
    off(first, 0)
    assert off.load_changed(None) == set()  # the mode off: nothing to redraw


def test_a_word_that_moves_a_stage_is_recoloured_where_it_already_shows(
    qapp: QApplication,
) -> None:
    tools = learner()
    changed: list[object] = []
    tools.load_changed.connect(changed.append)
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    line = shown()
    red, orange, *_ = STAGE_COLOURS
    assert (*SPANS["电脑"], red, None) in colours(marks(line, 0))
    hear(tools, "电脑 电脑")
    assert changed == [frozenset()]  # two meetings: no stage moved
    hear(tools, "电脑")
    assert changed[-1] == frozenset({entry(tools, "电脑")})
    assert marks.load_changed(changed[-1]) == {line.key}
    assert (*SPANS["电脑"], orange, None) in colours(marks(line, 0))


# -- the Lab's switch, the settings and the app ----------------------------------


def test_the_lab_keeps_the_mode_and_reads_it_leniently() -> None:
    assert CaptionLab().load is False  # off until the learner turns it on
    lab = CaptionLab(load=True, load_rare=LoadRare.DIMMED)
    assert lab.to_stored() == {"load": True, "load_rare": "dimmed"}
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    assert CaptionLab.from_stored({"load": "yes", "load_rare": 3}) == CaptionLab()


def test_a_languages_rules_are_kept_and_read_leniently() -> None:
    store = MemorySettingsStore()
    built = Built(store)
    try:
        settings = built.desktop.settings
        assert settings.value.load_rules_for("zh") is None  # the mode is off
        settings.update(caption_lab={"load": True})
        assert settings.value.load_rules_for("zh") == LoadRules()
        rules = LoadRules(size=250, step=2, counting=Counting.DAY, stage_limit=40)
        settings.update(**load_rules_changes(settings.value, "zh", rules))
        assert settings.value.learning_load == {
            "zh": {"size": 250, "step": 2, "counting": "day", "limit": 40}
        }
        assert settings.value.load_rules_for("zh") == rules
        assert settings.value.load_rules_for("en") == LoadRules()  # its own
        settings.update(**load_rules_changes(settings.value, "zh", LoadRules()))
        assert settings.value.learning_load == {}  # the defaults: nothing kept
    finally:
        built.close()
    odd = {"size": "big", "step": 0, "counting": "weekly", "limit": -1}
    assert load_rules_from(odd) == LoadRules()
    assert load_rules_from({"size": True}) == LoadRules()
    assert load_rules_from(None) == LoadRules()


def test_the_labs_switch_turns_the_load_on_for_the_learner(qapp: QApplication) -> None:
    built = Built(tools=True)
    try:
        tools = built.desktop.tools
        assert tools is not None
        assert tools.vocabulary.load.rules is None
        built.panels.look.set_lab(replace(built.panels.look.value.lab, load=True))
        built.panels.save_look()  # as it settles
        assert tools.vocabulary.load.rules == LoadRules()
        window = next(iter(built.windows.windows.values()), None)
        if window is not None:
            assert window.marks.panel.load
        built.panels.look.set_lab(replace(built.panels.look.value.lab, load=False))
        built.panels.save_look()
        assert tools.vocabulary.load.rules is None
    finally:
        built.close()


def test_words_added_by_hand_raise_the_size_the_settings_keep(
    qapp: QApplication,
) -> None:
    built = Built(tools=True)
    try:
        tools = built.desktop.tools
        assert tools is not None
        settings = built.desktop.settings
        settings.update(caption_lab={"load": True})
        tools.add_next_to_load(25)
        assert settings.value.load_rules_for("zh") == LoadRules(size=525)
        assert tools.vocabulary.load.rules == LoadRules(size=525)
    finally:
        built.close()


def test_the_lab_card_has_the_switch_and_the_choice_for_words_outside(
    qapp: QApplication,
) -> None:
    from polyglotic_desktop.ui_next.lab_panel import LabPanel

    built = Built()
    panel = LabPanel(built.panels.look)
    try:
        assert not panel.load.switch.isChecked()
        panel.load.switch.click()
        assert built.panels.look.value.lab.load
        panel.load_rare.choose(LoadRare.DIMMED)
        assert built.panels.look.value.lab.load_rare is LoadRare.DIMMED
        built.panels.look.reset_lab()
        assert not panel.load.switch.isChecked()
    finally:
        panel.deleteLater()
        built.close()


def test_dimming_the_words_outside_the_load_turns_the_load_on(
    qapp: QApplication,
) -> None:
    """365: a choice greyed out until another row's switch was on - now it
    can be chosen, and brings the switch with it."""
    from polyglotic_desktop.ui_next.lab_panel import LabPanel

    built = Built()
    look = built.panels.look
    panel = LabPanel(look)
    try:
        assert panel.load_rare.isEnabled()
        panel.load_rare.choose(LoadRare.DIMMED)
        assert look.value.lab.load and look.value.lab.load_rare is LoadRare.DIMMED
        assert panel.load.switch.isChecked()
        # off again: the load goes, the choice is kept for when it's back
        panel.load.switch.click()
        assert not look.value.lab.load
        assert look.value.lab.load_rare is LoadRare.DIMMED
        assert panel.load_rare.value() is LoadRare.NORMAL  # nothing dimmed now
        panel.load.switch.click()
        assert panel.load_rare.value() is LoadRare.DIMMED
        # As now changes nothing else
        panel.load.switch.click()
        panel.load_rare.choose(LoadRare.NORMAL)
        assert not look.value.lab.load
    finally:
        panel.deleteLater()
        built.close()


def test_a_new_caption_in_the_mode_within_its_budget(qapp: QApplication) -> None:
    """The mode on with every word of the made-up conversation in the load
    (the most there is to colour), the window holding 150 captions: a new
    caption - its meetings counted, its words coloured - still within
    NEW_CAPTION (8 ms), timed as the other budget tests are."""
    from tests.budget_judge import sampled, within
    from tests.ui_next.made_up import finished_updates

    from polyglotic_desktop.core.listening.sources import SourceLabel
    from polyglotic_desktop.perf import budgets
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow
    from polyglotic_desktop.ui_next.views.caption_window import (
        CaptionLook,
        WindowChoices,
    )
    from polyglotic_desktop.ui_next.views.placement import Rect

    sample = chinese_sample()
    ranks = {r.headword: 1000 + n for n, r in enumerate(sample.by_id.values())}
    tools = tools_for(
        ChineseDictionary(chinese_sample(frequency_ranks=ranks)), "hsk-2025"
    )
    tools.vocabulary.set_load_rules(LoadRules(size=500))
    assert len(tools.vocabulary.load.members()) > 20
    window = CaptionWindow(
        "lab",
        APP,
        WindowChoices(),
        SourceLabel("Discord", "#4dd0e1"),
        areas=lambda: [Rect(0, 0, 1920, 1040)],
        learner=tools,
    )
    window.set_look(replace(CaptionLook(), lab=CaptionLab(load=True)))
    for update in finished_updates(150):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    window.canvas.repaint()
    arriving = iter(finished_updates(40, start=150))  # 10, warmed up, twice
    staged = 0

    def arrive() -> None:
        nonlocal staged
        update = next(arriving)
        said = " ".join(c.original for c in update.clauses)
        tools.vocabulary.caption_finished(
            update.caption_id, tools.words_in(said), by_you=False
        )
        window.view.apply(update)
        window.apply_changed(new_caption=True)
        window.canvas.repaint()
        line = window.view.lines[-1]
        staged += sum(len(window.marks(line, row)) for row in range(len(line.rows)))

    try:
        within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 10))
        assert staged  # the captions timed did hold coloured words
    finally:
        window.close()
