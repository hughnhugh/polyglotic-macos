"""What the learner chose for each language they learn, beside their line
(polyglotic-hq 323): the learning window's size - a setting, per language,
that the captions' marks follow at once. Made-up captions, the sample
dictionaries."""

from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import english_sample
from tests.ui.fakes import MemorySettingsStore, tools_for

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.levels import UNLIMITED, LanguageChoices
from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished
from polyglotic_desktop.ui.settings import AppSettings, language_choices_changes
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line

EN = Language("en")
ZH = Language("zh")
LINE = "They keep running, awkward"  # ranks 35, 250, 202 (run), 2,500


def english_tools() -> LearningTools:
    return tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)


def dotted(marks: CaptionMarks, line: Line) -> list[str]:
    """The words of the line's first row dotted as new."""
    text = line.rows[0].text
    return [
        text[start:end]
        for start, end, format_ in marks(line, 0)
        if isinstance(format_, QTextCharFormat)
        and format_.underlineStyle() is QTextCharFormat.UnderlineStyle.DotLine
    ]


def test_the_choices_are_kept_per_language_and_read_leniently() -> None:
    value = AppSettings()
    assert value.choices_for("zh") == LanguageChoices()  # nothing chosen
    changes = language_choices_changes(value, "zh", LanguageChoices(window_size=500))
    assert changes == {"language_choices": {"zh": {"window": 500}}}
    stored = {**value.to_stored(), **changes}
    again = AppSettings.from_stored(stored)
    assert again.choices_for("zh").window_size == 500
    assert again.choices_for("en") == LanguageChoices()  # each its own
    # another language's choice leaves this one; the default again leaves no entry
    both = AppSettings.from_stored(
        {
            **stored,
            **language_choices_changes(again, "en", LanguageChoices(window_size=2000)),
        }
    )
    assert both.language_choices == {"zh": {"window": 500}, "en": {"window": 2000}}
    assert language_choices_changes(both, "zh", LanguageChoices()) == {
        "language_choices": {"en": {"window": 2000}}
    }
    # a value this version doesn't know (a newer one's, or a damaged file's)
    # loses only itself; a map that isn't one, the lot
    odd = {"zh": {"window": "wide", "newer": 1}, "en": {"window": 100}}
    read = AppSettings.from_stored({"language_choices": odd})
    assert read.choices_for("zh") == LanguageChoices()
    assert read.choices_for("en").window_size == 100
    assert AppSettings.from_stored({"language_choices": [1]}).language_choices == {}
    assert LanguageChoices.from_stored({"window": True}) == LanguageChoices()
    assert LanguageChoices.from_stored({"window": -5}) == LanguageChoices()


def test_a_caption_marks_the_window_at_the_size_chosen(qapp: QApplication) -> None:
    """A learner who knows about 1,000 words: "awkward" (2,500th) is rarer
    than a window of 1,000, and in one of 2,000 - and the caption follows
    the choice without a restart."""
    tools = english_tools()
    tools.vocabulary.set_known_words(1000)
    view = CaptionLines((APP,), ZH, keep=10)
    view.apply(finished("a", clause(LINE, "他们一直跑，很尴尬"), language=EN))
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.OFF, WordIntroductions.EVERY)
    told: list[str] = []
    tools.changed.connect(told.append)
    line = view.lines[0]
    assert dotted(marks, line) == []  # the default window ends at 2,000
    tools.set_choices(LanguageChoices(window_size=2000))
    assert told == [Changed.LEVEL.value]  # the windows work their marks out again
    assert marks.learning_changed(told[0])
    assert dotted(marks, line) == ["awkward"]
    tools.set_choices(LanguageChoices(window_size=2000))
    assert told == [Changed.LEVEL.value]  # the same choice: nothing to redo
    tools.set_choices(LanguageChoices(window_size=500))
    marks.learning_changed(told[-1])
    assert dotted(marks, line) == []
    # a number of the learner's own, and no end at all (decision 0144)
    tools.set_choices(LanguageChoices(window_size=3000))
    marks.learning_changed(told[-1])
    assert dotted(marks, line) == ["awkward"]
    tools.set_choices(LanguageChoices(window_size=1001))
    marks.learning_changed(told[-1])
    assert dotted(marks, line) == []  # ends at 2,001
    tools.set_choices(LanguageChoices(window_size=UNLIMITED))
    marks.learning_changed(told[-1])
    assert dotted(marks, line) == ["awkward"]


def test_the_tools_follow_the_settings_for_their_own_language(
    qapp: QApplication,
) -> None:
    tools = english_tools()
    store = MemorySettingsStore(
        {"language_choices": {"en": {"window": 100}, "zh": {"window": 2000}}}
    )
    desktop = DesktopApp(store, tools, None)
    try:
        assert tools.choices.window_size == 100  # English's, not Chinese's
        value = desktop.settings.value
        desktop.settings.update(
            **language_choices_changes(value, "en", LanguageChoices(window_size=500))
        )
        assert tools.choices.window_size == 500
        assert desktop.settings.value.choices_for("zh").window_size == 2000
    finally:
        desktop.deleteLater()


def test_the_start_fills_our_curriculums_set_only_once_the_window_is_up(
    qapp: QApplication,
) -> None:
    """The app's start turns our curriculum on with the quiet view's chosen
    words but leaves its set unfilled: filling looks through every word
    heard, 31 ms at 30,000 words met on the main PC, and put the start over
    its 400 ms (polyglotic-hq 509). `main` fills it after the first paint
    (`DesktopApp.fill_curriculum`)."""
    tools = english_tools()
    desktop = DesktopApp(MemorySettingsStore({}), tools, None)
    try:
        assert tools.vocabulary.curriculum.on
        assert tools.vocabulary.curriculum.members() == []
        desktop.fill_curriculum()
        assert len(tools.vocabulary.curriculum.members()) > 0
    finally:
        desktop.deleteLater()


def test_which_words_are_linked_is_kept_with_the_windows_size() -> None:
    """Word links' choice for a language, and where they start (323)."""
    from polyglotic_desktop.core.learning.levels import LinkChoice

    chosen = LanguageChoices(500, LinkChoice.PAST_KNOWN, 2000)
    stored = chosen.to_stored()
    assert stored == {"window": 500, "links": "past_known", "links_from": 2000}
    assert LanguageChoices.from_stored(stored) == chosen
    assert LanguageChoices().to_stored() == {}  # every word: nothing to keep
    # a choice a newer version made reads as every word; the rest is kept
    read = LanguageChoices.from_stored({"links": "by_colour", "window": 100})
    assert read == LanguageChoices(window_size=100)
    assert LanguageChoices.from_stored({"links": "off"}).links is LinkChoice.OFF


def test_the_chosen_window_reaches_our_curriculum_and_the_edge_words(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 496: the learning window's size chosen for the language
    is the one `Vocabulary` lights words at your edge and takes the
    conversation's words by (491 used the default)."""
    tools = english_tools()
    assert tools.vocabulary.learning_window.size == 1000  # the default
    tools.set_choices(LanguageChoices(window_size=100))
    assert tools.vocabulary.learning_window.size == 100
    tools.set_choices(LanguageChoices(window_size=UNLIMITED))
    assert tools.vocabulary.learning_window.size is UNLIMITED
