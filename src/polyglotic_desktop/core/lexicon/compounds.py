"""A word a pack hasn't got, looked up by its parts (polyglotic-hq 390), as
a Chinese word the dictionary hasn't got shows its words and characters.

Any spaced language joins words with a hyphen (Blog-Erfahrung, T-Rex,
franco-alemán); German also writes compounds closed up (Internetmaterialien
is Internet + Materialien), often with a linking letter or two between the
parts (Arbeitsplatz: Arbeit + s + Platz) or a word cut short in front
(Schulbus: Schule + Bus). On real German captions such words were links
with no word found under them (polyglotic-hq 380).

The parts are asked for only when the whole isn't found
(`core.lexicon.basic`): a word the pack has is never cut. A closed
compound is cut only where every part is a word the pack has (not a
name), into as few parts as will do, then the commonest; a hyphenated
word is cut at its hyphens, each piece looked up - and cut again where
the language closes compounds up.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from polyglotic_desktop.core.lexicon import korean_forms

LINKS: dict[str, tuple[str, ...]] = {"de": ("", "s", "es", "n", "en", "e", "er", "ens")}
"""The languages that write compounds closed up, and what may stand
between two parts (German's linking letters: Arbeit-s-platz,
Sonne-n-schein, Kind-er-garten); the part before is the word without them."""
CUT_SHORT: dict[str, tuple[str, ...]] = {"de": ("e", "en", "n")}
"""What a part may have lost at its end (Schul-bus: Schule; Wohn-zimmer:
wohnen; Wander-weg: wandern)."""
NOUNS_CAPITALISED = frozenset({"de"})
"""Languages whose nouns are written with a capital: a part inside a
compound, in lower case there, is a noun first ("zeit" is Zeit)."""
MIN_PART = 3
"""The fewest letters a closed compound's part has: Eis, Tag, Ort."""
MIN_CUT_SHORT = 4
"""The fewest letters a part cut short has as written (Schul, Grenz): on
FLEURS' German, "Bod" was cut as Boden and "nen" as nenn (polyglotic-hq
390)."""
MAX_PARTS = 4
PARTICIPLES: dict[str, re.Pattern[str]] = {"de": re.compile(r"(?<=en)d(?:e[mnrs]?)?$")}
"""A present participle's ending, after the infinitive (schreien-d-en):
such a word whose infinitive the pack has is no compound - "schreienden"
isn't Schrei + enden (polyglotic-hq 390)."""
UNRANKED = 1_000_000
"""The rank a part's entry without one is weighed at."""

Find = Callable[[str, bool], int | None]
"""Whether the pack has a form as written: (form, whether a hyphenated
word's piece - a name or a small word will do there) -> its commonest
entry's frequency rank (`UNRANKED` if it has none), or None if the pack
hasn't got it as a word that can be a part."""


@dataclass(frozen=True)
class Part:
    """One part of a word: `start` and `end` in the word (a linking letter
    is the part before's: "Arbeits" in Arbeitsplatz), and `form`, as the
    pack has it ("Arbeit"; "Materialien" for "materialien"; "Schule" for
    "Schul")."""

    start: int
    end: int
    form: str
    found: bool = True
    """False for a hyphenated word's piece the pack hasn't got: shown, as
    not in the dictionary, rather than left out."""


_Cut = tuple[int, float, tuple[Part, ...]]
"""A cut of a word's end: (how many parts, their mean log rank, the parts)."""


def parts(word: str, language: str, find: Find) -> list[Part]:
    """`word`'s parts, in order - [] if it has none the pack has."""
    if "-" in word.strip("-"):
        return _hyphenated(word, language, find)
    if language == "ko":
        return _korean(word, find)
    return _closed(word, language, find)


def _korean(word: str, find: Find) -> list[Part]:
    """A Korean word's parts (polyglotic-hq 516): Korean closes compounds up
    (국립공원, national park; 연구진, research team) and Wiktionary lists
    few. Its noun - the word without its particles, or the word - is cut
    into words of two syllables or more, then a one-syllable suffix or
    word read by hand (`korean_forms.COMPOUND_ENDS`: -성, -ness; 층, floor:
    바깥층) at its end, or a prefix (`korean_forms.COMPOUND_STARTS`: 대-) at its
    start - a prefix only where no cut without one will do; never into
    single syllables alone, any of which is some word (국, soup; 공, ball). Its particles are no parts: they are no words of a caption's
    own, as 학교에서's 에서 isn't. A word the pack has with its particles on
    (공원은) has no parts: its lookup finds it."""
    nouns = korean_forms.nouns(word)
    if any(find(noun, True) is not None for noun in nouns):
        return []
    for noun in [*nouns, word]:
        inside = _korean_noun(noun, find)
        if inside:
            return inside
    return []


def _korean_noun(noun: str, find: Find) -> list[Part]:
    """`noun` cut as `_korean` says - the fewest parts, then the commonest;
    [] if it can't be cut so."""
    best: dict[int, _Cut | None] = {len(noun): (0, 0.0, ())}

    def rest(start: int) -> _Cut | None:
        if start in best:
            return best[start]
        found: _Cut | None = None
        for end in range(start + 1, len(noun) + 1):
            if start == 0 and end == len(noun):
                continue  # the whole word is no part of itself
            text = noun[start:end]
            weighs = 1
            if len(text) > 1:
                form, rank = text, find(text, False)
            elif end == len(noun) and text in korean_forms.COMPOUND_ENDS:
                form = (
                    korean_forms.COMPOUND_ENDS[text] or text
                )  # -성 (-ness); 층 (floor)
                rank = find(form, False)
            elif start == 0 and text in korean_forms.COMPOUND_STARTS:
                # 대- (great): after any cut without a prefix
                form = korean_forms.COMPOUND_STARTS[text] or text
                rank, weighs = find(form, False), 2
            else:
                continue
            if rank is None:
                continue
            tail = rest(end)
            if tail is None or tail[0] + weighs > MAX_PARTS:
                continue
            count = tail[0] + weighs
            mean = (tail[1] * tail[0] + math.log(rank)) / count
            found = _better(found, (count, mean, (Part(start, end, form), *tail[2])))
        best[start] = found
        return found

    cut = rest(0)
    return list(cut[2]) if cut is not None and cut[0] > 1 else []


def spellings(text: str, language: str) -> tuple[str, ...]:
    """How a part written `text` may be in the pack, likeliest first: as
    written, in lower case, capitalised - a noun first where nouns are
    capitalised - and in each case with what it lost (`CUT_SHORT`)."""
    whole = (text, *(text + ending for ending in CUT_SHORT.get(language, ())))
    nouns = [w.capitalize() for w in whole] if language in NOUNS_CAPITALISED else []
    rest = [x for w in whole for x in (w, w.lower(), w.capitalize())]
    return tuple(dict.fromkeys([*nouns, *rest]))


def _first(
    text: str, language: str, find: Find, names_too: bool
) -> tuple[str, int] | None:
    """The first of `text`'s `spellings` the pack has, with its rank."""
    for form in spellings(text, language):
        if len(form) > len(text) and len(text) < MIN_CUT_SHORT:
            continue
        rank = find(form, names_too)
        if rank is not None:
            return form, rank
    return None


def _hyphenated(word: str, language: str, find: Find) -> list[Part]:
    out: list[Part] = []
    start = 0
    for piece in word.split("-"):
        end = start + len(piece)
        if piece:
            hit = _first(piece, language, find, names_too=True)
            if hit is not None:
                out.append(Part(start, end, hit[0]))
            else:
                inside = [_moved(p, start) for p in _closed(piece, language, find)]
                out += inside or [Part(start, end, piece, found=False)]
        start = end + 1
    return out if any(p.found for p in out) else []


def _moved(part: Part, offset: int) -> Part:
    """`part`, `offset` letters on (a piece's part, in the whole word)."""
    return Part(part.start + offset, part.end + offset, part.form, part.found)


def _closed(word: str, language: str, find: Find) -> list[Part]:
    """A closed compound's parts (`LINKS`): the fewest, then the commonest
    - the least mean log rank, which for Zipf's ranks is the greatest
    geometric mean of the parts' frequencies (Koehn and Knight's rule for
    German, 2003); [] if it can't be cut so."""
    links = LINKS.get(language)
    if links is None or len(word) < 2 * MIN_PART:
        return []
    participle = PARTICIPLES.get(language)
    ending = participle.search(word) if participle else None
    if ending and _first(word[: ending.start()], language, find, False):
        return []  # zurückkehrenden: zurückkehren's participle
    pieces: dict[tuple[int, int], tuple[str, int] | None] = {}
    best: dict[tuple[int, int], _Cut | None] = {}

    def piece(start: int, end: int) -> tuple[str, int] | None:
        if (start, end) not in pieces:
            pieces[(start, end)] = _first(word[start:end], language, find, False)
        return pieces[(start, end)]

    def rest(start: int, left: int) -> _Cut | None:
        """The best cut of word[start:] into at most `left` parts."""
        if (start, left) in best:
            return best[(start, left)]
        found: _Cut | None = None
        for end in range(start + MIN_PART, len(word) + 1):
            if start == 0 and end == len(word):
                continue  # the whole word is no part of itself
            hit = piece(start, end)
            if hit is None:
                continue
            form, rank = hit
            weight = math.log(rank)
            if end == len(word):
                found = _better(found, (1, weight, (Part(start, end, form),)))
                continue
            for link in links if left > 1 else ():
                after = end + len(link)
                if not word.startswith(link, end) or len(word) - after < MIN_PART:
                    continue
                tail = rest(after, left - 1)
                if tail is not None:
                    count = tail[0] + 1
                    mean = (tail[1] * tail[0] + weight) / count
                    found = _better(
                        found, (count, mean, (Part(start, after, form), *tail[2]))
                    )
        best[(start, left)] = found
        return found

    cut = rest(0, MAX_PARTS)
    return list(cut[2]) if cut is not None else []


def _better(current: _Cut | None, candidate: _Cut) -> _Cut:
    """Fewer parts, then the commoner; on a tie the one found first."""
    if current is None or candidate[:2] < current[:2]:
        return candidate
    return current
