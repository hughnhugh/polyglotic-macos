"""Word links by what the learner knows (polyglotic-hq 323): every word,
only words past what they know, or none - per language learned - and, in
a language with no full dictionary, key links only. Made-up captions, the
sample dictionaries."""

from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import FakeDictionaryFile, english_sample
from tests.lexicon.test_basic import SPANISH, FakeSplit
from tests.ui.fakes import tools_for

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.levels import LanguageChoices, LinkChoice
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import (
    CaptionRow,
    DisplayOptions,
    LinkedWords,
    RowKind,
    WordLinks,
)
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, clause, finished
from polyglotic_desktop.ui_next.caption_layout import LINK_MARK
from polyglotic_desktop.ui_next.caption_marks import CaptionMarks
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line
from polyglotic_desktop.ui_next.views.links import RowLinks, hidden_links
from polyglotic_desktop.ui_next.views.lookup import Lookup

EN = Language("en")
ZH = Language("zh")
VI = Language("vi")
PAST = LanguageChoices(links=LinkChoice.PAST_KNOWN)


# -- the rule ------------------------------------------------------------------------


def row(text: str, clause_: int, *links: LinkedWords, said: bool = True) -> CaptionRow:
    kind = RowKind.ORIGINAL if said else RowKind.TRANSLATION
    return CaptionRow(text, kind, None, clause_, said, links)


SAID = row("They keep running", 0, LinkedWords(0, 4, 0), LinkedWords(5, 17, 1))
MEANT = row("他们一直跑", 0, LinkedWords(0, 2, 0), LinkedWords(2, 5, 1), said=False)


def test_a_link_shows_unless_every_word_under_it_is_known() -> None:
    they, keep, running = (0, 4), (5, 9), (10, 17)
    hidden = hidden_links
    assert hidden([SAID, MEANT], [None, None]) == set()  # no say: as before
    assert hidden([SAID, MEANT], [RowLinks(every=True), None]) == set()
    assert hidden([SAID, MEANT], [RowLinks(known=[they]), None]) == {(0, 0)}
    # "keep running" is one link: known only when both its words are
    assert hidden([SAID, MEANT], [RowLinks(known=[they, keep]), None]) == {(0, 0)}
    assert hidden([SAID, MEANT], [RowLinks(known=[they, keep, running]), None]) == {
        (0, 0),
        (0, 1),
    }
    assert hidden([SAID, MEANT], [RowLinks(off=True), None]) == {(0, 0), (0, 1)}


def test_a_number_needs_no_link() -> None:
    """1940 has no letters: no word past what anyone knows (polyglotic-hq
    338 - real captions linked every number); M16 has one, not known."""
    text = "In 1940 an M16"
    said = row(text, 0, LinkedWords(3, 7, 0), LinkedWords(11, 14, 1))
    assert hidden_links([said], [RowLinks()]) == {(0, 0)}  # past what you know
    assert hidden_links([said], [RowLinks(key_only=True)]) == {(0, 0)}
    assert hidden_links([said], [RowLinks(every=True)]) == set()  # every word


def test_the_captioned_language_decides_for_a_learner_of_both() -> None:
    """The user (2026-11-15, 338): "it should be determined by captioned
    language not by translated language". Before, either row keeping a
    link showed it."""
    knows_they = RowLinks(known=[(0, 4)])
    # heard in English, learned: its say alone, whatever the Chinese row's
    assert hidden_links([SAID, MEANT], [knows_they, RowLinks()]) == {(0, 0)}
    assert hidden_links([SAID, MEANT], [knows_they, RowLinks(known=[(0, 2)])]) == {
        (0, 0)
    }
    assert hidden_links([SAID, MEANT], [RowLinks(off=True), RowLinks()]) == {
        (0, 0),
        (0, 1),
    }
    # heard in a language not learned: the translation's say decides
    assert hidden_links([SAID, MEANT], [None, RowLinks(known=[(0, 2)])]) == {(0, 0)}


def test_real_lines_where_the_translation_kept_a_known_word_linked() -> None:
    """Claude's validation loop (346), real captions from the real models:
    目前 (known at 5,000 Chinese words) kept by "currently", and "is" (known)
    kept by 身处 on English speech."""
    zh = row("目前他在北京", 0, LinkedWords(0, 2, 0))
    en = row("He is currently in Beijing", 0, LinkedWords(6, 15, 0), said=False)
    knows_muqian = RowLinks(known=[(0, 2), (3, 4)])
    assert hidden_links([zh, en], [knows_muqian, RowLinks()]) == {(0, 0)}
    said = row("She is in the city", 0, LinkedWords(4, 6, 0))
    meant = row("她身处城市", 0, LinkedWords(1, 3, 0), said=False)
    assert hidden_links([said, meant], [RowLinks(known=[(4, 6)]), RowLinks()]) == {
        (0, 0)
    }


def test_a_translations_every_word_has_no_say() -> None:
    """A learner of Chinese (every word) who added English (past what you
    know) saw every link on an English caption: its Chinese translation
    kept them all (polyglotic-hq 338). Every word is said of a language's
    words where it was heard."""
    knows_they = RowLinks(known=[(0, 4)])
    every = RowLinks(every=True)
    assert hidden_links([SAID, MEANT], [knows_they, every]) == {(0, 0)}
    # heard in the language of every word: every link, whatever the other says
    assert hidden_links([SAID, MEANT], [every, RowLinks(known=[(0, 2)])]) == set()
    # nobody else says: every link shows, as before 323
    assert hidden_links([SAID, MEANT], [None, every]) == set()


def test_with_no_dictionary_only_key_links_show() -> None:
    said = row(
        "Tôi muốn ăn phở", 0, LinkedWords(4, 8, 0, False), LinkedWords(12, 15, 1)
    )
    meant = row(
        "I want to eat pho", 0, LinkedWords(2, 6, 0, False), LinkedWords(14, 17, 1)
    )
    assert hidden_links([said, meant], [RowLinks(key_only=True), None]) == {(0, 0)}
    # each clause's links are its own: the same number in another clause stays
    other = row("phở", 1, LinkedWords(0, 3, 0))
    assert hidden_links(
        [said, meant, other], [RowLinks(key_only=True), None, None]
    ) == {(0, 0)}


# -- in a caption window's marks -------------------------------------------------------


def english_tools(choices: LanguageChoices) -> LearningTools:
    tools = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    tools.vocabulary.set_known_words(1000)
    tools.set_choices(choices)
    return tools


def line_of(language: Language = EN) -> Line:
    """ "They keep running, awkward" (ranks 35, 250, 202 for run, 2,500),
    each word linked to its translation; "They" a minor link."""
    view = CaptionLines(
        (APP,), ZH, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    pairs = (
        ("They", "他们", False),
        ("keep", "一直"),
        ("running", "跑"),
        ("awkward", "尴尬"),
    )
    said = clause("They keep running, awkward", "他们一直跑，很尴尬", pairs, into=ZH)
    view.apply(finished("a", said, language=language))
    return view.lines[0]


def linked(marks: CaptionMarks, line: Line, row_: int = 0) -> list[str]:
    text = line.rows[row_].text
    return [
        text[start:end]
        for start, end, format_ in marks(line, row_)
        if isinstance(format_, QTextCharFormat) and format_.hasProperty(LINK_MARK)
    ]


def marks_for(tools: LearningTools) -> CaptionMarks:
    marks = CaptionMarks(tools)
    marks.set_look(WordLinks.COLOURS, WordIntroductions.OFF)
    return marks


def test_links_only_on_words_past_what_the_learner_knows(qapp: QApplication) -> None:
    """A learner of about 1,000 English words: They, keep and running are
    known, so only "awkward" is linked - on its row and on the
    translation's. Before the fix every word was, whatever was known."""
    tools = english_tools(PAST)
    marks, line = marks_for(tools), line_of()
    assert linked(marks, line) == ["awkward"]
    assert linked(marks, line, 1) == ["尴尬"]  # its counterpart, and only it
    # every word (as before 323, and until the learner chooses)
    tools.set_choices(LanguageChoices())
    marks.learning_changed("level")
    assert linked(marks, line) == ["They", "keep", "running", "awkward"]
    # off for this language
    tools.set_choices(LanguageChoices(links=LinkChoice.OFF))
    marks.learning_changed("level")
    assert linked(marks, line) == [] and linked(marks, line, 1) == []


def test_chinese_every_word_doesnt_link_every_word_of_english(
    qapp: QApplication,
) -> None:
    """The user's case (2026-11-15, 338): Chinese learned before 323 (every
    word) and English added since (past what you know). On an English
    caption the Chinese translation's choice kept every link."""
    tools = english_tools(PAST)
    tools.set_choices(PAST, {"zh": LanguageChoices()})  # Chinese: every word
    marks, line = marks_for(tools), line_of()
    assert linked(marks, line) == ["awkward"]
    assert linked(marks, line, 1) == ["尴尬"]


def test_where_links_start_can_be_moved_from_the_line(qapp: QApplication) -> None:
    """The user's example: 3,000 known, links from 2,000 up - here 1,000
    known and links from 200: keep (250th) and run (202nd) are linked too."""
    tools = english_tools(LanguageChoices(links=LinkChoice.PAST_KNOWN, links_from=200))
    marks, line = marks_for(tools), line_of()
    assert linked(marks, line) == ["keep", "running", "awkward"]
    tools.set_choices(LanguageChoices(links=LinkChoice.PAST_KNOWN, links_from=3000))
    marks.learning_changed("level")
    assert linked(marks, line) == []


def test_the_learners_own_word_wins_over_the_estimate(qapp: QApplication) -> None:
    tools = english_tools(PAST)
    marks, line = marks_for(tools), line_of()
    keep = tools.lookup("keep")[0].entry_id
    awkward = tools.lookup("awkward")[0].entry_id
    assert linked(marks, line) == ["awkward"]  # by the estimate
    tools.vocabulary.set_status(keep, WordStatus.LEARNING)  # in the deck: linked
    tools.vocabulary.set_status(awkward, WordStatus.KNOWN)  # known: not linked
    assert marks.forget(keep, ()) == {line.key}  # a word judged: the line again
    assert linked(marks, line) == ["keep"]


def test_a_language_learned_without_a_full_dictionary_links_key_words(
    qapp: QApplication,
) -> None:
    """The tester's Vietnamese (2026-11-14): no dictionary says which words
    are common, so "past what I know" shows the key links only - and a
    language that isn't learned is linked as before."""
    tools = english_tools(LanguageChoices())
    marks, line = marks_for(tools), line_of(VI)
    assert linked(marks, line) == ["They", "keep", "running", "awkward"]  # not learned
    tools.set_choices(LanguageChoices(), {"vi": PAST})
    marks.learning_changed("level")
    assert linked(marks, line) == ["keep", "running", "awkward"]  # "They": minor
    tools.set_choices(LanguageChoices(), {"vi": LanguageChoices(links=LinkChoice.OFF)})
    marks.learning_changed("level")
    assert linked(marks, line) == []


def test_a_language_with_its_pack_links_past_the_packs_ranks(
    qapp: QApplication,
) -> None:
    """Russian with its pack (polyglotic-hq 338): only key links showed, and
    the server marks every Russian word key - every word was linked, и and
    в too. The pack ranks its words (decision 0120): links start past the
    1,000 commonest, or where the learner chose."""
    tools = english_tools(LanguageChoices())
    tools.basic["es"] = BasicDictionary(SPANISH, FakeSplit(), "es")
    view = CaptionLines(
        (APP,), ZH, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    pairs = (
        ("supe", "知道"),
        ("casa", "房子"),
        ("casar", "结婚"),
        ("Darwin", "达尔文"),
    )
    said = clause("supe casa casar Darwin", "知道房子结婚达尔文", pairs, into=ZH)
    view.apply(finished("a", said, language=Language("es")))
    line, marks = view.lines[0], marks_for(tools)
    tools.set_choices(LanguageChoices(), {"es": PAST})
    # saber (supe) the 160th, casa the 300th; casar the 2,000th, Darwin 8,000th
    assert linked(marks, line) == ["casar", "Darwin"]
    tools.set_choices(
        LanguageChoices(),
        {"es": LanguageChoices(links=LinkChoice.PAST_KNOWN, links_from=5000)},
    )
    marks.learning_changed("level")
    assert linked(marks, line) == ["Darwin"]
    del tools.basic["es"]  # no pack on this PC: key links, as before
    marks.learning_changed("level")
    assert linked(marks, line) == ["supe", "casa", "casar", "Darwin"]


def test_marking_either_form_known_hides_both(qapp: QApplication) -> None:
    """The user (2026-11-15, 338): does marking "thousands" known hide it? A
    status is kept by the entry a caption's word counts for - its base
    word's - and the card marks that same entry: marking "thousands" or
    "thousand" known hides both. (Before 338's base words, "thousands" was
    in no dictionary: it couldn't be marked at all.)"""
    records = [
        EntryRecord("ecdict:thousand", "thousand", "", "", ("num. 千",), 2457),
        EntryRecord("ecdict:many", "many", "", "", ("a. 许多",), 90),
    ]
    file = FakeDictionaryFile(
        records, forms={r.headword: [r.entry_id] for r in records}
    )
    for marked in ("thousands", "thousand"):
        tools = tools_for(EnglishDictionary(file), ENGLISH_FREQUENCY.id)
        tools.vocabulary.set_known_words(1000)
        tools.set_choices(PAST)
        view = CaptionLines(
            (APP,), ZH, keep=10, options=DisplayOptions(word_links=WordLinks.COLOURS)
        )
        pairs = (("thousand", "一千"), ("thousands", "数千"))
        said = clause("thousand many thousands", "一千许多数千", pairs, into=ZH)
        view.apply(finished("a", said, language=EN))
        line, marks = view.lines[0], marks_for(tools)
        assert linked(marks, line) == ["thousand", "thousands"]
        card = Lookup(tools)
        card.show(marked, LookupContext("thousand many thousands"), pinned=True)
        known = card.known()
        assert known is not None and known.headword == "thousand"
        marks.learning_changed("statuses")
        assert linked(marks, line) == [], marked
