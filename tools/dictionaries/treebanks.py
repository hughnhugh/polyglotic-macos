"""Universal Dependencies treebanks: how often a word is each part of
speech, to put a word's commonest part of speech first on its card
(polyglotic-hq 393).

Wiktionary lists a word's entries by etymology, so the first is often not
the one a learner meets: Thai's กับ showed "trap" before "with", มัน "fat"
before "it", Arabic's قد "to cut into strips" before the particle. A
treebank says how its sentences use each word - กับ is a preposition far
more than a noun - and `kaikki.read_language` orders a headword's entries
by that (`kaikki.Uses`).

Only counts are taken: no sentence of a treebank reaches a pack. The
treebanks are 359's for word roles (CC BY-SA, Spanish's AnCora CC BY),
each repository at its release 2.17 commit; Ukrainian's only large one
(IU) is non-commercial, so Ukrainian has none.
"""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path

from tools.dictionaries.sources import Source

RELEASE = "2.17"
COMMITS = {
    "Arabic-PUD": "2865170299b7bc25ae742fd5a0c62ca62022170c",
    "Czech-CAC": "414d8497523be1df3b23d153755c16d1fd15855f",
    "Czech-PUD": "dfab1926110b82c2e01278c292d9c01b0abbc0ff",
    "Dutch-Alpino": "d64749ac918f18d31dd4c4e75ff56626432d9ba3",
    "English-EWT": "c5baffde1e106bcd828c520109eb905bfc3ac06f",
    "Dutch-LassySmall": "b8cdca9661408608945133e80bb566a6a58146ea",
    "French-GSD": "b40dc639c6eff162075d1e576d59fa8506c5a402",
    "French-PUD": "c281ae7df41405c38d49499b72f3e29963f05a33",
    "German-GSD": "02f0333fe0a87d4faa83a6352ad5b2b4a1c8b991",
    "German-PUD": "e42201a08c2512818471efcdedc44bb22d9f1df2",
    "Greek-GUD": "33143eaefbd7b73509c83109823e156a5022ab80",
    "Hindi-PUD": "66d03982c23dd3049b7f7d11964247794411079c",
    "Indonesian-GSD": "50630b97c8c87b39747a5920f3e75d5e067b6997",
    "Indonesian-PUD": "0b217909f5e0ed6779d064e34c6a5b2d61d8f552",
    "Italian-PUD": "bae2181e24fef395d662b22190e7eb5725dac3b5",
    "Macedonian-MTB": "6c94c92e6e98134582f8deff7b38c8b1bb641393",
    "Persian-Seraji": "f993cdd1189448b71f6dfa4fa537618ea46df10a",
    "Polish-PUD": "aa2cd9244d59e40394c27732ad054fc044075374",
    "Portuguese-Bosque": "53bb7584bec8f6b83a27eaefe0656690df9d7773",
    "Portuguese-PUD": "7b8897dc3d2fef397eed177ab6d89bbf3e33f017",
    "Romanian-RRT": "a1bd569722e2a4b445dd76a4787bb0c6474ecdc3",
    "Russian-GSD": "9acc9d677327043bd416fcc89e4b3407c620d885",
    "Russian-PUD": "1228be1571bca125ac19c922ef52ae71d3cdbb83",
    "Spanish-AnCora": "f503b2dfb4bca0a4224668ca31a24f5b9092bd63",
    "Spanish-PUD": "9ecbc7ea9a49ead815ce66750ebea3409b68caad",
    "Swedish-PUD": "823b52ee34db3e45d6ecd9c279d708a4848a0e51",
    "Swedish-Talbanken": "463c1eb7176c19e8d7cc54e5f5b0f21d6d6ce44d",
    "Tagalog-TRG": "7d4e6ef4c875b1462122a4dbe1cda0feb1e05806",
    "Thai-PUD": "4e0e10fd6d026750990d578c939507cfd2de13af",
    "Thai-TUD": "94dadd92b41cb31da657d0e21538cc867a1e0c5a",
    "Turkish-BOUN": "5cb7559d4efd63c22d253ff9e3fa2b0202b7913e",
    "Turkish-PUD": "4817a5e719906e25662fd6ea8d937b4992c6897d",
    "Vietnamese-VTB": "4216d3aed0fa8a11d61284df0776a8a17d7fe6aa",
}
"""Each treebank repository's commit for release 2.17."""
LICENCES = {
    "Arabic-PUD": "CC BY-SA 3.0",
    "French-PUD": "CC BY-SA 3.0",
    "German-PUD": "CC BY-SA 3.0",
    "Hindi-PUD": "CC BY-SA 3.0",
    "Indonesian-PUD": "CC BY-SA 3.0",
    "Italian-PUD": "CC BY-SA 3.0",
    "Portuguese-PUD": "CC BY-SA 3.0",
    "Russian-PUD": "CC BY-SA 3.0",
    "Spanish-AnCora": "CC BY 4.0",
    "Spanish-PUD": "CC BY-SA 3.0",
    "Thai-PUD": "CC BY-SA 3.0",
    "Turkish-PUD": "CC BY-SA 3.0",
}
"""The treebanks whose licence isn't CC BY-SA 4.0."""
FILES = (
    (
        "en",
        "English-EWT",
        "en_ewt-ud-train",
        "6fe5692f2e02198262483daba0626efe346dd19f0ce6c3ee7728b08af9b90a9c",
    ),
    (
        "en",
        "English-EWT",
        "en_ewt-ud-dev",
        "de507882611c54f19934f9a65d654b37f55a5c315da1794b9f13348b28b39c12",
    ),
    (
        "en",
        "English-EWT",
        "en_ewt-ud-test",
        "b837531faddd54f5c89cf5259cfe5306b075556a9ff19b2271393df29c6b02f8",
    ),
    (
        "ar",
        "Arabic-PUD",
        "ar_pud-ud-test",
        "befc6dd18b5b8803644ae8208e2e5f52c0957a36437627c05110914ec42281a3",
    ),
    (
        "cs",
        "Czech-PUD",
        "cs_pud-ud-test",
        "af365749e569cc9daeeebee916dd33161e5c23b278077553f6ffbf4f82c5b652",
    ),
    (
        "cs",
        "Czech-CAC",
        "cs_cac-ud-dev",
        "06ab3b41d0192641a063048c58f27ecc10640b61c0bae3112dd778ea1f4201f7",
    ),
    (
        "cs",
        "Czech-CAC",
        "cs_cac-ud-test",
        "71c03ef1ab14451e294bbc0d7896ea4f8a3faf26790fc2f04cc473e62e43162c",
    ),
    (
        "de",
        "German-PUD",
        "de_pud-ud-test",
        "a530bdb50349bbd7c13706b6a759a9d73e8f514fff41fbf27149e914b0c3e723",
    ),
    (
        "de",
        "German-GSD",
        "de_gsd-ud-dev",
        "39c7b34178ca9f339422640ca9373c88a1b7a94b0eacc7fa8ec247587550853b",
    ),
    (
        "de",
        "German-GSD",
        "de_gsd-ud-test",
        "23dec3e3dfe773b1f90f1510a49169a6bd391e940de47606375a43a431fda3cf",
    ),
    (
        "el",
        "Greek-GUD",
        "el_gud-ud-train",
        "4dc85099cde6dbfb8dc5c0eb1f3c2366e3478c1650d515289a899325a4ceb678",
    ),
    (
        "el",
        "Greek-GUD",
        "el_gud-ud-test",
        "e66595e7522d83532bc0c0657dcd05cb8edaa94cd13c03118baeda0b99cacd9f",
    ),
    (
        "es",
        "Spanish-PUD",
        "es_pud-ud-test",
        "71d9844c57073f6ba466d2afd7e446b72be344507bc63ac5c709287e7c06dc9f",
    ),
    (
        "es",
        "Spanish-AnCora",
        "es_ancora-ud-dev",
        "a7a6f19880955c59f2f7420ffd4739ad4d8b36221e03a4196fc33cf67bf741e9",
    ),
    (
        "es",
        "Spanish-AnCora",
        "es_ancora-ud-test",
        "abee215c3e8ae605421afdcd776986439e1d049e5e25aba89843ad01045a1165",
    ),
    (
        "fa",
        "Persian-Seraji",
        "fa_seraji-ud-dev",
        "acc241631c278f96b084285946db28b87fe9c97d81ac58119cdaad0be05799b0",
    ),
    (
        "fa",
        "Persian-Seraji",
        "fa_seraji-ud-test",
        "6d2311596634c739eaf4c4ef4d4125d4ff7562ac56ea4da0b3db6501ecb25710",
    ),
    (
        "fr",
        "French-PUD",
        "fr_pud-ud-test",
        "793540702db111d2bfe04f846edddb23e7a2a432294fe17cb612dd795fb0301f",
    ),
    (
        "fr",
        "French-GSD",
        "fr_gsd-ud-dev",
        "e3e351618331fe2848be11dcd72c7c3bb5ab64957026ece704af5ff712234732",
    ),
    (
        "fr",
        "French-GSD",
        "fr_gsd-ud-test",
        "a75470b1faa49e39c38a85e68bdb444fcd82a08b1600e58975b7ee52091ff8df",
    ),
    (
        "hi",
        "Hindi-PUD",
        "hi_pud-ud-test",
        "3562b7f49420912acad70a45a483f683dcb44624ea92f82e21b29f2ee41a9dff",
    ),
    (
        "id",
        "Indonesian-PUD",
        "id_pud-ud-test",
        "07efad4d64863ab442aef820afdb34c269f80366c6efb583225f943e5baf88b2",
    ),
    (
        "id",
        "Indonesian-GSD",
        "id_gsd-ud-dev",
        "56d4ab12267317d33511326da9fcd5b7eff641435c3b6365401937a33ce05e4b",
    ),
    (
        "id",
        "Indonesian-GSD",
        "id_gsd-ud-test",
        "155171c985bc04b12aa9dfa5704fa686a9fb8182cd2d1f42c3ede828e1502e70",
    ),
    (
        "it",
        "Italian-PUD",
        "it_pud-ud-test",
        "ad5d302bdfd05194155d9ad43dc54c3cb915076d66b3eb6ef33eca9a11f1372a",
    ),
    (
        "mk",
        "Macedonian-MTB",
        "mk_mtb-ud-test",
        "93219e9c20d85ad98fcdbb9df398d33489c865bed7388ac9e712446d8d671b05",
    ),
    (
        "nl",
        "Dutch-Alpino",
        "nl_alpino-ud-dev",
        "0444fc2590d7f522b5f201473940a40f0f1790770fcb568450581f12bcbcffd9",
    ),
    (
        "nl",
        "Dutch-Alpino",
        "nl_alpino-ud-test",
        "20d0f718cdc73b51dbb2744386c9d4ecb1a9df6a076efa81b4c008ace3801fc0",
    ),
    (
        "nl",
        "Dutch-LassySmall",
        "nl_lassysmall-ud-dev",
        "fce8302576a33c0d2b7e98ef7565fb6cefdfd6802dd657529c5b97a2767ce3b5",
    ),
    (
        "nl",
        "Dutch-LassySmall",
        "nl_lassysmall-ud-test",
        "a52efa0878331f1d49f6350ee95f86d1f6dc8578fcf90c652ce5764d486ad4cf",
    ),
    (
        "pl",
        "Polish-PUD",
        "pl_pud-ud-test",
        "6dccca751cf1b701196d238b8f2a259afbddc07f45322839feb4acd99b7e90fb",
    ),
    (
        "pt",
        "Portuguese-PUD",
        "pt_pud-ud-test",
        "e2bd4012a3d0e17dc7ba5d699dd17e05f57986901bb24df07bd0a271cf23178c",
    ),
    (
        "pt",
        "Portuguese-Bosque",
        "pt_bosque-ud-dev",
        "f8a67abae12fbab85a3995204a6459d1958c11065062d4ea5349d6b914e78f81",
    ),
    (
        "pt",
        "Portuguese-Bosque",
        "pt_bosque-ud-test",
        "9a824650b7a02cf411f6e09b39e8fb423c85e1a5fb3a55b87e7f4c0c2ea5b3bb",
    ),
    (
        "ro",
        "Romanian-RRT",
        "ro_rrt-ud-dev",
        "facd931151fac154b6f68a3247b2fcc5156057070a326d7d440d13a92d103efa",
    ),
    (
        "ro",
        "Romanian-RRT",
        "ro_rrt-ud-test",
        "ceb685dee7bcba4c189ff1e145ff6cad46733a502d00ec36795fb440d0eff9d7",
    ),
    (
        "ru",
        "Russian-PUD",
        "ru_pud-ud-test",
        "91a755eb4296451472cc9dd54fcb3b77e33d91378a50a2fd29360b8c94bc4c33",
    ),
    (
        "ru",
        "Russian-GSD",
        "ru_gsd-ud-dev",
        "e3e3d4e8d1d7544e531b2b81ae64257efacc97f93276ce6d2ce52fd1de052fa2",
    ),
    (
        "ru",
        "Russian-GSD",
        "ru_gsd-ud-test",
        "f26e022329162a1c6306f76644d06f770f1572501755421165387137fe63138d",
    ),
    (
        "sv",
        "Swedish-PUD",
        "sv_pud-ud-test",
        "0668c7e71a9ff78cc67319c5c477393ed765bb4dfd054f90ac84f51411f88439",
    ),
    (
        "sv",
        "Swedish-Talbanken",
        "sv_talbanken-ud-dev",
        "31917fc04cfe9ef7ce8c11ed8570b739a0cefdcda5e06ff93207e6d84f37117b",
    ),
    (
        "sv",
        "Swedish-Talbanken",
        "sv_talbanken-ud-test",
        "b8909c4f5f2c64b3cee251de7004fa293717d309e54ca59d149a61d75e8571d7",
    ),
    (
        "th",
        "Thai-PUD",
        "th_pud-ud-test",
        "0eeeaf5cf4352df2fe0b7f114e29d5ab5c1f54476faf64e99313de14d588a31b",
    ),
    (
        "th",
        "Thai-TUD",
        "th_tud-ud-dev",
        "ad6a334d5cebb96e86b1d1928f30515765724e6041543833ad78393e3106dc93",
    ),
    (
        "th",
        "Thai-TUD",
        "th_tud-ud-test",
        "294547eb580d2d44aee73f131355f7a9cb552a93515bef24b855d7366a24e2f7",
    ),
    (
        "tl",
        "Tagalog-TRG",
        "tl_trg-ud-test",
        "d21eb1072f6da530de2e0e3a9065a76ae36559efd43afc7c6d48264024afa8c1",
    ),
    (
        "tr",
        "Turkish-PUD",
        "tr_pud-ud-test",
        "7c1b6fe01662a7617758fbecdda6af6fc3914ace46b1809d6514af0a1c1df88c",
    ),
    (
        "tr",
        "Turkish-BOUN",
        "tr_boun-ud-dev",
        "f6d1ed6e3b57b4e658177eb16089e9fb616bc68fb110eb0894c2b409e41b5c76",
    ),
    (
        "tr",
        "Turkish-BOUN",
        "tr_boun-ud-test",
        "4f74fc0f9efdd1285d781f3efd1e98cbf39cf4433df9eb4dc14162e8ed36773b",
    ),
    (
        "vi",
        "Vietnamese-VTB",
        "vi_vtb-ud-dev",
        "0b779257b9225575b3b30e15d64cc4ef9945a77f8cceb9f92d794b483a2752dd",
    ),
    (
        "vi",
        "Vietnamese-VTB",
        "vi_vtb-ud-test",
        "abc1b0ea98661bbb494a8c0da123ba2fe1a3ef71322c380fe66468884d9b4285",
    ),
)
"""(language, repository, file, its sha256) - every file read for a
language."""

UD = "https://github.com/UniversalDependencies"


def source(language: str, repository: str, file: str, sha256: str) -> Source:
    commit = COMMITS[repository]
    licence = LICENCES.get(repository, "CC BY-SA 4.0")
    return Source(
        name=f"ud-{file}",
        title=f"Universal Dependencies: UD_{repository}, {file}.conllu",
        version=f"release {RELEASE}, commit {commit[:12]}",
        url=(
            f"https://raw.githubusercontent.com/UniversalDependencies/UD_{repository}/"
            f"{commit}/{file}.conllu"
        ),
        sha256=sha256,
        filename=f"ud-{file}-{commit[:12]}.conllu",
        homepage=f"{UD}/UD_{repository}",
        licence=licence,
        notice=(
            f"UD_{repository}, by its authors as its README names them, from "
            "Universal Dependencies (https://universaldependencies.org/). Only "
            "counts of each word's parts of speech are used; none of its text "
            "is in the pack"
        ),
        used_for="the order of a word's entries: its commonest part of speech first",
    )


def of(language: str) -> tuple[Source, ...]:
    """The treebank files read for `language` (none: Wiktionary's order)."""
    return tuple(source(*row) for row in FILES if row[0] == language)


def uses(
    files: Iterable[Path],
    written: Callable[[str], str] | None = None,
    forms_only: bool = False,
) -> dict[str, Counter[str]]:
    """Each word (lower case; as captions write it, by `written`) -> how
    often the treebanks use it as each part of speech ("ADP": 140): a word
    counts under its lemma, and under its form where that differs. By its
    form alone, a verb counted only its infinitive, which news uses as a
    noun: Spanish's poder showed "power" before "to be able to". Multiword
    tokens' lines ("1-2", Spanish's "del") and empty nodes ("8.1") are
    skipped: their words have lines of their own. A treebank without
    lemmas (Thai's: "_") counts forms. `forms_only`: each word as written
    alone, not under its lemma - how a written form is used: Turkish's
    treebanks give a verb's stem as its lemma, so by lemma "de" ("too") was
    demek's (to say) 1,000 times over (polyglotic-hq 413)."""
    found: dict[str, Counter[str]] = defaultdict(Counter)
    for path in files:
        for sentence in sentences(path):
            names = {c[6] for c in sentence if joins_a_name(c)}
            for cols in sentence:
                said = {
                    unicodedata.normalize("NFC", col).lower()
                    for col in cols[1 : 2 if forms_only else 3]
                    if col != "_"
                }
                tag = tag_of(cols, cols[0] in names)
                for word in {written(w) for w in said} if written else said:
                    found[word][tag] += 1
    return dict(found)


def joins_a_name(cols: Sequence[str]) -> bool:
    """A word that makes its head a name of several words with it: joined
    by a flat relation ("Uniti" in "Stati Uniti"), or a capitalised
    adjective ("Romano" in "Impero Romano": Italian's "Impero" had opened on
    a river of that name, not "empire")."""
    relation = cols[7] if len(cols) > 7 else ""
    return relation.startswith("flat") or (relation == "amod" and cols[1][:1].isupper())


def sentences(path: Path) -> Iterator[list[list[str]]]:
    """A treebank file's sentences, each its words' lines split into
    columns; multiword tokens' lines ("1-2") and empty nodes ("8.1") left
    out."""
    sentence: list[list[str]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                if sentence:
                    yield sentence
                sentence = []
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 4 and cols[0].isdigit():
                sentence.append(cols)
    if sentence:
        yield sentence


AS_DETERMINER = frozenset({"det", "det:poss", "nmod:poss"})
"""The relations by which a word is attached to a noun as its determiner."""
IN_NAME = "PROPN:flat"
"""The tag `tag_of` gives a name's word in a name of several words."""
POSSESSIVE = "PRON:det"
"""The tag `tag_of` gives a pronoun attached as a determiner: Wiktionary's
determiner where the word has one, else its pronoun (`kaikki.resolved`)."""


def tag_of(cols: Sequence[str], heads_a_name: bool = False) -> str:
    """A treebank line's part of speech, its own tag but `IN_NAME` for a
    name's word in a name of several (joined by a flat relation, or
    `heads_a_name` of them: "Stati" in "Stati Uniti"), and `POSSESSIVE` for
    a pronoun attached to a noun as its determiner (`AS_DETERMINER`).
    Italian's "stati" is a name only in "Stati Uniti", never the surname
    Stati (`packs.name_frequency`).
    Treebanks tag possessives as pronouns - Italian's "mio" in "il mio
    libro" (det:poss), Swedish's "din" in "din bil" (nmod:poss) - which
    Wiktionary has as determiners ("my", "your") or as pronouns (Swedish's
    "min", "my"): Italian's "mio" had opened on "mine (used
    predicatively)", Swedish's "din" on ditt's "you (vocative ...)"
    (polyglotic-hq 416)."""
    relation = cols[7] if len(cols) > 7 else ""
    if cols[3] == "PROPN" and (heads_a_name or relation.startswith("flat")):
        return IN_NAME
    if cols[3] == "PRON" and relation in AS_DETERMINER:
        return POSSESSIVE
    return cols[3]


def lemmas(
    files: Iterable[Path], written: Callable[[str], str] | None = None
) -> dict[str, Counter[str]]:
    """Each word as written (lower case; as captions write it, by
    `written`) -> how often the treebanks name each lemma for it, written
    the same way: whether they take Arabic's "علي" for على ("on", 26
    times) or "لكن" for itself ("but") (`packs.lemma_used`)."""
    found: dict[str, Counter[str]] = defaultdict(Counter)
    for path in files:
        with path.open(encoding="utf-8") as f:
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 4 or not cols[0].isdigit() or cols[2] == "_":
                    continue
                form, lemma = (
                    unicodedata.normalize("NFC", col).lower() for col in cols[1:3]
                )
                if written:
                    form, lemma = written(form), written(lemma)
                found[form][lemma] += 1
    return dict(found)


def lemmas_for(
    language: str,
    paths: Mapping[str, Path],
    written: Callable[[str], str] | None = None,
) -> dict[str, Counter[str]] | None:
    """`lemmas` from `language`'s treebanks in `paths`, or None if it has
    none there."""
    files = [paths[s.name] for s in of(language) if s.name in paths]
    return lemmas(files, written) if files else None


def uses_for(
    language: str,
    paths: Mapping[str, Path],
    written: Callable[[str], str] | None = None,
    forms_only: bool = False,
) -> dict[str, Counter[str]] | None:
    """`uses` from `language`'s treebanks in `paths`, or None if it has
    none there (a test's sources, a language without a treebank)."""
    files = [paths[s.name] for s in of(language) if s.name in paths]
    return uses(files, written, forms_only) if files else None
