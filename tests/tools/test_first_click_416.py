"""The last wrong first clicks in the top 200 words (polyglotic-hq 416):
Turkish's postpositions opened on the nouns they are made from, French's
"Paris" on "bet", Swedish's "din" and "mindre", Hindi's पहले, Arabic's
لكن and Italian's "Mio" on another word's meaning, and Portuguese's
"melhor" and Italian's "c'" on the wrong one of their lemmas."""

from __future__ import annotations

from pathlib import Path

from tools.dictionaries import kaikki, packs, treebanks


def sense(gloss: str, *tags: str) -> dict[str, object]:
    return {"glosses": [gloss], "tags": list(tags)}


def form_of(gloss: str, lemma: str, *tags: str) -> dict[str, object]:
    return {
        "glosses": [gloss],
        "form_of": [{"word": lemma}],
        "tags": ["form-of", *tags],
    }


def obj(word: str, pos: str, *senses: dict[str, object], **more: object) -> dict:
    return {"word": word, "pos": pos, "senses": list(senses), **more}


def row(form: str, *tags: str) -> dict[str, object]:
    return {"form": form, "tags": list(tags)}


def test_a_pronoun_attached_as_a_determiner_counts_as_a_determiner(
    tmp_path: Path,
) -> None:
    """Treebanks tag possessives as pronouns where Wiktionary has them as
    determiners: Italian's "mio" in "il mio libro" (det:poss), Swedish's
    "din" in "din bil" (nmod:poss). Used alone ("è mio"), it stays a
    pronoun; a line without a relation keeps its tag."""
    bank = tmp_path / "it.conllu"
    lines = [
        "1\tmio\tmio\tPRON\t_\t_\t3\tdet:poss",
        "2\tmio\tmio\tPRON\t_\t_\t3\tdet:poss",
        "3\tdin\tdu\tPRON\t_\t_\t4\tnmod:poss",
        "4\tmio\tmio\tPRON\t_\t_\t0\troot",
        "5\tquesto\tquesto\tPRON",
    ]
    bank.write_bytes(("\n".join(lines) + "\n").encode())
    found = treebanks.uses([bank], forms_only=True)
    assert found["mio"] == {treebanks.POSSESSIVE: 2, "PRON": 1}
    assert found["din"] == {treebanks.POSSESSIVE: 1}
    assert found["questo"] == {"PRON": 1}


def test_a_possessive_is_the_determiner_where_the_word_has_one() -> None:
    """Italian's "mio" is a determiner ("my") and a pronoun ("mine"), in
    that order on Wiktionary's page but the pronoun first in the pack: its
    uses as a possessive are the determiner's, so "my" comes first.
    Swedish's "min" ("my") is only a pronoun on Wiktionary: its possessive
    uses stay its pronoun's, before "minute". Swedish's "din" ("your", a
    determiner) is in ditt's pronoun table: it stays its own."""
    p = treebanks.POSSESSIVE
    words = kaikki.read_language(
        [
            obj("mio", "pron", sense("mine (used predicatively)")),
            obj("mio", "det", sense("my")),
            obj("min", "noun", sense("minute")),
            obj("min", "pron", sense("my")),
            obj("din", "det", sense("your")),
            obj("ditt", "pron", sense("you (vocative)"), forms=[row("din")]),
        ],
        uses={"mio": {p: 7}, "min": {p: 40, "NOUN": 2}},
    )
    firsts: dict[str, str] = {}
    for e in words.entries:
        firsts.setdefault(e.word, e.pos)
    assert firsts == {"mio": "det", "min": "pron", "din": "det", "ditt": "pron"}
    assert packs.lemma_used(words, {"din": {p: 5}}) == {}


def test_a_postposition_made_from_a_noun_keeps_its_own() -> None:
    """Turkish's "içinde" (inside) is iç's (the inside) locative with "its",
    and a postposition of its own; the treebanks tag it a noun, as they do
    every case form used as a postposition. It had opened on iç's "inner".
    Spanish's "veces" is vez's plural (times) and its own preposition
    ("times", multiplying): a plural is no case, so it stays vez's."""
    words = kaikki.read_language(
        [
            obj("içinde", "postp", sense("in, within, inside")),
            obj("iç", "noun", sense("inside"), forms=[row("içinde", "locative")]),
            obj("veces", "prep", sense("times (multiplication)")),
            obj("vez", "noun", sense("time, instance"), forms=[row("veces", "plural")]),
        ]
    )
    uses = {"içinde": {"NOUN": 35, "ADJ": 5}, "veces": {"NOUN": 120}}
    assert packs.lemma_used(words, uses) == {"veces": frozenset({"vez"})}


def test_a_degree_of_comparison_keeps_its_own() -> None:
    """Swedish's "mindre" is its own adjective, "smaller; less", and lite's
    comparative (in its adjective table): used as the adverb 21 times in 32,
    it had opened on lite's "a little". Czech's "starší" (older) is starý's
    comparative and a noun of its own, "a church elder": no adjective of
    its own, so it opens on starý, "old". A form in the lemma's table with
    no degree still moves."""
    words = kaikki.read_language(
        [
            obj("mindre", "adj", sense("smaller; less")),
            obj("mindre", "adv", form_of("comparative of lite", "lite", "comparative")),
            obj("lite", "adv", sense("a little")),
            obj("lite", "adj", sense("little"), forms=[row("mindre", "comparative")]),
            obj("starší", "noun", sense("a church elder")),
            obj("starý", "adj", sense("old"), forms=[row("starší", "comparative")]),
            obj("est", "noun", sense("east")),
            obj("être", "verb", sense("to be"), forms=[row("est", "present")]),
        ]
    )
    uses = {"mindre": {"ADV": 21, "ADJ": 8, "PRON": 3}, "est": {"AUX": 775}}
    uses |= {"starší": {"ADJ": 40, "NOUN": 2}}
    assert packs.lemma_used(words, uses) == {
        "est": frozenset({"être"}),
        "starší": frozenset({"starý"}),
    }
    assert words.link_kinds == {
        ("mindre", "lite"): {"comparative"},
        ("starší", "starý"): {"comparative"},
    }


def test_a_form_looked_up_through_a_capitalised_word_keeps_its_row() -> None:
    """Ukrainian's "Того" opens on той ("that") before Togo; "тоголезький"
    (Togolese), looked up through Того, still opens on Togo. Czech's
    "Hlavou" goes as "Hlava" goes: on hlava (head), not the surname."""
    forms = {"Того": ["Togo"], "той": ["that"], "тоголезький": ["Togolese"]}
    forms |= {"Hlava": ["Hlava"], "hlava": ["head"]}
    lemmas = {"тоголезький": "Того", "того": "той", "Hlavou": "Hlava"}
    capitals = {"Того": ["that", "Togo"], "Hlava": ["head", "Hlava"]}
    assert packs.through_capitals(forms, lemmas, capitals) == {
        "тоголезький": ["Togo", "Togolese"]
    }


def test_an_adpositions_form_with_a_pronoun_counts_only_where_the_treebanks_say() -> (
    None
):
    """Arabic's لكن ("but") is written as ل's (to, for) "to you" (feminine
    plural): the treebank tags it ADP 40 times in 65, but names لكن as its
    lemma - it splits a preposition with a pronoun in two. It had opened
    on ل, "to". Its "علي", which it takes for على ("on") 26 times, is
    على's, though it is also the name Ali and a verb."""
    words = kaikki.read_language(
        [
            obj("لكن", "conj", sense("but, however")),
            obj(
                "ل",
                "prep",
                sense("to, for"),
                forms=[row("لكن", "feminine", "plural", "second-person")],
            ),
            obj("علي", "verb", sense("to be exalted")),
            obj(
                "على",
                "prep",
                sense("on"),
                forms=[row("علي", "first-person", "singular")],
            ),
        ]
    )
    uses = {"لكن": {"ADP": 40, "PART": 24, "CCONJ": 1}, "علي": {"ADP": 26}}
    named = {"لكن": {"لكن": 65}, "علي": {"على": 26}}
    assert packs.lemma_used(words, uses, named) == {"علي": frozenset({"على"})}
    assert packs.lemma_used(words, uses) == {}
    assert words.link_kinds[("لكن", "ل")] == {"pronoun"}


def test_the_lemmas_use_must_be_a_share_of_the_forms() -> None:
    """Hindi's पहले ("before") is पहला's (first) oblique form: the treebank
    uses it as the adjective 10 times in 45, and mostly as a postposition,
    which neither word has an entry for. It had opened on "first"."""
    words = kaikki.read_language(
        [
            obj("पहले", "adv", sense("previously, earlier, before")),
            obj("पहला", "adj", sense("first"), forms=[row("पहले", "oblique")]),
        ]
    )
    uses = {"पहले": {"ADP": 20, "NOUN": 13, "ADJ": 10, "ADV": 2}}
    assert packs.lemma_used(words, uses) == {}
    uses = {"पहले": {"ADJ": 10, "ADV": 2}}
    assert packs.lemma_used(words, uses) == {"पहले": frozenset({"पहला"})}


def test_a_name_whose_lower_case_is_a_word_keeps_its_share() -> None:
    """French's Paris is also "paris", pari's plural ("bets"): wordfreq,
    in lower case, can't tell them apart, so the city had no frequency,
    was cut, and opened on "bet". The treebanks use "paris" as a name 34
    times in 35: the city takes that share. Where they don't say, or seldom
    use it as a name, a name whose lower case is a word still has none."""
    words = kaikki.read_language(
        [
            obj("Paris", "name", sense("Paris")),
            obj("pari", "noun", sense("bet"), forms=[row("paris", "plural")]),
            obj("Est", "name", sense("the East")),
            obj("est", "noun", sense("east")),
        ]
    )
    freq = {"paris": 0.00035, "pari": 0.00001, "est": 0.003}
    draft = packs.draft_of(words)
    assert packs.frequencies(draft, freq)["Paris|name|"] == 0.0
    draft.uses = {"paris": {"PROPN": 34, "NOUN": 1}, "est": {"AUX": 775, "PROPN": 9}}
    total = packs.frequencies(draft, freq)
    assert abs(total["Paris|name|"] - 0.00035 * 34 / 35) < 1e-12
    assert total["Est|name|"] == 0.0
    # Italian's "stati" is a name only in "Stati Uniti": not the surname
    draft.uses = {"paris": {treebanks.IN_NAME: 34, "NOUN": 1}}
    assert packs.frequencies(draft, freq)["Paris|name|"] == 0.0


def test_a_word_of_a_name_of_several_is_counted_apart(tmp_path: Path) -> None:
    """ "Stati" in "Stati Uniti" (its head) and "Uniti" (flat:name) are
    words of a name of several, and so is "Impero" in "Impero Romano"
    (a capitalised adjective); "Paris" alone is a name."""
    bank = tmp_path / "it.conllu"
    lines = [
        "1\tStati\tStati\tPROPN\t_\t_\t0\troot",
        "2\tUniti\tUniti\tPROPN\t_\t_\t1\tflat:name",
        "",
        "1\tParis\tParis\tPROPN\t_\t_\t0\troot",
        "",
        "1\tImpero\tImpero\tPROPN\t_\t_\t0\troot",
        "2\tRomano\tromano\tADJ\t_\t_\t1\tamod",
    ]
    bank.write_bytes(("\n".join(lines) + "\n").encode())
    found = treebanks.uses([bank], forms_only=True)
    assert found["stati"] == {treebanks.IN_NAME: 1}
    assert found["uniti"] == {treebanks.IN_NAME: 1}
    assert found["paris"] == {"PROPN": 1}
    assert found["impero"] == {treebanks.IN_NAME: 1}
    assert treebanks.lemmas([bank])["stati"] == {"stati": 1}


def test_a_form_of_two_words_opens_on_the_one_it_is_used_as() -> None:
    """Portuguese's "melhor" is bom's comparative (better) and bem's: used
    as an adjective 25 times and an adverb 8, it had opened on the commoner
    bem, "well". Where the treebanks say nothing, the commoner lemma."""
    words = kaikki.read_language(
        [
            obj("bom", "adj", sense("good"), forms=[row("melhor", "comparative")]),
            obj("bem", "adv", sense("well"), forms=[row("melhor", "comparative")]),
        ]
    )
    draft = packs.draft_of(words)
    draft.came_through = dict(words.came_through)
    every = {e.key for e in draft.entries}
    total = {"bom|adj|": 1.0, "bem|adv|": 5.0}
    assert packs.lemma_table(draft, every, total, {})[0] == {"melhor": "bem"}
    draft.uses = {"melhor": {"ADJ": 29, "ADV": 8}}  # by lemma: not these
    assert packs.lemma_table(draft, every, total, {})[0] == {"melhor": "bem"}
    draft.written = {"melhor": {"ADJ": 25, "ADV": 8}}  # as written
    assert packs.lemma_table(draft, every, total, {})[0] == {"melhor": "bom"}


def test_one_of_the_commonest_words_comes_before_a_names_own_headword() -> None:
    """Where no treebank says (Ukrainian has none), a name's own headword
    kept its card: Ukrainian's "Того" (того, той's "of that", one of the
    commonest hundred words) opened on Togo. The word itself must be among
    the commonest, not its lemma: "Кім" stays the surname Kim, though кім
    is a form of хто ("who"); Tournai, whose lower case is tourner's, stays
    the city; and Україна stays Ukraine, whose lower case is the same word
    - as Filipino's "Isa" (Jesus; isa, "one") is, so far."""
    forms = {"той": ["той"], "Того": ["Того"], "isa": ["isa"], "Isa": ["Isa"]}
    forms |= {"tourner": ["tourner"], "Tournai": ["Tournai"]}
    forms |= {"хто": ["хто"], "Кім": ["Кім"]}
    forms |= {"україна": ["україна"], "Україна": ["Україна"]}
    lemmas = {"того": "той", "tournai": "tourner", "кім": "хто"}
    rank = {"той": 27, "Того": 21796, "isa": 8, "Isa": 8051, "хто": 40}
    rank |= {"tourner": 622, "Tournai": 29561, "Кім": 9000}
    rank |= {"україна": 60, "Україна": 1 << 30}
    pos = {"той": "det", "Того": "name", "isa": "num", "Isa": "name"}
    pos |= {"tourner": "verb", "Tournai": "name", "хто": "pron", "Кім": "name"}
    pos |= {"україна": "noun", "Україна": "name"}
    said = {word: (word, part) for word, part in pos.items()}
    commonest = frozenset({"того", "isa", "хто", "україна"})
    assert packs.capitals_first(forms, lemmas, rank, said, None, False, commonest) == {
        "Того": ["той", "Того"]
    }
    assert packs.capitals_first(forms, lemmas, rank, said, None) == {}
