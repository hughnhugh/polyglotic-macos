"""Reading CC-CEDICT's text format (https://cc-cedict.org/wiki/format:syntax).

One entry per line: `Traditional Simplified [pin1 yin1] /meaning/meaning/`.
Lines starting with `#` are comments; `#! date=...` gives the release.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tools.dictionaries.entry_ids import SourceEntry

LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\] /(.*)/\s*$")
_WORD = re.compile(r"[a-z]+")
_STOP = frozenset({"a", "an", "the", "to", "of", "and", "or", "sth", "sb", "cl"})

# Meaning similarity each match key needs before an entry carries an ID
# across a key change (decision 0007), in the order of `match_keys`.
THRESHOLDS = (0.0, 0.3, 0.3, 0.5)


@dataclass(frozen=True)
class CedictLine:
    traditional: str
    simplified: str
    pinyin: str  # numbered, as in the file: "dian4 nao3"
    meanings: tuple[str, ...]

    @property
    def key(self) -> str:
        """The entry's identity in CC-CEDICT, which has no IDs: its head."""
        return f"{self.traditional} {self.simplified} [{self.pinyin}]"

    def source_entry(self) -> SourceEntry:
        plain = self.pinyin.lower().replace("u:", "v")
        toneless = re.sub(r"[1-5]", "", plain).replace(" ", "")
        return SourceEntry(
            key=self.key,
            match_keys=(
                f"{self.traditional}|{self.simplified}|{toneless}",  # tones, case
                f"s|{self.simplified}|{plain}",  # traditional corrected
                f"t|{self.traditional}|{plain}",  # simplified corrected
                f"c|{self.traditional}|{self.simplified}",  # same characters
            ),
            meaning_words=meaning_words(self.meanings),
        )


def meaning_words(meanings: Iterable[str]) -> frozenset[str]:
    words: set[str] = set()
    for meaning in meanings:
        if not meaning.startswith("CL:"):
            words.update(_WORD.findall(meaning.lower()))
    return frozenset(words - _STOP)


def parse(lines: Iterable[str]) -> Iterator[CedictLine]:
    """Every entry, with whitespace in its pinyin made single spaces. A key
    that appears twice (CC-CEDICT has none as of 2026-09-27) is one entry
    with both lines' meanings."""
    seen: dict[str, CedictLine] = {}
    for line in lines:
        if line.startswith("#"):
            continue
        match = LINE.match(line)
        if not match:
            continue
        traditional, simplified, pinyin, meanings = match.groups()
        entry = CedictLine(
            traditional,
            simplified,
            " ".join(pinyin.split()),
            tuple(m for m in meanings.split("/") if m),
        )
        earlier = seen.get(entry.key)
        if earlier:
            entry = CedictLine(
                traditional,
                simplified,
                entry.pinyin,
                earlier.meanings + entry.meanings,
            )
        seen[entry.key] = entry
    yield from seen.values()


def read(path: Path) -> list[CedictLine]:
    """A release, from its `.txt.gz` (as MDBG publishes it) or `.txt`."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return list(parse(f))


def release_date(path: Path) -> str:
    """The `#! date=` line of a release, or "" if it has none."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            if line.startswith("#! date="):
                return line.removeprefix("#! date=").strip()
    return ""
