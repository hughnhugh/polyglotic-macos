"""The basic dictionary packs (polyglotic-hq project 164), end to end on
small fixtures in the sources' real formats: Wiktionary as kaikki.org
extracts it, JMdict as jmdict-simplified's JSON, the JLPT CSV, wordfreq."""

import gzip
import json
import sys
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from tests.tools.wordfreq_data import msgpack
from tools.dictionaries import coverage, kaikki, packs, rank_check
from tools.dictionaries import sources as sources_module

from polyglotic_desktop.adapters import spaced_split
from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.adapters.sqlite_dictionary import RANKS, SqliteDictionary
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.thai import ThaiSplit
from polyglotic_desktop.core.lexicon.vietnamese import VietnameseSplit
from polyglotic_desktop.ports.dictionary import EntryRecord


def sense(gloss: str, form_of: str = "", **extra: object) -> dict[str, object]:
    out: dict[str, object] = {"glosses": [gloss], **extra}
    if form_of:
        out["form_of"] = [{"word": form_of}]
        out["tags"] = ["form-of"]
    return out


def line(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
    obj = {"word": word, "pos": pos, "lang_code": "es", "senses": list(senses), **extra}
    return json.dumps(obj, ensure_ascii=False)


SPANISH = [
    line("casa", "noun", sense("house"), etymology_number=1),
    line("casa", "verb", sense("inflection of casar:", "casar"), etymology_number=2),
    line("casas", "noun", sense("plural of casa", "casa")),
    line("casas", "verb", sense("second-person singular of casar", "casar")),
    line("casar", "verb", sense("to marry")),
    line(
        "saber",
        "verb",
        sense("to know"),
        forms=[
            {"form": "es-conj", "tags": ["table-tags"]},
            {"form": "saber", "tags": ["infinitive"]},
            {"form": "sé", "tags": ["first-person", "present"]},
            {"form": "me sé", "tags": ["reflexive"]},
        ],
        sounds=[{"ipa": "/saˈbeɾ/"}],
    ),
    line("saber", "noun", sense("knowledge")),
    line("supe", "verb", sense("first-person singular preterite of saber", "saber")),
    # a short form counts from a table only with a page of its own (390)
    line("sé", "verb", sense("first-person singular present of saber", "saber")),
    line("decir", "verb", sense("to say")),
    line(
        "dímelo",
        "verb",
        sense(
            "imperative of decir",
            "decir combined with indirect object me and direct object lo",
        ),
    ),
    line("hacer", "verb", sense("to do"), sense("to make")),
    line("rarísimo", "adj", sense("very rare")),  # no frequency: cut
    line("a la vez", "phrase", sense("at once")),  # a phrase: not a word
    # an abbreviation in capitals written like a common word: "NO" is
    # noroeste's, "no" is no (polyglotic-hq 325)
    line("no", "adv", sense("no, not")),
    line("noroeste", "noun", sense("northwest")),
    line("NO", "noun", sense("abbreviation of noroeste", "noroeste")),
    "not json {",
]


def fr(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
    obj = {"word": word, "pos": pos, "lang_code": "fr", "senses": list(senses), **extra}
    return json.dumps(obj, ensure_ascii=False)


FRENCH = [
    fr("homme", "noun", sense("man"), sounds=[{"ipa": "/ɔm/"}]),
    fr("hommes", "noun", sense("plural of homme", "homme")),
    fr("l'", "article", sense("the (before a vowel)")),
    fr("aujourd'hui", "adv", sense("today")),
    fr(
        "avoir",
        "verb",
        sense("to have"),
        forms=[{"form": "ai", "tags": ["first-person", "present"]}],
    ),
]


def ru(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
    obj = {"word": word, "pos": pos, "lang_code": "ru", "senses": list(senses), **extra}
    return json.dumps(obj, ensure_ascii=False)


def forms(*pairs: tuple[str, str]) -> list[dict[str, object]]:
    """A headword's `forms`: (form, its tags space-separated)."""
    return [{"form": f, "tags": t.split()} for f, t in pairs]


RUSSIAN = [
    ru(
        "рука",
        "noun",
        sense("hand"),
        sense("arm"),
        forms=forms(
            ("рука́", "canonical feminine inanimate"),
            ("ruká", "romanization"),
            ("ручно́й", "adjective relational"),  # another word
            ("ру́чка", "diminutive"),  # another word
            ("ru-noun-table", "inflection-template"),
            ("ру́ку", "accusative singular"),
            ("ру́ки", "nominative plural"),
            ("руки́", "genitive singular"),
        ),
        sounds=[{"ipa": "[rʊˈka]"}],
    ),
    ru(
        "руку",
        "noun",
        sense("accusative singular of рука́ (ruká)", "рука́"),
        forms=forms(("ру́ку", "canonical")),
    ),
    ru(
        "говорить",
        "verb",
        sense("to speak, to talk"),
        forms=forms(
            ("говори́ть", "canonical imperfective"),
            ("сказа́ть", "perfective"),  # its aspect partner: another word
            ("говорю́", "first-person present singular"),
            ("говоря́щий", "active participle present"),
            ("говоря́", "adverbial participle present"),
            ("govorjú", "first-person present singular"),  # a romanisation
        ),
    ),
    ru(
        "сказать",
        "verb",
        sense("to say, to tell"),
        forms=forms(
            ("сказа́ть", "canonical perfective"),
            ("ска́занный", "participle passive past"),
            ("сказа́л", "masculine singular past"),
        ),
    ),
    ru("ещё", "adv", sense("still, yet")),  # ё: always stressed, no mark
    ru(
        "стоимость",
        "noun",
        {
            "glosses": ["cost, value, worth"],
            "form_of": [{"word": "стоить"}],
            "tags": ["form-of", "noun-from-verb"],
        },
        forms=forms(("сто́имость", "canonical")),
    ),
    ru(
        "США",
        "name",
        {
            "glosses": ["initialism of Соединённые Шта́ты Аме́рики: USA"],
            "alt_of": [{"word": "Соединённые Шта́ты Аме́рики"}],
            "tags": ["abbreviation", "alt-of", "initialism", "plural"],
        },
    ),
    ru(
        "я",
        "pron",
        sense("I"),
        # the table of every personal pronoun, on each one's page
        forms=forms(("её", "feminine genitive personal pronoun third-person")),
    ),
    ru("я", "character", sense("The thirty-third letter of the Russian alphabet")),
    ru("она", "pron", sense("she"), forms=forms(("она́", "canonical"))),
    ru("её", "pron", sense("genitive of она́", "она́")),
    # an affix and a name written like a common word: neither is "в" or
    # "или" (polyglotic-hq 325)
    ru("в", "prep", sense("in")),
    ru("в-", "prefix", sense("in-, into")),
    ru("-ить", "suffix", sense("forms verbs")),
    ru("или", "conj", sense("or")),
    ru("Или", "name", sense("Ili (a river in Kazakhstan)")),
    ru("земля", "noun", sense("earth, soil"), forms=forms(("земли", "genitive"))),
    ru("Земля", "name", sense("Earth"), forms=forms(("Земли", "genitive"))),
]


def vi(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
    obj = {"word": word, "pos": pos, "lang_code": "vi", "senses": list(senses), **extra}
    return json.dumps(obj, ensure_ascii=False)


VIETNAMESE = [
    vi("học sinh", "noun", sense("pupil, student"), sounds=[{"ipa": "[hawk͡p̚ sïŋ]"}]),
    vi("học", "verb", sense("to study")),
    vi("sinh", "verb", sense("to give birth")),  # never alone in the subtitles
    vi("sinh viên", "noun", sense("university student")),
    vi("bất kì", "det", sense("any; whatever")),
    vi(
        "bất kỳ",
        "det",
        {
            "glosses": ["alternative spelling of bất kì"],
            "alt_of": [{"word": "bất kì"}],
            "tags": ["alt-of"],
        },
    ),
    vi("學生", "character", sense("Hán Nôm form of học sinh")),  # not a caption's
    vi("Việt Nam", "name", sense("Vietnam")),
    vi("lâu lắm", "adv", sense("for a very long time")),  # never said: cut
]
SUBTITLES_VI = "".join(
    f"{line}\n"
    for line in (
        "Các học sinh học bài.",
        "Học sinh và sinh viên ở Việt Nam.",
        "Bất kỳ ai?",
        "bất kì",
    )
)
"""Vietnamese subtitles, as OPUS's monolingual OpenSubtitles file has them."""


def th(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
    obj = {"word": word, "pos": pos, "lang_code": "th", "senses": list(senses), **extra}
    return json.dumps(obj, ensure_ascii=False)


def roman(said: str, *others: tuple[str, str]) -> list[dict[str, object]]:
    """A Thai entry's `forms`: its romanization, then (form, tag) pairs."""
    forms: list[dict[str, object]] = [{"form": said, "tags": ["romanization"]}]
    return forms + [{"form": f, "tags": [tag]} for f, tag in others]


THAI = [
    th("ไทย", "noun", sense("Thai"), forms=roman("tai", ("ไท", "alternative"))),
    # its classifier and an abstract noun are other words, not its forms
    th("หมา", "noun", sense("dog"), forms=roman("mǎa", ("ตัว", "classifier"))),
    th("ดี", "adj", sense("good"), forms=roman("dii", ("ความดี", "abstract-noun"))),
    th("ตัว", "noun", sense("body"), forms=roman("dtuua")),
    th("กิน", "verb", sense("to eat"), forms=roman("gin")),
    th("จะ", "verb", sense("will"), forms=roman("jà")),
    th("ณ", "prep", sense("at"), forms=roman("ná")),
    # never said in the sentences: kept all the same, so the split finds it
    # whole rather than as กา (crow) + the rest
    th("กาแล็กซี", "noun", sense("galaxy"), forms=roman("gaa-lɛ́k-sii")),
    th("กา", "noun", sense("crow"), forms=roman("gaa")),
    # a letter's own entry, an affix, a texting spelling of one letter
    th("ก", "character", sense("the first letter of the Thai alphabet")),
    th("อ", "prefix", sense("un-")),
    th(
        "จ",
        "verb",
        {"glosses": ["alternative form of จะ"], "alt_of": [{"word": "จะ"}]},
        tags=["alt-of"],
    ),
]
COMMON_VOICE_TH = "".join(
    f"{line}\n"
    for line in (
        "หมากินดี",
        "หมาจะกิน",
        "หมาตัวนี้ดี",
        "ไทจะกิน ณ ไทย",
        "จกิน",  # a lone จ: no word, and no count for จะ
        "กาดี",
    )
)
"""Common Voice's Thai sentences, one a line."""
ZH = [
    json.dumps({"word": w, "pos": p, "lang_code": lc, "senses": s}, ensure_ascii=False)
    for w, p, lc, s in [
        ("рука", "noun", "ru", [{"glosses": ["手"]}]),
        ("casa", "noun", "es", [{"glosses": ["房子 [接 de]"]}]),
        ("decir", "verb", "es", [{"glosses": ["说"]}]),
        ("hacer", "unknown", "es", [{"glosses": ["做"]}]),  # no part of speech
        ("食べる", "verb", "ja", [{"glosses": ["吃"]}]),
        ("たべる", "soft-redirect", "ja", [{}]),
        ("する", "verb", "ja", [{"glosses": ["做"]}]),  # whose する?
    ]
]
JMDICT = {
    "version": "3.6.2",
    "dictDate": "2026-11-02",
    "words": [
        {
            "id": "1358280",
            "kanji": [{"common": True, "text": "食べる"}],
            "kana": [{"common": True, "text": "たべる"}],
            "sense": [{"misc": [], "gloss": [{"text": "to eat"}, {"text": "to have"}]}],
        },
        {
            "id": "1157170",
            "kanji": [{"common": False, "text": "為る"}],
            "kana": [{"common": True, "text": "する"}],
            "sense": [{"misc": ["uk"], "gloss": [{"text": "to do"}]}],
        },
        {
            "id": "1567440",  # usually written する too, but rare: cut
            "kanji": [{"common": False, "text": "掏る"}],
            "kana": [{"common": False, "text": "する"}],
            "sense": [{"misc": ["uk"], "gloss": [{"text": "to pickpocket"}]}],
        },
        {
            "id": "1581900",
            "kanji": [{"common": True, "text": "剃る"}],
            "kana": [
                {"common": True, "text": "そる"},
                {"common": False, "text": "する"},
            ],
            "sense": [{"misc": [], "gloss": [{"text": "to shave"}]}],
        },
        {
            "id": "9999999",
            "kanji": [],
            "kana": [{"common": False, "text": "ぬるぽ"}],
            "sense": [{"misc": [], "gloss": [{"text": "unranked"}]}],
        },
        {
            "id": "1508860",
            "kanji": [{"common": True, "text": "米軍"}],
            "kana": [{"common": True, "text": "べいぐん"}],
            "sense": [{"misc": [], "gloss": [{"text": "US armed forces"}]}],
        },
    ],
}


def in_(language: str) -> Callable[..., str]:
    """A kaikki line maker for `language` (the batch paired with English,
    polyglotic-hq 380)."""

    def make(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
        obj = {"word": word, "pos": pos, "lang_code": language, "senses": list(senses)}
        return json.dumps({**obj, **extra}, ensure_ascii=False)

    return make


de, it, ar, hi, tr = in_("de"), in_("it"), in_("ar"), in_("hi"), in_("tr")
ms, id_ = in_("ms"), in_("id")


def derived(gloss: str, base: str, tag: str) -> dict[str, object]:
    """A Turkish derived word's sense: "causative of araşmak: ..." """
    return {"glosses": [gloss], "form_of": [{"word": base}], "tags": ["form-of", tag]}


BATCH = {
    "de": [
        de("Mensch", "noun", sense("human"), forms=forms(("Menschen", "plural"))),
        # a rare lower-case word spelled the same: "one" (a pronoun)
        de("mensch", "pron", sense("one, they", tags=["informal", "rare", "slang"])),
        # a common one: "ich" is I; the noun "Ich" (the ego) takes no rank
        de("ich", "pron", sense("I")),
        de("Ich", "noun", sense("ego")),
        de("gehen", "verb", sense("to go")),
    ],
    "it": [
        it("della", "contraction", sense("contraction of di la; of the", "di la")),
        it("l'", "article", sense("the (before a vowel)")),
        it("uomo", "noun", sense("man")),
    ],
    "ar": [
        ar(
            "كتاب",
            "noun",
            sense("book"),
            forms=forms(
                ("كِتَاب", "canonical"),
                ("kitāb", "romanization"),
                ("كُتُب", "plural"),
                ("الْكِتَابُ", "definite nominative"),
            ),
        ),
        ar("أرض", "noun", sense("earth"), forms=forms(("الْأَرْض", "definite"))),
        # the planet's name, spelled as "the earth"
        ar("الأرض", "name", sense("Earth (the planet)")),
        ar("وزير", "noun", sense("minister")),
    ],
    "hi": [
        hi(
            "जाना",
            "verb",
            sense("to go"),
            forms=forms(("jānā", "romanization"), ("गया", "perfective")),
        ),
        hi("गया", "name", sense("Gaya (a city)")),
        hi("हिंदी", "name", sense("Hindi (language)")),
    ],
    "tr": [
        tr("araşmak", "verb", sense("to call each other")),
        tr(
            "araştırmak",
            "verb",
            derived("causative of araşmak: to research", "araşmak", "causative"),
            forms=forms(("araştırdı", "past")),
        ),
        # a derived word whose gloss says nothing of its own stays a form
        tr("aratmak", "verb", derived("causative of araşmak", "araşmak", "causative")),
        tr("İngiltere", "name", sense("England")),
        tr("ev", "noun", sense("house"), forms=forms(("evler", "plural"))),
    ],
    "ms": [
        ms("kereta", "noun", sense("car")),
        ms("rumah", "noun", sense("house")),
    ],
    "id": [
        id_("kereta", "noun", sense("carriage")),  # Malay's own is kept
        id_("penting", "adj", sense("important")),
        id_("TV", "noun", sense("initialism of tanda vital")),
        id_("jakarta", "name", sense("Jakarta")),
    ],
}
"""The first batch paired with English: lines for the rules each needs;
Portuguese, Indonesian and Polish read as French does."""
uk, fa, tl = in_("uk"), in_("fa"), in_("tl")
ZWNJ = "\u200c"
SECOND = {
    "uk": [
        uk(
            "який",
            "pron",
            sense("which, what"),
            forms=forms(("яки́й", "canonical"), ("яка́", "feminine nominative")),
        ),
    ],
    "fa": [
        fa(
            "کتاب",
            "noun",
            sense("book"),
            forms=forms(
                ("kitāb", "romanization"),
                ("ketâb", "romanization"),
                ("کُتُب", "plural"),
            ),
        ),
        fa(
            "کردن",
            "verb",
            sense("to do"),
            forms=forms(("kardan", "romanization"), ("کُنَم", "aorist first-person")),
        ),
        fa("داستان", "noun", sense("story")),
        fa("و", "character", sense("The thirtieth letter of the Persian alphabet")),
        fa("و", "conj", sense("and")),
    ],
    "tl": [
        tl("isa", "num", sense("one")),
        tl("Isang", "name", sense("a diminutive of the female given name Isabel")),
        tl("noon", "adv", sense("then")),
        tl("kung", "conj", sense("if")),
    ],
}
"""The second batch paired with English (polyglotic-hq 387): lines for the
rules each needs; Dutch, Swedish, Czech, Romanian, Greek and Macedonian
read as French does."""
COMMONVOICE_FA = f"داستان{ZWNJ}های من\nداستان و کتاب\nمی{ZWNJ}کنم\n"
"""Persian sentences as Common Voice's: "داستان" is in no wordfreq list
here, only in them."""
JLPT = "Kanji,Reading,Level\n食べる,たべる,5\nする,する,5\n"
FREQ: dict[str, dict[int, list[str]]] = {
    "es": {
        150: ["no"],
        200: ["casa", "saber", "decir"],
        300: ["casar", "supe", "casas", "hacer"],
        420: ["noroeste"],
    },
    "fr": {200: ["homme", "l'", "avoir"], 300: ["hommes", "ai", "aujourd'hui"]},
    "de": {150: ["ich"], 200: ["mensch", "gehen"], 300: ["menschen"]},
    "it": {150: ["della"], 200: ["l'", "uomo"]},
    "ar": {150: ["الأرض"], 200: ["كتاب", "وزير"], 250: ["الكتاب", "كتب"]},
    "hi": {150: ["गया"], 200: ["जाना", "हिंदी"]},
    "tr": {200: ["araştırmak", "ev", "ingiltere"], 300: ["araşmak", "aratmak"]},
    "ms": {200: ["kereta", "rumah", "penting", "tv", "jakarta"]},
    **{language: {300: []} for language in ("pt", "id", "pl")},
    **{language: {300: []} for language in ("nl", "sv", "cs", "ro", "el", "mk")},
    "uk": {150: ["яка"], 200: ["який"]},
    "fa": {150: ["و"], 200: ["کتاب", "کردن"]},
    "fil": {150: ["isang"], 200: ["isa", "noon", "noong", "kung"]},
    "ja": {200: ["する"], 300: ["食べる"], 400: ["剃る"]},
    "ru": {
        110: ["в", "или"],
        250: ["земля", "земли"],
        150: ["я", "её"],
        200: ["рука", "руку", "руки", "говорить", "еще", "сказано"],
        300: ["сказать", "стоимость", "сша", "говорю", "ещё", "она", "the"],
        450: ["ить"],
    },
}

SUBTITLES_RU = "".join(f"{word} {n}\n" for word, n in (("сказать", 500), ("я", 400)))
"""Russian as said in films: OpenSubtitles' counts, as FrequencyWords
publishes them."""


def sources(folder: Path) -> dict[str, Path]:
    folder.mkdir()
    paths = {
        "kaikki-es": folder / "es.jsonl.gz",
        "kaikki-fr": folder / "fr.jsonl.gz",
        "kaikki-ru": folder / "ru.jsonl.gz",
        "kaikki-zh": folder / "zh.jsonl",
        "jmdict": folder / "jmdict.json.zip",
        "jlpt": folder / "jlpt.csv",
        "wordfreq": folder / "wordfreq.whl",
        "frequencywords-ru": folder / "ru_50k.txt",
        "kaikki-vi": folder / "vi.jsonl.gz",
        "opensubtitles-vi": folder / "vi.txt.gz",
        "kaikki-th": folder / "th.jsonl.gz",
        "commonvoice-th": folder / "th.txt",
    }
    paths["kaikki-es"].write_bytes(gzip.compress("\n".join(SPANISH).encode("utf-8")))
    paths["kaikki-fr"].write_bytes(gzip.compress("\n".join(FRENCH).encode("utf-8")))
    paths["kaikki-ru"].write_bytes(gzip.compress("\n".join(RUSSIAN).encode("utf-8")))
    for language in (
        *("de", "pt", "it", "id", "ar", "hi", "pl", "tr", "ms"),
        *("nl", "uk", "fa", "sv", "cs", "ro", "el", "tl", "mk"),
    ):
        lines = "\n".join(BATCH.get(language, SECOND.get(language, [])))
        paths[f"kaikki-{language}"] = folder / f"{language}.jsonl.gz"
        paths[f"kaikki-{language}"].write_bytes(gzip.compress(lines.encode("utf-8")))
    paths["commonvoice-fa"] = folder / "commonvoice-fa.txt"
    paths["commonvoice-fa"].write_text(COMMONVOICE_FA, encoding="utf-8")
    paths["kaikki-zh"].write_text("\n".join(ZH), encoding="utf-8")
    with zipfile.ZipFile(paths["jmdict"], "w") as archive:
        archive.writestr(
            "jmdict-eng-3.6.2.json", json.dumps(JMDICT, ensure_ascii=False)
        )
    paths["jlpt"].write_text(JLPT, encoding="utf-8")
    paths["frequencywords-ru"].write_text(SUBTITLES_RU, encoding="utf-8")
    paths["kaikki-vi"].write_bytes(gzip.compress("\n".join(VIETNAMESE).encode("utf-8")))
    paths["opensubtitles-vi"].write_bytes(gzip.compress(SUBTITLES_VI.encode("utf-8")))
    paths["kaikki-th"].write_bytes(gzip.compress("\n".join(THAI).encode("utf-8")))
    paths["commonvoice-th"].write_bytes(COMMON_VOICE_TH.encode("utf-8"))
    with zipfile.ZipFile(paths["wordfreq"], "w") as wheel:
        for language, buckets in FREQ.items():
            data = msgpack(
                [
                    {"format": "cB", "version": 1},
                    *(buckets.get(i, []) for i in range(500)),
                ]
            )
            wheel.writestr(
                f"wordfreq/data/large_{language}.msgpack.gz", gzip.compress(data)
            )
    return paths


@pytest.fixture
def built(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    paths = sources(tmp_path / "upstream")
    out = tmp_path / "out"
    out.mkdir()
    for pack in packs.PACKS.values():
        packs.build(pack, paths, out)
    return out


def test_kaikki_lines_become_entries_and_form_relations() -> None:
    found = kaikki.read_language(kaikki.lines_of(SPANISH, "es"))
    assert [e.key for e in found.entries] == [
        "casa|noun|1",
        "casar|verb|",
        "saber|verb|",
        "saber|noun|",
        "decir|verb|",
        "hacer|verb|",
        "rarísimo|adj|",
        "no|adv|",
        "noroeste|noun|",
    ]
    assert found.forms["casas"] == {"casa", "casar"}
    assert found.forms["dímelo"] == {"decir"}  # "combined with ..." dropped
    assert found.forms["sé"] == {"saber"}  # its page, and saber's table
    assert "me sé" not in found.forms and "es-conj" not in found.forms
    assert found.entries[2].reading == "/saˈbeɾ/"


def test_the_spanish_pack_finds_lemmas_and_its_own_entries(built: Path) -> None:
    file = SqliteDictionary(built / "wiktes.sqlite")
    spanish = EnglishDictionary(file)  # the same lookup: lemma, then own
    assert file.info["tier"] == "basic" and file.info["language"] == "es"

    def first(word: str) -> str:
        return spanish.lookup(word)[0].meanings[0]

    assert first("casa") == "(noun) house"  # its own entry, not casar's
    assert first("casas") == "(noun) house"  # casa is commoner than casar
    assert first("supe") == "(verb) to know"  # the verb, as the source orders it
    assert first("dímelo") == "(verb) to say"
    assert first("sé") == "(verb) to know"
    assert spanish.lookup("rarísimo") == []  # no frequency rank: cut
    assert spanish.lookup("a la vez") == []
    assert all(e.entry_id.startswith("wiktes:") for e in spanish.lookup("hacer"))
    assert spanish.lookup("hacer")[0].meanings == ("(verb) to do", "(verb) to make")


def test_the_chinese_file_has_chinese_where_the_chinese_edition_has_it(
    built: Path,
) -> None:
    english = EnglishDictionary(SqliteDictionary(built / "wiktes.sqlite"))
    chinese = EnglishDictionary(SqliteDictionary(built / "wiktes-zh.sqlite"))
    assert chinese.lookup("casa")[0].meanings == ("房子",)  # its note trimmed
    # no part of speech in the Chinese edition: its meanings go on the
    # word's first entry
    assert chinese.lookup("hacer")[0].meanings == ("做",)
    assert chinese.lookup("supe")[0].meanings == ("(verb) to know",)  # English
    assert [e.entry_id for e in chinese.lookup("casa")] == [
        e.entry_id for e in english.lookup("casa")
    ]


def test_the_japanese_pack_has_readings_levels_and_kana_forms(built: Path) -> None:
    file = SqliteDictionary(built / "jmdict.sqlite")
    eat = file.records("食べる")
    assert [(r.headword, r.reading, r.meanings) for r in eat] == [
        ("食べる", "たべる", ("to eat; to have",))
    ]
    assert eat[0].levels == (("jlpt", 1),)  # N5
    assert file.records("たべる") == eat
    do = file.records("する")
    assert [r.headword for r in do] == ["する", "剃る"]  # usually kana, commonest
    assert do[0].levels == (("jlpt", 1),) and do[1].levels == ()
    assert file.records("ぬるぽ") == []  # no rank, no level: cut
    # wordfreq can't rank 米軍 (its tokenizer splits it), but JMdict marks
    # it common
    assert [r.meanings for r in file.records("米軍")] == [("US armed forces",)]
    zh = SqliteDictionary(built / "jmdict-zh.sqlite")
    assert zh.records("食べる")[0].meanings == ("吃",)
    # the Chinese edition's する is 為る's - the only common entry usually
    # written so - not 掏る's (rare) or 剃る's, whose kana it is too
    assert [r.meanings for r in zh.records("する")] == [("做",), ("to shave",)]


def test_the_russian_pack_finds_forms_without_stress_marks(built: Path) -> None:
    file = SqliteDictionary(built / "wiktru.sqlite")
    russian = EnglishDictionary(file)  # the same lookup: lemma, then own
    assert file.info["tier"] == "basic" and file.info["language"] == "ru"

    def first(word: str) -> tuple[str, str, str]:
        entry = russian.lookup(word)[0]
        return entry.headword, entry.reading, entry.meanings[0]

    # the reading is the headword with its stress marked
    assert first("рука") == ("рука", "рука́", "(noun) hand")
    # inflections, from the table and from a "form of" page, unmarked
    assert first("руку") == first("руки") == first("рука")
    assert first("говорю")[0] == "говорить"
    # ё spelled е, as most text writes it; nothing to mark on ё
    assert first("еще") == first("ещё") == ("ещё", "", "(adv) still, yet")
    # a participle declined as an adjective counts for its verb
    assert first("говорящая")[0] == "говорить"
    assert first("сказано")[0] == "сказать"
    # derived words and aspect partners are words of their own, not forms
    assert file.lemma("ручной") is None and file.lemma("ручка") is None
    assert file.lemma("сказать") is None
    assert file.lemma("govorju") is None
    assert first("стоимость") == ("стоимость", "сто́имость", "(noun) cost, value, worth")
    assert first("США")[2].startswith("(name) initialism of")
    # я's table of every pronoun doesn't make её я's; её's own page does
    assert [e.headword for e in russian.lookup("её")] == ["она"]
    # a letter of the alphabet is no entry: я is "I"
    assert [e.meanings for e in russian.lookup("я")] == [("(pron) I",)]
    assert all(e.entry_id.startswith("wiktru:") for e in russian.lookup("рука"))
    assert float(file.info["running_words"]) > 0.9  # "the": another script
    # each inflected form keeps its own stress: it moves, and two forms
    # can be written alike
    assert file.form_reading("руку") == "ру́ку"
    assert file.form_reading("руки") == "ру́ки, руки́"
    assert file.form_reading("говорю") == "говорю́"
    assert file.form_reading("рука") == ""  # its entry says it
    assert file.form_reading("ручки") == ""  # wordfreq never met it
    zh = EnglishDictionary(SqliteDictionary(built / "wiktru-zh.sqlite"))
    assert zh.lookup("руку")[0].meanings == ("手",)


def test_affixes_and_names_written_like_words_take_no_words_rank(
    built: Path,
) -> None:
    """wordfreq has no hyphens and no capitals: "в-" had been given "в"'s
    frequency and "Или" (a river) "или"'s, so Russian's commonest entry was
    a prefix and its top 1,000 held 79 affixes (polyglotic-hq 325). They
    have no rank now, so the cut leaves them out, and "Или" at the start of
    a sentence finds "or"."""
    file = SqliteDictionary(built / "wiktru.sqlite")
    assert file.records("в-") == [] and file.records("-ить") == []
    assert file.records("Или") == []
    assert file.records("Земля") == []  # nor from its forms ("Земли": земли)
    # an abbreviation in capitals doesn't make its word as common as "no"
    spanish = SqliteDictionary(built / "wiktes.sqlite")
    ranks_es = {r.headword: r.frequency_rank or 0 for r in every_record(spanish)}
    assert ranks_es["no"] == 1 and ranks_es["noroeste"] == max(ranks_es.values())
    assert [r.meanings for r in file.records("или")] == [("(conj) or",)]
    ranks = {r.headword: r.frequency_rank or 0 for r in every_record(file)}
    assert ranks["в"] < ranks["или"]


def test_a_word_with_a_digit_takes_no_rank() -> None:
    """wordfreq writes digits as 0s and a hyphenated number took its parts'
    frequencies: "311", "9-3" and "4x4" were in French's top 1,000
    (polyglotic-hq 374)."""
    freq = {"311": 1e-4, "9": 1e-3, "3": 1e-3, "4x4": 1e-5, "homme": 1e-3}
    assert [packs.frequency_of(w, freq) for w in ("311", "9-3", "4x4")] == [0, 0, 0]
    assert packs.frequency_of("homme", freq) == 1e-3


def test_a_word_with_a_digit_takes_no_rank_from_its_forms() -> None:
    """French's "4x4" has "quatre-quatre" as a form: it had taken that
    form's frequency and stayed in the top 1,000 (polyglotic-hq 380)."""
    draft = packs.Draft(
        [packs.DraftEntry("4x4|noun|", "4x4", "", ("4WD",), ("4x4",))],
        {"4x4": ["4x4|noun|"]},
        {"quatre-quatre": {"4x4"}},
    )
    total = packs.frequencies(draft, {"quatre": 1e-3})
    assert total == {"4x4|noun|": 0.0}


def test_a_pack_whose_ranks_carry_junk_fails_its_build(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """The build checks the top 1,000 for 325's junk (`rank_check`) and
    says so; `main` fails on it as on the coverage floor (374)."""
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    paths = sources(tmp_path / "upstream")
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    assert packs.build(packs.PACKS["ru"], paths, good)["ranks pass the junk check"]

    def with_english(found: Mapping[str, Path]) -> packs.Draft:
        draft = packs.read_russian(found)
        the = packs.DraftEntry("the|art", "the", "", ("(article) the",), ("the",))
        draft.entries.append(the)
        draft.forms["the"] = ["the|art"]
        return draft

    monkeypatch.setattr(rank_check, "LATIN_WORDS", 0)  # one is past the line
    stats = packs.build(replace(packs.PACKS["ru"], read=with_english), paths, bad)
    assert stats["ranks pass the junk check"] is False
    assert "Latin-alphabet words" in str(stats["rank problems"])


def test_a_rank_is_a_word_whose_entries_share_it(built: Path) -> None:
    """323's "the top 1,000 words" is a thousand words: a headword's
    entries share its rank, as CC-CEDICT's do; Russian's top 1,000 entries
    had been about 700 words (polyglotic-hq 325)."""
    file = SqliteDictionary(built / "wiktes.sqlite")
    verb, noun = file.records("saber")
    assert verb.frequency_rank == noun.frequency_rank
    ranks = sorted({r.frequency_rank or 0 for r in every_record(file)})
    assert ranks == list(range(1, len(ranks) + 1))  # one rank a word, no gaps
    assert list(file.words_ranked(len(ranks))) == ranks


def test_a_pack_says_what_its_ranks_are(built: Path) -> None:
    """323's learner model reads a pack's ranks by what its `info` says
    (decision 0120)."""
    for name, lists in (
        ("wiktes", "wordfreq"),
        ("wiktru", "wordfreq+frequencywords-ru"),
        ("jmdict", "wordfreq"),
    ):
        file = SqliteDictionary(built / f"{name}.sqlite")
        ranked = sum(1 for r in every_record(file) if r.frequency_rank)
        assert file.info["ranks"] == RANKS
        assert file.info["frequency_source"] == lists
        assert int(file.info["ranked_entries"]) == ranked > 0


def test_russian_ranks_average_speech_and_wordfreqs_blend(built: Path) -> None:
    """Captions are speech: Russian's ranks average OpenSubtitles' counts
    with wordfreq's mostly written blend (polyglotic-hq 325). In wordfreq
    alone говорить (with говорю) is commoner than сказать; in films
    сказать is said far more."""
    file = SqliteDictionary(built / "wiktru.sqlite")
    ranks = {r.headword: r.frequency_rank or 0 for r in every_record(file)}
    assert ranks["сказать"] < ranks["говорить"]
    credits = (built / "wiktru.CREDITS.md").read_text(encoding="utf-8")
    assert "FrequencyWords" in credits and "opensubtitles.org" in credits


def every_record(file: SqliteDictionary) -> list[EntryRecord]:
    """Each entry of `file` once."""
    found = {r.entry_id: r for w in file.headwords() for r in file.records(w)}
    return list(found.values())


def test_the_vietnamese_pack_has_words_of_several_syllables_ranked_by_use(
    built: Path,
) -> None:
    """Vietnamese writes each syllable apart: a word ("học sinh") is an
    entry, ranked by how often the subtitles say it, counted by the app's
    own word split (polyglotic-hq 325, decision 0121)."""
    file = SqliteDictionary(built / "wiktvi.sqlite")
    assert file.info["language"] == "vi"
    assert file.info["frequency_source"] == "opensubtitles-vi"
    assert [(r.meanings, r.reading) for r in file.records("học sinh")] == [
        (("(noun) pupil, student",), "[hawk͡p̚ sïŋ]")
    ]
    # another spelling is a written form of its word, so the split finds it
    assert [r.headword for r in file.records("bất kỳ")] == ["bất kì"]
    assert file.records("學生") == []  # Hán Nôm: not how captions write
    assert file.records("lâu lắm") == [] and file.records("sinh") == []  # never said
    ranks = {r.headword: r.frequency_rank for r in every_record(file)}
    # học sinh twice; bất kì once and once as bất kỳ; the rest once each
    assert ranks == {
        "học sinh": 1,
        "bất kì": 2,
        "học": 3,
        "sinh viên": 4,
        "Việt Nam": 5,
    }
    split = VietnameseSplit(file)
    dictionary = BasicDictionary(file, split, "vi")
    line = "Học sinh hỏi bất kỳ ai."
    assert [line[a:b] for a, b in dictionary.words(line)] == [
        "Học sinh",
        "hỏi",
        "bất kỳ",
        "ai",
    ]
    assert [w.entry.frequency_rank for w in dictionary.words_in(line, "vi")] == [1, 2]
    # English meanings only: other languages' are to come as files of their
    # own (polyglotic-hq 326)
    assert not (built / "wiktvi-zh.sqlite").exists()
    credits = (built / "wiktvi.CREDITS.md").read_text(encoding="utf-8")
    assert "Only word counts" in credits and "opensubtitles.org" in credits


def test_the_thai_pack_has_its_words_ranked_by_common_voice(built: Path) -> None:
    """Thai: Wiktionary's words, found in a line without spaces by the
    app's own split and ranked by Common Voice's sentences, counted by it
    (polyglotic-hq 389, decision 0173)."""
    file = SqliteDictionary(built / "wiktth.sqlite")
    assert file.info["language"] == "th"
    assert file.info["frequency_source"] == "commonvoice-th"
    assert [(r.meanings, r.reading) for r in file.records("หมา")] == [
        (("(noun) dog",), "mǎa")
    ]
    # a classifier and an abstract noun are no forms of the word
    assert [r.meanings for r in file.records("ตัว")] == [("(noun) body",)]
    assert file.records("ความดี") == []
    # another spelling is a written form of its word
    assert [r.headword for r in file.records("ไท")] == ["ไทย"]
    # no letter's own entry, affix or one-letter spelling; ณ ("at") stays
    assert file.records("ก") == file.records("อ") == file.records("จ") == []
    assert [r.headword for r in file.records("ณ")] == ["ณ"]
    ranks = {
        r.headword: r.frequency_rank for r in every_record(file) if r.frequency_rank
    }
    # กิน 4 times, หมา and ดี 3; ไทย (once as ไท) and จะ twice - the lone จ
    # gave จะ nothing - in the source's order; ตัว, ณ and กา once
    assert ranks == {
        "กิน": 1,
        "หมา": 2,
        "ดี": 3,
        "ไทย": 4,
        "จะ": 5,
        "ตัว": 6,
        "ณ": 7,
        "กา": 8,
    }
    # a word never said is kept, unranked, and found whole
    assert [r.frequency_rank for r in file.records("กาแล็กซี")] == [None]
    dictionary = BasicDictionary(file, ThaiSplit(file), "th")
    line = "หมาจะกินดี"
    assert [line[a:b] for a, b in dictionary.words(line)] == ["หมา", "จะ", "กิน", "ดี"]
    assert [w.entry.frequency_rank for w in dictionary.words_in(line, "th")] == [
        2,
        5,
        1,
        3,
    ]
    assert dictionary.words("กาแล็กซีดี") == [(0, 8), (8, 10)]
    assert not (built / "wiktth-zh.sqlite").exists()
    credits = (built / "wiktth.CREDITS.md").read_text(encoding="utf-8")
    assert "Common Voice" in credits and "publicdomain/zero" in credits


def test_the_french_pack_finds_a_word_written_onto_an_elided_one(built: Path) -> None:
    """French writes "l'homme" as one run of letters: the split cuts it after
    the elided word, so each is found - and "aujourd'hui", one word, stays
    whole (polyglotic-hq 341)."""
    file = SqliteDictionary(built / "wiktfr.sqlite")
    assert file.info["language"] == "fr"
    dictionary = BasicDictionary(file, SpacedSplit("fr"), "fr")
    line = "L'homme, aujourd'hui j'ai vu les hommes."
    found = {
        line[w.start : w.end]: [
            e.headword for e in dictionary.lookup_split(line[w.start : w.end], w)
        ]
        for w in SpacedSplit("fr").words(line)
    }
    assert found["L'"] == ["l'"] and found["homme"] == ["homme"]
    assert found["aujourd'hui"] == ["aujourd'hui"]
    assert found["ai"] == ["avoir"] and found["hommes"] == ["homme"]
    assert [r.reading for r in file.records("homme")] == ["/ɔm/"]
    assert not (built / "wiktfr-zh.sqlite").exists()  # other meanings: riders


def test_credits_name_each_pack_source_and_its_licence(built: Path) -> None:
    text = (built / "jmdict.CREDITS.md").read_text(encoding="utf-8")
    assert "CC BY-SA 4.0" in text and "EDRDG" in text and "Jonathan Waller" in text
    spanish = (built / "wiktes.CREDITS.md").read_text(encoding="utf-8")
    assert "Wiktionary" in spanish and "wordfreq" in spanish


def test_a_pack_builds_byte_for_byte_the_same(
    built: Path, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    again = tmp_path / "again"
    again.mkdir()
    paths = {p.stem.split(".")[0]: p for p in (tmp_path / "upstream").iterdir()}
    named = {
        "kaikki-es": paths["es"],
        "kaikki-zh": paths["zh"],
        "jmdict": paths["jmdict"],
        "jlpt": paths["jlpt"],
        "wordfreq": paths["wordfreq"],
    }
    packs.build(packs.PACKS["es"], named, again)
    assert (again / "wiktes.sqlite").read_bytes() == (
        built / "wiktes.sqlite"
    ).read_bytes()


def test_an_entry_keeps_its_id_whatever_else_its_pack_keeps(
    built: Path, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A language's full dictionary in place of its basic pack - more
    entries, from the same source - gives every entry the basic pack had
    the ID it had, so the learner's words carry over unchanged (decision
    0089, polyglotic-hq 298)."""
    bigger = dict(FREQ)
    bigger["es"] = {**FREQ["es"], 400: ["rarísimo"]}  # one more word kept
    monkeypatch.setattr(sys.modules[__name__], "FREQ", bigger)
    paths = sources(tmp_path / "bigger-sources")
    out = tmp_path / "bigger"
    out.mkdir()
    packs.build(packs.PACKS["es"], paths, out)
    basic = SqliteDictionary(built / "wiktes.sqlite")
    full = SqliteDictionary(out / "wiktes.sqlite")
    ids = {r.entry_id for w in basic.headwords() for r in basic.records(w)}
    assert full.records("rarísimo") and not basic.records("rarísimo")
    for word in basic.headwords():
        assert [r.entry_id for r in basic.records(word)] == [
            r.entry_id for r in full.records(word) if r.entry_id in ids
        ]


def test_pack_names_fit_the_servers_entry_id_pattern() -> None:
    for pack in packs.PACKS.values():
        assert pack.name.isascii() and pack.name.isalnum() and pack.name.islower()


def test_a_new_spaced_language_is_a_config_of_the_wiktionary_reader(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """A language with no pack yet needs no module of its own:
    `wiktionary_pack` reads its Wiktionary as French's is read - English
    meanings, IPA, inflections from form-of senses and inflection tables,
    ranked by wordfreq (polyglotic-hq 380; Lithuanian stands in since Dutch
    has its pack, 387)."""
    monkeypatch.setattr(packs, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    upstream = sources(tmp_path / "upstream")
    monkeypatch.setattr(coverage, "PROBE", tmp_path)
    (tmp_path / "lt.txt").write_text("De huizen, het huis.", encoding="utf-8")

    def lt(word: str, pos: str, *senses: dict[str, object], **extra: object) -> str:
        obj = {"word": word, "pos": pos, "lang_code": "lt", "senses": list(senses)}
        return json.dumps({**obj, **extra}, ensure_ascii=False)

    words = [
        lt(
            "huis",
            "noun",
            sense("house"),
            sounds=[{"ipa": "/ɦœys/"}],
            forms=forms(("huizen", "plural")),
        ),
        lt("huisje", "noun", sense("diminutive of huis", "huis")),
        lt("gaan", "verb", sense("to go"), forms=forms(("ging", "past"))),
    ]
    upstream["kaikki-lt"] = tmp_path / "lt.jsonl.gz"
    upstream["kaikki-lt"].write_bytes(gzip.compress("\n".join(words).encode()))
    with zipfile.ZipFile(upstream["wordfreq"], "a") as wheel:
        data = msgpack(
            [
                {"format": "cB", "version": 1},
                *([[]] * 200),
                ["huis", "gaan"],
                *([[]] * 99),
                ["huizen", "ging"],
            ]
        )
        wheel.writestr("wordfreq/data/large_lt.msgpack.gz", gzip.compress(data))
    stand_in = replace(sources_module.KAIKKI_FR, name="kaikki-lt")
    pack = packs.wiktionary_pack("lt", "Lithuanian", stand_in)
    out = tmp_path / "out"
    out.mkdir()
    packs.build(pack, upstream, out)
    file = SqliteDictionary(out / "wiktlt.sqlite")
    dictionary = BasicDictionary(file, SpacedSplit("lt"), "lt")
    assert [e.headword for e in dictionary.lookup("huizen")] == ["huis"]
    assert [e.headword for e in dictionary.lookup("huisje")] == ["huis"]
    assert [e.headword for e in dictionary.lookup("ging")] == ["gaan"]
    assert [r.reading for r in file.records("huis")] == ["/ɦœys/"]
    assert file.info["language"] == "lt" and file.info["meanings_language"] == "en"
    assert pack.about.startswith("Wiktionary's Lithuanian words with their English")
    assert not (out / "wiktlt-zh.sqlite").exists()  # English first (DECISIONS #175)
    file.close()


def test_a_spelling_rule_writes_inflected_forms_as_captions_write_them() -> None:
    """A language whose inflection tables mark what captions leave out
    (Arabic's vowels) rewrites each form; a form that becomes its lemma
    once rewritten is no inflection of it (polyglotic-hq 380)."""
    words = kaikki.read_language(
        kaikki.lines_of(
            [
                json.dumps(
                    {
                        "word": "kat",
                        "pos": "noun",
                        "lang_code": "xx",
                        "senses": [sense("cat")],
                        "forms": forms(
                            ("kát", "canonical"),
                            ("kàt", "singular"),
                            ("kàts", "plural"),
                        ),
                    },
                ),
            ],
            "xx",
        )
    )
    plain = packs.rewritten(
        words, lambda form: form.replace("\u0300", "").replace("à", "a")
    )
    assert dict(plain.forms) == {"kats": {"kat"}}


def headwords(dictionary: BasicDictionary, line: str) -> dict[str, list[str]]:
    """Each word of `line` as the split cuts it -> what a lookup finds."""
    split = dictionary._split
    return {
        line[w.start : w.end]: [
            e.headword for e in dictionary.lookup_split(line[w.start : w.end], w)
        ]
        for w in split.words(line)
    }


def test_german_nouns_keep_their_rank_beside_a_lower_case_twin(built: Path) -> None:
    """German writes nouns with a capital: "Mensch" isn't a name spelled
    like the pronoun "mensch", so it and its forms take the word's
    frequency (it had none: Menschen was the probe's commonest miss)."""
    file = SqliteDictionary(built / "wiktde.sqlite")
    german = BasicDictionary(file, SpacedSplit("de"), "de")
    assert [e.headword for e in german.lookup("Menschen")] == ["Mensch"]
    rank = {
        r.headword: r.frequency_rank
        for w in ("Mensch", "gehen")
        for r in file.records(w)
    }
    mensch, gehen = rank["Mensch"], rank["gehen"]
    assert mensch is not None and gehen is not None and mensch < gehen
    assert [r.headword for r in file.records("Ich")] == []  # not kept: no rank
    assert [e.meanings for e in german.lookup("Ich")] == [("(pron) I",)]


def test_italian_cuts_elided_words_and_keeps_its_contractions(built: Path) -> None:
    """ "l'uomo" is two words, as French's "l'homme"; "della" (di + la) is
    a contraction with a meaning of its own, not a form of the phrase
    "di la", which no caption looks up whole."""
    italian = BasicDictionary(
        SqliteDictionary(built / "wiktit.sqlite"), SpacedSplit("it"), "it"
    )
    found = headwords(italian, "L'uomo della casa")
    assert found["L'"] == ["l'"] and found["uomo"] == ["uomo"]
    assert found["della"] == ["della"]
    assert italian.lookup("della")[0].meanings == (
        "(contraction) contraction of di la; of the",
    )


def test_arabic_is_found_without_vowel_marks_or_the_small_words_on_it(
    built: Path,
) -> None:
    """Captions write no vowel marks and put "and", "the", "with" onto the
    next word: the table's forms lose their marks, the split guesses the
    word without its small words - only where the pack hasn't got it whole
    (وزير is minister, not و + زير). The planet's name, spelled as "the
    earth", gives its frequency to earth (polyglotic-hq 380)."""
    file = SqliteDictionary(built / "wiktar.sqlite")
    arabic = BasicDictionary(file, SpacedSplit("ar"), "ar")
    found = headwords(arabic, "الكتاب والكتب بكتابه وزير الأرض")
    assert found == {
        "الكتاب": ["كتاب"],
        "والكتب": ["كتاب"],
        "بكتابه": ["كتاب"],
        "وزير": ["وزير"],
        "الأرض": ["أرض"],
    }
    assert [r.reading for r in file.records("كتاب")] == ["kitāb"]
    assert not file.records("الأرض")  # the name: no rank, so not kept


def test_hindi_words_keep_their_vowel_signs_and_a_name_gives_way(
    built: Path,
) -> None:
    """ "गया" is "went" (जाना's form) far more than the city Gaya: the form's
    frequency is the verb's. A whole Hindi word is one word to the split."""
    file = SqliteDictionary(built / "wikthi.sqlite")
    hindi = BasicDictionary(file, SpacedSplit("hi"), "hi")
    assert headwords(hindi, "वह गया।")["गया"] == ["जाना"]
    assert [r.reading for r in file.records("जाना")] == ["jānā"]
    assert hindi.words("हिंदी बोलता") == [(0, 5), (6, 11)]


def test_turkish_words_are_found_under_their_suffixes(
    built: Path, monkeypatch: MonkeyPatch
) -> None:
    """A causative Wiktionary glosses is a word of its own: araştırmalar
    had been shown as araşmak, "to call each other" (polyglotic-hq 388).
    Its suffixes are guessed off, without simplemma as installed; İngiltere
    has its frequency (Python's lower case of İ had none) and is kept."""
    monkeypatch.setattr(spaced_split, "_lemmatizer", lambda: None)
    file = SqliteDictionary(built / "wikttr.sqlite")
    turkish = BasicDictionary(file, SpacedSplit("tr"), "tr")
    found = headwords(turkish, "Araştırmalar evlerimizde İngiltere'de araştırıldı")
    assert found == {
        "Araştırmalar": ["araştırmak"],
        "evlerimizde": ["ev"],
        "İngiltere'de": ["İngiltere"],
        "araştırıldı": ["araştırmak"],
    }
    assert turkish.lookup("araştırmak")[0].meanings == (
        "(verb) causative of araşmak: to research",
    )
    assert turkish.lookup("aratmak")[0].headword == "araşmak"


def test_a_derived_word_whose_gloss_says_what_it_means_is_a_word_of_its_own() -> None:
    lines = BATCH["tr"][:3]
    plain = kaikki.read_language(kaikki.lines_of(lines, "tr"))
    assert plain.forms["araştırmak"] == {"araşmak"}
    assert "araştırmak" not in {e.word for e in plain.entries}
    found = kaikki.read_language(
        kaikki.lines_of(lines, "tr"), derived=kaikki.DERIVATIONS
    )
    assert "araştırmak" not in found.forms
    assert "araştırmak" in {e.word for e in found.entries}
    assert found.forms["aratmak"] == {"araşmak"}  # says nothing of its own


def test_malay_takes_the_words_it_shares_with_indonesian_marked_so(
    built: Path,
) -> None:
    """Malay's Wiktionary hasn't got "penting" (important): Indonesian's
    entry is taken, its meanings marked as Indonesian's. Malay's own
    entry wins ("kereta" is a car, not Indonesian's carriage); no name or
    capitalised initialism is taken (polyglotic-hq 388)."""
    malay = BasicDictionary(
        SqliteDictionary(built / "wiktms.sqlite"), SpacedSplit("ms"), "ms"
    )
    assert malay.lookup("penting")[0].meanings == ("(adj) important" + packs.SHARED,)
    assert [e.meanings for e in malay.lookup("kereta")] == [("(noun) car",)]
    assert malay.lookup("TV") == [] and malay.lookup("jakarta") == []


def test_a_word_with_a_dotted_capital_i_has_its_frequency() -> None:
    """Python's lower case of İ is i with a combining dot, which no list
    writes: İngiltere had no frequency and was cut (polyglotic-hq 388)."""
    assert packs.frequency_of("İngiltere", {"ingiltere": 3e-5}) == 3e-5


def test_ukrainian_forms_are_found_without_their_stress_marks(built: Path) -> None:
    """Ukrainian's tables mark the stress (яка́), captions don't: 54.8 % of
    the probe's words were found in the installed app without this
    (polyglotic-hq 387). Its reading is the headword with the stress."""
    file = SqliteDictionary(built / "wiktuk.sqlite")
    ukrainian = BasicDictionary(file, SpacedSplit("uk"), "uk")
    assert [e.headword for e in ukrainian.lookup("яка")] == ["який"]
    assert [r.reading for r in file.records("який")] == ["яки́й"]


def test_persian_words_are_whole_at_their_joiner_and_ranked_with_common_voice(
    built: Path,
) -> None:
    """Persian writes plurals and the present's prefix on with a zero-width
    non-joiner: the word is whole, its parts guessed off (داستان‌های:
    داستان; می‌کنم: کنم, کردن's). Forms lose their vowel marks; the reading
    is Iran's (ketâb, not kitāb). Ranks are wordfreq's and Common Voice's
    words counted: داستان, only in the sentences, is ranked (polyglotic-hq
    374, 387)."""
    file = SqliteDictionary(built / "wiktfa.sqlite")
    persian = BasicDictionary(file, SpacedSplit("fa"), "fa")
    found = headwords(persian, f"داستان{ZWNJ}های کتابهای میکنم كتاب و")
    assert found == {
        f"داستان{ZWNJ}های": ["داستان"],
        "کتابهای": ["کتاب"],
        "میکنم": ["کردن"],
        "كتاب": ["کتاب"],  # Arabic's kaf, as some text writes it
        "و": ["و"],
    }
    assert persian.lookup("و")[0].meanings == ("(conj) and",)
    assert [r.reading for r in file.records("کتاب")] == ["ketâb"]
    assert [r.frequency_rank is not None for r in file.records("داستان")] == [True]
    assert file.info["frequency_source"] == "wordfreq+commonvoice-fa"


def test_filipinos_linker_makes_a_form_of_its_word(built: Path) -> None:
    """ "isang" is isa with the linker -ng, "noong" noon with -g: forms of
    their word, so isa takes isang's frequency and the name Isang, spelled
    the same, gives way (it had been the pack's 8th word; polyglotic-hq
    387). A word that is its own ("kung") is left alone."""
    file = SqliteDictionary(built / "wikttl.sqlite")
    filipino = BasicDictionary(file, SpacedSplit("tl"), "tl")
    assert [e.headword for e in filipino.lookup("Isang")] == ["isa"]
    assert [e.headword for e in filipino.lookup("noong")] == ["noon"]
    assert [e.headword for e in filipino.lookup("kung")] == ["kung"]
    assert not file.records("Isang")  # no rank of its own: not kept
    isa, noon = file.records("isa")[0], file.records("noon")[0]
    assert isa.frequency_rank is not None and noon.frequency_rank is not None
    assert isa.frequency_rank < noon.frequency_rank


def test_a_letter_of_the_alphabet_is_no_entry_of_its_word(tmp_path: Path) -> None:
    """Wiktionary lists a language's letters under the words they spell:
    Polish's "w" (in) had "the twenty-sixth letter" as its first meaning,
    at the word's rank (polyglotic-hq 387: Persian's و, "and", its first
    word). A one-letter word keeps its own entries."""
    pl = in_("pl")
    source = tmp_path / "pl.jsonl.gz"
    lines = [
        pl("w", "character", sense("The twenty-sixth letter of the Polish alphabet")),
        pl("w", "noun", sense("The name of the Latin-script letter W/w.")),
        pl("w", "prep", sense("in")),
        pl("o", "prep", sense("about")),
    ]
    source.write_bytes(gzip.compress("\n".join(lines).encode("utf-8")))
    draft = packs.read_wiktionary("pl", {"kaikki-pl": source})
    assert [(e.headword, e.meanings) for e in draft.entries] == [
        ("w", ("(prep) in",)),
        ("o", ("(prep) about",)),
    ]


def test_a_form_of_several_words_is_shared_by_how_common_each_is() -> None:
    """Italian's "sono" is essere's and also suonare's (via sonare): it had
    made suonare a top-25 word. Where the reader splits shared forms, each
    lemma takes the share its own frequency gives it (polyglotic-hq 380)."""
    draft = packs.Draft(
        [
            packs.DraftEntry("essere|verb|", "essere", "", ("to be",), ("essere",)),
            packs.DraftEntry(
                "suonare|verb|", "suonare", "", ("to play",), ("suonare",)
            ),
        ],
        {"essere": ["essere|verb|"], "suonare": ["suonare|verb|"]},
        {"sono": {"essere", "suonare"}},
        split_shared_forms=True,
    )
    freq = {"essere": 9e-4, "suonare": 1e-4, "sono": 6e-3}
    total = packs.frequencies(draft, freq)
    assert total["essere|verb|"] == pytest.approx(9e-4 + 6e-3 * 0.9)
    assert total["suonare|verb|"] == pytest.approx(1e-4 + 6e-3 * 0.1)
    draft.split_shared_forms = False  # the older readers: the whole to each
    assert packs.frequencies(draft, freq)["suonare|verb|"] == pytest.approx(6.1e-3)


def test_a_word_is_found_in_a_list_that_folds_its_case() -> None:
    """wordfreq folds ß to ss: "Straße" had no frequency, so German's pack
    left it out (polyglotic-hq 380)."""
    wordfreq = {"strasse": 2e-4, "gross": 1e-4}
    assert packs.frequency_of("Straße", wordfreq) == 2e-4
    assert packs.frequency_of("groß-straße", wordfreq) == pytest.approx(
        1 / (1 / 1e-4 + 1 / 2e-4) / packs.JOINED
    )


def test_a_form_of_target_with_an_aspect_a_gender_or_two_lemmas_is_no_phrase() -> None:
    """kaikki writes after a form-of target's word its aspect ("стать pf"),
    a gender ("uovo m") or a second lemma ("fondare and fondere"; "avere
    and"): the form is still an inflection, not a word of its own whose
    meaning is "plural past indicative of стать pf" - Russian's "стали" had
    been its 683rd word, Italian's "ha" and "ho" entries (polyglotic-hq
    390). A real phrase ("di la") stays a meaning."""

    def read(word: str, target: str) -> kaikki.Language:
        obj = {
            "word": word,
            "pos": "verb",
            "lang_code": "xx",
            "senses": [sense(f"some form of {target}", target)],
        }
        return kaikki.read_language(kaikki.lines_of([json.dumps(obj)], "xx"))

    for word, target, lemmas in [
        ("стали", "стать pf", {"стать"}),
        ("боюсь", "бояться impf", {"бояться"}),
        ("uova", "uovo m", {"uovo"}),
        ("gran", "grande m or f by sense", {"grande"}),
        ("fonderò", "fondare and fondere", {"fondare", "fondere"}),
        ("ha", "avere and", {"avere"}),
    ]:
        found = read(word, target)
        assert found.entries == [] and found.forms[word] == lemmas, word
    lo = kaikki.read_language(  # a small word's two lemmas are its meaning
        kaikki.lines_of(
            [
                json.dumps(
                    {
                        "word": "lo",
                        "pos": "pron",
                        "lang_code": "xx",
                        "senses": [sense("accusative of él and usted", "él and usted")],
                    }
                )
            ],
            "xx",
        )
    )
    assert [e.meanings for e in lo.entries] == [("accusative of él and usted",)]
    della = read("della", "di la")
    assert [e.meanings for e in della.entries] == [("some form of di la",)]
    assert "della" not in della.forms


def test_a_name_like_a_lower_case_word_keeps_its_own_forms_frequency() -> None:
    """Polska (Poland) is "polska", polski's feminine, in lower case: it
    takes none of that, but its own "Polsce" ("in Poland", Polish's 167th
    word) is no lower-case word's, and counts. It had been cut from the
    pack (polyglotic-hq 390)."""
    draft = packs.Draft(
        [
            packs.DraftEntry(
                "Polska|name|", "Polska", "", ("(name) Poland",), ("Polska",)
            ),
            packs.DraftEntry(
                "polski|adj|", "polski", "", ("(adj) Polish",), ("polski",)
            ),
        ],
        {"Polska": ["Polska|name|"], "polski": ["polski|adj|"]},
        {"Polsce": {"Polska"}, "Polski": {"Polska"}, "polska": {"polski"}},
    )
    freq = {"polska": 5e-4, "polsce": 2e-4, "polski": 4e-4}
    total = packs.frequencies(draft, freq)
    assert total["Polska|name|"] == pytest.approx(2e-4)  # Polsce's alone
    assert total["polski|adj|"] == pytest.approx(9e-4)


def test_a_page_the_extracts_havent_got_is_supplied_until_they_have() -> None:
    """kaikki's extracts have no page "i": Polish's "and", 2.7 % of its
    running words, had no entry (polyglotic-hq 380, 390). It takes kaikki's
    key, so the ID is the same once the source has it - and then the
    source's entry is the one kept."""
    empty = packs.Draft([], {})
    found = packs.supplied(empty, "pl")
    assert [(e.key, e.headword, e.meanings[0]) for e in found.entries] == [
        ("i|conj|", "i", "(conj) and")
    ]
    assert found.forms == {"i": ["i|conj|"]}
    own = packs.DraftEntry("i|conj|", "i", "", ("(conj) and, plus",), ("i",))
    has_it = packs.supplied(packs.Draft([own], {"i": ["i|conj|"]}), "pl")
    assert has_it.entries == [own]
    assert packs.supplied(packs.Draft([], {}), "es").entries == []


def test_arabic_is_found_written_without_hamza_or_with_alif_maqsura() -> None:
    """Five of Arabic's 200 commonest words in wordfreq's list are written
    so (انت for أنت, فى for في) and found nothing (polyglotic-hq 390)."""
    assert packs.arabic_spellings("أنت") == {"انت"}
    assert packs.arabic_spellings("في") == {"فى"}
    assert packs.arabic_spellings("إلى") == {"الى", "إلي", "الي"}
    words = kaikki.Language(
        entries=[
            kaikki.WiktEntry("أنت|pron|", "أنت", "pron", ("you",)),
            kaikki.WiktEntry("انت|verb|", "انت", "verb", ("a word of its own",)),
            kaikki.WiktEntry("إلى|prep|", "إلى", "prep", ("to",)),
        ]
    )
    words.forms["كتب"] = {"كتاب"}
    found = packs.also_written(words, packs.arabic_spellings)
    assert found.forms["الى"] == {"إلى"}
    assert "انت" not in found.forms  # a word of its own keeps what it finds
    assert found.forms["كتب"] == {"كتاب"}


def test_one_word_repeated_with_a_hyphen_is_as_rare_as_can_be() -> None:
    """Filipino's stutters "ang-ang" and "at-at" had been its 30th and 62nd
    words: the phrase of two very common parts over `JOINED` is still
    common (polyglotic-hq 387, 390). Two different words keep the rule."""
    freq = {"ang": 5e-2, "at": 3e-2, "tem": 1e-3}
    assert packs.frequency_of("ang-ang", freq) == packs.REPEATED
    assert packs.frequency_of("at-at-at", freq) == packs.REPEATED
    assert packs.frequency_of("ang-at", freq) == pytest.approx(
        1 / (1 / 5e-2 + 1 / 3e-2) / packs.JOINED
    )


def test_a_short_form_in_a_table_never_counts_its_page_does() -> None:
    """A broken Romanian template listed "ii" and "i" as forms of vârtejire
    (whirlwind), its 47th word; nouns list bare endings (polyglotic-hq
    387, 390). Spanish's "va" is ir's form by its own page."""

    def obj(word: str, pos: str, *forms: str, gloss: str = "x") -> str:
        return json.dumps(
            {
                "word": word,
                "pos": pos,
                "lang_code": "xx",
                "senses": [sense(gloss)],
                "forms": [{"form": f, "tags": ["plural"]} for f in forms],
            }
        )

    found = kaikki.read_language(
        kaikki.lines_of(
            [
                obj("vârtejire", "noun", "ii", "i", "-lor", "vârtejiri"),
                obj("ir", "verb", "va", "vamos"),
                line(
                    "va",
                    "verb",
                    sense("third-person singular of ir", "ir"),
                    lang_code="xx",
                ),
            ],
            "xx",
        )
    )
    assert dict(found.forms) == {
        "vârtejiri": {"vârtejire"},
        "va": {"ir"},
        "vamos": {"ir"},
    }
    assert ("va", "ir") in found.verb_forms


def test_only_a_name_keeps_its_own_forms_frequency() -> None:
    """German's surname Haus is "haus" in lower case, hausen's imperative:
    unlike Polska, a word that isn't only a name stays without a frequency,
    so the noun's card isn't joined by a surname (polyglotic-hq 390)."""
    draft = packs.Draft(
        [
            packs.DraftEntry(
                "Haus|name|", "Haus", "", ("(name) a surname",), ("Haus",)
            ),
            packs.DraftEntry("Haus|verb|", "Haus", "", ("(verb) lives",), ("Haus",)),
            packs.DraftEntry(
                "hausen|verb|", "hausen", "", ("(verb) to dwell",), ("hausen",)
            ),
        ],
        {"Haus": ["Haus|name|", "Haus|verb|"], "hausen": ["hausen|verb|"]},
        {"Hauses": {"Haus"}, "haus": {"hausen"}},
    )
    total = packs.frequencies(draft, {"hauses": 1e-4, "haus": 1e-3, "hausen": 1e-5})
    assert total["Haus|name|"] == total["Haus|verb|"] == 0.0


def test_a_letter_takes_no_frequency_as_an_abbreviation_or_a_capital() -> None:
    """wordfreq's "d" is the letter or the elided de: once 387 dropped the
    letters' own entries, French's "D" (abbreviation of dame) made dame its
    9th word, German's "a" (symbol of Ar) made Ar its 184th and the
    letter-nouns S and D came into its top 300 (polyglotic-hq 390)."""
    found = kaikki.read_language(
        kaikki.lines_of(
            [
                json.dumps(
                    {
                        "word": "D",
                        "pos": "noun",
                        "lang_code": "xx",
                        "senses": [
                            {
                                "glosses": ["abbreviation of dame"],
                                "tags": ["abbreviation", "alt-of"],
                                "alt_of": [{"word": "dame"}],
                            }
                        ],
                    }
                ),
                json.dumps(
                    {
                        "word": "Mme",
                        "pos": "noun",
                        "lang_code": "xx",
                        "senses": [
                            {
                                "glosses": ["abbreviation of madame"],
                                "tags": ["abbreviation", "alt-of"],
                                "alt_of": [{"word": "madame"}],
                            }
                        ],
                    }
                ),
            ],
            "xx",
        )
    )
    assert dict(found.forms) == {"Mme": {"madame"}} and found.entries == []
    contraction = kaikki.read_language(  # kaikki tags it "abbreviation" too
        kaikki.lines_of(
            [
                json.dumps(
                    {
                        "word": "do",
                        "pos": "contraction",
                        "lang_code": "xx",
                        "senses": [
                            {
                                "glosses": ["contraction of de + o"],
                                "tags": ["abbreviation", "alt-of", "contraction"],
                                "alt_of": [{"word": "de"}],
                            }
                        ],
                    }
                )
            ],
            "xx",
        )
    )
    assert dict(contraction.forms) == {"do": {"de"}}
    assert packs.frequency_of("S", {"s": 1e-3}) == 0.0
    assert packs.frequency_of("s", {"s": 1e-3}) == 1e-3  # a lower-case word: kept
