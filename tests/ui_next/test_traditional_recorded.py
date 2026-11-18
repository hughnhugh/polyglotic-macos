"""A Traditional learner hears the recorded word (polyglotic-hq 439).

CC-CEDICT's recorded words are kept under their Simplified headwords
(424, decision 0197), and a learner who reads Traditional looks up the
Traditional form: 52% of the 10,000 are written differently, and went to
Windows' Taiwanese voice or "no voice". The card finds the recording
through the word's Simplified form - its first entry's headword, then the
converter's - and never plays another word's: a Traditional form written
for two words (乾: 干 "dry", 乾 "heaven") is the one the card shows first."""

import time
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import chinese_sample
from tests.ui_next.test_lookup_view import Learner
from tests.ui_next.test_say_it import HANHAN, HUIHUI, Speaker, pin

from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.main import MandarinScript
from polyglotic_desktop.ports.speaker import RECORDED, Voice
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.views.lookup import Lookup, LookupContext
from polyglotic_desktop.ui_next.word_speech import WordSpeech

OURS = Voice(f"{RECORDED}zh", "Chatterbox", "zh-CN")
"""CC-CEDICT's recorded voice (its file says zh-CN)."""

SAMPLE = """\
電腦 电脑 [dian4 nao3] /computer/
乾 干 [gan1] /dry/
乾 乾 [qian2] /one of the Eight Trigrams/
乾淨 干净 [gan1 jing4] /clean/
乾燥 干燥 [gan1 zao4] /dry/
藉口 藉口 [jie4 kou3] /to use as an excuse/
借口 借口 [jie4 kou3] /excuse/
"""


def chinese(traditional: bool) -> ChineseDictionary:
    """CC-CEDICT, and Traditional shown (the converter told) or not."""
    dictionary = ChineseDictionary(chinese_sample(SAMPLE))
    if traditional:
        dictionary.read_traditional({"藉": "借", "乾": "干", "腦": "脑", "電": "电"})
    return dictionary


def learner(traditional: bool = True) -> Learner:
    return learner_of(chinese(traditional))


def learner_of(dictionary: ChineseDictionary) -> Learner:
    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    vocabulary = Vocabulary(MemoryLearningStore(), facts, "hsk-2025", Clock())
    return Learner(vocabulary, dictionary)


def simplified(word: str, traditional: bool = True) -> tuple[str, ...]:
    lookup = Lookup(learner(traditional))
    lookup.show(word, LookupContext(word), pinned=True)
    return lookup.card().simplified


def test_a_traditional_card_knows_its_simplified_forms_best_first() -> None:
    assert simplified("電腦") == ("电脑",)  # the dictionary's own pair
    assert simplified("电脑") == ()  # written in Simplified: as it is
    # two words written 乾: the one the card shows first ("dry", gān)
    assert simplified("乾") == ("干",)
    # CC-CEDICT's own headword first, then the converter's
    assert simplified("藉口") == ("藉口", "借口")


def test_a_word_that_is_a_simplified_headword_too_is_as_written_for_a_simplified_reader() -> (
    None
):
    """乾 in Simplified text is qián (乾隆): read as written unless
    Traditional is shown. A form only Traditional writes is still found."""
    assert simplified("乾", traditional=False) == ()
    assert simplified("電腦", traditional=False) == ("电脑",)


class Recorded:
    """The recorded voice's words (`Recordings.has`)."""

    def __init__(self, *words: str) -> None:
        self.words = set(words)

    def __call__(self, voice: Voice, word: str) -> bool:
        return voice == OURS and word in self.words


@pytest.fixture(params=[True], ids=["traditional"])
def card(qapp: QApplication, request: pytest.FixtureRequest) -> Iterator[LookupCard]:
    made = LookupCard(learner(request.param))
    yield made
    made.close_card()
    made.close()
    made.deleteLater()
    qapp.processEvents()


def said(card: LookupCard, word: str, *recorded: str) -> str:
    """What the card's speaker says for `word`, and in which voice."""
    speaker = Speaker((OURS, HUIHUI, HANHAN))
    speech = WordSpeech(speaker, recorded=Recorded(*recorded), parent=card)
    card.use_speech(speech)
    pin(card, word)
    card.do("say")
    card.close_card()
    return f"{speaker.said[0][0]} {speaker.said[0][1]}" if speaker.said else ""


def test_a_traditional_form_plays_the_recording_of_its_simplified_one(
    card: LookupCard,
) -> None:
    assert said(card, "電腦", "电脑") == f"电脑 {OURS.id}"


def test_a_traditional_form_for_two_words_plays_the_one_the_card_shows(
    card: LookupCard,
) -> None:
    """乾 is recorded too, as the Simplified word 乾 (qián): never played
    for the card's 乾 "dry"."""
    assert said(card, "乾", "干", "乾") == f"干 {OURS.id}"
    # its own word not recorded: Taiwan's voice says it as written
    assert said(card, "乾", "乾") == "乾 zh-tw-1"


def test_the_converters_form_is_tried_after_the_dictionarys(
    card: LookupCard,
) -> None:
    assert said(card, "藉口", "借口") == f"借口 {OURS.id}"
    assert said(card, "藉口", "藉口", "借口") == f"藉口 {OURS.id}"


def test_a_simplified_word_and_an_unrecorded_one_are_as_before(
    card: LookupCard,
) -> None:
    assert said(card, "电脑", "电脑") == f"电脑 {OURS.id}"
    assert said(card, "電腦") == "電腦 zh-tw-1"  # not recorded: Taiwan's voice


def test_a_second_click_plays_a_traditional_learners_recording_again(
    card: LookupCard,
) -> None:
    """The recorded voice is the mainland's (zh-CN): every click asks it for
    the Simplified form it holds, at its own pace - the recording again,
    never the PC's voice slower (polyglotic-hq 518)."""
    speaker = Speaker((OURS, HUIHUI, HANHAN))
    speech = WordSpeech(speaker, recorded=Recorded("电脑"), parent=card)
    card.use_speech(speech)
    pin(card, "電腦")
    card.do("say")
    assert speaker.ended is not None
    speaker.ended(True)
    QApplication.processEvents()
    card.do("say")
    assert speaker.said == [("电脑", OURS.id, 1.0), ("电脑", OURS.id, 1.0)]


@pytest.mark.parametrize("card", [False], indirect=True, ids=["simplified"])
def test_a_simplified_readers_word_plays_its_own_recording(card: LookupCard) -> None:
    assert said(card, "乾", "干", "乾") == f"乾 {OURS.id}"


ZHE = """著 着 [zhe5] /aspect particle/
著 著 [zhu4] /to write/
"""


@pytest.fixture
def words_card(
    qapp: QApplication,
) -> Iterator[tuple[LookupCard, MandarinScript, ChineseDictionary]]:
    """A card opened from Words - no caption yet this run - and the
    "Show Mandarin in" choice, with the converter's real table (442)."""
    dictionary = ChineseDictionary(chinese_sample(SAMPLE + ZHE))
    script = MandarinScript(lambda: dictionary)
    made = LookupCard(learner_of(dictionary))
    yield made, script, dictionary
    made.close_card()
    made.close()
    made.deleteLater()
    qapp.processEvents()


def told(dictionary: ChineseDictionary, wanted: bool) -> None:
    """Waits (a few seconds at most) for the converter's table, read on a
    thread of its own, to be told to the dictionary - or forgotten."""
    deadline = time.monotonic() + 10
    while (dictionary.simplified("著") == "着") != wanted:
        assert time.monotonic() < deadline, "never told" if wanted else "never forgot"
        time.sleep(0.01)


def test_a_card_from_words_before_any_caption_plays_the_simplified_recording(
    words_card: tuple[LookupCard, MandarinScript, ChineseDictionary],
) -> None:
    """442: Traditional is told to the dictionary when it's chosen (at the
    start, or switched on), not with the first converted caption."""
    card, script, dictionary = words_card
    script.traditional = True
    told(dictionary, True)
    assert said(card, "著", "着", "著") == f"着 {OURS.id}"


def test_switched_back_to_simplified_a_word_is_read_as_written_again(
    words_card: tuple[LookupCard, MandarinScript, ChineseDictionary],
) -> None:
    """著 is a Simplified headword too (zhù): once Traditional is switched
    off, it plays its own recording again, as before it was ever on."""
    card, script, dictionary = words_card
    script.traditional = True
    told(dictionary, True)
    script.traditional = False
    told(dictionary, False)
    assert said(card, "著", "着", "著") == f"著 {OURS.id}"
