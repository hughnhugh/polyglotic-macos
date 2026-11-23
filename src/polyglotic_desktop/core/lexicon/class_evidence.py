"""Dictionary evidence for exact units in the text of a caption row."""

from collections.abc import Collection, Iterable

from polyglotic_desktop.core.lexicon import english
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.lexicon.scripts import fits, script_of
from polyglotic_desktop.ports.word_classes import (
    ClassSpan,
    WordClass,
    WordClassEvidence,
)


def complete(entries: Iterable[DictionaryEntry]) -> WordClassEvidence | None:
    allowed: set[WordClass] = set()
    outside = False
    reviewed = False
    for entry in entries:
        senses = [sense for sense in entry.senses if not sense.gloss.startswith("CL:")]
        if not senses:
            return None
        for sense in senses:
            if sense.classes is None:
                return None
            reviewed = True
            outside |= not sense.classes
            allowed.update(sense.classes)
    return WordClassEvidence(frozenset(allowed), outside) if reviewed else None


def for_spans(
    dictionary: BasicDictionary | ChineseDictionary | EnglishDictionary,
    text: str,
    language: str,
    spans: Collection[ClassSpan],
) -> dict[ClassSpan, WordClassEvidence]:
    if not spans or not dictionary.ready or not dictionary.has_sense_classes:
        return {}
    candidates = {
        (start, end): word
        for start, end in spans
        if 0 <= start < end <= len(text)
        and fits(word := text[start:end], language)
        and all(fits(char, language) for char in word if script_of(char) is not None)
        and not any(char.isspace() for char in word)
    }
    if not candidates:
        return {}
    if isinstance(dictionary, BasicDictionary):
        lookups = (
            (span, dictionary.class_entries(candidates[span], word))
            for word in dictionary.split(text)
            if (span := (word.start, word.end)) in candidates
        )
    elif isinstance(dictionary, EnglishDictionary):
        lookups = (
            (span, dictionary.class_entries(candidates[span]))
            for span in english.words(text)
            if span in candidates
        )
    else:
        lookups = (
            (span, dictionary.lookup(candidates[span]))
            for span in dictionary.split(text)
            if span in candidates
        )
    return {
        span: evidence for span, entries in lookups if (evidence := complete(entries))
    }
