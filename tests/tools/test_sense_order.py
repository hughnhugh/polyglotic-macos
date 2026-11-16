"""A card shows a word's commonest meaning first (polyglotic-hq 393):
Wiktionary lists a word's entries by etymology, and a sense's tags say
when it is rare, so the reader orders both - without changing any key, so
no entry ID moves (decision 0089)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from tools.dictionaries import kaikki, packs, treebanks


def sense(gloss: str, *tags: str) -> dict[str, object]:
    return {"glosses": [gloss], "tags": list(tags)}


def obj(
    word: str, pos: str, *senses: dict[str, object], number: int | None = None
) -> dict[str, object]:
    out: dict[str, object] = {"word": word, "pos": pos, "senses": list(senses)}
    if number is not None:
        out["etymology_number"] = number
    return out


def meanings(language: kaikki.Language) -> list[tuple[str, tuple[str, ...]]]:
    return [(e.key, e.meanings) for e in language.entries]


def test_an_entrys_rare_senses_come_after_its_others() -> None:
    """Thai's ออก showed "to pay" before "to go out"; a sense Wiktionary
    marks obsolete, archaic, dated... is one a learner seldom meets."""
    found = kaikki.read_language(
        [
            obj(
                "ออก",
                "verb",
                sense("to pay", "archaic"),
                sense("to come under a governing power", "obsolete"),
                sense("to go out"),
                sense("to issue"),
            )
        ]
    )
    assert found.entries[0].meanings == (
        "to go out",
        "to issue",
        "to pay",
        "to come under a governing power",
    )


def test_a_gloss_given_once_as_everyday_is_not_rare() -> None:
    found = kaikki.read_language(
        [obj("so", "adv", sense("thus", "dated"), sense("so"), sense("thus"))]
    )
    assert found.entries[0].meanings == ("thus", "so")
    denken = kaikki.read_language(
        [
            obj(
                "denken",
                "verb",
                sense("to think", "intransitive", "rare", "transitive"),
                sense("not to forget; to remember"),
            )
        ]
    )
    assert denken.entries[0].meanings[0] == "to think"


def test_a_letter_a_name_and_a_rare_entry_come_after_the_word() -> None:
    """Spanish's "de" showed "the name of the Latin script letter D" before
    "of": the Spanish reader keeps two-letter letter names. Keys and the
    places of other words' entries stay as they were."""
    found = kaikki.read_language(
        [
            obj(
                "de",
                "noun",
                sense("The name of the Latin script letter D/d."),
                number=1,
            ),
            obj("casa", "noun", sense("house")),
            obj("de", "name", sense("a surname"), number=2),
            obj("de", "conj", sense("if", "obsolete"), number=3),
            obj("de", "prep", sense("of"), sense("from"), number=4),
            obj("de", "prefix", sense("de-", "morpheme"), number=5),
        ]
    )
    mi = kaikki.read_language(
        [
            obj("mi", "noun", sense("mu; the Greek letter Μ, μ"), number=2),
            obj("mi", "noun", sense("mi (musical note)"), number=3),
        ]
    )
    assert mi.entries[0].meanings == ("mi (musical note)",)
    assert meanings(found) == [
        ("de|prep|4", ("of", "from")),
        ("casa|noun|", ("house",)),
        ("de|conj|3", ("if",)),
        ("de|name|2", ("a surname",)),
        ("de|noun|1", ("The name of the Latin script letter D/d.",)),
        ("de|prefix|5", ("de-",)),
    ]


THAI = [
    obj("กับ", "noun", sense("trap; gin"), number=1),
    obj("กับ", "prep", sense("with; together with"), number=2),
    obj("กับ", "noun", sense("accompanying dish to eat with rice"), number=3),
]


def test_a_words_commonest_part_of_speech_comes_first() -> None:
    """Thai's กับ showed "trap" (etymology 1) before "with" (etymology 2):
    the treebanks use it as a preposition far more often."""
    before = kaikki.read_language(THAI)
    after = kaikki.read_language(THAI, uses={"กับ": {"ADP": 90, "NOUN": 3}})
    assert [e.meanings[0] for e in after.entries] == [
        "with; together with",
        "trap; gin",
        "accompanying dish to eat with rice",
    ]
    assert sorted(e.key for e in after.entries) == sorted(e.key for e in before.entries)


def test_a_name_comes_first_where_the_treebanks_say_it_is_the_word() -> None:
    """Arabic has no capitals: مصر is Egypt far more than "to make
    Egyptian". Without capitals a name keeps its place; the treebanks may
    put it first."""
    words = [
        obj("مصر", "verb", sense("to make Egyptian"), number=1),
        obj("مصر", "name", sense("Egypt"), number=2),
    ]
    assert kaikki.read_language(words).entries[0].meanings == ("to make Egyptian",)
    found = kaikki.read_language(words, uses={"مصر": {"PROPN": 30, "VERB": 1}})
    assert found.entries[0].meanings == ("Egypt",)
    named_first = kaikki.read_language(words[::-1])
    assert named_first.entries[0].meanings == ("Egypt",)


def test_wiktionarys_order_stays_unless_the_treebanks_are_clear() -> None:
    """Spanish's mañana is a noun (the morning) about as often as an adverb
    (tomorrow); a word met fewer than `MIN_USES` times says nothing."""
    words = [
        obj("mañana", "adv", sense("tomorrow")),
        obj("mañana", "noun", sense("the morning")),
    ]
    near = kaikki.read_language(words, uses={"mañana": {"ADV": 19, "NOUN": 20}})
    assert near.entries[0].meanings == ("tomorrow",)
    rare = kaikki.read_language(THAI, uses={"กับ": {"ADP": 3}})
    assert rare.entries[0].meanings == ("trap; gin",)


def test_treebanks_count_a_word_under_its_lemma_and_its_form(tmp_path: Path) -> None:
    """Spanish's poder, counted by its form alone, was a noun ("el poder",
    in news); its forms (puede) are the verb's. Multiword tokens' lines are
    skipped; a treebank without lemmas counts forms."""
    conllu = tmp_path / "es.conllu"
    conllu.write_text(
        "# text = El poder puede del\n"
        "1\tEl\tel\tDET\n"
        "2\tpoder\tpoder\tNOUN\n"
        "3\tpuede\tpoder\tAUX\n"
        "4-5\tdel\t_\t_\n"
        "4\tde\tde\tADP\n"
        "5\tel\tel\tDET\n"
        "6\tกับ\t_\tADP\n",
        encoding="utf-8",
    )
    found = treebanks.uses([conllu])
    assert found["poder"] == {"NOUN": 1, "AUX": 1}
    assert found["puede"] == {"AUX": 1}
    assert found["el"] == {"DET": 2}
    assert "del" not in found
    assert found["กับ"] == {"ADP": 1}


def test_arabic_treebanks_are_counted_without_vowel_marks(tmp_path: Path) -> None:
    conllu = tmp_path / "ar.conllu"
    conllu.write_text("1\tقد\tقَد\tPART\n", encoding="utf-8")
    assert treebanks.uses([conllu], packs.ARABIC.written) == {"قد": {"PART": 1}}


def test_a_packs_reader_orders_entries_by_its_treebanks(tmp_path: Path) -> None:
    """The generic reader finds its language's treebanks among the pack's
    sources; without them (a test, a language with none) it keeps
    Wiktionary's order. The entry keys - so the IDs - are the same."""
    lines = [
        {"lang_code": "pl", **o}
        for o in (
            obj("w", "noun", sense("a kind of fish"), number=1),
            obj("w", "prep", sense("in"), number=2),
        )
    ]
    source = tmp_path / "pl.jsonl.gz"
    source.write_bytes(
        gzip.compress("\n".join(json.dumps(x) for x in lines).encode("utf-8"))
    )
    ud = treebanks.of("pl")[0]
    (tmp_path / ud.filename).write_text("1\tw\tw\tADP\n" * 9, encoding="utf-8")
    plain = packs.read_wiktionary("pl", {"kaikki-pl": source})
    ordered = packs.read_wiktionary(
        "pl", {"kaikki-pl": source, ud.name: tmp_path / ud.filename}
    )
    assert plain.forms["w"] == ["w|noun|1", "w|prep|2"]
    assert ordered.forms["w"] == ["w|prep|2", "w|noun|1"]
    assert {e.key for e in plain.entries} == {e.key for e in ordered.entries}


def test_every_pack_reads_its_languages_treebanks() -> None:
    """A language's treebanks order its pack's cards, whichever reader it
    has: Thai's pack has its own (#738, 389), which had left them out -
    กับ showed "trap" before "with" (polyglotic-hq 389, 393, 394)."""
    for language in {row[0] for row in treebanks.FILES}:
        pack = packs.PACKS.get(language)
        if pack is not None:
            assert set(treebanks.of(language)) <= set(pack.sources), language


def test_thais_reader_orders_entries_by_its_treebanks(tmp_path: Path) -> None:
    lines = [
        {"lang_code": "th", **o}
        for o in (
            obj("กับ", "noun", sense("trap"), number=1),
            obj("กับ", "prep", sense("with"), number=2),
        )
    ]
    source = tmp_path / "th.jsonl.gz"
    source.write_bytes(
        gzip.compress("\n".join(json.dumps(x) for x in lines).encode("utf-8"))
    )
    voice = tmp_path / "th.txt"
    voice.write_text("กับ\n", encoding="utf-8")
    ud = treebanks.of("th")[0]
    (tmp_path / ud.filename).write_text("1\tกับ\tกับ\tADP\n" * 9, encoding="utf-8")
    paths = {"kaikki-th": source, "commonvoice-th": voice}
    plain = packs.read_thai(paths)
    ordered = packs.read_thai({**paths, ud.name: tmp_path / ud.filename})
    assert plain.forms["กับ"] == ["กับ|noun|1", "กับ|prep|2"]
    assert ordered.forms["กับ"] == ["กับ|prep|2", "กับ|noun|1"]


def test_malays_indonesian_cards_are_ordered_by_indonesians_treebanks(
    tmp_path: Path,
) -> None:
    """Malay's pack takes the words its Wiktionary hasn't got from
    Indonesian's, whose treebanks it hadn't listed, so those cards kept
    Wiktionary's order (polyglotic-hq 394, 396)."""
    assert set(treebanks.of("id")) <= set(packs.PACKS["ms"].sources)

    def gz(name: str, code: str, *objects: dict[str, object]) -> Path:
        path = tmp_path / name
        path.write_bytes(
            gzip.compress(
                "\n".join(
                    json.dumps({"lang_code": code, **o}) for o in objects
                ).encode()
            )
        )
        return path

    paths = {
        "kaikki-ms": gz("ms.jsonl.gz", "ms", obj("saya", "pron", sense("I"))),
        "kaikki-id": gz(
            "id.jsonl.gz",
            "id",
            obj("pada", "noun", sense("a kind of tree"), number=1),
            obj("pada", "prep", sense("at, on"), number=2),
        ),
    }
    ud = treebanks.of("id")[0]
    (tmp_path / ud.filename).write_text("1\tpada\tpada\tADP\n" * 9, encoding="utf-8")
    plain = packs.read_malay(paths)
    ordered = packs.read_malay({**paths, ud.name: tmp_path / ud.filename})
    assert plain.forms["pada"] == ["pada|noun|1", "pada|prep|2"]
    assert ordered.forms["pada"] == ["pada|prep|2", "pada|noun|1"]


def test_every_treebank_may_be_used_commercially_and_is_credited() -> None:
    """359's rule: no non-commercial treebank (Ukrainian's IU is NC)."""
    allowed = {"CC BY-SA 4.0", *packs.OTHER_CC}
    for language in {row[0] for row in treebanks.FILES}:
        for source in treebanks.of(language):
            assert source.licence in allowed, source.name
    credits = packs.credits(packs.PACKS["ar"])
    assert "UD_Arabic-PUD" in credits
    assert "https://creativecommons.org/licenses/by-sa/3.0/" in credits


def form_of(gloss: str, lemma: str) -> dict[str, object]:
    return {"glosses": [gloss], "form_of": [{"word": lemma}], "tags": ["form-of"]}


def test_a_form_given_first_as_its_lemmas_shows_the_lemma_first() -> None:
    """Spanish's "su" showed "about, approximately" first: its page starts
    "apocopic form of suyo" (his, her), a form-of sense the reader turns
    into a link, so only the rare sense was left as its own. A form whose
    page starts with it as its lemma's form shows the lemma first; "casa"
    (a house first, then casar's "marries") keeps its own."""
    words = kaikki.read_language(
        [
            obj(
                "su",
                "det",
                form_of("apocopic form of suyo", "suyo"),
                sense("about, approximately"),
            ),
            obj("suyo", "det", sense("his, her, its")),
            obj("casa", "noun", sense("house"), number=1),
            obj("casa", "verb", form_of("inflection of casar", "casar"), number=2),
            obj("casar", "verb", sense("to marry")),
        ]
    )
    assert words.lemma_first == {"su": frozenset({"suyo"})}
    draft = packs.draft_of(words)
    kept = {e.key for e in draft.entries}
    lemmas, after = packs.lemma_table(
        draft, kept, dict.fromkeys(kept, 1.0), {"su": 2.0, "casa": 2.0}
    )
    assert lemmas == {"su": "suyo"}
    assert after == {"casa": "casar"}


def test_a_form_that_is_a_word_of_its_own_keeps_its_own_first() -> None:
    """German's "danke" (a verb's form, but "thanks"), "meist" ("superlative
    of viel", but used as the adverb "mostly"), Arabic's وقت ("verbal noun
    of وقت", but "time"), and "chica" (girl, maid) keep their own first."""
    lines = [
        obj("danke", "verb", form_of("first-person singular of danken", "danken")),
        obj("danke", "intj", sense("thanks")),
        obj("meist", "adj", form_of("superlative degree of viel", "viel")),
        obj("meist", "adv", sense("mostly")),
        obj(
            "وقت",
            "noun",
            {
                "glosses": ["verbal noun of وقت"],
                "form_of": [{"word": "وَقَتَ"}],
                "tags": ["form-of", "noun-from-verb"],
            },
            sense("time"),
        ),
        obj(
            "chica",
            "noun",
            form_of("female equivalent of chico", "chico"),
            sense("girl"),
            sense("maid"),
        ),
        obj(
            "novia",
            "noun",
            form_of("female equivalent of novio, girlfriend", "novio"),
            sense("a type of sweet roll"),
        ),
    ]
    found = kaikki.read_language(lines, uses={"meist": {"ADV": 40, "ADJ": 2}})
    assert found.lemma_first == {}


def test_the_lemma_its_page_names_comes_first() -> None:
    """Spanish's "una" starts "feminine of uno", though it is also a form
    of the commoner un: its card leads with uno, the lemma the page names."""
    words = kaikki.read_language(
        [
            obj("una", "noun", form_of("feminine of uno", "uno")),
            obj("una", "article", form_of("feminine singular of un", "un")),
            obj("una", "pron", sense("one")),
            obj("uno", "num", sense("one")),
            obj("un", "article", sense("a, an")),
        ]
    )
    draft = packs.draft_of(words)
    kept = {e.key for e in draft.entries}
    total = {k: (5.0 if k.startswith("un|") else 1.0) for k in kept}
    lemmas, _ = packs.lemma_table(draft, kept, total, {"una": 2.0})
    assert lemmas == {"una": "uno"}


def test_a_form_with_no_entry_of_its_own_still_counts_for_its_commonest_lemma() -> None:
    """Spanish's "hayas" starts "plural of haya" (beech trees) but is
    haber's "you have" (174's hard forms): a form with no entry of its own
    keeps the commonest lemma, whatever its page starts with."""
    words = kaikki.read_language(
        [
            obj("hayas", "noun", form_of("plural of haya", "haya")),
            obj("hayas", "verb", form_of("second-person singular of haber", "haber")),
            obj("haya", "noun", sense("beech")),
            obj("haber", "verb", sense("to have")),
        ]
    )
    draft = packs.draft_of(words)
    kept = {e.key for e in draft.entries}
    total = {k: (5.0 if k.startswith("haber") else 1.0) for k in kept}
    lemmas, _ = packs.lemma_table(draft, kept, total, {"hayas": 0.1})
    assert lemmas == {"hayas": "haber"}
