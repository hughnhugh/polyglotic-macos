"""A word a pack hasn't got, looked up by its parts (polyglotic-hq 390):
German compounds and hyphenated words, which real German captions linked
with no word found under them (Internetmaterialien, Blog-Erfahrung)."""

from tests.lexicon.sample import FakeDictionaryFile
from tests.lexicon.test_basic import FakeSplit, record

from polyglotic_desktop.core.lexicon import compounds
from polyglotic_desktop.core.lexicon.basic import BasicDictionary

WORDS = [
    *("Internet", "Material", "Blog", "Erfahrung", "Arbeit", "Platz", "Schule"),
    *("Bus", "Zeit", "zeit", "Haus", "Haustür", "Tür", "Berlin", "T", "Feld"),
]
GERMAN = FakeDictionaryFile(
    [
        record("wiktde:Internet", "Internet", "(noun) Internet", 900),
        record("wiktde:Material", "Material", "(noun) material", 1500),
        record("wiktde:Blog", "Blog", "(noun) blog", 6000),
        record("wiktde:Erfahrung", "Erfahrung", "(noun) experience", 700),
        record("wiktde:Arbeit", "Arbeit", "(noun) work", 200),
        record("wiktde:Platz", "Platz", "(noun) place", 400),
        record("wiktde:Schule", "Schule", "(noun) school", 350),
        record("wiktde:Bus", "Bus", "(noun) bus", 2500),
        record("wiktde:Zeit", "Zeit", "(noun) time", 60),
        record("wiktde:zeit", "zeit", "(preposition) during", 30000),
        record("wiktde:Haus", "Haus", "(noun) house", 150),
        record("wiktde:Haustür", "Haustür", "(noun) front door", 9000),
        record("wiktde:Tür", "Tür", "(noun) door", 800),
        record("wiktde:Berlin", "Berlin", "(name) Berlin", 500),
        record("wiktde:T", "T", "(letter) T", 20000),
        record("wiktde:Feld", "Feld", "(noun) field", 1200),
    ],
    {w: [f"wiktde:{w}"] for w in WORDS},
    lemmas={"Materialien": "Material", "Häuser": "Haus"},
)


def german() -> BasicDictionary:
    return BasicDictionary(GERMAN, FakeSplit(), "de")


def cut(dictionary: BasicDictionary, word: str) -> list[tuple[str, str, bool]]:
    return [(word[p.start : p.end], p.form, p.found) for p in dictionary.parts(word)]


def test_a_german_compound_the_pack_hasnt_got_is_its_words() -> None:
    d = german()
    assert d.lookup("Internetmaterialien") == []  # not in it as a whole
    assert cut(d, "Internetmaterialien") == [
        ("Internet", "Internet", True),
        ("materialien", "Materialien", True),  # a noun, its plural's lemma
    ]


def test_a_linking_letter_belongs_to_the_part_before() -> None:
    assert cut(german(), "Arbeitsplatz") == [
        ("Arbeits", "Arbeit", True),
        ("platz", "Platz", True),
    ]


def test_a_part_cut_short_is_the_word_it_was_cut_from() -> None:
    # Schul-bus: Schule; and a lower-case part is a noun first (Zeit, not zeit)
    assert cut(german(), "Schulbuszeit") == [
        ("Schul", "Schule", True),
        ("bus", "Bus", True),
        ("zeit", "Zeit", True),
    ]


def test_the_fewest_parts_win_then_the_commonest() -> None:
    # Haustür + feld, not Haus + tür + feld
    assert [form for _, form, _ in cut(german(), "Haustürfeld")] == ["Haustür", "Feld"]


def test_a_word_the_pack_has_whole_is_never_cut() -> None:
    assert german().parts("Haustür") == []


def test_no_cut_unless_every_part_is_a_word_the_pack_has_and_no_name() -> None:
    d = german()
    assert d.parts("Kovelun") == []  # a name the speech model misheard
    assert d.parts("Berlinzeit") == []  # a name is no compound's part
    assert d.parts("Arbeitxyz") == []


def test_a_hyphenated_word_is_its_pieces_each_shown_found_or_not() -> None:
    d = german()
    assert cut(d, "Blog-Erfahrung") == [
        ("Blog", "Blog", True),
        ("Erfahrung", "Erfahrung", True),
    ]
    assert cut(d, "T-Rex") == [("T", "T", True), ("Rex", "Rex", False)]
    assert cut(d, "Berlin-Arbeitsplatz") == [  # a name will do, pieces cut again
        ("Berlin", "Berlin", True),
        ("Arbeits", "Arbeit", True),
        ("platz", "Platz", True),
    ]
    assert d.parts("Xy-Zw") == []  # nothing found: no parts at all


def test_only_german_closes_compounds_up_but_any_language_has_hyphens() -> None:
    spanish = BasicDictionary(GERMAN, FakeSplit(), "es")
    assert spanish.parts("Internetmaterialien") == []
    assert [p.form for p in spanish.parts("Blog-Erfahrung")] == ["Blog", "Erfahrung"]


def test_a_captions_words_are_a_compounds_parts_each_over_its_own_letters() -> None:
    line = "Die Internetmaterialien am Arbeitsplatz"
    words = german().words_in(line, "de-frequency")
    found = [(line[w.start : w.end], w.entry.entry_id) for w in words]
    # every letter of the compound is under a part, so a link over it is
    # known only when every part is
    assert found == [
        ("Internet", "wiktde:Internet"),
        ("materialien", "wiktde:Material"),
        ("Arbeits", "wiktde:Arbeit"),
        ("platz", "wiktde:Platz"),
    ]


def test_spellings_put_a_noun_first_where_nouns_are_capitalised() -> None:
    assert compounds.spellings("zeit", "de")[0] == "Zeit"
    assert compounds.spellings("zeit", "es")[0] == "zeit"


def test_a_participle_or_a_small_word_is_no_compounds_part() -> None:
    """On FLEURS' German, "schreienden" was cut as Schrei + enden, and
    "wiederzuerkennendes" as its verb + des (polyglotic-hq 390)."""
    file = FakeDictionaryFile(
        [
            record("wiktde:schreien", "schreien", "(verb) to scream", 2000),
            record("wiktde:Schrei", "Schrei", "(noun) scream", 4000),
            record("wiktde:enden", "enden", "(verb) to end", 1500),
            record("wiktde:den", "den", "(article) the", 5),
            record("wiktde:Bod", "Boden", "(noun) floor", 900),
            record("wiktde:Abo", "Abo", "(noun) subscription", 3000),
        ],
        {
            "schreien": ["wiktde:schreien"],
            "Schrei": ["wiktde:Schrei"],
            "enden": ["wiktde:enden"],
            "den": ["wiktde:den"],
            "Boden": ["wiktde:Bod"],
            "Abo": ["wiktde:Abo"],
        },
    )
    d = BasicDictionary(file, FakeSplit(), "de")
    assert d.parts("schreienden") == []
    assert d.parts("Schreiden") == []  # Schrei + den: "den" is a small word
    assert d.parts("Bodabo") == []  # "Bod" is too short to be Boden cut short
    assert [p.form for p in d.parts("Bodenabo")] == ["Boden", "Abo"]


KOREAN_WORDS = {
    "국립": ("(noun) national", 2245),
    "공원": ("(noun) park", 759),
    "식물": ("(noun) plant", 1800),
    "-성": ("(suffix) -ity, -ness", 0),
    "여행": ("(noun) travel, trip", 600),
    "객": ("(noun) guest", 3000),
    "대-": ("(prefix) large, great", 0),
    "도시": ("(noun) city", 350),
    "대표": ("(noun) representative", 50000),
    "팀": ("(noun) team", 30000),
    "표팀": ("(noun) a word made up to tempt a cut", 1),
    "바깥": ("(noun) outside", 2000),
    "층": ("(noun) floor, layer", 515),
    "국": ("(noun) soup", 900),
    "립": ("(syllable) 立: stand", 0),
    "공": ("(noun) ball", 800),
    "원": ("(noun) won (currency)", 200),
    "파티": ("(noun) party", 3000),
    "-마": ("(suffix) horse", 0),
}
KOREAN = FakeDictionaryFile(
    [
        record(f"wiktko:{w}", w, meaning, rank)
        for w, (meaning, rank) in KOREAN_WORDS.items()
    ],
    {w: [f"wiktko:{w}"] for w in KOREAN_WORDS},
)


def korean() -> BasicDictionary:
    return BasicDictionary(KOREAN, FakeSplit(), "ko")


def test_a_korean_compound_is_its_words_of_two_syllables_or_more() -> None:
    """Korean closes compounds up (국립공원, national park) and Wiktionary
    lists few: such a word is its words of two syllables or more - never
    single syllables, any of which is some word (국, 립, 공, 원) - then a
    one-syllable suffix, word or prefix read by hand (polyglotic-hq 516)."""
    assert cut(korean(), "국립공원") == [("국립", "국립", True), ("공원", "공원", True)]
    assert cut(korean(), "식물성") == [("식물", "식물", True), ("성", "-성", True)]
    assert cut(korean(), "바깥층") == [("바깥", "바깥", True), ("층", "층", True)]
    assert cut(korean(), "대도시") == [("대", "대-", True), ("도시", "도시", True)]


def test_a_prefix_only_where_no_cut_without_one_will_do() -> None:
    assert [p.form for p in korean().parts("대표팀")] == [
        "대표",
        "팀",
    ]  # not 대- + 표팀


def test_a_korean_compounds_particles_are_no_parts() -> None:
    """국립공원은 is 국립공원 + 은: its parts are 국립 and 공원, as 학교에서's
    word is 학교 - a particle is no word of a caption's own."""
    assert cut(korean(), "국립공원은") == [
        ("국립", "국립", True),
        ("공원", "공원", True),
    ]
    assert [p.form for p in korean().parts("여행객에게도")] == ["여행", "객"]
    assert korean().parts("공원은") == []  # a word the pack has, with a particle


def test_a_name_in_hangul_isnt_cut_at_any_syllable() -> None:
    assert korean().parts("파티마") == []  # Fatima: not 파티 + -마
