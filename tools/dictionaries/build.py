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
  `--english-frequency ecdict` from ECDICT's own columns);
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
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_dictionary import (
    FORMAT,
    RANKS,
    write_dictionary,
)
from polyglotic_desktop.core.lexicon import chinese
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.ports.dictionary import EntryRecord
from tools.dictionaries import cedict, ecdict, wordfreq_ranks
from tools.dictionaries.entry_ids import Registry, assign_ids
from tools.dictionaries.sources import (
    CEDICT,
    ECDICT,
    HSK30,
    JIEBA,
    MIT,
    SOURCES,
    WORDFREQ,
    Source,
    fetch,
)

REPO = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).parent / "registry"
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
    ids = assign_ids(registry, (row.word for row in kept))
    lemmas = ecdict.lemmas(rows, {row.word for row in kept})
    if frequency == "wordfreq":
        words = [row.word for row in kept]
        ranks = wordfreq_ranks.frequency_ranks(paths["wordfreq"], words, lemmas)
        used, licence = [ECDICT, WORDFREQ], "CC BY-SA 4.0"
    else:
        ranks = ecdict.frequency_ranks(kept)
        used, licence = [ECDICT], ECDICT.licence
    records = [
        EntryRecord(
            entry_id=ids[row.word],
            headword=row.word,
            traditional="",
            reading=row.phonetic,
            meanings=row.meanings,
            frequency_rank=ranks.get(row.word),
        )
        for row in kept
    ]
    write_dictionary(
        out,
        {
            **info(
                ECDICT,
                used,
                frequency=frequency,
                schemes="en-frequency",
                ranked=sum(1 for r in records if r.frequency_rank),
            ),
            "licence": licence,
        },
        records,
        {r.headword: [r.entry_id] for r in records},
        lemmas=lemmas,
        merged=registry.resolved_merges(),
    )
    return {
        "entries": len(records),
        "of ECDICT rows": len(rows),
        "ranked": len(ranks),
        "inflected forms": len(lemmas),
    }


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
        "  given IDs, frequency ranks added.",
        "",
    ]
    for source in SOURCES:
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
        else:
            cc_by_sa = "https://creativecommons.org/licenses/by-sa/4.0/"
            lines += [f"{source.notice}. Licensed under CC BY-SA 4.0: {cc_by_sa}", ""]
    return "\n".join(lines)


NEEDS = {
    "cedict": ("cedict", "jieba", "hsk30"),
    "ecdict": ("ecdict", "wordfreq"),
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
    for source in (s for s in SOURCES if s.name in needed):
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
