"""Every word met's facts - what Words asks for - read ahead, off the
interface thread, and handed back (polyglotic-hq project 212): Words'
first show then reads nothing from the dictionary."""

from tests.learning.words_met import (
    APPLE,
    ENTRIES,
    ENTRIES_AND_APPLE,
    HEARD,
    Counting,
    eid,
    started,
)

from polyglotic_desktop.core.shared import Level, WordInLine


def test_every_word_mets_facts_read_ahead_leave_words_nothing_to_read() -> None:
    lookup = Counting()
    vocabulary = started(lookup)
    read = vocabulary.facts_to_read()
    assert lookup.read == []  # nothing read until the read runs
    found = read()
    assert sorted(e for e, _ in lookup.read) == sorted(
        eid(w) for w in [*HEARD, "折扣", "水果"]
    )
    vocabulary.know_facts(found)
    lookup.read.clear()
    met = vocabulary.met_words()
    rows = vocabulary.vocabulary_list()
    hearing = vocabulary.keep_hearing()
    assert lookup.read == []  # what Words asks for: all read ahead
    # the same as read on the way
    itself = started(Counting())
    assert met == itself.met_words()
    assert rows == itself.vocabulary_list()
    assert hearing == itself.keep_hearing()


def test_the_read_ahead_reads_what_was_met_and_leaves_out_what_it_didnt_find() -> None:
    """The read runs on another thread: it reads the words met when it was
    asked for (a word heard since is read as it's counted). A word the
    dictionary didn't answer - it may have been out - is asked for again
    when wanted, rather than kept as unknown."""
    lookup = Counting()
    vocabulary = started(lookup)
    read = vocabulary.facts_to_read()
    vocabulary.caption_finished("c1", [WordInLine(0, 2, APPLE)], by_you=False)
    lookup.read.clear()
    lookup.entries = {eid("我"): ENTRIES[eid("我")]}  # the rest not answered
    found = read()
    assert len(lookup.read) == 7 and APPLE.entry_id not in dict(lookup.read)
    assert list(found.found) == [eid("我")]
    lookup.entries = ENTRIES_AND_APPLE
    vocabulary.know_facts(found)
    lookup.read.clear()
    vocabulary.met_words()
    assert sorted(e for e, _ in lookup.read) == sorted(
        eid(w) for w in ("超市", "酸奶", "榴莲", "张伟")
    )  # 我 read ahead; the apple read when it was counted


def test_facts_read_ahead_in_one_scheme_arent_used_in_another() -> None:
    lookup = Counting()
    vocabulary = started(lookup)
    found = vocabulary.facts_to_read()()
    vocabulary.set_level(Level("en-frequency", 2))  # another scheme since
    vocabulary.know_facts(found)
    lookup.read.clear()
    vocabulary.met_words()
    assert {scheme for _, scheme in lookup.read} == {"en-frequency"}
