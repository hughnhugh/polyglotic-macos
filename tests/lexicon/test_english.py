"""English lookups (core.lexicon.english): words in a line, and inflected
forms counting for their entry - statuses and exposures are per entry."""

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon.english import (
    EnglishDictionary,
    inside_sentence,
    names_first,
    word_at,
    words,
)
from polyglotic_desktop.core.shared import EntryId
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


def test_a_lower_case_word_found_only_capitalised_is_tried_so() -> None:
    """ECDICT has "North", "I" and "Mr" only capitalised: a lower-case
    caption's "north", "i'm" or "mr" was in no dictionary (polyglotic-hq
    447's top-200 check, 462). A word written in lower case is tried
    capitalised when it isn't found; a name never finds the word before
    its own entry."""
    records = [
        record("North", "n. 北方", 578),
        record("I", "pron. 我", 11),
        record("Mr", "先生", 123),
        record("Bill", "n. 比尔", 5000),
        record("bill", "n. 账单", 800),
        record("S", "n. 硫", 2800),
    ]
    d = EnglishDictionary(
        FakeDictionaryFile(records, forms={r.headword: [r.entry_id] for r in records})
    )

    def headwords(word: str) -> list[str]:
        return [e.headword for e in d.lookup(word)]

    assert headwords("north") == ["North"]
    assert headwords("i") == headwords("i'm") == headwords("i've") == ["I"]
    assert headwords("mr") == ["Mr"]
    assert headwords("bill") == ["bill"] and headwords("Bill") == ["Bill"]
    assert headwords("nOrth") == [] and headwords("xyzzy") == []
    assert headwords("s") == [] and headwords("S") == ["S"]  # 1990s: a letter


def test_spoken_forms_open_the_word_they_are_made_of() -> None:
    """ "gonna", "cannot", "wanna" and "gotta" aren't in ECDICT: they were
    in no dictionary, though "gonna" is among English's commonest 500
    words (polyglotic-hq 462's top-200 check, 463). Each opens its word:
    going to (go's), can not, want to, got to (get's)."""
    records = [
        record("go", "vi. 去", 47),
        record("going", "n. 去", 900),
        record("can", "aux. 能", 28),
        record("want", "vt. 要", 78),
        record("get", "vt. 得到", 36),
    ]
    d = EnglishDictionary(
        FakeDictionaryFile(
            records,
            forms={r.headword: [r.entry_id] for r in records},
            lemmas={"going": "go", "got": "get"},
        )
    )
    assert [e.headword for e in d.lookup("gonna")] == ["go", "going"]
    assert d.entry_for_word("Gonna") == d.lookup("go")[0]
    assert [e.headword for e in d.lookup("cannot")] == ["can"]
    assert [e.headword for e in d.lookup("wanna")] == ["want"]
    assert [e.headword for e in d.lookup("gotta")] == ["get"]


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


def names_dictionary() -> EnglishDictionary:
    """As polyglotic-hq 464's build writes them: "John" a name of our own
    (ECDICT's john is a toilet); "Bill" the word bill, then the name;
    "bit" its own entry, then bite's."""
    records = [
        record("john", "n. 厕所", 30000),
        record("John", "n. 约翰（男子名）"),
        record("bill", "n. 帐单", 900),
        record("Bill", "n. 比尔（男子名）"),
        record("bite", "v. 咬", 2000),
        record("bit", "n. 少量", 400),
        record("Monday", "n. 星期一", 700),
    ]
    forms = {r.headword: [r.entry_id] for r in records}
    forms["Bill"] = ["ecdict:bill", "ecdict:Bill"]
    forms["bit"] = ["ecdict:bit", "ecdict:bite"]
    return EnglishDictionary(FakeDictionaryFile(records, forms=forms))


def test_a_word_is_inside_a_sentence_unless_it_starts_one() -> None:
    line = 'Bill said "Will you?" and Bill left. - Mark? Then: Rose, and Grace'
    inside = {line[s:e]: inside_sentence(line, s) for s, e in words(line)}
    assert inside == {
        "Bill": True,  # the second (a dict keeps the last)
        "said": True,
        "Will": False,  # after an opening quote at a sentence's start
        "you": True,
        "and": True,
        "left": True,
        "Mark": False,  # a dialogue line's dash
        "Then": False,
        "Rose": False,  # after a colon
        "Grace": True,
    }
    assert not inside_sentence(line, 0)
    assert not inside_sentence("  Bill", 2)


def test_a_given_name_ecdict_has_only_as_a_word_opens_as_a_name() -> None:
    """polyglotic-hq 464: a caption's "John" opened john, 厕所 ("toilet");
    "Bill" inside a sentence is the name, but a sentence's first "Bill" is
    still looked up as the word, the name second."""
    d = names_dictionary()
    assert [e.headword for e in d.lookup("John")] == ["John"]
    assert [e.headword for e in d.lookup("John", inside=True)] == ["John"]
    assert d.lookup("John")[0].is_name
    assert [e.headword for e in d.lookup("john")] == ["john"]
    assert [e.headword for e in d.lookup("Bill")] == ["bill", "Bill"]
    assert [e.headword for e in d.lookup("Bill", inside=True)] == ["Bill", "bill"]
    assert [e.headword for e in d.lookup("Bill's", inside=True)] == ["Bill", "bill"]
    assert [e.headword for e in d.lookup("bill", inside=True)] == ["bill"]
    assert [e.headword for e in d.lookup("Monday", inside=True)] == ["Monday"]

    line = "Bill paid the bill and Bill left with John"
    counted = [(line[w.start : w.end], w.entry.is_name) for w in d.words_in(line, "x")]
    assert counted == [
        ("Bill", False),  # a sentence's first word: the word bill
        ("bill", False),
        ("Bill", True),
        ("John", True),
    ]
    assert names_first(d.lookup("Bill"), "bill") == d.lookup("Bill")


def test_a_form_listed_with_its_own_entry_first_counts_for_it() -> None:
    """polyglotic-hq 464: "a bit" opened bite (咬), and counted for it. The
    dictionary file lists bit's own entry first, then bite's."""
    d = names_dictionary()
    assert [e.headword for e in d.lookup("bit")] == ["bit", "bite"]
    assert d.entry_for_word("bit") == d.lookup("bit")[0]
    assert d.entry_for_word("Bit") == d.lookup("bit")[0]


class SpanishMeanings:
    """A stand-in meanings file: ECDICT's meanings in Spanish (decision 0234)."""

    def __init__(self, rows: dict[str, tuple[str, ...]]) -> None:
        self.rows = rows

    def meanings(self, entry_id: str) -> tuple[str, ...] | None:
        return self.rows.get(entry_id)


def test_an_entry_the_learners_meanings_file_has_is_shown_in_their_language() -> None:
    """Decision 0234: the card's meanings are the learner's language's where
    the file has the entry - its form ("ran") too, through its lemma - and
    the dictionary's own where it hasn't; the entry is still the same one,
    so statuses don't change."""
    english = dictionary()
    english.explain_in(SpanishMeanings({"ecdict:run": ("(verb) correr",)}))
    (run,) = english.lookup("ran")
    assert run.meanings == ("(verb) correr",)
    assert (run.entry_id, run.frequency_rank) == ("ecdict:run", 202)
    assert english.lookup("leave")[0].meanings == ("v. 离开",)  # not in the file
    entry = english.entry(EntryId("ecdict:run"))
    assert entry is not None and entry.meanings == ("(verb) correr",)
    english.explain_in(None)
    assert english.lookup("run")[0].meanings == ("v. 跑",)
