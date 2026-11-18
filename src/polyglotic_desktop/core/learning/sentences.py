"""Saved sentences, and finding them again (polyglotic-hq 459; the user's
design, 2026-11-14; decision 0216).

A saved sentence is what the learner selected in captions or a transcript
- one clause or many, across lines, captions and speakers - kept with the
translation and the word links it had when it was saved, in a category
shared with saved words. It is kept in the learning data of the language
it was spoken in, on this PC only: like a saved word's line, none of its
text is sent anywhere.

- `SentencePart`: each clause the selection held - what was said (as much
  of it as was selected), its translation, the links between the two, and
  the speaker's label it showed under.
- `SavedSentence`: the parts in reading order, and the text of each side
  joined as the transcript joins clauses.
- `SentenceSearch`: the sentences found by a query - "most words matched
  in the text. characters matched for chinese or words matched in english"
  (the user, 2026-11-14) - over what was said and the translation
  together, best first; or by a saved word, or a category. A scan of text
  prepared once per sentence: a search takes about 7 ms (median; 13 ms at
  the 95th percentile) at 5,000 sentences (`tools/bench_sentences.py`).

Holds the learner's caption text: never log it.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from polyglotic_desktop.core.learning.saved_words import CategoryId, SavedWord

SentenceId = str


@dataclass(frozen=True, slots=True)
class SentenceLink:
    """Words of a part's original and of its translation that say the same
    thing: `[start, end)` in each, as the caption's word link had them.
    `key`: content words, not a minor link."""

    original: tuple[int, int]
    translation: tuple[int, int]
    key: bool = True


@dataclass(frozen=True, slots=True)
class SentencePart:
    """One clause of a saved sentence: `original` - the part of it that was
    selected, or all of it - its `translation` (the clause's whole, or ""
    for none), the `links` between them, and `speaker`: the label its
    caption showed ("You", an app's name; "" for none)."""

    original: str
    translation: str = ""
    links: tuple[SentenceLink, ...] = ()
    speaker: str = ""


@dataclass(frozen=True)
class SavedSentence:
    """A saved sentence: its parts, the text of each side joined
    (`original`, `translation`), the category, when it was saved, and the
    language the translation is in ("" for none)."""

    id: SentenceId
    original: str
    translation: str
    parts: tuple[SentencePart, ...]
    category_id: CategoryId
    saved_at: datetime
    translation_language: str = ""

    @property
    def speakers(self) -> tuple[str, ...]:
        """The speakers' labels, each once, in the order they speak."""
        return tuple(dict.fromkeys(p.speaker for p in self.parts if p.speaker))


# -- finding sentences ------------------------------------------------------------

_UNSPACED_CHARS = (
    ("\u2e80", "\u9fff"),  # CJK radicals, kana, Han
    ("\uac00", "\ud7af"),  # Hangul syllables: a character is a syllable
    ("\uf900", "\ufaff"),  # CJK compatibility ideographs
    ("\U00020000", "\U0003ffff"),  # Han extensions
)
"""Scripts whose characters each count as a word of a query (the user,
2026-11-14: "characters matched for chinese")."""
_UNSPACED_RUNS = (
    ("\u0e00", "\u0eff"),  # Thai, Lao
    ("\u1000", "\u109f"),  # Myanmar
    ("\u1780", "\u17ff"),  # Khmer
)
"""Scripts written without spaces whose characters are letters, not
words: a run of them in a query is one word, found anywhere in the text."""
_WORD = re.compile(
    "[\\w"
    "\u0300-\u036f\u0483-\u0489"  # combining accents; Cyrillic's
    "\u0591-\u05c7\u0610-\u061a\u064b-\u065f\u0670"  # Hebrew's, Arabic's
    "\u0900-\u0dff\u0e00-\u0eff\u0f00-\u0fff\u1000-\u109f\u1780-\u17ff"
    "\u3099\u309a"  # kana's voicing marks
    "]+"
)
"""A word's letters - and the marks a regular expression's word leaves
out, which some scripts write their vowels with (Thai, Hindi): a word
isn't cut at them."""
_CHARACTER = 1
_RUN = 2


def _kind(char: str) -> int:
    if any(low <= char <= high for low, high in _UNSPACED_CHARS):
        return _CHARACTER
    if any(low <= char <= high for low, high in _UNSPACED_RUNS):
        return _RUN
    return 0


def normalized(text: str) -> str:
    """`text` as it's compared: full-width forms as their usual ones, any
    case as lower case, and words separated by one space - punctuation
    gone."""
    return " ".join(_WORD.findall(unicodedata.normalize("NFKC", text).casefold()))


def query_words(query: str) -> list[str]:
    """What a query is matched by, each once: its words - each Chinese or
    Japanese character on its own, a run of Thai (or of another script
    written without spaces) whole."""
    found: dict[str, None] = {}
    for word in normalized(query).split():
        run = ""
        for char in word:
            if _kind(char) == _CHARACTER:
                if run:
                    found[run] = None
                    run = ""
                found[char] = None
            else:
                run += char
        if run:
            found[run] = None
    return list(found)


def _found(word: str, text: str) -> bool:
    """Whether `word` of a query is in `text` (`_Prepared.text`): a
    character, or a run of a script without spaces, anywhere; any other
    word at the start of one of its words ("learn" finds "learning", as
    the learner types)."""
    if _kind(word[0]):
        return word in text
    return f" {word}" in text


@dataclass(frozen=True, slots=True)
class Found:
    """A sentence found, with how many of the query's words it has, of how
    many."""

    sentence: SavedSentence
    matched: int
    of: int


@dataclass(slots=True)
class _Prepared:
    sentence: SavedSentence
    text: str
    """What was said and the translation, `normalized`, each after a space."""
    original: str
    """What was said, `normalized`, after a space."""


class SentenceSearch:
    """The saved sentences of one learning file, and searching them. Each
    sentence's text is prepared for search once, the first time one is
    searched for - not when they're read, so a learner who never searches
    never pays for it (about 13 microseconds a sentence)."""

    def __init__(self, sentences: Iterable[SavedSentence] = ()) -> None:
        self._all = {sentence.id: sentence for sentence in sentences}
        self._prepared: dict[SentenceId, _Prepared] | None = None

    def __len__(self) -> int:
        return len(self._all)

    def get(self, sentence_id: SentenceId) -> SavedSentence | None:
        return self._all.get(sentence_id)

    def sentences(self) -> list[SavedSentence]:
        """Every sentence, newest first."""
        return sorted(self._all.values(), key=lambda s: s.saved_at, reverse=True)

    def add(self, sentence: SavedSentence) -> None:
        """Adds or replaces it."""
        self._all[sentence.id] = sentence
        if self._prepared is not None:
            self._prepared[sentence.id] = _prepare(sentence)

    def remove(self, sentence_id: SentenceId) -> None:
        self._all.pop(sentence_id, None)
        if self._prepared is not None:
            self._prepared.pop(sentence_id, None)

    def search(
        self,
        query: str = "",
        category: CategoryId | None = None,
        word: SavedWord | None = None,
    ) -> list[Found]:
        """The sentences `query` finds, best first: those with at least half
        of its words (`query_words`) in what was said or the translation
        - the most of them first, then those with the query as it was
        typed, then the newest. No query: every sentence, newest first.
        `category`: only that category's; `word`: only those whose
        original has the saved word in it (`_has_word`)."""
        if self._prepared is None:
            self._prepared = {s.id: _prepare(s) for s in self._all.values()}
        words = query_words(query)
        phrase = normalized(query)
        needed = (len(words) + 1) // 2
        forms = _forms(word) if word is not None else ()
        found: list[tuple[int, bool, datetime, Found]] = []
        for each in self._prepared.values():
            sentence = each.sentence
            if category is not None and sentence.category_id != category:
                continue
            if forms and not _has_word(forms, each.original):
                continue
            text = each.text
            matched = 0
            for position, query_word in enumerate(words):
                if _found(query_word, text):
                    matched += 1
                elif len(words) - position - 1 + matched < needed:
                    break  # can't reach half any more
            if matched < needed:
                continue
            whole = bool(phrase) and _found(phrase, text)
            found.append(
                (
                    matched,
                    whole,
                    sentence.saved_at,
                    Found(sentence, matched, len(words)),
                )
            )
        found.sort(key=lambda f: (f[0], f[1], f[2]), reverse=True)
        return [f[3] for f in found]


def _prepare(sentence: SavedSentence) -> _Prepared:
    original = " " + normalized(sentence.original)
    return _Prepared(
        sentence, original + " " + normalized(sentence.translation), original
    )


def _forms(word: SavedWord) -> tuple[str, ...]:
    """A saved word's forms, `normalized`."""
    return tuple(dict.fromkeys(f for f in map(normalized, word.forms) if f))


def _has_word(forms: Sequence[str], original: str) -> bool:
    """Whether `original` (`_Prepared.original`) has one of a saved word's
    `forms`: a Chinese or Japanese form anywhere, as saved words are found
    in captions; any other as whole words (an inflected form isn't
    found)."""
    for form in forms:
        if _kind(form[0]) and form in original:
            return True
        if f" {form} " in f"{original} ":
            return True
    return False


def saved_words_in(
    sentence: SavedSentence, words: Iterable[SavedWord]
) -> list[SavedWord]:
    """The saved words in `sentence`'s original (`_has_word`)."""
    original = " " + normalized(sentence.original)
    return [w for w in words if _has_word(_forms(w), original)]
