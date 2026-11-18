"""Names stay names in Chinese captions (polyglotic-hq 496, DECISIONS
#214's note and #215): a foreign name cut into pieces (杜|瓦|尔) and a word
its translation writes by its sound (万里 of 黄万里, "Huang Wanli") are
neither lit blue in the quiet view nor coloured by how well they're known -
and our curriculum is told they're names. Made-up captions, the sample
dictionary with the real pack's ranks."""

from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.lexicon.test_chinese_names import NAMES, RANKS
from tests.ui.fakes import tools_for

from polyglotic_desktop.core.learning.curriculum import ChosenWords
from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.levels import UNLIMITED
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import DisplayOptions, WordLinks
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.ui.captions import CaptionFeed
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC, Pair, clause, finished
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks, Panel
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line

EN = Language("en")
EDGE = frozenset({ChosenWords.EDGE})


def learner(chosen: frozenset[ChosenWords] = EDGE) -> LearningTools:
    """A learner of 100 words whose window has no end: every word past 100
    is at their edge."""
    tools = tools_for(ChineseDictionary(chinese_sample(NAMES, RANKS)), "hsk-2025")
    tools.vocabulary.set_known_words(100)
    tools.vocabulary.set_window_size(UNLIMITED)
    tools.vocabulary.set_chosen(chosen, 50)
    return tools


def shown(text: str, meant: str, pairs: tuple[Pair, ...] = ()) -> Line:
    """The line as a window with its links kept shows it: the quiet view
    keeps them for the hover (`shown_links`)."""
    view = CaptionLines(
        (APP,), EN, keep=10, options=DisplayOptions(word_links=WordLinks.HOVER)
    )
    view.apply(finished("a", clause(text, meant, pairs)))
    return view.lines[0]


def marked(tools: LearningTools, line: Line, panel: Panel) -> list[str]:
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.OFF, panel)
    return [line.rows[0].text[s:e] for s, e, _ in marks(line, 0)]


QUIET = Panel(quiet=True, quiet_words=EDGE)
LOAD = Panel(load=True)


def test_a_foreign_names_pieces_are_neither_blue_nor_coloured(
    qapp: QApplication,
) -> None:
    tools = learner()
    line = shown("杜瓦尔已婚", "Duval is married")
    assert marked(tools, line, QUIET) == ["已婚"]
    assert marked(tools, line, LOAD) == ["已婚"]


def test_a_word_its_translation_writes_by_its_sound_is_neither(
    qapp: QApplication,
) -> None:
    tools = learner()
    linked = shown("黄万里是", "Huang Wanli is", (("黄", "Huang"), ("万里", "Wanli")))
    assert marked(tools, linked, QUIET) == []
    assert marked(tools, linked, LOAD) == ["是"]  # known: in its colour
    # with no word links nothing says it's a name: a word at the edge
    unlinked = shown("黄万里是", "Huang Wanli is")
    assert marked(tools, unlinked, QUIET) == ["黄", "万里"]


def test_our_curriculum_is_told_it_is_a_name(qapp: QApplication) -> None:
    tools = learner(frozenset({ChosenWords.CURRICULUM}))
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)
    feed.apply(
        finished(
            "a",
            clause("黄万里是", "Huang Wanli is", (("黄", "Huang"), ("万里", "Wanli"))),
        )
    )
    window = tools.vocabulary.curriculum.themes.window(APP)
    assert window is not None
    said = {s.form: s.entry.is_name for s in window.said()}
    assert said["万里"] and said["黄"]


def test_a_word_of_a_set_said_as_a_name_is_not_blue(qapp: QApplication) -> None:
    """万里 in the learning load (or our curriculum's set, where the talk
    put it from captions with no word links) stays grey where this caption
    says it as a name."""
    from polyglotic_desktop.core.learning.load import LoadRules

    tools = learner(frozenset({ChosenWords.LOAD}))
    tools.vocabulary.set_load_rules(LoadRules(size=20))
    load = frozenset({ChosenWords.LOAD})
    panel = Panel(quiet=True, quiet_words=load)
    linked = shown("黄万里是", "Huang Wanli is", (("黄", "Huang"), ("万里", "Wanli")))
    assert marked(tools, linked, panel) == []
    assert marked(tools, shown("万里", "far away"), panel) == ["万里"]
