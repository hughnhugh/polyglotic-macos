"""Words' "Your words" in the list's order without a row for each word
met, and "Words you keep hearing" - a merged entry's status as `status`
has it (polyglotic-hq project 212)."""

from tests.learning.words_met import (
    ENTRIES,
    HEARD_BY_ID,
    Counting,
    eid,
    started,
    store,
)

from polyglotic_desktop.core.shared import EntryId, WordStatus


def test_your_words_are_in_the_lists_order_without_reading_their_facts() -> None:
    """Most heard first, then most heard by you, then by ID - a word never
    heard (only saved, or given a status) last; with a status, only those.
    Without one, no word's facts are read: a row is made only for those
    shown (`vocabulary_row`)."""
    lookup = Counting()
    vocabulary = started(lookup)
    order = vocabulary.met_entries()
    assert lookup.read == []
    assert order == [
        eid("我"), eid("超市"), eid("榴莲"), eid("酸奶"), eid("张伟"),
        eid("折扣"), eid("水果"),
    ]  # fmt: skip
    assert order == [row.entry_id for row in vocabulary.vocabulary_list()]
    assert [vocabulary.vocabulary_row(e) for e in order] == vocabulary.vocabulary_list()
    for status in WordStatus:
        assert vocabulary.met_entries(status) == [
            row.entry_id
            for row in vocabulary.vocabulary_list()
            if row.status.status is status
        ]
    assert vocabulary.met_entries(WordStatus.KNOWN) == [eid("我"), eid("折扣")]
    assert vocabulary.met_entries(WordStatus.IGNORED) == [eid("张伟")]


def test_a_merged_entrys_status_is_its_new_entrys_in_every_list() -> None:
    """A word heard under an entry ID the dictionary has since merged: its
    facts name the new entry, whose status counts - in "Your words" by
    status and in "Words you keep hearing", as in `status`."""
    old = EntryId("test:old")
    lookup = Counting({**ENTRIES, old: ENTRIES[eid("酸奶")]})  # merged into 酸奶
    vocabulary = started(lookup, store({**HEARD_BY_ID, old: (9, 0)}))
    assert old in [e for e, _ in vocabulary.keep_hearing()]
    vocabulary.set_status(eid("酸奶"), WordStatus.LEARNING)
    assert old in vocabulary.met_entries(WordStatus.LEARNING)
    assert old not in vocabulary.met_entries(WordStatus.NEW)
    assert old not in [e for e, _ in vocabulary.keep_hearing()]
