"""Reading Open English WordNet (https://en-word.net), the English
dictionary's English meanings (polyglotic-hq 447, decision 0211).

The release's WN-LMF file (`english-wordnet-<year>-plus.xml.gz`: the
"plus" edition has names and places too - London, David) lists each word
in each part of speech (`LexicalEntry`) with its senses in WordNet's order -
its commonest first, as Princeton numbered them from tagged text - and
each sense's meaning group (`Synset`) with its definition and examples.
Only the written form, part of speech, definition and examples are read.
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PARTS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}
"""WordNet's parts of speech, as a card names them (a satellite adjective,
"s", is an adjective)."""


@dataclass(frozen=True)
class Sense:
    """One sense of a word in one part of speech."""

    pos: str  # PARTS' values: "noun", "verb", "adjective", "adverb"
    definition: str
    examples: tuple[str, ...]


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def read(path: Path) -> dict[str, list[Sense]]:
    """Each written form (as WordNet writes it: "run", "New York") -> its
    senses, part of speech by part of speech in the file's order, each part
    of speech's senses in WordNet's order. A form WordNet gives only as
    another word's irregular form ("media" of medium, "children" of child) has
    that word's senses in that part of speech, after any of its own."""
    entries: list[tuple[str, str, list[str]]] = []  # form, pos, synset IDs
    irregular: list[tuple[str, str, list[str]]] = []
    synsets: dict[str, tuple[str, tuple[str, ...]]] = {}
    with gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb") as f:
        for _, element in ET.iterparse(f, events=("end",)):
            tag = _local(element.tag)
            if tag == "LexicalEntry":
                lemma = next(e for e in element if _local(e.tag) == "Lemma")
                senses = [
                    e.attrib["synset"] for e in element if _local(e.tag) == "Sense"
                ]
                pos = lemma.attrib["partOfSpeech"]
                entries.append((lemma.attrib["writtenForm"], pos, senses))
                irregular += [
                    (e.attrib["writtenForm"], pos, senses)
                    for e in element
                    if _local(e.tag) == "Form"
                ]
                element.clear()
            elif tag == "Synset":
                definition = next(
                    (e.text or "" for e in element if _local(e.tag) == "Definition"),
                    "",
                )
                examples = tuple(
                    e.text or "" for e in element if _local(e.tag) == "Example"
                )
                synsets[element.attrib["id"]] = (definition.strip(), examples)
                element.clear()
    out: dict[str, list[Sense]] = defaultdict(list)
    own = {form for form, _, _ in entries}
    for form, pos, ids in [
        *entries,
        *((f, pos, ids) for f, pos, ids in irregular if f not in own),
    ]:
        part = PARTS.get(pos)
        if part is None:
            continue
        for synset in ids:
            definition, examples = synsets.get(synset, ("", ()))
            if definition:
                out[form].append(Sense(part, definition, examples))
    return dict(out)


def senses_of(senses: Mapping[str, list[Sense]], word: str) -> list[Sense]:
    """`word`'s senses as written, else in lower case ("Internet" is
    "internet"), else capitalised (ECDICT has "david" and "york"; WordNet
    "David" and "York")."""
    for spelling in (word, word.lower(), word.capitalize()):
        if spelling in senses:
            return senses[spelling]
    return []
