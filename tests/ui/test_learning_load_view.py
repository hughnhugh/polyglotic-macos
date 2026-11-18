"""Learning load's viewing mode in a caption window (polyglotic-hq 324,
then 489): with the Lab's switch on, every word of a finished caption in
a language being learned is in a colour by how well the learner knows it
- red to green, or orange to blue - readable on every preset and in
order of lightness; new-word dots, deck dashes and saved words' colours
aren't drawn, word links are; and off, nothing changes. Made-up
captions, the sample dictionary with made-up ranks."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import Built, MemorySettingsStore, tools_for
from tests.ui.test_caption_marks import colours, dashed, dotted, saved_in

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.load import Counting, LoadRules
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import DisplayOptions, WordLinks
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished, live
from polyglotic_desktop.ui.settings import load_rules_changes, load_rules_from
from polyglotic_desktop.ui_next.caption_layout import LINK_MARK
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks, Panel
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.known_colours import Palette, known_colour
from polyglotic_desktop.ui_next.views.lab import CaptionLab
from polyglotic_desktop.ui_next.views.presets import (
    PRESETS,
    contrast,
    luminance,
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


def on(key: str = "classic", palette: Palette = Palette.RED_GREEN) -> Panel:
    preset = next(p for p in PRESETS if p.key == key)
    return Panel(
        preset.background,
        preset.original,
        preset.translation,
        load=True,
        palette=palette,
    )


def chance_of(tools: LearningTools, word: str) -> float:
    found = tools.vocabulary.chances.of(tools.words_in(word)[0].entry)
    assert found is not None
    return found.chance


def test_the_sample_line_splits_as_the_tests_say(qapp: QApplication) -> None:
    tools = learner()
    assert {
        LINE[w.start : w.end]: (w.start, w.end) for w in tools.words_in(LINE)
    } == SPANS


def test_every_word_is_in_the_colour_of_how_well_it_is_known(
    qapp: QApplication,
) -> None:
    tools = learner()
    marks = CaptionMarks(tools)
    panel = on()
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, panel)
    found = {(s, e): colour for s, e, colour, _ in colours(marks(shown(), 0))}
    assert set(found) == set(SPANS.values())  # every word, known ones too
    for word, span in SPANS.items():
        expected = known_colour(
            chance_of(tools, word), Palette.RED_GREEN, panel.background
        )
        assert found[span] == expected, word
    # the commonest the lightest, the rarest the darkest: 人 (5th) to 足球
    order = ["人", "这个", "电脑", "游戏", "研究", "足球"]
    shades = [luminance(found[SPANS[w]]) for w in order]
    assert shades == sorted(shades, reverse=True)
    assert found[SPANS["人"]] != found[SPANS["足球"]]


def test_a_word_heard_today_keeps_its_colour_until_tomorrow(
    qapp: QApplication,
) -> None:
    """Every word of a caption was just heard: today's hearing counts from
    tomorrow (decision 0226), so the rarest stays red while it is read."""
    tools = learner()
    rarest = entry(tools, "足球")
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    before = chance_of(tools, "足球")
    hear(tools, "足球")
    assert tools.vocabulary.exposures(rarest).days_heard == 1
    assert chance_of(tools, "足球") == before
    found = {(s, e): c for s, e, c, _ in colours(marks(shown(), 0))}
    assert found[SPANS["足球"]] == known_colour(
        before, Palette.RED_GREEN, on().background
    )


def test_a_word_set_known_turns_green_at_once(qapp: QApplication) -> None:
    tools = learner()
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    line = shown()
    marks(line, 0)
    tools.vocabulary.set_status(entry(tools, "足球"), WordStatus.KNOWN)
    assert marks.learning_changed(Changed.STATUSES.value)  # the window repaints
    found = {(s, e): c for s, e, c, _ in colours(marks(line, 0))}
    assert found[SPANS["足球"]] == known_colour(
        0.98, Palette.RED_GREEN, on().background
    )


def test_the_mode_replaces_dots_dashes_and_saved_words_and_keeps_word_links(
    qapp: QApplication,
) -> None:
    tools = learner()
    tools.vocabulary.set_status(entry(tools, "足球"), WordStatus.LEARNING)
    saved_in(tools, "电脑")
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

    marks.set_look(WordLinks.COLOURS, WordIntroductions.EVERY, on())
    assert not dotted(marks(line, 0)) and not dashed(marks(line, 0))
    coloured = colours(marks(line, 0))
    assert {(s, e) for s, e, *_ in coloured} == set(SPANS.values())
    assert all(tint is None for *_, tint in coloured)  # no saved word's tint
    # word links as ever (340): 电脑 in its colour, and its link's bar
    linked = [
        [(s, e) for s, e, f in marks(line, row) if f.hasProperty(LINK_MARK)]
        for row in range(len(line.rows))
    ]
    assert linked == [[SPANS["电脑"]], [(0, len("Computer"))]]


def test_in_the_mode_a_linked_word_keeps_its_known_colour(qapp: QApplication) -> None:
    """On real captions (346, a learner of 1,000 words) a linked word was
    drawn in its link's colour, over the colour of how well it's known -
    the words past the line, the ones the mode is for. In the mode a link
    is its bar under the word; off, the look's choice as ever."""
    from polyglotic_desktop.ui_next.caption_layout import Ink
    from polyglotic_desktop.ui_next.caption_window import look_ink
    from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

    look = CaptionLook()
    assert look.said_in_link_colours and look.translation_in_link_colours
    off = look_ink(Ink(), look)
    assert off.said_in_link_colours and off.translation_in_link_colours
    on = look_ink(Ink(), replace(look, lab=CaptionLab(load=True)))
    assert not on.said_in_link_colours and not on.translation_in_link_colours


def test_ignored_words_keep_the_rows_colour(qapp: QApplication) -> None:
    tools = learner()
    tools.vocabulary.set_status(entry(tools, "游戏"), WordStatus.IGNORED)
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    spans = {(s, e) for s, e, *_ in colours(marks(shown(), 0))}
    assert SPANS["游戏"] not in spans
    assert len(spans) == len(SPANS) - 1


def test_a_live_caption_shows_no_colours(qapp: QApplication) -> None:
    tools = learner()
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(live("b", clause(LINE)))
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    assert marks(view.lines[-1], 0) == []


@pytest.mark.parametrize("palette", list(Palette))
@pytest.mark.parametrize("preset", [p.key for p in PRESETS])
def test_the_colours_read_on_every_preset_in_order_of_lightness(
    qapp: QApplication, preset: str, palette: Palette
) -> None:
    """As text on the panel (4.5:1), and from the least known to the best
    known in one direction of lightness: away from the panel."""
    panel = on(preset, palette)
    shades = [known_colour(n / 20, palette, panel.background) for n in range(21)]
    assert all(contrast(c, panel.background) >= 4.5 for c in shades)
    light = [luminance(c) for c in shades]
    if luminance(panel.background) >= 0.4:  # Paper: darker as better known
        assert light == sorted(light, reverse=True)
    else:
        assert light == sorted(light)
    assert len(set(shades)) == len(shades)
    # and a translation row in a learned language is coloured as well
    tools = learner()
    zh = Language("zh")
    view = CaptionLines((APP,), zh, keep=10)
    view.apply(finished("a", clause("Computer games.", LINE, into=zh), language=EN))
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, panel)
    coloured = {(s, e) for s, e, *_ in colours(marks(view.lines[0], 1))}
    assert coloured == set(SPANS.values())


def test_the_learning_loads_stages_no_longer_redraw_its_lines(
    qapp: QApplication,
) -> None:
    tools = learner()
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.A_FEW, on())
    marks(shown(), 0)
    assert not marks.learning_changed(Changed.LOAD.value)
    assert marks.load_changed(None) == set()  # the colours don't follow stages


# -- the Lab's switch, the settings and the app ----------------------------------


def test_the_lab_keeps_the_mode_and_reads_it_leniently() -> None:
    assert CaptionLab().load is False  # off until the learner turns it on
    assert CaptionLab().load_colours is Palette.RED_GREEN  # the user's
    lab = CaptionLab(load=True, load_colours=Palette.ORANGE_BLUE)
    assert lab.to_stored() == {"load": True, "load_colours": "orange_blue"}
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    assert CaptionLab.from_stored({"load": "yes", "load_colours": 3}) == CaptionLab()
    # 324's dimming, kept by an older app, is read as nothing
    older = {"load": True, "load_rare": "dimmed"}
    assert CaptionLab.from_stored(older) == CaptionLab(load=True)


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


def test_the_lab_card_has_the_switch_and_the_colours(qapp: QApplication) -> None:
    from polyglotic_desktop.ui_next.lab_panel import LabPanel

    built = Built()
    panel = LabPanel(built.panels.look)
    try:
        assert not panel.load.switch.isChecked()
        panel.load.switch.click()
        assert built.panels.look.value.lab.load
        panel.load_colours.choose(Palette.ORANGE_BLUE)
        assert built.panels.look.value.lab.load_colours is Palette.ORANGE_BLUE
        built.panels.look.reset_lab()
        assert not panel.load.switch.isChecked()
        assert panel.load_colours.value() is Palette.RED_GREEN
    finally:
        panel.deleteLater()
        built.close()


def test_choosing_the_colours_turns_learning_load_on(qapp: QApplication) -> None:
    """365: a choice is never greyed out; it brings the switch with it."""
    from polyglotic_desktop.ui_next.lab_panel import LabPanel

    built = Built()
    look = built.panels.look
    panel = LabPanel(look)
    try:
        panel.load_colours.choose(Palette.ORANGE_BLUE)
        assert look.value.lab.load
        assert look.value.lab.load_colours is Palette.ORANGE_BLUE
        assert panel.load.switch.isChecked()
        # off again: the colours are kept for when it's back
        panel.load.switch.click()
        assert not look.value.lab.load
        assert panel.load_colours.value() is Palette.ORANGE_BLUE
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
