"""Every full language learned at once (polyglotic-hq 306, DECISIONS #110,
decision 0095): with Chinese and English both learned, a word on a Chinese
line is looked up, marked, counted and saved in Chinese's dictionary and
learning data, and one on an English line in English's - whichever is
main. Each keeps its own categories; one dictionary out leaves the other
working. Made-up text and the sample dictionaries; offscreen. (Here with
today's `ui.learning.LearningTools`, which `main` hands over.)"""

from pathlib import Path

import pytest
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample, english_sample
from tests.ui.fakes import tools_for
from tests.ui.test_check_install import sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import (
    DEFAULT_CHINESE_SCHEME,
    ENGLISH_FREQUENCY,
)
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ui.captions import CaptionFeed
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.views.lookup import Lookup, Shows

ZH, EN = Language("zh"), Language("en")
RUN = EntryId("ecdict:run")


def chinese(
    problem: DictionaryProblem | None = None, ready: bool = True
) -> LearningTools:
    return tools_for(
        ChineseDictionary(chinese_sample()), DEFAULT_CHINESE_SCHEME.id, ready, problem
    )


def english() -> LearningTools:
    return tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)


def both(
    main_language: str = "zh", problem: DictionaryProblem | None = None
) -> tuple[LearningTools, LearningTools, LearningTools]:
    """The main language's tools with the other beside it, then Chinese's
    and English's."""
    zh, en = chinese(problem), english()
    first, other = (zh, en) if main_language == "zh" else (en, zh)
    first.learn_beside(other)
    return first, zh, en


def computer() -> EntryId:
    """电脑's entry ID in the sample CC-CEDICT (`default_id`'s hash)."""
    return ChineseDictionary(chinese_sample()).lookup("电脑")[0].entry_id


# -- which tools a line goes to -----------------------------------------------------------


@pytest.mark.parametrize("main_language", ["zh", "en"])
def test_a_line_goes_to_its_own_languages_tools_whichever_is_main(
    qapp: QApplication, main_language: str
) -> None:
    tools, zh, en = both(main_language)
    assert tools.of("zh") is tools.of("zh-hant") is zh
    assert tools.of("en") is en
    assert tools.of("ja") is tools.of("th") is tools.of(None) is tools
    assert tools.every == ((zh, en) if main_language == "zh" else (en, zh))
    assert zh.every == (zh,) or zh is tools  # the others hold none of their own


@pytest.mark.parametrize("main_language", ["zh", "en"])
def test_each_line_is_split_and_looked_up_in_its_own_dictionary(
    qapp: QApplication, main_language: str
) -> None:
    tools, _, _ = both(main_language)
    assert tools.word_at("我的电脑", 2, "zh") == (2, 4)  # the Chinese word split
    assert tools.word_at("they run", 6, "en") == (5, 8)
    assert [e.entry_id for e in tools.lookup("电脑", "zh")][:1] == [computer()]
    assert [e.entry_id for e in tools.lookup("run", "en")] == [RUN]
    assert [w.entry.entry_id for w in tools.words_in("they run", "en")][-1] == RUN
    assert [w.entry.entry_id for w in tools.words_in("电脑", "zh")] == [computer()]


def test_without_english_learned_an_english_line_is_as_before(
    qapp: QApplication,
) -> None:
    """Chinese alone: an English line is Chinese's - "Chinese for it" on its
    words, as before 306."""
    zh = chinese()
    assert zh.of("en") is zh
    lookup = Lookup(zh)
    lookup.show("run", LookupContext("they run"), pinned=True, language="en")
    assert lookup.card().shows is Shows.CHINESE_FOR


# -- saving, and the categories ------------------------------------------------------------


@pytest.mark.parametrize("main_language", ["zh", "en"])
def test_a_word_saved_from_either_line_goes_into_its_own_languages_words(
    qapp: QApplication, main_language: str
) -> None:
    tools, zh, en = both(main_language)
    lookup = Lookup(tools)
    lookup.show("run", LookupContext("they run"), pinned=True, language="en")
    card = lookup.card()
    assert card.shows is Shows.ENTRY and card.actions
    assert card.categories == tuple(en.vocabulary.categories)  # English's own
    saved = lookup.save_to(en.vocabulary.categories[1].id)
    assert saved is not None and saved.entry_id == RUN
    assert en.vocabulary.saved_word(RUN) is not None
    assert zh.vocabulary.saved_words == []
    lookup.show("电脑", LookupContext("我的电脑"), pinned=True, language="zh")
    assert lookup.add_to_deck() is not None
    assert zh.vocabulary.status_of_entry(computer()).status is WordStatus.LEARNING
    assert en.vocabulary.status_of_entry(computer()).status is not WordStatus.LEARNING
    # a lookup is reported to its own language's learning data too
    lookup.show("run", LookupContext("they run"), pinned=False, language="en")
    assert lookup.card().saved_in
    assert en.vocabulary.lookups(RUN).pinned == 1  # English's (one click: still
    assert zh.vocabulary.lookups(RUN).pinned == 0  # known, 397)


def test_each_language_keeps_its_own_categories(qapp: QApplication) -> None:
    """The plainest rule that never loses a learner's data: each language's
    categories are in its own learning data file, as they always were - a
    category made from an English word is English's; Chinese's are as they
    were. Nothing is copied, merged or moved."""
    tools, zh, en = both()
    before = list(zh.vocabulary.categories)
    lookup = Lookup(tools)
    lookup.show("run", LookupContext("they run"), pinned=True, language="en")
    assert lookup.new_category("Verbs") is not None
    assert "Verbs" in [c.name for c in en.vocabulary.categories]
    assert zh.vocabulary.categories == before


# -- what's heard, and the marks -----------------------------------------------------------


def test_what_is_heard_counts_toward_the_language_it_was_heard_in(
    qapp: QApplication,
) -> None:
    tools, zh, en = both()
    feed = CaptionFeed(CaptionHistory(), tools)
    feed.apply(finished("a", clause("我的电脑"), language=ZH))
    feed.apply(finished("b", clause("they run"), language=EN))
    assert zh.vocabulary.exposures(computer()).heard == 1
    assert en.vocabulary.exposures(RUN).heard == 1
    assert en.vocabulary.exposures(computer()).heard == 0
    # the same caption finished again in the other language (a join): what
    # the first counted is taken back, and it counts in the other
    feed.apply(finished("b", clause("我的电脑"), language=ZH))
    assert en.vocabulary.exposures(RUN).heard == 0
    assert zh.vocabulary.exposures(computer()).heard == 2
    # a language not learned counts nowhere
    feed.apply(finished("c", clause("they run"), language=Language("es")))
    assert en.vocabulary.exposures(RUN).heard == 0


def test_both_lines_are_marked_in_their_own_languages_colours(
    qapp: QApplication,
) -> None:
    """A Chinese caption translated into English: its saved Chinese word in
    Chinese's category colour, its saved English word in English's."""
    tools, zh, en = both()
    zh_category, en_category = zh.vocabulary.categories[0], en.vocabulary.categories[1]
    assert zh_category.color != en_category.color
    zh.vocabulary.save(
        computer(), "电脑", "電腦", "", "computer", zh_category.id, LookupContext("")
    )
    en.vocabulary.save(RUN, "run", "", "", "跑", en_category.id, LookupContext(""))
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑", "they run my computer"), language=ZH))
    line = view.lines[0]
    assert [row.language for row in line.rows] == ["zh", "en"]
    marks = CaptionMarks(tools)

    def coloured(row: int) -> list[tuple[int, int, str]]:
        return [
            (start, end, format_.foreground().color().name())
            for start, end, format_ in marks(line, row)
            if isinstance(format_, QTextCharFormat)
            and format_.hasProperty(QTextCharFormat.Property.ForegroundBrush)
        ]

    assert coloured(0) == [(2, 4, zh_category.color)]
    assert coloured(1) == [(5, 8, en_category.color)]


def test_another_languages_changes_and_readiness_come_out_of_the_main(
    qapp: QApplication,
) -> None:
    """Views connect to the main tools alone: English's changes redraw, and
    the marks wait for every word split - here Chinese's, beside English."""
    en, zh = english(), chinese(ready=False)
    en.learn_beside(zh)
    changed: list[str] = []
    ready: list[bool] = []
    en.changed.connect(changed.append)
    en.dictionary_ready.connect(lambda: ready.append(True))
    assert not en.ready  # Chinese's split not read yet
    zh.vocabulary.set_status(computer(), WordStatus.KNOWN)
    assert changed  # Chinese's change, out of English's
    zh.dictionary_ready.emit()
    assert ready == [True]


# -- one dictionary out --------------------------------------------------------------------


@pytest.mark.parametrize("main_language", ["zh", "en"])
def test_one_dictionary_out_leaves_the_other_working(
    qapp: QApplication, main_language: str
) -> None:
    tools, _, _ = both(main_language, problem=DictionaryProblem.MISSING)
    lookup = Lookup(tools)
    lookup.show("电脑", LookupContext("我的电脑"), pinned=True, language="zh")
    card = lookup.card()
    assert (card.shows, card.problem) == (
        Shows.DICTIONARY_OUT,
        DictionaryProblem.MISSING,
    )
    lookup.show("run", LookupContext("they run"), pinned=True, language="en")
    assert lookup.card().shows is Shows.ENTRY and lookup.card().problem is None


# -- `main` opens them ---------------------------------------------------------------------


def test_main_opens_every_full_language_learned_each_in_its_own_file(
    qapp: QApplication, tmp_path: Path
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    beside = main.tools_beside(
        tools, folder, data, LearningLanguages("zh", ("ja", "en", "th"))
    )
    try:
        assert list(tools.also) == ["en"] and len(beside) == 1
        assert (data / "learning.sqlite").exists()
        assert (data / "learning-en.sqlite").exists()
        assert tools.lookup("run", "en")[0].entry_id == RUN
        assert tools.of("en").dictionary_problem is None
    finally:
        store.close()
        for _, other in beside:
            other.close()


def test_nothing_learned_a_chinese_captions_words_are_looked_up_in_chinese(
    qapp: QApplication, tmp_path: Path
) -> None:
    """368: nothing learned on a German PC, the guess is English - and a
    Chinese caption's words were looked up nowhere. Chinese opens beside it,
    so they're split and looked up in Chinese's, as an English PC's are."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, True, data)
    beside = main.tools_beside(tools, folder, data, LearningLanguages(), own="de")
    try:
        assert list(tools.also) == ["zh"]
        assert tools.has_dictionary("zh")
        assert tools.word_at("我的电脑", 2, "zh") == (2, 4)
        assert tools.lookup("电脑", "zh")
    finally:
        store.close()
        for _, other in beside:
            other.close()


def test_main_with_one_dictionary_missing_opens_the_other_and_says_which(
    qapp: QApplication, tmp_path: Path
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    (folder / "ecdict.sqlite").unlink()
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    beside = main.tools_beside(tools, folder, data, LearningLanguages("zh", ("en",)))
    try:
        assert tools.dictionary_problem is None and tools.lookup("电脑", "zh")
        english_tools = tools.of("en")
        assert english_tools is not tools
        assert english_tools.dictionary_problem is DictionaryProblem.MISSING
        assert tools.lookup("run", "en") == []
    finally:
        store.close()
        for _, other in beside:
            other.close()


def test_each_languages_anki_export_holds_its_own_words(qapp: QApplication) -> None:
    """Words' export is per section: each language's file has only its own
    words, each note in its own language (its own sub-deck in the deck
    file: Polyglotic::Chinese, Polyglotic::English)."""
    tools, zh, en = both()
    lookup = Lookup(tools)
    lookup.show("run", LookupContext("they run"), pinned=True, language="en")
    lookup.add_to_deck()
    lookup.show("电脑", LookupContext("我的电脑"), pinned=True, language="zh")
    lookup.add_to_deck()
    english_notes = en.vocabulary.anki_words().export(en.describe).notes
    chinese_notes = zh.vocabulary.anki_words().export(zh.describe).notes
    assert [(n.word, n.language) for n in english_notes] == [("run", "en")]
    assert [(n.word, n.language) for n in chinese_notes] == [("电脑", "zh")]


# -- a full language added during the run ---------------------------------------------------


def test_one_added_during_the_run_opens_and_the_open_ones_dont_again(
    qapp: QApplication, tmp_path: Path
) -> None:
    """`main` calls `tools_beside` again as the list changes (Learning's
    "Learn it", a lookup's "Learn it too"): what's open stays as it is; a
    new full language opens; a basic one opens nothing."""
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, False, data)
    stores = [store]
    try:
        assert main.tools_beside(tools, folder, data, LearningLanguages("zh")) == []
        added = main.tools_beside(
            tools, folder, data, LearningLanguages("zh", ("ja", "en"))
        )
        stores += [s for _, s in added]
        assert [other.language for other, _ in added] == ["en"]
        assert tools.of("en") is added[0][0]
        again = main.tools_beside(
            tools, folder, data, LearningLanguages("zh", ("ja", "en"))
        )
        assert again == [] and list(tools.also) == ["en"]
    finally:
        for each in stores:
            each.close()


def test_a_newer_apps_learning_data_leaves_that_language_closed(
    qapp: QApplication, tmp_path: Path
) -> None:
    """English's file from a newer app: refused, as for the main language -
    but beside it, it doesn't stop the start: English stays closed (its
    lines looked up as before), the file untouched."""
    import sqlite3

    from polyglotic_desktop.adapters.sqlite_learning import VERSION, open_learning_store

    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    data.mkdir()
    english_file = main.learning_file(data, "en")
    open_learning_store(english_file).close()
    db = sqlite3.connect(english_file)
    db.execute(f"PRAGMA user_version = {VERSION + 1}")
    db.commit()
    db.close()
    before = english_file.read_bytes()
    tools, store = main.learner_tools(folder, False, data)
    try:
        opened = main.tools_beside(
            tools, folder, data, LearningLanguages("zh", ("en",))
        )
        assert opened == [] and tools.of("en") is tools
        assert english_file.read_bytes() == before
    finally:
        store.close()


def test_the_hub_shows_a_language_opened_during_the_run(qapp: QApplication) -> None:
    """Words gets its section (and the first one its heading); Learning's
    card for it shows its level, to change now."""
    from tests.ui.fakes import Built, MemorySettingsStore

    store = MemorySettingsStore({"learning": "zh", "also_learning": ["en"]})
    built = Built(store, tools=True)
    try:
        hub, tools = built.hub, built.desktop.tools
        assert tools is not None and hub.words is not None
        assert [s.language for s in hub.words.sections] == ["zh"]
        assert not hub.words.sections[0].heading.isVisibleTo(hub.words)
        card = hub.learning.card("en")
        assert card is not None and card.change_level is None  # not open yet
        en = english()
        tools.learn_beside(en)
        hub.language_opened(en)
        assert [s.language for s in hub.words.sections] == ["zh", "en"]
        assert hub.words.sections[0].heading.isVisibleTo(hub.words)
        assert not hub.words.sections[1].words.isVisibleTo(hub.words)  # closed
        card = hub.learning.card("en")
        assert card is not None and card.change_level is not None
    finally:
        built.close()


# -- each language's own choices (polyglotic-hq 323) --------------------------------------


def test_each_open_language_has_its_own_window_and_links(qapp: QApplication) -> None:
    """323 keeps a learning window and word links per language: with both
    open, each language's own tools hold its own - set on the main tools,
    handed on, and to a language opened after they were set."""
    from polyglotic_desktop.core.learning.levels import LanguageChoices, LinkChoice

    zh, en = chinese(), english()
    zh.learn_beside(en)
    mine = LanguageChoices(window_size=500)
    theirs = LanguageChoices(window_size=2000, links=LinkChoice.OFF)
    zh.set_choices(mine, {"zh": mine, "en": theirs})
    assert (zh.choices, en.choices) == (mine, theirs)
    assert zh.choices_of("en") == en.choices_of("en") == theirs
    later = english()  # opened during the run, after the choices were set
    other = chinese()
    other.set_choices(mine, {"zh": mine, "en": theirs})
    other.learn_beside(later)
    assert later.choices == theirs


def test_an_english_row_beside_chinese_is_linked_by_englishs_own_rules(
    qapp: QApplication,
) -> None:
    """Word links "past what you know" on an English row: with English open
    beside Chinese, the row is judged by English's own words - as with
    English learned alone - not as a language without a dictionary (key
    links only)."""
    from polyglotic_desktop.core.learning.levels import LanguageChoices, LinkChoice
    from polyglotic_desktop.core.listening.display import DisplayOptions, WordLinks
    from polyglotic_desktop.ui_next.caption_layout import LINK_MARK

    past = LanguageChoices(links=LinkChoice.PAST_KNOWN)
    off = LanguageChoices(links=LinkChoice.OFF)  # the Chinese row: no say
    said = clause(
        "they keep running",
        "他们一直在跑",
        (("they", "他们", True), ("keep", "一直", False), ("running", "跑", False)),
        into=ZH,
    )

    def links_with(learner: LearningTools) -> list[tuple[int, int]]:
        view = CaptionLines(
            (APP,), ZH, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
        )
        view.apply(finished("a", said, language=EN))
        marks = CaptionMarks(learner)
        marks.set_look(WordLinks.COLOURS, marks.introductions)
        return [
            (start, end)
            for start, end, format_ in marks(view.lines[0], 0)
            if isinstance(format_, QTextCharFormat) and format_.hasProperty(LINK_MARK)
        ]

    alone = english()
    alone.vocabulary.set_status(alone.lookup("they")[0].entry_id, WordStatus.KNOWN)
    alone.set_choices(past, {"en": past, "zh": off})
    zh, _, en = both()
    en.vocabulary.set_status(en.lookup("they")[0].entry_id, WordStatus.KNOWN)
    zh.set_choices(off, {"zh": off, "en": past})
    chinese_alone = chinese()
    chinese_alone.set_choices(off, {"zh": off, "en": past})

    expected = links_with(alone)
    assert (0, 4) not in expected  # "they", known: no link
    assert links_with(zh) == expected
    assert links_with(chinese_alone) != expected  # key links only, before 306


def test_every_language_has_the_main_tools_basic_packs(
    qapp: QApplication, tmp_path: Path
) -> None:
    """327: one dict of basic packs, `main`'s own, for every learner's tools.
    A pack downloaded while English is open beside Chinese (327's delivery
    puts it in that dict, `PackDelivery._open`) is looked up at once, with
    no restart: a basic language's line goes to the main tools (`of`), and
    English's tools hold the same dict."""
    from tests.lexicon.test_basic import SPANISH, FakeSplit

    from polyglotic_desktop.core.lexicon.basic import BasicDictionary

    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    basic: dict[str, BasicDictionary] = {}
    tools, store = main.learner_tools(folder, False, data, basic)
    beside = main.tools_beside(tools, folder, data, LearningLanguages("zh", ("en",)))
    try:
        english_tools = tools.of("en")
        assert english_tools is not tools
        assert tools.basic is basic and english_tools.basic is basic
        assert tools.lookup("casa", "es") == []  # no pack yet
        basic["es"] = BasicDictionary(SPANISH, FakeSplit(), "es")  # downloaded
        assert [e.headword for e in tools.lookup("casa", "es")] == ["casa"]
        assert tools.is_basic("es") and tools.of("es") is tools
        assert english_tools.is_basic("es")
    finally:
        store.close()
        for _, other in beside:
            other.close()


def test_with_the_load_mode_on_another_languages_row_is_drawn_as_without_it(
    qapp: QApplication,
) -> None:
    """324's learning load follows the language in use (the main tools'
    rules, `DesktopApp._follow_load_rules`): with the Lab's mode on, an
    English row beside Chinese is drawn exactly as with the mode off - its
    own new words, deck and saved colours - not in load colours."""
    from polyglotic_desktop.core.learning.highlights import WordIntroductions
    from polyglotic_desktop.core.listening.display import WordLinks
    from polyglotic_desktop.ui_next.caption_marks import Panel

    zh, _, en = both()
    run = en.lookup("run")[0].entry_id
    en.vocabulary.set_status(run, WordStatus.LEARNING)  # dashes
    en.vocabulary.save(
        en.lookup("keep")[0].entry_id, "keep", "", "", "",
        en.vocabulary.categories[0].id, LookupContext(""),
    )  # fmt: skip
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑", "they keep running"), language=ZH))
    line = view.lines[0]

    def english_row(load: bool) -> list[tuple[int, int, object, object]]:
        marks = CaptionMarks(zh)
        marks.set_look(WordLinks.OFF, WordIntroductions.EVERY, Panel(load=load))
        return [
            (s, e, f.underlineStyle(), f.foreground().color().name())
            for s, e, f in marks(line, 1)
            if isinstance(f, QTextCharFormat)
        ]

    off = english_row(False)
    assert off  # something to compare: a saved colour, deck dashes
    assert english_row(True) == off


def test_a_full_language_added_is_asked_its_level_once_it_opens(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """323 asks "how many words do you know?" when a language is added: with
    several open, for any full one - English, added beside Chinese, once it
    has opened (a moment after the click, `open_added`), for its own tools;
    not for a basic one, nor again for one asked."""
    from tests.ui.fakes import Built, MemorySettingsStore

    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    try:
        hub, tools = built.hub, built.desktop.tools
        assert tools is not None
        asked: list[str] = []
        monkeypatch.setattr(hub, "change_level", asked.append)
        hub._languages_wanted(LearningLanguages("zh", ("en", "ja")))
        assert asked == []  # English isn't open yet
        en = english()
        tools.learn_beside(en)
        hub.language_opened(en)
        assert asked == ["en"]
        hub.language_opened(en)  # the same again: not asked twice
        assert asked == ["en"]
    finally:
        built.close()


def test_the_quiet_view_marks_the_line_being_learned_unless_asked(
    qapp: QApplication,
) -> None:
    """Decision 0252 (the user, 2026-11-19): with English learned too, the
    quiet view marked the English translation of Mandarin speech as well.
    Its words go in what was said; "both lines" brings the other back."""
    from polyglotic_desktop.core.learning.highlights import WordIntroductions
    from polyglotic_desktop.core.listening.display import WordLinks
    from polyglotic_desktop.ui_next.caption_marks import ChosenWords, Panel
    from polyglotic_desktop.ui_next.views.caption_window import MarksIn

    tools, zh, en = both()
    zh.vocabulary.save(
        computer(), "电脑", "電腦", "", "computer",
        zh.vocabulary.categories[0].id, LookupContext(""),
    )  # fmt: skip
    en.vocabulary.save(
        RUN, "run", "", "", "跑", en.vocabulary.categories[1].id, LookupContext("")
    )
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished("a", clause("我的电脑", "they run my computer"), language=ZH))
    line = view.lines[0]
    marks = CaptionMarks(tools)

    def marked(where: MarksIn) -> tuple[bool, bool]:
        chosen = frozenset({ChosenWords.SAVED})
        panel = Panel(quiet=True, quiet_words=chosen, marks_in=where)
        marks.set_look(WordLinks.OFF, WordIntroductions.OFF, panel)
        return bool(marks(line, 0)), bool(marks(line, 1))

    assert marked(MarksIn.LEARNED) == (True, False)
    assert marked(MarksIn.BOTH) == (True, True)
    assert marked(MarksIn.SAID) == (True, False)
