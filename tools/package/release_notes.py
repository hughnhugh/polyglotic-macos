"""The release notes' one source: `RELEASE-NOTES.md` (polyglotic-hq RELEASING.md section 10, G7).

    python -m tools.package.release_notes v0.1.0 [--out notes.md]
    python -m tools.package.release_notes v0.1.5 --cut --date 2026-11-14 [--dry-run]

The first prints that version's notes as Markdown - the text the GitHub
Release carries above the SHA-256s (`release.yml`) and the update feed's
notes (`pack.sh`) - and exits 1 if the file has no section for it, or the
section has no lines. The second is the release's prep step: it moves
Unreleased's lines under `## 0.1.5 - 2026-11-14` (the date is Melbourne's
day, given, not guessed) and leaves Unreleased's three groups empty;
`--dry-run` prints what it would move and writes nothing. The file:

    ## Unreleased                 <- each pull request people would notice adds a line
    ### New / ### Better / ### Fixed

    ## 0.1.0 - 2026-11-11         <- at a release, Unreleased moves under its version
    One optional paragraph.
    ### New
    - A line, in plain words.

The groups are the site's (`content/releases.json`): New, Better and Fixed,
in that order; a version leaves out a group it has nothing for, and one
nobody would notice (0.1.1) has only its paragraph. Newest version first. A
line under a version never sits under Unreleased too: it shipped (321,
2026-11-14: Unreleased had kept 0.1.0-0.1.4's lines). Standard library only:
the release workflow runs it without installing the app.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

NOTES = Path(__file__).resolve().parents[2] / "RELEASE-NOTES.md"
GROUPS = ("New", "Better", "Fixed")
UNRELEASED = "Unreleased"
VERSION_HEADING = re.compile(
    r"^## (?P<version>(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))"
    r" - (?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})$"
)


@dataclass
class Section:
    """One `## ` section: Unreleased, or a version and its date."""

    title: str
    date: str = ""
    intro: list[str] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)

    def lines(self) -> int:
        return sum(len(items) for items in self.groups.values())

    def markdown(self) -> str:
        """The section's text, without its own heading: the intro, then each
        group that has lines."""
        out = [" ".join(self.intro)] if self.intro else []
        for name in GROUPS:
            if self.groups.get(name):
                out.append(
                    f"### {name}\n\n"
                    + "\n".join(f"- {line}" for line in self.groups[name])
                )
        return "\n\n".join(out) + "\n"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def parse(text: str) -> list[Section]:
    """Every `## ` section, in the file's order; ValueError for anything the
    format doesn't allow (an unknown heading or group, a version without its
    date, versions out of order, a line outside a group)."""
    sections: list[Section] = []
    group: list[str] | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        where = f"RELEASE-NOTES.md line {number}"
        if line.startswith("## "):
            if line == f"## {UNRELEASED}":
                sections.append(Section(UNRELEASED))
            elif heading := VERSION_HEADING.match(line):
                sections.append(Section(heading["version"], heading["date"]))
            else:
                raise ValueError(
                    f"{where}: a section is '## Unreleased' or '## X.Y.Z - YYYY-MM-DD'"
                )
            group = None
        elif not sections:
            continue  # the title and the file's own introduction
        elif line.startswith("### "):
            name = line[4:]
            if name not in GROUPS:
                raise ValueError(f"{where}: the groups are {', '.join(GROUPS)}")
            if name in sections[-1].groups:
                raise ValueError(f"{where}: {name} twice in one section")
            group = sections[-1].groups[name] = []
        elif line.startswith("- "):
            if group is None:
                raise ValueError(f"{where}: a line belongs in New, Better or Fixed")
            group.append(line[2:].strip())
        elif line.startswith("  ") and group:
            group[-1] += " " + line.strip()  # a line wrapped onto the next
        elif line and group is None:
            sections[-1].intro.append(line.strip())
        elif line:
            raise ValueError(f"{where}: inside a group, each line starts with '- '")
    versions = [s.title for s in sections if s.title != UNRELEASED]
    if len(set(versions)) != len(versions):
        raise ValueError("RELEASE-NOTES.md: a version has two sections")
    if versions != sorted(versions, key=_version_key, reverse=True):
        raise ValueError("RELEASE-NOTES.md: the newest version comes first")
    _nothing_shipped_is_unreleased(sections)
    return sections


def _words(line: str) -> str:
    """A line as said, however it's wrapped or spaced."""
    return " ".join(line.split())


def _nothing_shipped_is_unreleased(sections: list[Section]) -> None:
    """ValueError if a line under Unreleased is also under a version: it
    shipped in that version, so the next one doesn't bring it (321)."""
    shipped: dict[str, str] = {}
    for section in sections:
        if section.title != UNRELEASED:
            for items in section.groups.values():
                for line in items:
                    shipped.setdefault(_words(line), section.title)
    for section in sections:
        if section.title == UNRELEASED:
            for items in section.groups.values():
                for line in items:
                    if version := shipped.get(_words(line)):
                        raise ValueError(
                            f"RELEASE-NOTES.md: Unreleased has a line {version} shipped"
                            f" - take it out of Unreleased: {line[:70]}"
                        )


def cut(text: str, version: str, day: str) -> str:
    """`text` with Unreleased's lines (and any paragraph it has) moved under
    `## version - day`, just below an Unreleased left with its three empty
    groups; a group with no lines isn't carried over. ValueError if the
    version or the day isn't one, the version isn't newer than the newest
    section, or Unreleased has no lines to release."""
    version = version.removeprefix("v")
    heading = f"## {version} - {day}"
    if not VERSION_HEADING.match(heading):
        raise ValueError(f"'{heading}' isn't '## X.Y.Z - YYYY-MM-DD'")
    date.fromisoformat(day)  # a day the calendar has
    sections = parse(text)
    if not sections or sections[0].title != UNRELEASED:
        raise ValueError("RELEASE-NOTES.md: Unreleased isn't the first section")
    if not sections[0].lines():
        raise ValueError("RELEASE-NOTES.md: Unreleased has no lines to release")
    if len(sections) > 1 and _version_key(version) <= _version_key(sections[1].title):
        raise ValueError(f"{version} isn't newer than {sections[1].title}, the newest")
    lines = [line.rstrip() for line in text.splitlines()]
    start = lines.index(f"## {UNRELEASED}")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    chunks: list[list[str]] = [[]]  # the paragraph, then each group
    for line in lines[start + 1 : end]:
        if line.startswith("### "):
            chunks.append([])
        chunks[-1].append(line)
    moved: list[str] = []
    for chunk in chunks:
        if (
            chunk
            and chunk[0].startswith("### ")
            and not any(line.startswith("- ") for line in chunk)
        ):
            continue  # an empty group
        for line in chunk:
            if line or (moved and moved[-1]):
                moved.append(line)  # one blank line between blocks
    while moved and not moved[-1]:
        moved.pop()
    empty = [f"## {UNRELEASED}", ""] + [x for g in GROUPS for x in (f"### {g}", "")]
    rest = lines[end:]
    out = lines[:start] + empty + [heading, ""] + moved + ([""] + rest if rest else [])
    return "\n".join(out) + "\n"


def notes_for(text: str, version: str) -> Section:
    """`version`'s section (`0.1.0`, or the tag `v0.1.0`); LookupError if
    the file has none or it has no lines."""
    version = version.removeprefix("v")
    for section in parse(text):
        if section.title == version:
            if not section.lines():
                raise LookupError(f"RELEASE-NOTES.md: {version} has no lines")
            return section
    raise LookupError(
        f"RELEASE-NOTES.md has no '## {version} - YYYY-MM-DD': move Unreleased"
        " under it in the release's prep pull request (python -m"
        f" tools.package.release_notes v{version} --cut --date YYYY-MM-DD)"
    )


def _cut(file: Path, tag: str, day: str | None, dry_run: bool) -> int:
    if not day:
        print(
            "Not cut: --cut needs --date YYYY-MM-DD (Melbourne's day)", file=sys.stderr
        )
        return 1
    try:
        raw = file.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        new = cut(text, tag, day)
        section = notes_for(new, tag)
    except (OSError, LookupError, ValueError) as e:
        print(f"Not cut: {e}", file=sys.stderr)
        return 1
    counts = ", ".join(f"{len(v)} {k}" for k, v in section.groups.items() if v)
    said = f"## {section.title} - {section.date}: {counts}, from Unreleased"
    if dry_run:
        print(f"{said} (dry run: {file.name} unchanged)\n")
        sys.stdout.write(section.markdown())
        return 0
    file.write_text(new, encoding="utf-8", newline="\r\n" if b"\r\n" in raw else "\n")
    print(f"{said}; Unreleased is empty")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.release_notes")
    parser.add_argument("tag", help="the release's tag (v0.1.0) or version")
    parser.add_argument("--file", type=Path, default=NOTES)
    parser.add_argument("--out", type=Path, help="write the notes here, not to stdout")
    parser.add_argument(
        "--cut",
        action="store_true",
        help="the release's prep step: move Unreleased under this version",
    )
    parser.add_argument("--date", help="with --cut: the release's day, YYYY-MM-DD")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --cut: say what moves, write nothing",
    )
    args = parser.parse_args(argv)
    if args.cut:
        return _cut(args.file, args.tag, args.date, args.dry_run)
    try:
        section = notes_for(args.file.read_text(encoding="utf-8"), args.tag)
    except (OSError, LookupError, ValueError) as e:
        print(f"No release notes: {e}", file=sys.stderr)
        return 1
    if args.out:
        args.out.write_text(section.markdown(), encoding="utf-8")
    else:
        sys.stdout.write(section.markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
