"""Project pinned lexical labels onto the seven classes used by the app."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace

from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_classes import SenseClasses, WordClass

_WIKTIONARY = {
    "noun": "noun name",
    "verb": "verb aux auxiliary",
    "adjective": "adj adjective",
    "adverb": "adv adverb",
    "pronoun": "pron pronoun det determiner article",
    "particle": "prep preposition postp postposition adposition conj conjunction particle intj interjection",
    "number": "num numeral number classifier",
}
_ECDICT = {
    "noun": "n",
    "verb": "v vt vi aux",
    "adjective": "a adj",
    "adverb": "adv",
    "pronoun": "pron det art",
    "particle": "prep conj interj int",
    "number": "num",
}
_JMDICT = {
    "noun": "n n-adv n-pr n-t vs adj-no",
    "verb": "aux aux-v cop v-unspec vk vn vr vz vs-c vs-i vs-s",
    "adjective": "adj-i adj-ix adj-na adj-t adj-ku adj-nari adj-shiku aux-adj",
    "adverb": "adv adv-to n-adv",
    "pronoun": "pn adj-pn",
    "particle": "prt conj int",
    "number": "num ctr",
}


def _labels(groups: dict[str, str]) -> dict[str, WordClass]:
    return {tag: WordClass(cls) for cls, tags in groups.items() for tag in tags.split()}


_WIKT_LABELS = _labels(_WIKTIONARY)
_WIKT_LABELS["proper noun"] = WordClass.NOUN
_WIKT_OTHER = {
    "character",
    "symbol",
    "letter",
    "prefix",
    "suffix",
    "infix",
    "interfix",
    "circumfix",
    "affix",
}
_ECDICT_LABELS = _labels(_ECDICT)
_ECDICT_PREFIX = re.compile(r"^([a-z]+(?:[./][a-z]+)*\.)\s*(?=\S)")
_JM_LABELS = {
    tag: {WordClass(cls) for cls, group in _JMDICT.items() if tag in group.split()}
    for tags in _JMDICT.values()
    for tag in tags.split()
}


def wikt(pos: str) -> SenseClasses:
    cls = _WIKT_LABELS.get(pos)
    return (cls,) if cls else () if pos in _WIKT_OTHER else None


def legacy_wikt(
    meanings: Sequence[str], pos: str
) -> tuple[tuple[SenseClasses, ...], tuple[int, ...]]:
    """Only mark a prefix produced from this entry's pinned source POS."""
    prefix = f"({pos}) "
    cls = wikt(pos)
    if cls is None:
        return (), ()
    lengths = tuple(
        len(prefix) if gloss.startswith(prefix) else 0 for gloss in meanings
    )
    return tuple(cls if length else None for length in lengths), lengths


def jm(tags: Iterable[str]) -> SenseClasses:
    # vt and vi qualify the verb tag. An expression or a bound form needs
    # individual review even when it has another tag.
    classes: set[WordClass] = set()
    for tag in tags:
        if tag in {"vt", "vi"}:
            continue
        if tag.startswith(("v1", "v2", "v4", "v5")):
            classes.add(WordClass.VERB)
        elif matched := _JM_LABELS.get(tag):
            classes.update(matched)
        else:
            return None
    return tuple(cls for cls in WordClass if cls in classes) if classes else None


def english(record: EntryRecord, *, chinese_glosses: bool) -> EntryRecord:
    """ECDICT abbreviations and the formatter used for WordNet and editorial senses."""
    labels: list[SenseClasses] = []
    prefixes = []
    for gloss in record.meanings:
        classes: SenseClasses = None
        length = 0
        if chinese_glosses:
            match = _ECDICT_PREFIX.match(gloss)
            if match:
                tags = re.split(r"[./]", match[1][:-1])
                if all(tag in _ECDICT_LABELS for tag in tags):
                    found = {_ECDICT_LABELS[tag] for tag in tags}
                    classes = tuple(cls for cls in WordClass if cls in found)
                    length = match.end()
        elif gloss.startswith("("):
            pos, separator, body = gloss[1:].partition(") ")
            if separator and body and (classes := wikt(pos)) is not None:
                length = len(pos) + 3
        labels.append(classes)
        prefixes.append(length)
    return replace(record, sense_classes=tuple(labels), sense_prefixes=tuple(prefixes))


def coverage(records: Iterable[EntryRecord], verified: int = 0) -> dict[str, int]:
    counts = {
        "structured": 0,
        "verified": verified,
        "multi": 0,
        "reviewed_other": 0,
        "pending": 0,
        "notes": 0,
    }
    for record in records:
        classes = record.sense_classes or (None,) * len(record.meanings)
        for gloss, labels in zip(record.meanings, classes, strict=True):
            if gloss.startswith("CL:"):
                counts["notes"] += 1
            elif labels is None:
                counts["pending"] += 1
            elif not labels:
                counts["reviewed_other"] += 1
            else:
                counts["structured"] += 1
                counts["multi"] += len(labels) > 1
    counts["structured"] -= verified
    counts["senses"] = (
        counts["structured"] + verified + counts["reviewed_other"] + counts["pending"]
    )
    return counts
