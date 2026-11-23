"""Apply human-reviewed 746 drafts to exact senses in a pinned pack and build."""

import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_classes import SenseClasses, WordClass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(gloss: str) -> str:
    return unicodedata.normalize("NFC", gloss)


def apply_reviews(
    records: Sequence[EntryRecord],
    folder: Path | None,
    pack: str,
    language: str,
    gloss_language: str,
) -> tuple[Sequence[EntryRecord], dict[str, str], int]:
    """Read <pack>.json (draft-review.json after review) beside the frozen
    <pack>.sqlite. The reviewer supplies `reviewer` and `classes` and sets
    `human_reviewed`. Unreviewed rows and changed or ambiguous senses stay pending.
    """
    if folder is None:
        return records, {}, 0
    path = folder / f"{pack}.json"
    if not path.is_file():
        return records, {}, 0
    data = path.read_bytes()
    rows = [row for row in json.loads(data) if row.get("human_reviewed") is True]
    if not rows:
        return records, {}, 0
    frozen = folder / f"{pack}.sqlite"
    with frozen.open("rb") as file:
        fingerprint = hashlib.file_digest(file, "sha256").hexdigest()
    by_id = {record.entry_id: record for record in records}
    approved: dict[str, dict[int, list[SenseClasses]]] = defaultdict(
        lambda: defaultdict(list)
    )
    previous = SqliteDictionary(frozen)
    try:
        if (
            previous.info.get("language", language) != language
            or previous.info.get("meanings_language", gloss_language) != gloss_language
        ):
            raise ValueError(f"{pack}: reviewed against a different dictionary variant")
        for row in rows:
            if (
                row.get("language") != language
                or row.get("gloss_language") != gloss_language
                or row.get("pack_sha256") != fingerprint
                or not row.get("reviewer")
                or not row.get("source_ref")
                or not isinstance(row.get("classes"), list)
            ):
                raise ValueError(
                    f"{pack}: review lacks provenance or identifies a different pack"
                )
            entry_id = row["entry_id"]
            old = previous.record(entry_id)
            record = by_id.get(entry_id)
            ordinal = row["ordinal"]
            if (
                old is None
                or old.entry_id != entry_id
                or not 0 <= ordinal < len(old.meanings)
                or old.meanings[ordinal] != row["gloss"]
                or _sha(old.meanings[ordinal].encode("utf-8"))
                != row.get("gloss_sha256")
                or (old.headword, old.reading) != (row["headword"], row["reading"])
            ):
                raise ValueError(f"{pack}: review does not identify a frozen sense")
            if (
                record is None
                or (old.headword, old.traditional, old.reading)
                != (record.headword, record.traditional, record.reading)
                or row["gloss"].startswith("CL:")
            ):
                continue
            identity = _identity(row["gloss"])
            if sum(_identity(gloss) == identity for gloss in old.meanings) != 1:
                continue
            matches = [
                n
                for n, gloss in enumerate(record.meanings)
                if _identity(gloss) == identity
            ]
            if len(matches) == 1:
                labels = {WordClass(cls) for cls in row["classes"]}
                approved[entry_id][matches[0]].append(
                    tuple(cls for cls in WordClass if cls in labels)
                )
    finally:
        previous.close()

    verified = 0
    annotated = []
    for record in records:
        if record.entry_id in approved:
            classes = list(record.sense_classes or (None,) * len(record.meanings))
            for ordinal, candidates in approved[record.entry_id].items():
                if len(candidates) == 1 and classes[ordinal] is None:
                    classes[ordinal] = candidates[0]
                    verified += bool(candidates[0])
            record = replace(record, sense_classes=tuple(classes))
        annotated.append(record)
    provenance = {
        "sense_classes_review": f"sha256:{_sha(data)}; frozen pack sha256:{fingerprint}"
    }
    return annotated, provenance, verified
