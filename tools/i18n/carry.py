"""Carry translations across deliberate changes to their English source."""

import json
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from tools.i18n import extract, keep, ts

Key = tuple[str, str, str]


@dataclass(frozen=True)
class Change:
    old: Key
    new: Key
    retain_old: bool = False


@dataclass
class Counts:
    carried: int = 0
    kept: int = 0
    dropped: int = 0
    ambiguous: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.carried + self.kept + self.dropped + self.ambiguous


def read_map(path: Path) -> list[Change]:
    """Read the public ``{context: {old English: new English}}`` format."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("the map must be an object")
    changes: list[Change] = []
    for context, replacements in value.items():
        if not isinstance(context, str) or not isinstance(replacements, dict):
            raise TypeError("each context must contain an object of replacements")
        for old, new in replacements.items():
            if not isinstance(old, str) or not isinstance(new, str):
                raise TypeError("old and new English must be strings")
            changes.append(Change((context, old, ""), (context, new, "")))
    return changes


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    old_path: str
    hunks: list[tuple[range, range]] = field(default_factory=list)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=extract.REPO,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


def _changed_ranges(base: str) -> dict[str, FileDiff]:
    patch = _git(
        "-c",
        "core.quotePath=false",
        "diff",
        "--unified=0",
        "--find-renames",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        base,
        "--",
        extract.SOURCE.relative_to(extract.REPO).as_posix(),
    )
    files: dict[str, FileDiff] = {}
    old_path = ""
    file = None
    for line in patch.split("\n"):
        if line.startswith("diff --git "):
            old_path = ""
            file = None
        elif line.startswith("--- a/") and file is None:
            old_path = line[6:].removesuffix("\t")
        elif line.startswith("+++ b/") and file is None:
            new_path = line[6:].removesuffix("\t")
            file = files[new_path] = FileDiff(old_path)
        elif file is not None and (match := _HUNK.match(line)):
            old, old_count, new, new_count = match.groups()
            old_n, new_n = int(old_count or 1), int(new_count or 1)
            file.hunks.append(
                (range(int(old), int(old) + old_n), range(int(new), int(new) + new_n))
            )
    return files


def _base_messages(base: str, files: Iterable[str]) -> list[extract.Message]:
    return [
        message
        for file in files
        for message in extract.read_text(_git("show", f"{base}:{file}"), file).messages
    ]


def _touches(message: extract.Message, lines: range) -> bool:
    return bool(lines) and message.line < lines.stop and message.end_line >= lines.start


def _ordered(messages: Iterable[extract.Message]) -> list[extract.Message]:
    return sorted(messages, key=lambda message: (message.line, message.column))


def _same_placeholders(old: extract.Message, new: extract.Message) -> bool:
    return (
        old.numerus == new.numerus
        and sorted(keep.PLACEHOLDER.findall(old.source))
        == sorted(keep.PLACEHOLDER.findall(new.source))
        and keep.TAG.findall(old.source) == keep.TAG.findall(new.source)
    )


def _hunk_matches(
    before: list[extract.Message], after: list[extract.Message]
) -> Iterable[tuple[extract.Message, tuple[Key, ...]]]:
    old_contexts = {m.context for m in before}
    new_contexts = {m.context for m in after}
    shared = old_contexts & new_contexts
    groups = [
        ([m for m in before if m.context == c], [m for m in after if m.context == c])
        for c in sorted(shared)
    ]
    groups.append(
        (
            [m for m in before if m.context not in shared],
            [m for m in after if m.context not in shared],
        )
    )
    for old, new in groups:
        old_keys = {m.key for m in old}
        new_keys = {m.key for m in new}
        if old_keys == new_keys:
            continue
        if len(old) != len(new):
            # Unchanged messages can share a hunk with an insertion or removal.
            old = [m for m in old if m.key not in new_keys]
            new = [m for m in new if m.key not in old_keys]
        if len(old) == len(new) and (
            len(old) == 1
            or all(
                a.key == b.key or _same_placeholders(a, b)
                for a, b in zip(old, new, strict=True)
            )
        ):
            yield from (
                (b, (a.key,)) for a, b in zip(old, new, strict=True) if a.key != b.key
            )
        else:
            yield from ((b, ()) for b in new if b.key not in old_keys)


def _file_matches(
    before: list[extract.Message], after: list[extract.Message], diff: FileDiff
) -> Iterable[tuple[extract.Message, tuple[Key, ...]]]:
    # A multiline call may connect multiple hunks. Pair it just once.
    old_group: set[extract.Message] = set()
    new_group: set[extract.Message] = set()
    seen: set[extract.Message] = set()
    for old_lines, new_lines in diff.hunks:
        old = {m for m in before if _touches(m, old_lines)}
        new = {m for m in after if _touches(m, new_lines)}
        if not (old_group & old or new_group & new):
            yield from _hunk_matches(_ordered(old_group), _ordered(new_group))
            old_group, new_group = set(), set()
        old_group.update(old)
        new_group.update(new)
        seen.update(new)
    yield from _hunk_matches(_ordered(old_group), _ordered(new_group))

    # Editing a translation wrapper's context can change calls outside the hunks.
    old_keys = {m.key for m in before}
    for message in after:
        if message in seen or message.key in old_keys:
            continue
        offset = 0
        for old_lines, new_lines in diff.hunks:
            new_end = new_lines.stop if new_lines else new_lines.start + 1
            if new_end > message.line:
                break
            old_end = old_lines.stop if old_lines else old_lines.start + 1
            offset = old_end - new_end
        candidates = tuple(
            m.key
            for m in before
            if (m.line, m.column, m.source, m.comment)
            == (message.line + offset, message.column, message.source, message.comment)
        )
        yield message, candidates


def from_diff(base: str) -> tuple[list[Change], list[str]]:
    """Pair changed messages by context and source order within each hunk."""
    diffs = _changed_ranges(base)
    current_keys: set[Key] = set()
    targets: dict[Key, extract.Message] = {}
    candidates: dict[Key, set[Key]] = defaultdict(set)
    for path in extract.source_files(extract.SOURCE):
        new_path = path.relative_to(extract.REPO).as_posix()
        after = extract.read_file(path).messages
        current_keys.update(m.key for m in after)
        if (diff := diffs.get(new_path)) is None:
            continue
        before = _base_messages(base, (diff.old_path,)) if diff.old_path else []
        for message, sources in _file_matches(before, after, diff):
            targets.setdefault(message.key, message)
            candidates[message.key].update(sources)

    changes: list[Change] = []
    ambiguous: list[str] = []
    for key, message in targets.items():
        if len(candidates[key]) == 1:
            (old,) = candidates[key]
            changes.append(Change(old, key, retain_old=old in current_keys))
        else:
            ambiguous.append(
                f"{message.file}:{message.line}: no unique old source for "
                f"{message.context}: {message.source!r}"
            )
    return changes, ambiguous


def carry_file(
    path: Path, changes: list[Change], ambiguous: int, dry_run: bool
) -> Counts:
    file = ts.read(path)
    counts = Counts(ambiguous=ambiguous)
    original = file.translations.copy()
    carried_keys: dict[Key, Key] = {}
    destinations = {change.new for change in changes}
    obsolete: set[Key] = set()
    for change in changes:
        old_key = change.old
        translation = original.get(old_key)
        if translation is None and not old_key[2]:
            matches = [key for key in original if key[:2] == old_key[:2]]
            if len(matches) == 1:
                old_key = matches[0]
                translation = original[old_key]
        new_key = change.new
        if old_key != change.old and not new_key[2]:
            new_key = (new_key[0], new_key[1], old_key[2])
        existing = file.translations.get(new_key)
        label = f"{new_key[0]}: {new_key[1]!r}"
        if existing is not None and not existing.empty:
            if existing.done:
                counts.kept += 1
                counts.details.append(f"kept finished: {label}")
                continue
            # A retained source or a chain can still have text on a rerun.
            if (
                translation is None
                or translation.empty
                or translation.forms == existing.forms
                or (old_key in destinations and not translation.done)
            ):
                counts.kept += 1
                continue
        if translation is None or translation.empty:
            counts.dropped += 1
            counts.details.append(f"dropped {label}: no old translation")
            continue
        problem = keep.broken(new_key[1], translation.forms, file.language)
        if problem:
            counts.dropped += 1
            counts.details.append(f"dropped {label}: {problem}")
            continue
        file.translations[new_key] = ts.Translation(translation.forms, done=False)
        carried_keys[new_key] = old_key
        if not change.retain_old and old_key != new_key:
            obsolete.add(old_key)
        counts.carried += 1
    if not dry_run and counts.carried:
        # Leave old rows for `update` to trim.
        root_messages = _messages_in(path)
        messages = {m.key: m for m in root_messages}
        for key in obsolete - destinations - carried_keys.keys():
            file.translations.pop(key, None)
        for key, old in carried_keys.items():
            if key not in messages:
                root_messages.append(
                    replace(
                        messages[old],
                        context=key[0],
                        source=key[1],
                        comment=key[2],
                        numerus=bool(keep.COUNT.search(key[1])),
                    )
                )
        path.write_text(
            ts.write(path, file.language, root_messages, file), encoding="utf-8"
        )
    return counts


def _messages_in(path: Path) -> list[extract.Message]:
    """The messages already represented by a TS file, in its stable order."""
    import xml.etree.ElementTree as ET

    messages: list[extract.Message] = []
    for context in ET.parse(path).getroot().iter("context"):
        name = context.findtext("name") or ""
        for node in context.iter("message"):
            location = node.find("location")
            messages.append(
                extract.Message(
                    name,
                    node.findtext("source") or "",
                    node.findtext("comment") or "",
                    node.get("numerus") == "yes",
                    (
                        location.get("filename", "") if location is not None else ""
                    ).removeprefix("../"),
                    note=node.findtext("extracomment") or "",
                )
            )
    return messages


def run(
    folder: Path, changes: list[Change], ambiguous: list[str], dry_run: bool
) -> int:
    output = [f"ambiguous: {detail}" for detail in ambiguous]
    for path in sorted(folder.glob("polyglotic_*.ts")):
        if path.stem == "polyglotic_en":
            continue
        counts = carry_file(path, changes, len(ambiguous), dry_run)
        for detail in counts.details:
            output.append(f"{path.stem.removeprefix('polyglotic_')}: {detail}")
        output.append(
            f"{path.stem.removeprefix('polyglotic_')}: "
            f"carried {counts.carried}, kept {counts.kept}, dropped {counts.dropped}, "
            f"ambiguous {counts.ambiguous}, total {counts.total}"
        )
    encoding = sys.stdout.encoding or "utf-8"
    for line in output:
        # Windows redirects stdout using a legacy code page by default. Reporting
        # must not interrupt a completed carry just because English contains a
        # character (for example, ⌘) that code page cannot represent.
        print(line.encode(encoding, errors="backslashreplace").decode(encoding))
    return 1 if ambiguous else 0
