"""The bands: words met by frequency band (a written form once, its best
status) or by level, each known / in the deck / new / not heard yet against
the dictionary's size; the rarer words apart; and the words met - heard in
a finished caption from what the PC played, names never (polyglotic-hq
project 163, 155's L1)."""

from tests.learning.fakes import facts, words_of
from tests.learning.test_vocabulary import ENTRIES, Setup, eid

from polyglotic_desktop.core.learning.bands import Band, by_frequency, by_level
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level, WordStatus

K, D, N, I = WordStatus.KNOWN, WordStatus.LEARNING, WordStatus.NEW, WordStatus.IGNORED


def word(rank: int | None, level: int | None = None, name: str = "") -> EntryFacts:
    return facts(name or f"r{rank}", level=level, rank=rank)


def test_frequency_bands_by_status_against_their_sizes() -> None:
    met = [
        (word(5), K),
        (word(6), I),  # ignored: known
        (word(900), D),
        (word(1500), N),
        (word(9000), N),
        (word(12000), K),  # past the last band: rarer
        (word(None), N),  # no rank: rarer
    ]
    bands, rarer = by_frequency(met, [1000, 1000, 3000, 5000])
    assert bands == [
        Band(known=2, deck=1, new=0, size=1000),
        Band(known=0, deck=0, new=1, size=1000),
        Band(size=3000),
        Band(known=0, deck=0, new=1, size=5000),
    ]
    assert bands[0].not_heard == 997 and bands[2].not_heard == 3000
    assert rarer == Band(known=1, deck=0, new=1, size=None) and rarer.not_heard == 0


def test_a_written_form_counts_once_with_its_best_status() -> None:
    """还 hái and huán share a rank: one word, known if either is."""
    hai, huan = facts("hai", rank=40), facts("huan", rank=40)
    bands, _ = by_frequency([(hai, N), (huan, K)], [1000, 1000, 3000, 5000])
    assert bands[0] == Band(known=1, size=1000)


def test_a_band_never_has_fewer_than_none_not_heard() -> None:
    assert Band(known=3, size=2).not_heard == 0


def test_level_bands() -> None:
    met = [(word(1, 1), K), (word(2, 1), D), (word(3, 2), N), (word(4, None), N)]
    assert by_level(met, {1: 300, 2: 200, 7: 5600}) == {
        1: Band(known=1, deck=1, size=300),
        2: Band(new=1, size=200),
        7: Band(size=5600),
    }


def test_words_met_are_heard_from_what_the_pc_played_names_never() -> None:
    s = Setup()
    s.vocab.set_level(Level("hsk-2025", 1))
    s.vocab.caption_finished("c1", words_of("我 今天 和 张伟 去 超市", ENTRIES), False)
    s.vocab.caption_finished("c2", words_of("酸奶", ENTRIES), True)  # the mic
    s.vocab.set_status(eid("超市"), WordStatus.LEARNING)
    met = {f.entry_id: status for f, status in s.vocab.met_words()}
    assert met == {
        eid("我"): K,  # level 1: estimated known
        eid("今天"): K,
        eid("和"): K,
        eid("去"): K,
        eid("超市"): D,
    }


def test_a_words_facts_are_read_from_the_dictionary_once() -> None:
    read: list[EntryId] = []
    s = Setup()

    def counting(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        read.append(entry_id)
        return ENTRIES["我"] if entry_id == eid("我") else None

    s.vocab._facts = counting
    s.vocab.caption_finished("c1", words_of("我", ENTRIES), False)
    read.clear()
    for _ in range(3):
        s.vocab.met_words()
        s.vocab.vocabulary_list()
    assert read == []  # the counting looked it up already: kept since
