"""Saved sentences: kept with their parts, links and speakers, in a
category shared with saved words, and found again by "most words matched
in the text. characters matched for chinese or words matched in english"
(the user, 2026-11-14; polyglotic-hq 459)."""

from datetime import UTC, datetime, timedelta

import pytest
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.learning.test_vocabulary import eid, lookup

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.saved_words import SavedWord
from polyglotic_desktop.core.learning.sentences import (
    Found,
    SavedSentence,
    SentenceLink,
    SentencePart,
    SentenceSearch,
    normalized,
    query_words,
    saved_words_in,
)
from polyglotic_desktop.core.learning.vocabulary import (
    Changed,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ports.learning import StoredSentence

AT = datetime(2026, 11, 17, 4, 0, tzinfo=UTC)


def sentence(
    n: int, original: str, translation: str = "", category: str = "saved"
) -> SavedSentence:
    return SavedSentence(
        f"s{n}",
        original,
        translation,
        (SentencePart(original, translation),),
        category,
        AT + timedelta(minutes=n),
    )


def ids(found: list[Found]) -> list[str]:
    return [f.sentence.id for f in found]


def test_a_query_is_its_words_and_each_chinese_character() -> None:
    assert query_words("Let's GO, go home!") == ["let", "s", "go", "home"]
    assert query_words("我们去吃饭") == ["我", "们", "去", "吃", "饭"]
    assert query_words("去 coffee 店") == ["去", "coffee", "店"]
    assert query_words("ＡＢＣ") == ["abc"]  # full-width as usual
    assert query_words("สวัสดีครับ") == ["สวัสดีครับ"]  # a Thai run is one word
    assert query_words("  ...  ") == []
    assert normalized("Hello,   World!") == "hello world"


def test_most_of_the_querys_words_find_a_sentence_not_a_consecutive_match() -> None:
    search = SentenceSearch(
        [
            sentence(1, "I went to the shop to buy some fruit"),
            sentence(2, "The fruit was fresh"),
            sentence(3, "Nothing to see here"),
        ]
    )
    # "buy fruit shop": all three words in 1, apart; one of three in 2
    assert ids(search.search("buy fruit shop")) == ["s1"]
    # two words: one is half - found, after those with both
    assert ids(search.search("fresh fruit")) == ["s2", "s1"]
    found = search.search("buy fruit shop")[0]
    assert (found.matched, found.of) == (3, 3)


def test_chinese_is_matched_character_by_character() -> None:
    search = SentenceSearch(
        [
            sentence(1, "我今天去超市买水果"),
            sentence(2, "你吃饭了吗"),
            sentence(3, "今天天气很好"),
        ]
    )
    # 今 天 买 果: all four in 1, two in 3 (half), none in 2
    assert ids(search.search("今天买果")) == ["s1", "s3"]
    assert ids(search.search("吃饭")) == ["s2"]


def test_the_translation_is_searched_too() -> None:
    search = SentenceSearch(
        [
            sentence(1, "我今天去超市", "I went to the supermarket today"),
            sentence(2, "你吃饭了吗", "Have you eaten?"),
        ]
    )
    assert ids(search.search("supermarket")) == ["s1"]
    assert ids(search.search("eaten")) == ["s2"]
    # a query in both: what was said and the translation together
    assert ids(search.search("超市 today")) == ["s1"]


def test_a_word_is_found_from_its_start_as_the_learner_types() -> None:
    search = SentenceSearch([sentence(1, "We are learning Chinese")])
    assert ids(search.search("learn")) == ["s1"]
    assert ids(search.search("earn")) == []  # not inside a word
    assert ids(search.search("CHINESE")) == ["s1"]


def test_ranked_by_words_found_then_the_query_as_typed_then_newest() -> None:
    search = SentenceSearch(
        [
            sentence(1, "go home now please"),  # oldest, as typed
            sentence(2, "now go home"),  # "go home" as typed
            sentence(3, "home, then go"),  # both, apart
            sentence(4, "go somewhere"),  # one of two
        ]
    )
    assert ids(search.search("go home")) == ["s2", "s1", "s3", "s4"]


def test_no_query_is_every_sentence_newest_first_and_a_category_filters() -> None:
    search = SentenceSearch(
        [
            sentence(1, "one", category="saved"),
            sentence(2, "two", category="trip"),
            sentence(3, "three", category="saved"),
        ]
    )
    assert ids(search.search()) == ["s3", "s2", "s1"]
    assert ids(search.search(category="saved")) == ["s3", "s1"]
    search.remove("s3")
    assert ids(search.search(category="saved")) == ["s1"]


def saved(headword: str, traditional: str = "") -> SavedWord:
    return SavedWord(
        EntryId(f"x:{headword}"), headword, traditional, "", "", "saved", "", "", AT
    )


def test_a_saved_word_finds_the_sentences_it_is_in() -> None:
    search = SentenceSearch(
        [
            sentence(1, "我的电脑又卡了"),
            sentence(2, "我的電腦壞了"),  # the traditional form
            sentence(3, "I run every day"),
            sentence(4, "a long runway"),
            sentence(5, "电视", "the computer"),  # in the translation only
        ]
    )
    assert ids(search.search(word=saved("电脑", "電腦"))) == ["s2", "s1"]
    assert ids(search.search(word=saved("run"))) == ["s3"]  # whole words
    assert saved_words_in(
        sentence(1, "我的电脑 and I run"), [saved("电脑"), saved("run"), saved("go")]
    ) == [saved("电脑"), saved("run")]


def test_searching_5000_sentences_is_quick() -> None:
    """The user's bound (2026-11-14): under 100 ms at 5,000 sentences. A
    loose check here; `tools/bench_sentences.py` measures it."""
    import time

    search = SentenceSearch(
        sentence(n, f"我们今天去第{n}家店吃饭 {n}", f"We went to shop number {n} today")
        for n in range(5000)
    )
    started = time.perf_counter()
    found = search.search("今天 shop number 吃饭")
    assert time.perf_counter() - started < 0.5
    assert len(found) == 5000


# -- kept by the vocabulary --------------------------------------------------------


def vocabulary(store: MemoryLearningStore, clock: Clock | None = None) -> Vocabulary:
    return Vocabulary(store, lookup, "hsk-2025", clock=clock or Clock())


PARTS = (
    SentencePart(
        "我今天去超市", "I went to the supermarket today",
        (SentenceLink((4, 6), (14, 25)),), "Discord",
    ),
    SentencePart("买水果", "to buy fruit", (), "You"),
)  # fmt: skip


def test_a_saved_sentence_is_kept_with_its_parts_links_and_speakers() -> None:
    store = MemoryLearningStore()
    vocab = vocabulary(store)
    changes: list[object] = []
    vocab.subscribe(changes.append)
    kept = vocab.save_sentence(
        PARTS, "我今天去超市买水果", "I went to the supermarket today to buy fruit",
        "saved", "en",
    )  # fmt: skip
    assert changes == [VocabularyChanged(Changed.SENTENCES)]  # nothing for the server
    assert kept.speakers == ("Discord", "You")
    again = vocabulary(store)
    assert again.sentences == [kept]
    assert ids(again.find_sentences("超市 fruit")) == [kept.id]


def test_a_sentence_moves_category_and_is_deleted() -> None:
    store = MemoryLearningStore()
    vocab = vocabulary(store)
    tricky = vocab.categories[1].id
    kept = vocab.save_sentence(PARTS, "我今天去超市买水果", "", "saved")
    vocab.move_sentence(kept.id, tricky)
    assert ids(vocab.find_sentences(category_id=tricky)) == [kept.id]
    assert vocabulary(store).sentences[0].category_id == tricky
    vocab.unsave_sentence(kept.id)
    assert vocab.sentences == [] and store.sentences == {}
    with pytest.raises(ValueError, match="no category"):
        vocab.save_sentence(PARTS, "我", "", "no-such-category")
    with pytest.raises(ValueError, match="empty"):
        vocab.save_sentence((), " ", "", "saved")


def test_sentences_go_with_their_category_and_with_the_learning_data() -> None:
    store = MemoryLearningStore()
    vocab = vocabulary(store)
    trip = vocab.add_category("Trip").id
    vocab.save_sentence(PARTS, "我今天去超市", "", trip)
    kept = vocab.save_sentence(PARTS, "买水果", "", "saved")
    vocab.remove_category(trip)
    assert vocab.sentences == [kept] and list(store.sentences) == [kept.id]
    assert ids(vocab.find_sentences("超市")) == []
    vocab.delete_learning_data()
    assert vocab.sentences == [] and store.sentences == {}
    assert vocab.find_sentences() == []


def test_a_saved_word_filters_the_sentences() -> None:
    vocab = vocabulary(MemoryLearningStore())
    vocab.save(
        eid("超市"), "超市", "超市", "chāo shì", "supermarket", "saved",
        LookupContext("", ""),
    )  # fmt: skip
    kept = vocab.save_sentence(PARTS, "我今天去超市", "", "saved")
    vocab.save_sentence(PARTS, "买水果", "", "saved")
    assert ids(vocab.find_sentences(word=eid("超市"))) == [kept.id]
    assert vocab.find_sentences(word=eid("水果")) == []  # not saved: nothing


class CountingStore(MemoryLearningStore):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    def saved_sentences(self) -> list[StoredSentence]:
        self.reads += 1
        return super().saved_sentences()


def test_saved_sentences_are_read_when_first_wanted_not_at_the_start() -> None:
    """A learner's thousands of sentences never slow the start: read once,
    by the first look at them or the first save."""
    store = CountingStore()
    vocab = vocabulary(store)
    vocab.set_status(eid("超市"), WordStatus.KNOWN)
    assert store.reads == 0
    vocab.save_sentence(PARTS, "我今天去超市", "", "saved")
    vocab.find_sentences("超市")
    assert store.reads == 1 and len(vocab.sentences) == 1
