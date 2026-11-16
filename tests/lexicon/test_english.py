"""English lookups (core.lexicon.english): words in a line, and inflected
forms counting for their entry - statuses and exposures are per entry."""

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon.english import EnglishDictionary, word_at, words
from polyglotic_desktop.ports.dictionary import EntryRecord


def record(word: str, meaning: str, rank: int | None = None) -> EntryRecord:
    return EntryRecord(f"ecdict:{word}", word, "", "", (meaning,), rank)


def dictionary() -> EnglishDictionary:
    records = [
        record("run", "v. 跑", 202),
        record("running", "n. 赛跑", 3252),
        record("leave", "v. 离开", 300),
        record("left", "a. 左边的", 771),
        record("English", "n. 英语", 900),
        record("I", "pron. 我", 11),
    ]
    file = FakeDictionaryFile(
        records,
        forms={r.headword: [r.entry_id] for r in records},
        lemmas={"running": "run", "ran": "run", "runs": "run", "left": "leave"},
    )
    return EnglishDictionary(file)


def test_words_in_a_line() -> None:
    line = "Doing it like this is overdoing it"
    assert word_at(line, 10) == (9, 13)
    assert word_at("I don't know", 3) == (2, 7)
    assert word_at("tiếng Việt", 2) == (0, 5)
    assert word_at("a, b", 1) is None
    assert words("well-known, it's") == [(0, 10), (12, 16)]


def test_a_word_keeps_the_marks_its_letters_carry() -> None:
    """Devanagari's vowel signs and Arabic's vowel marks are marks, not
    letters, to Python: "हिंदी" had been cut into ह, द (polyglotic-hq 380).
    A mark stays with its word; a word never starts with one."""
    line = "मैं हिंदी बोलता हूँ, وَالكتابُ ру́ку"
    assert [line[a:b] for a, b in words(line)] == [
        "मैं",
        "हिंदी",
        "बोलता",
        "हूँ",
        "وَالكتابُ",
        "ру́ку",
    ]
    assert words("́abc") == [(1, 4)]


def test_a_zero_width_joiner_is_inside_a_word_never_between_two() -> None:
    """Persian writes its plurals and its verbs' prefix on with a zero-width
    non-joiner (داستان‌های, می‌کنم): it had cut them, so "های" was a word
    (polyglotic-hq 387: 36 of the probe's misses). One at a word's edge is
    no part of it."""
    zwnj = "\u200c"
    line = f"داستان{zwnj}های علمی می{zwnj}کنم {zwnj}و"
    assert [line[a:b] for a, b in words(line)] == [
        f"داستان{zwnj}های",
        "علمی",
        f"می{zwnj}کنم",
        "و",
    ]


def test_a_word_among_chinese_characters_is_only_its_letters() -> None:
    """Code-switching (我用English说): the Latin word alone, not the Chinese
    characters it touches (polyglotic-hq 133: a click on iPhone looked up
    年的iPhone太贵了)."""
    line = "李明说2026年的iPhone太贵了！"
    assert word_at(line, line.index("P")) == (9, 15)
    assert word_at(line, line.index("贵")) is None  # the Chinese split's
    assert words("我用English说hello world，好吗") == [(2, 9), (10, 15), (16, 21)]
    assert words("〇〇七 James Bond") == [(4, 9), (10, 14)]


def test_inflected_forms_count_for_their_entry() -> None:
    d = dictionary()
    run = d.lookup("run")[0]
    assert d.entry_for_word("running") == run
    assert d.entry_for_word("ran") == run
    assert d.entry_for_word("Runs") == run  # lower case tried too
    assert d.entry_for_word("xyzzy") is None


def test_a_form_with_meanings_of_its_own_is_looked_up_after_its_lemma() -> None:
    d = dictionary()
    assert [e.headword for e in d.lookup("left")] == ["leave", "left"]
    assert [e.headword for e in d.lookup("running")] == ["run", "running"]


def test_a_possessive_is_its_words_entry() -> None:
    """ "the game's graphics": ECDICT has no "game's" - a possessive is its
    word's, straight or curly apostrophe, and counts for it in a line
    (polyglotic-hq 329: the card said "Not in the dictionary")."""
    d = dictionary()
    assert [e.headword for e in d.lookup("English's")] == ["English"]
    assert [e.headword for e in d.lookup("run’s")] == ["run"]
    assert [e.headword for e in d.lookup("running's")] == ["run", "running"]
    assert d.lookup("xyzzy's") == []
    assert d.lookup("'s") == []
    line = "the run's end"
    found = d.words_in(line, "en-frequency")
    assert [(line[w.start : w.end], w.entry.entry_id) for w in found] == [
        ("run's", "ecdict:run")
    ]


def test_a_form_the_dictionary_lacks_is_found_by_its_base_word() -> None:
    """Real captions (polyglotic-hq 338, Claude's validation loop): ECDICT's
    inflection table has no "thousands", "chilies", "flavorings" or
    "don't", so they were in no dictionary - linked "past what you know"
    at every known line, and "Not in the dictionary" on the card."""
    records = [
        record("thousand", "num. 千", 2457),
        record("chili", "n. 辣椒", 9614),
        record("flavor", "n. 味道", 4585),
        record("flavoring", "n. 调味品", 29144),
        record("city", "n. 城市", 226),
        record("carry", "v. 携带", 624),
        record("do", "v. 做", 28),
        record("can", "v. 能", 27),
        record("they", "pron. 他们", 38),
        record("I", "pron. 我", 11),
        record("glass", "n. 玻璃", 1315),
    ]
    d = EnglishDictionary(
        FakeDictionaryFile(
            records,
            forms={r.headword: [r.entry_id] for r in records},
            lemmas={"flavoring": "flavor"},
        )
    )

    def base(word: str) -> str | None:
        entry = d.entry_for_word(word)
        return entry.headword if entry else None

    assert base("thousands") == base("Thousands") == "thousand"
    assert base("chilies") == "chili" and base("cities") == "city"
    assert base("flavorings") == "flavor"  # then its lemma, as written
    assert base("glasses") == "glass" and base("carried") == "carry"
    assert base("don't") == base("Don’t") == "do"
    assert base("can't") == "can" and base("they're") == "they"
    assert base("I'm") == "I"
    assert base("mosasaurs") is None  # no base the dictionary has
    line = "thousands don't"
    assert [w.entry.frequency_rank for w in d.words_in(line, "en-frequency")] == [
        2457,
        28,
    ]


def test_capitalised_words_are_names_but_i_is_not() -> None:
    d = dictionary()
    assert d.lookup("English")[0].is_name
    assert not d.lookup("I")[0].is_name
    assert not d.lookup("run")[0].is_name


def test_the_words_past_a_rank_are_the_ones_captions_count() -> None:
    """What a learning load takes in (polyglotic-hq 324): commonest first;
    "running" and "left" have ranks of their own, but a caption counts
    them for "run" and "leave", so they are left out."""
    past = dictionary().words_past(100, 10, "en-frequency")
    assert [(rank, f.entry_id) for rank, f in past] == [
        (202, "ecdict:run"),
        (300, "ecdict:leave"),
        (900, "ecdict:English"),
    ]
    assert dictionary().words_past(250, 1, "en-frequency")[0][0] == 300
    # a batch of nothing but inflected forms is read past, not the end
    assert [r for r, _ in dictionary().words_past(700, 1, "en-frequency")] == [900]
    assert dictionary().words_past(900, 5, "en-frequency") == []
