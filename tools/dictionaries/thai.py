"""Thai's own rules for its pack (polyglotic-hq 389; decision 0173).

- **Which words:** Wiktionary's Thai words, not its letters' own entries
  (ก, "the first letter"), symbols or affixes (the prefix "อ"): as
  headwords they would let the word split (`core.lexicon.thai`) find a
  "word" in any letter. Words written with a space are phrases and
  proverbs, as for every language but Vietnamese.
- **Forms:** Thai doesn't inflect. A Thai entry's `forms` list other
  spellings (ไท for ไทย), its romanization, and two kinds of other words:
  the noun's classifier (ตัว for หมา) and an adjective's or verb's
  abstract noun (ความดี for ดี). Those two are words of their own, never
  forms of this one (`own_forms`); other spellings are forms of their own,
  so the word split finds them (as Vietnamese's are).
- **Counting words:** wordfreq has no Thai, and the Thai National Corpus's
  counts can't be shipped (389: Chulalongkorn University keeps its rights;
  PyThaiNLP's CC0 covers only what PyThaiNLP made). So the pack counts its
  own words in Common Voice's Thai sentences (CC0), cut by the app's own
  word split (`counted_words`), as Vietnamese counts its subtitles.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Iterator, Mapping
from pathlib import Path

from polyglotic_desktop.core.lexicon.thai import (
    WORD,
    has_thai,
    prefixes,
    spellings,
    split,
    word_cost,
    written,
)
from tools.dictionaries.frequency import Frequencies

NOT_A_WORD = frozenset(
    {"character", "symbol", "punct", "prefix", "suffix", "infix", "romanization"}
)
"""Wiktionary's Thai parts of speech that are no word of a caption."""
OTHER_WORDS = frozenset({"classifier", "abstract-noun"})
"""Tags of a Thai entry's `forms` that name another word, not a form."""


def own_forms(obj: Mapping[str, object]) -> dict[str, object]:
    """`obj` (a kaikki line) without the forms that are other words
    (`OTHER_WORDS`)."""
    forms = obj.get("forms")
    if not isinstance(forms, list):
        return dict(obj)
    kept = [
        f
        for f in forms
        if not (isinstance(f, dict) and OTHER_WORDS & set(f.get("tags") or ()))
    ]
    return {**obj, "forms": kept}


def words(objects: Iterable[dict[str, object]]) -> Iterator[dict[str, object]]:
    """The kaikki lines that are Thai words (`NOT_A_WORD`), with their own
    forms only."""
    for obj in objects:
        word = str(obj.get("word") or "")
        if obj.get("pos") not in NOT_A_WORD and has_thai(word):
            yield own_forms(obj)


ONE_LETTER_WORDS = frozenset({"ณ"})
"""The one word of a single letter a caption writes (ณ, "at"). Wiktionary's
others are archaic (ธ, บ, ฤ), an ordinal (ฉ), or texting's spellings (จ
for จะ, ก for ก็, ผ for ผ่าน): as written forms they let the word split
take any lone consonant - in a name it hasn't got - for a word, and
counting had made ค (an interjection) the 86th word."""


def caption_word(form: str) -> bool:
    """Whether a written form is one a caption's words are found by: not
    a lone letter (`ONE_LETTER_WORDS`)."""
    return len(form) > 1 or form in ONE_LETTER_WORDS


def counted_words(corpus: Path, forms: Collection[str]) -> Frequencies:
    """Each written form's share of the words in `corpus` (a sentence per
    line), the lines cut by the app's word split over `forms` - twice: the
    first count gives the second its ranks, as the app's split has them.
    Only the forms are counted: a piece they don't cover gives no word a
    count (a lone ค in a name isn't the interjection)."""
    own = frozenset(f for f in forms if has_thai(f))
    known = frozenset(s for f in own for s in spellings(f))
    starts = prefixes(known)
    lines = corpus.read_text(encoding="utf-8", errors="replace").splitlines()
    cost: dict[str, float] = {}
    counts: Counter[str] = Counter()
    for _ in range(2):
        counts = Counter()
        for line in lines:
            for word in split(line, known, starts, cost, WORD + 10):
                said = written(line[word.start : word.end])
                if said in own:
                    counts[said] += 1
        ranked = [w for w, _ in counts.most_common()]
        cost = {
            s: word_cost(n, len(ranked))
            for n, w in enumerate(ranked, 1)
            for s in spellings(w)
        }
    total = sum(counts.values()) or 1
    return Frequencies(((w, n / total) for w, n in counts.items()), hyphenated=True)
