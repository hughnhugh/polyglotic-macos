"""Build the dictionary files the app ships, from pinned sources.

    uv run python -m tools.dictionaries.build

Fetches each source at its pinned version (`sources.py`) into
`build/dictionary-sources/`, checks its checksum, and writes to
`build/dictionaries/` (with `--only cedict` or `--only ecdict`, that one
alone, from its own sources - CI's start gate builds only CC-CEDICT):
- `cedict.sqlite` - CC-CEDICT for Chinese learners, with jieba frequency
  ranks and HSK 3.0 levels (2025 syllabus and 2021 standard);
- `ecdict.sqlite` - ECDICT cut to the commonest words, for English
  learners, with inflections and frequency ranks (from wordfreq, or with
  `--english-frequency ecdict` from ECDICT's own columns), the commonest
  words' Chinese meanings everyday first (`ecdict_order`), and the
  10,000 commonest words respelled (KAY-oss: `respell`, CMUdict) as their
  form readings, for the reading line over English (polyglotic-hq 511);
- `ecdict-en.sqlite` - the same entries with their meanings in English
  (`english_meanings`: Open English WordNet and our own), for an English
  learner whose app isn't in Chinese (decision 0211);
- `CREDITS.md` - each source, its version, licence and what we changed.

The files are built, not committed: the release workflow (D5) runs this
and ships them (decision 0009). Entry IDs come from the registry
(decision 0007); if a new hash collision is salted, the registry changes
and the build says to commit it.
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_dictionary import (
    FORMAT,
    RANKS,
    write_dictionary,
)
from polyglotic_desktop.core.lexicon import chinese
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.ports.dictionary import EntryRecord
from tools.dictionaries import (
    cedict,
    ecdict,
    ecdict_order,
    english_meanings,
    oewn,
    respell,
    treebanks,
    wordfreq_ranks,
)
from tools.dictionaries.entry_ids import Registry, assign_ids
from tools.dictionaries.sources import (
    CEDICT,
    CMUDICT,
    ECDICT,
    HSK30,
    JIEBA,
    MIT,
    OEWN,
    SOURCES,
    WORDFREQ,
    WORDNET_LICENCE,
    Source,
    fetch,
)

REPO = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).parent / "registry"
TREEBANKS = treebanks.of("en")
"""UD English-EWT's files: how often English uses each word as each part
of speech, which orders its English meanings (`english_meanings`)."""
HSK_TABLES = {
    "hsk-2025": "hsk30/data/hsk2025_words.tsv",
    "hsk-2021": "hsk30/data/hsk30_words.tsv",
}


# -- Chinese ----------------------------------------------------------------------


def jieba_ranks(path: Path, words: set[str]) -> dict[str, int]:
    """Frequency ranks from jieba's counts (`word count tag` per line), for
    the words the dictionary has: 1 for the commonest."""
    counts: dict[str, int] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[0] in words and parts[1].isdigit():
                counts[parts[0]] = max(counts.get(parts[0], 0), int(parts[1]))
    ranked = sorted(counts, key=lambda w: (-counts[w], w))
    return {word: n for n, word in enumerate(ranked, start=1)}


def hsk_levels(wheel: Path) -> dict[str, dict[str, int]]:
    """scheme -> word -> level, from the hsk30 package's data files (read
    from the archive, never run). A word listed twice keeps its lowest
    level; 7 is "7-9"."""
    out: dict[str, dict[str, int]] = {}
    with zipfile.ZipFile(wheel) as archive:
        for scheme, member in HSK_TABLES.items():
            levels: dict[str, int] = {}
            lines = archive.read(member).decode("utf-8").splitlines()
            for line in lines[1:]:  # header: word, level
                word, level = line.split("\t")[:2]
                levels[word] = min(levels.get(word, 99), int(level))
            out[scheme] = levels
    return out


def attach_levels(
    entries: Sequence[DictionaryEntry], levels: Mapping[str, Mapping[str, int]]
) -> tuple[dict[str, list[tuple[str, int]]], dict[str, int]]:
    """Each HSK word's level goes on its entries with that simplified form -
    not on names or "variant of" entries, unless those are all there is.
    The lists give no pinyin, so every everyday reading of a word gets the
    word's level. Returns entry ID -> levels, and per scheme how many listed
    words the dictionary doesn't have."""
    by_word: dict[str, list[DictionaryEntry]] = defaultdict(list)
    for e in entries:
        by_word[e.headword].append(e)
    out: dict[str, list[tuple[str, int]]] = defaultdict(list)
    missing: dict[str, int] = {}
    for scheme, words in levels.items():
        missing[scheme] = 0
        for word, level in words.items():
            found = by_word.get(word, [])
            plain = [e for e in found if not e.is_name and not e.variant_only]
            for e in plain or found:
                out[e.entry_id].append((scheme, level))
            missing[scheme] += not found
    return out, missing


def build_chinese(
    paths: Mapping[str, Path], out: Path, registry: Registry
) -> dict[str, object]:
    lines = cedict.read(paths["cedict"])
    ids = assign_ids(registry, (line.key for line in lines))
    ranks = jieba_ranks(paths["jieba"], {line.simplified for line in lines})
    bare = [
        chinese.entry_from_record(
            EntryRecord(ids[x.key], x.simplified, x.traditional, x.pinyin, x.meanings)
        )
        for x in lines
    ]
    levels, missing = attach_levels(bare, hsk_levels(paths["hsk30"]))
    records = [
        EntryRecord(
            entry_id=ids[x.key],
            headword=x.simplified,
            traditional=x.traditional,
            reading=x.pinyin,
            meanings=x.meanings,
            frequency_rank=ranks.get(x.simplified),
            levels=tuple(sorted(levels.get(ids[x.key], ()))),
        )
        for x in lines
    ]
    entries = [chinese.entry_from_record(r) for r in records]
    uses = chinese.count_reading_uses(entries)
    by_form: dict[str, list[DictionaryEntry]] = defaultdict(list)
    for e in entries:
        for form in dict.fromkeys((e.headword, e.traditional)):
            by_form[form].append(e)
    forms = {
        form: [e.entry_id for e in chinese.everyday_first(form, found, uses)]
        for form, found in by_form.items()
    }
    meaning_words: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        for word in sorted(chinese.index_words(e)):
            meaning_words[word].append(e.entry_id)
    write_dictionary(
        out,
        info(
            CEDICT,
            [CEDICT, JIEBA, HSK30],
            frequency="jieba",
            schemes="hsk-2025 hsk-2021",
            ranked=sum(1 for r in records if r.frequency_rank),
        ),
        records,
        forms,
        meaning_words,
        merged=registry.resolved_merges(),
    )
    with_level = {s: sum(1 for r in records if s in dict(r.levels)) for s in HSK_TABLES}
    return {
        "entries": len(records),
        "ranked": sum(1 for r in records if r.frequency_rank),
        "names": sum(1 for e in entries if e.is_name),
        "entries with a level": with_level,
        "HSK words not in CC-CEDICT": missing,
    }


# -- English ----------------------------------------------------------------------


def build_english(
    paths: Mapping[str, Path],
    out: Path,
    registry: Registry,
    frequency: str = "wordfreq",
) -> dict[str, object]:
    """`frequency`: where English frequency ranks come from - "wordfreq"
    (preferred by project 019) or "ecdict" (ECDICT's own corpus columns).
    wordfreq's data is CC BY-SA, so the file is too when it's used."""
    rows = list(ecdict.read(paths["ecdict"]))
    kept = ecdict.cut(rows)
    given = given_names(kept)
    ids = assign_ids(registry, [*(row.word for row in kept), *given])
    lemmas = ecdict.lemmas(rows, {row.word for row in kept})
    written = ecdict.names(kept, lemmas)  # "mary": Mary (polyglotic-hq 464)
    lemmas, second = ecdict.own_first(lemmas)  # "bit": bit, then bite
    if frequency == "wordfreq":
        words = [row.word for row in kept]
        ranks = wordfreq_ranks.frequency_ranks(paths["wordfreq"], words, lemmas)
        used, licence = [ECDICT, WORDFREQ, CMUDICT, *TREEBANKS], "CC BY-SA 4.0"
        respelt = respellings(paths, lemmas)
    else:  # no respellings: their words are wordfreq's commonest
        ranks = ecdict.frequency_ranks(kept)
        used, licence = [ECDICT, *TREEBANKS], ECDICT.licence
        respelt = {}
    uses = treebanks.uses([paths[s.name] for s in TREEBANKS])
    first = ecdict_order.read_first()
    records = [
        EntryRecord(
            entry_id=ids[row.word],
            headword=written.get(row.word, row.word),
            traditional="",
            reading=row.phonetic,
            meanings=ecdict_order.ordered(
                row.word, row.meanings, ranks.get(row.word), uses, first
            ),
            frequency_rank=ranks.get(row.word),
        )
        for row in kept
    ]
    phonetic = {row.word: row.phonetic for row in kept}
    records += [
        EntryRecord(
            entry_id=ids[name.name],
            headword=name.name,
            traditional="",
            reading=phonetic.get(name.name.lower(), ""),
            meanings=(name.meaning,),
            frequency_rank=None,  # numbering them would move every rank after
        )
        for name in given.values()
    ]
    plain = lemmas
    lemmas = {form: written.get(lemma, lemma) for form, lemma in lemmas.items()}
    about = {
        **info(
            ECDICT,
            used,
            frequency=frequency,
            schemes="en-frequency",
            ranked=sum(1 for r in records if r.frequency_rank),
        ),
        "licence": licence,
    }
    forms = {r.headword: [r.entry_id] for r in records}
    for lower, word in ecdict.lower_case_forms({row.word for row in kept}).items():
        forms[lower] = [ids[word]]  # "tv": TV (polyglotic-hq 463)
    for form, lemma in second.items():
        forms[form].append(ids[lemma])
    for name in given.values():
        word = name.name.lower()
        forms[name.name] = [
            *(
                [*([ids[plain[word]]] if word in plain else []), ids[word]]
                if name.word_first and word in ids
                else []
            ),
            ids[name.name],
        ]
    merged = registry.resolved_merges()
    write_dictionary(
        out, about, records, forms, lemmas=lemmas, merged=merged, form_readings=respelt
    )
    names = {  # a name's first line in English: "a man's name"
        r.entry_id: "; ".join(kinds)
        for r in records
        if r.headword[:1].isupper() and (kinds := ecdict.name_kinds(r.meanings[0]))
    }
    english = english_records(paths, kept, rows, records, uses, names)
    write_dictionary(
        out.with_name(ENGLISH_MEANINGS),
        {
            **about,
            "sources": "; ".join(
                f"{s.name} {s.version} sha256:{s.sha256}" for s in [*used, OEWN]
            ),
            "licence": "CC BY-SA 4.0",
            "meanings": "en",
        },
        english,
        forms,
        lemmas=lemmas,
        merged=merged,
        form_readings=respelt,
    )
    return {
        "entries": len(records),
        "of ECDICT rows": len(rows),
        "ranked": len(ranks),
        "inflected forms": len(lemmas),
        "own entry first": len(second),
        "names ECDICT writes in lower case": len(written),
        "names of our own": len(given),
        "with English meanings": sum(1 for r in english if r.meanings),
        "respelled": len(respelt),
    }


def respellings(paths: Mapping[str, Path], lemmas: Mapping[str, str]) -> dict[str, str]:
    """How the commonest English words sound, respelled for learners - word
    to respelling, KAY-oss (`respell`, polyglotic-hq 471; DECISIONS #200):
    the English dictionary's form readings, read by the reading line over
    English (511). A heteronym's commoner sense only (record: REK-erd).

    And their inflected forms the 10,000 lack (`lemmas`: form to lemma,
    ECDICT's): passions, coordinating - a word past what the learner knows
    is often a common word's rarer form. CMUdict's first pronunciation; 511
    judged 38 of 40 sampled right, the two misses heteronyms' forms
    (transports), so a heteronym's forms are left out."""
    cmudict = respell.read_cmudict(paths["cmudict"].read_text(encoding="utf-8"))
    frequencies = wordfreq_ranks.frequencies(paths["wordfreq"])
    picks = respell.read_picks(respell.PICKS.read_text(encoding="utf-8"))
    rows = respell.table(respell.commonest(frequencies, RESPELLED), cmudict, picks)
    found = {row.word: row.respelling for row in rows}
    heteronyms = {row.word for row in rows if any("(" in a for a in row.alternates)}
    forms = sorted(
        form
        for form, lemma in lemmas.items()
        if lemma in found
        and lemma not in heteronyms
        and form not in found
        and respell.WORD.fullmatch(form)
    )
    found.update(
        (row.word, row.respelling) for row in respell.table(forms, cmudict, picks)
    )
    return found


RESPELLED = 10_000
"""How many of the commonest English words are respelled: the 10,000 471
picked pronunciations for and checked (99.5 % right, weighted by use) -
with their inflected forms (`respellings`)."""


ENGLISH_MEANINGS = "ecdict-en.sqlite"
"""The English dictionary with its meanings in English (decision 0211):
the same entries, IDs, inflections and ranks as `ecdict.sqlite`."""


def english_records(
    paths: Mapping[str, Path],
    kept: Sequence[ecdict.EcdictRow],
    rows: Sequence[ecdict.EcdictRow],
    records: Sequence[EntryRecord],
    uses: english_meanings.Uses,
    names: Mapping[str, str],
) -> list[EntryRecord]:
    """`records` (ECDICT's, in Chinese) with their meanings in English
    (`english_meanings`): Open English WordNet's, ordered by UD
    English-EWT's counts, and our own for the words WordNet lacks. An
    entry none of them has keeps no meanings: the card says so. A name's
    (`names`: entry ID -> "a man's name") comes first: WordNet's first
    "david" was the patron saint of Wales (polyglotic-hq 464)."""
    senses = oewn.read(paths["oewn"])
    core = english_meanings.read_core()
    forms = english_meanings.inflections(rows)
    by_id = {record.entry_id: row for record, row in zip(records, kept, strict=False)}
    out = []
    for record in records:
        row = by_id.get(record.entry_id)
        meanings = (
            english_meanings.meanings_of(row, senses, core, uses, forms)
            if row is not None
            else ()
        )
        if record.entry_id in names:
            meanings = (
                english_meanings.said("name", names[record.entry_id]),
                *meanings,
            )[: english_meanings.MAX_MEANINGS]
        out.append(replace(record, meanings=meanings))
    return out


def given_names(kept: Sequence[ecdict.EcdictRow]) -> dict[str, ecdict.GivenName]:
    """`english_names.txt`'s names by name. The build fails if ECDICT has
    one written so: it has its own entry now, so take it off the list."""
    words = {row.word for row in kept}
    given = {name.name: name for name in ecdict.read_names()}
    for name in given.values():
        if name.name in words:
            raise ValueError(f"english_names.txt: ECDICT has {name.name!r} now")
    return given


# -- both -----------------------------------------------------------------------------


def info(
    main: Source, used: Sequence[Source], frequency: str, schemes: str, ranked: int
) -> dict[str, str]:
    """A dictionary's `info`; `ranked`: how many entries have a frequency
    rank (what ranks mean: `RANKS`, decision 0120)."""
    return {
        "dictionary": main.name,
        "licence": main.licence,
        "sources": "; ".join(f"{s.name} {s.version} sha256:{s.sha256}" for s in used),
        "frequency_source": frequency,
        "ranks": RANKS,
        "ranked_entries": str(ranked),
        "level_schemes": schemes,
        "credits": "CREDITS.md, next to this file",
    }


def credits() -> str:
    lines = [
        "# Dictionary credits",
        "",
        "Polyglotic's dictionary files are built from these sources. They are",
        "plain SQLite files, separate from the app: you may open, copy and reuse",
        "them under the licences below.",
        "",
        "- `cedict.sqlite` is CC-CEDICT with word frequencies and HSK levels",
        "  added, and is shared under **CC BY-SA 4.0**",
        "  (https://creativecommons.org/licenses/by-sa/4.0/). Changes: converted",
        "  to SQLite; entries given IDs and ordered by everyday reading; jieba",
        "  frequency ranks and HSK 3.0 levels added; an index of English words.",
        "- `ecdict.sqlite` is ECDICT cut to its commonest words (ranked in its BNC",
        "  or modern-corpus columns, or on an exam list), with only the word, IPA,",
        "  Chinese meanings and inflections, plus frequency ranks from wordfreq.",
        "  ECDICT is MIT-licensed (below); with wordfreq's ranks the file is shared",
        "  under **CC BY-SA 4.0**. Changes: cut, converted to SQLite, entries",
        "  given IDs, frequency ranks added; the commonest words' meanings put in",
        "  everyday order, by how often UD English-EWT uses each word as each part",
        "  of speech (counts only) and Polyglotic's own first lines for some;",
        "  people's names written capitalised, and entries of Polyglotic's own",
        "  for given names ECDICT has only as other words (John, Bill).",
        "- `ecdict-en.sqlite` is `ecdict.sqlite` with English meanings in place",
        "  of the Chinese: Open English WordNet's definitions and examples",
        "  (CC BY 4.0; Princeton WordNet's licence below), shortened, their",
        "  parts of speech ordered by how often UD English-EWT uses each word as",
        "  each (counts only), and Polyglotic's own definitions of the commonest",
        "  words WordNet lacks (the, of, you...). It is shared under",
        "  **CC BY-SA 4.0**, as `ecdict.sqlite` is.",
        "- `ecdict-<language>.meanings`, downloaded beside them for an English",
        "  learner whose app is in that language, holds English words' meanings",
        "  in it: the words English Wiktionary's translation tables give for",
        "  each sense, and the definitions of that language's own Wiktionary,",
        "  as kaikki.org extracted them (wiktextract, Tatu Ylonen) on",
        "  2026-10-30 - Wiktionary's contributors (each page's history names",
        "  them), CC BY-SA 4.0 and GFDL. Changes: chosen per sense and ordered,",
        "  converted to SQLite by ECDICT's entry IDs. It is shared under",
        "  **CC BY-SA 4.0**.",
        "- Both English files carry respellings of the 10,000 commonest words",
        "  (KAY-oss), made by Polyglotic's own rules from CMUdict's American",
        "  pronunciations (its licence below), the usual one picked with",
        "  Wiktionary's help (CC BY-SA 4.0).",
        "",
    ]
    for source in (*SOURCES, *TREEBANKS):
        lines += [
            f"## {source.title}",
            "",
            f"- Used for: {source.used_for}",
            f"- Version: {source.version}",
            f"- From: {source.url}",
            f"- SHA-256: `{source.sha256}`",
            f"- Home: {source.homepage}",
            f"- Licence: {source.licence}",
            "",
        ]
        if source.licence == "MIT":
            lines += [f"{source.notice}", "", MIT, ""]
        elif source.name == CMUDICT.name:
            lines += [respell.CMUDICT_LICENCE, ""]
        elif source.name == OEWN.name:
            cc_by = "https://creativecommons.org/licenses/by/4.0/"
            lines += [f"{source.notice}. Licensed under CC BY 4.0: {cc_by}", ""]
            lines += [WORDNET_LICENCE, ""]
        else:
            cc_by_sa = "https://creativecommons.org/licenses/by-sa/4.0/"
            lines += [f"{source.notice}. Licensed under CC BY-SA 4.0: {cc_by_sa}", ""]
    return "\n".join(lines)


NEEDS = {
    "cedict": ("cedict", "jieba", "hsk30"),
    "ecdict": (
        "ecdict",
        "wordfreq",
        "oewn",
        "cmudict",
        *(source.name for source in TREEBANKS),
    ),
}
"""Each dictionary's sources, by name (`sources.py`)."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--sources", type=Path, default=REPO / "build" / "dictionary-sources"
    )
    parser.add_argument("--out", type=Path, default=REPO / "build" / "dictionaries")
    parser.add_argument(
        "--english-frequency",
        choices=["wordfreq", "ecdict"],
        default="wordfreq",
        help="where English frequency ranks come from (default: wordfreq)",
    )
    parser.add_argument(
        "--only",
        choices=sorted(NEEDS),
        default=None,
        help="build that dictionary alone, fetching only its sources",
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    names = (args.only,) if args.only else tuple(NEEDS)
    needed = {source for name in names for source in NEEDS[name]}
    paths = {}
    for source in (s for s in (*SOURCES, *TREEBANKS) if s.name in needed):
        started = time.perf_counter()
        paths[source.name] = fetch(source, args.sources)
        print(
            f"{source.name}: {source.version} ok ({time.perf_counter() - started:.1f}s)"
        )
    args.out.mkdir(parents=True, exist_ok=True)

    builds = {
        "cedict": build_chinese,
        "ecdict": lambda paths, out, registry: build_english(
            paths, out, registry, args.english_frequency
        ),
    }
    for name, build in ((name, builds[name]) for name in names):
        registry_path = REGISTRY / f"{name}.tsv"
        registry = Registry.load(registry_path, name)
        before = (dict(registry.ids), dict(registry.merged))
        started = time.perf_counter()
        out = args.out / f"{name}.sqlite"
        stats = build(paths, out, registry)
        took = time.perf_counter() - started
        print(
            f"{out.name}: {out.stat().st_size / 1e6:.1f}MB in {took:.1f}s, format {FORMAT}"
        )
        for key, value in stats.items():
            print(f"  {key}: {value}")
        if (registry.ids, registry.merged) != before:
            registry.save(registry_path)
            print(f"  ! {registry_path.name} changed (a hash was salted): commit it")
    (args.out / "CREDITS.md").write_text(credits(), encoding="utf-8", newline="\n")
    print(f"CREDITS.md written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
