"""The order of an English word's Chinese meanings (polyglotic-hq 463):
the everyday meaning first in `ecdict.sqlite`.

ECDICT lists a word's meanings a part of speech a line ("n. 罐头, 容器",
"aux. 能, 可以") in an order of its own, often the noun first: "can"
opened on 装罐 ("to can", as in tins), "will" on 意志 ("willpower"), "may"
on 五月 ("May"), "well" on 井 ("a water well"). The card shows the first
three lines, and a saved word and its Anki card keep them.

For the `TOP` commonest entries, two steps:
1. **The commoner part of speech first:** the lines are sorted by how
   often English text uses the word as that part of speech, counted in a
   treebank (`treebanks`, UD English-EWT, as `english_meanings` does) -
   a stable sort, so ECDICT's order stands between lines of the same
   part of speech, and a line without one ("[计] 与") goes after those
   with a count.
2. **Our own first lines** (`ecdict_first.txt`), read by a person, where
   the count still gets it wrong: "have" is an auxiliary about as often
   as a verb in the treebank, but 有 is what a learner needs first; "kid"
   opened on 小山羊 (a young goat). Each listed line goes
   first, in the order listed: a bare part of speech ("vt.") moves
   ECDICT's line with that label; a line with text of its own replaces
   ECDICT's line with that label, or is added if there's none.

Only the order changes, and only these words: ECDICT's text is kept but
for the lines `ecdict_first.txt` writes. The English meanings
(`ecdict-en.sqlite`) are `english_meanings`' and don't use this.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

FIRST = Path(__file__).parent / "ecdict_first.txt"
TOP = 600
"""The entries reordered: those ranked this common or more (the ranks
`ecdict.sqlite` carries). Each was read by a person (polyglotic-hq 463);
raise it only after reading the next ones. 600, not 500: the 500
commonest words of wordfreq's list open entries ranked up to 596."""
LABEL_TAGS: Mapping[str, tuple[str, ...]] = {
    "n.": ("NOUN",),
    "pl.": ("NOUN",),
    "v.": ("VERB", "AUX"),
    "vt.": ("VERB",),
    "vi.": ("VERB",),
    "aux.": ("AUX",),
    "a.": ("ADJ", "DET"),  # ECDICT's "a." covers determiners: "a. 这" for this
    "adj.": ("ADJ", "DET"),
    "adv.": ("ADV",),
    "prep.": ("ADP",),
    "conj.": ("CCONJ", "SCONJ"),
    "pron.": ("PRON",),
    "art.": ("DET",),
    "num.": ("NUM",),
    "interj.": ("INTJ",),
    "int.": ("INTJ",),
}
"""ECDICT's part-of-speech labels, as the treebank's tags they count. Not
PROPN: a name's uses ("IN", Indiana) aren't the lower-case word's."""
MIN_SHARE = 0.05
"""The least share of a word's uses a part of speech needs to count:
"in" is a noun 9 times in 3,838, which had put its "n. 执政者, 交情"
above "a. 在里面的"."""
_LABEL = re.compile(r"([a-z]+\.)(?:\s|$)")

First = Mapping[str, Sequence[str]]
"""Word -> its first lines (`read_first`)."""


def label(line: str) -> str:
    """A meaning line's part-of-speech label ("vt." of "vt. 装罐"), or ""."""
    found = _LABEL.match(line)
    return found.group(1) if found else ""


def read_first(path: Path = FIRST) -> dict[str, list[str]]:
    """`ecdict_first.txt`: "word | line", one line a line, in the order the
    card shows them; "#" lines are notes."""
    out: dict[str, list[str]] = {}
    for text in path.read_text(encoding="utf-8").splitlines():
        if not text.strip() or text.startswith("#"):
            continue
        word, line = (part.strip() for part in text.split("|", 1))
        out.setdefault(word, []).append(line)
    return out


def by_use(meanings: Sequence[str], uses: Mapping[str, int] | None) -> list[str]:
    """`meanings` with the parts of speech the treebank uses the word as
    most first (`uses`: tag -> count; under `MIN_SHARE` counts as none).
    Stable: lines without a count, or of one part of speech, keep ECDICT's
    order."""

    total = sum((uses or {}).values())

    def used(line: str) -> int:
        n = sum((uses or {}).get(tag, 0) for tag in LABEL_TAGS.get(label(line), ()))
        return n if n >= MIN_SHARE * total else 0

    return sorted(meanings, key=lambda line: -used(line))


def with_first(word: str, meanings: Sequence[str], first: Sequence[str]) -> list[str]:
    """`meanings` with `first` before the rest (`read_first`'s lines: a
    bare label moves ECDICT's line, a line of our own replaces it).
    Raises ValueError if a bare label names a line `word` hasn't got: an
    ECDICT update moved it, and the line needs reading again."""
    rest = list(meanings)
    out = []
    for line in first:
        wanted = label(line)
        at = next((n for n, m in enumerate(rest) if label(m) == wanted), None)
        if line == wanted:
            if at is None:
                raise ValueError(f"{word}: ECDICT has no {wanted!r} line")
            out.append(rest.pop(at))
        else:
            if at is not None and wanted:
                del rest[at]
            out.append(line)
    return out + rest


def ordered(
    word: str,
    meanings: Sequence[str],
    rank: int | None,
    uses: Mapping[str, Mapping[str, int]],
    first: First,
) -> tuple[str, ...]:
    """`word`'s ECDICT meanings in the order the card shows them: by use
    if it ranks within `TOP`, then `first`'s lines first (at any rank)."""
    within = rank is not None and rank <= TOP
    lines = by_use(meanings, uses.get(word.lower())) if within else list(meanings)
    return tuple(with_first(word, lines, first.get(word, ())))
