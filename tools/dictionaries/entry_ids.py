"""Stable entry IDs for dictionary entries (decision 0007).

An entry ID is the dictionary's name and ten characters of a hash of the
entry's key when it was first seen: `cedict:4k7q2m9x1c`. CC-CEDICT's key is
its entry's head line (`電腦 电脑 [dian4 nao3]`); ECDICT's is the word.

Most entries keep their key from one release to the next, so their ID needs
no record. A committed registry (`registry/<dictionary>.tsv`) records only
the exceptions:
- `id`: a key whose entry ID isn't its own hash - because its entry's key
  was corrected and it kept the old ID, or because its hash was taken;
- `merged`: an entry ID whose entry was merged into another, so statuses
  saved under it can follow.

`carry_forward` writes those records when a source's pinned version
changes, by comparing the old release with the new one.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Crockford's base32, lower case: digits and letters without i, l, o, u.
ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
HASH_LENGTH = 10  # characters: 50 bits
MAX_LENGTH = 64  # the most any entry ID may be, prefix included


def default_id(dictionary: str, key: str, salt: int = 0) -> str:
    """The entry ID an entry gets from its key: `cedict:4k7q2m9x1c`. A salt
    gives the next choice when the first is taken."""
    text = key if salt == 0 else f"{key}\x00{salt}"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    number = int.from_bytes(digest[:8], "big") >> (64 - 5 * HASH_LENGTH)
    chars = []
    for _ in range(HASH_LENGTH):
        chars.append(ALPHABET[number & 31])
        number >>= 5
    return f"{dictionary}:{''.join(reversed(chars))}"


@dataclass
class Registry:
    """The exceptions to `default_id` for one dictionary."""

    dictionary: str
    ids: dict[str, str] = field(default_factory=dict)  # key -> entry ID
    merged: dict[str, str] = field(default_factory=dict)  # old ID -> entry ID
    notes: dict[str, str] = field(default_factory=dict)  # key or old ID -> why

    HEADER = (
        "# Entry IDs that aren't their key's hash (decision 0007). Written by\n"
        "# `python -m tools.dictionaries.update_ids`; edit by hand only to fix\n"
        "# a wrong match. Columns, tab-separated:\n"
        "#   id      <key>     <entry ID>  <note>  this key has this ID\n"
        "#   merged  <old ID>  <entry ID>  <note>  that entry became this one\n"
    )

    @classmethod
    def load(cls, path: Path, dictionary: str) -> Registry:
        registry = cls(dictionary)
        if not path.exists():
            return registry
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 4 or parts[0] not in ("id", "merged"):
                raise ValueError(f"{path}:{number + 1}: not a registry line")
            kind, source, entry_id, note = parts
            table = registry.ids if kind == "id" else registry.merged
            table[source] = entry_id
            if note:
                registry.notes[source] = note
        return registry

    def save(self, path: Path) -> None:
        lines = [self.HEADER]
        for kind, table in (("id", self.ids), ("merged", self.merged)):
            for source in sorted(table):
                note = self.notes.get(source, "")
                lines.append(f"{kind}\t{source}\t{table[source]}\t{note}\n")
        path.write_text("".join(lines), encoding="utf-8", newline="\n")

    def resolved_merges(self) -> dict[str, str]:
        """Each merged ID -> the entry ID it ends at, through any chain of
        merges."""
        out = {}
        for old in self.merged:
            seen, target = {old}, self.merged[old]
            while target in self.merged:
                if target in seen:
                    raise ValueError(f"merges loop through {target}")
                seen.add(target)
                target = self.merged[target]
            out[old] = target
        return out


def assign_ids(registry: Registry, keys: Iterable[str]) -> dict[str, str]:
    """Every key's entry ID. Recorded IDs first; then each other key, in
    sorted order, gets its hash - or, if that's taken, the next salted one,
    which is recorded so it never moves."""
    keys = sorted(set(keys))
    ids = {key: registry.ids[key] for key in keys if key in registry.ids}
    taken = set(registry.ids.values()) | set(registry.merged)
    for key in keys:
        if key in ids:
            continue
        salt = 0
        entry_id = default_id(registry.dictionary, key)
        while entry_id in taken:
            salt += 1
            entry_id = default_id(registry.dictionary, key, salt)
        if salt:
            registry.ids[key] = entry_id
            registry.notes[key] = f"hash taken; salt {salt}"
        ids[key] = entry_id
        taken.add(entry_id)
    duplicates = len(ids) - len(set(ids.values()))
    if duplicates:
        raise ValueError(f"{duplicates} entry IDs given to more than one key")
    return ids


# -- carrying IDs forward to a new release ------------------------------------


@dataclass(frozen=True)
class SourceEntry:
    """What carry-forward compares between two releases of a dictionary.

    `match_keys` are what can stay the same when an entry's key is
    corrected, strongest first (for CC-CEDICT: the same characters and
    syllables without tones; ...; the same simplified form). `meaning_words`
    are the words of its meanings, for telling apart entries that match.
    """

    key: str
    match_keys: tuple[str, ...]
    meaning_words: frozenset[str]


@dataclass
class Changes:
    """What changed between two releases, by key."""

    carried: list[tuple[str, str]] = field(default_factory=list)  # old, new key
    merged: list[tuple[str, str]] = field(default_factory=list)  # old, into key
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    unchanged: int = 0


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """How alike two entries' meanings are: shared words over all words."""
    return len(a & b) / len(a | b) if a or b else 1.0


def carry_forward(
    registry: Registry,
    old: Sequence[SourceEntry],
    new: Sequence[SourceEntry],
    thresholds: Sequence[float],
    note: str,
    merge_threshold: float = 0.5,
) -> Changes:
    """Updates `registry` so entries of the `new` release keep the IDs they
    had in the `old` one. `thresholds[i]` is the meaning similarity a match
    on `match_keys[i]` needs. The rules (decision 0007):

    - Same key: same ID; nothing recorded.
    - Changed: a key only in the old release and one only in the new that
      share a match key (and are alike enough) - the new key keeps the old
      ID. The strongest match key, then the most alike meanings, win; each
      key matches at most once. If one entry became two (a split), the
      likelier one keeps the ID and the other is new.
    - Merged: an old key left over that matches a key in the new release
      with similarity of at least `merge_threshold` - its ID is recorded as
      merged into that entry's.
    - Removed: any other old key. Nothing new is recorded: if the same key
      comes back, so does its ID.
    - Added: any other new key - its hash, or a salted one if taken.
    """
    old_ids = assign_ids(registry, (e.key for e in old))
    old_keys = {e.key for e in old}
    new_keys = {e.key for e in new}
    changes = Changes(unchanged=len(old_keys & new_keys))
    gone = [e for e in old if e.key not in new_keys]
    arrived = [e for e in new if e.key not in old_keys]

    def index(
        entries: Iterable[SourceEntry],
    ) -> dict[tuple[int, str], list[SourceEntry]]:
        by: dict[tuple[int, str], list[SourceEntry]] = defaultdict(list)
        for e in entries:
            for level, match_key in enumerate(e.match_keys):
                by[level, match_key].append(e)
        return by

    arrived_by = index(arrived)
    pairs = []
    for e in gone:
        for level, match_key in enumerate(e.match_keys):
            for candidate in arrived_by.get((level, match_key), ()):
                alike = similarity(e.meaning_words, candidate.meaning_words)
                if alike >= thresholds[level]:
                    pairs.append((-level, alike, e.key, candidate.key))
    pairs.sort(key=lambda p: (p[0], p[1], p[2], p[3]), reverse=True)
    matched_old: dict[str, str] = {}
    matched_new: set[str] = set()
    for _, _, old_key, new_key in pairs:
        if old_key in matched_old or new_key in matched_new:
            continue
        matched_old[old_key] = new_key
        matched_new.add(new_key)

    for old_key, new_key in sorted(matched_old.items()):
        registry.ids.pop(old_key, None)
        registry.notes.pop(old_key, None)
        registry.ids[new_key] = old_ids[old_key]
        registry.notes[new_key] = f"{note}: was {old_key}"
        changes.carried.append((old_key, new_key))

    new_by = index(new)
    merges: dict[str, str] = {}
    for e in gone:
        if e.key in matched_old:
            continue
        best: tuple[float, int, str] | None = None
        for level, match_key in enumerate(e.match_keys):
            for candidate in new_by.get((level, match_key), ()):
                alike = similarity(e.meaning_words, candidate.meaning_words)
                if alike >= merge_threshold:
                    choice = (alike, -level, candidate.key)
                    best = choice if best is None or choice > best else best
        if best is None:
            changes.removed.append(e.key)
        else:
            merges[e.key] = best[2]
    changes.added = sorted(e.key for e in arrived if e.key not in matched_new)

    new_ids = assign_ids(registry, new_keys)
    for old_key, into_key in sorted(merges.items()):
        registry.ids.pop(old_key, None)
        registry.notes.pop(old_key, None)
        registry.merged[old_ids[old_key]] = new_ids[into_key]
        registry.notes[old_ids[old_key]] = f"{note}: {old_key} into {into_key}"
        changes.merged.append((old_key, into_key))
    # A removed key's record stays: its ID stays taken, and comes back with it.
    changes.removed.sort()
    registry.resolved_merges()  # fails on a loop
    return changes
