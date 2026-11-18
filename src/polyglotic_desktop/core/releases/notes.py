"""Release notes, and what's new after an update (polyglotic-hq 345,
decision 0137).

The notes are RELEASE-NOTES.md's sections - one per version, newest first,
`## 0.1.5 - 2026-11-15`, then New, Better and Fixed - the same text the
update feed carries (polyglotic-hq 299). The app carries the whole file, so
an updated copy knows its own version's notes and every version's before
it, whichever it updated from.

The rules for showing them:
- **Once per version, after an update:** the first start of a version the
  learner hasn't seen the notes of shows them on Home, until the learner
  closes the card (`seen` becomes this version). Help keeps them.
- **Never on a fresh install's first run:** it starts having seen this
  version (`seen_at_start`).
- **Several versions skipped:** each one's notes, newest first - Home
  shows the newest, and the others are a click away in Help.
- **From a version that kept nothing** (0.1.5 and before): this version's
  notes only, since which version it came from isn't known.

No I/O here: `main` reads the file and keeps `seen` in the settings.
"""

import re
from dataclasses import dataclass

_HEADING = re.compile(
    r"^## (?P<version>[0-9]+\.[0-9]+\.[0-9]+) - (?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\s*$"
)
_VERSION = re.compile(r"^v?(?P<major>[0-9]+)\.(?P<minor>[0-9]+)\.(?P<patch>[0-9]+)")
_GROUP = re.compile(r"^###\s+(?P<name>.+?)\s*$")
_ITEM = re.compile(r"^\s*[-*] (?P<text>.*)$")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MARKS = re.compile(r"\*\*|__|`")


@dataclass(frozen=True, slots=True)
class ReleaseNotes:
    """One version's notes: `markdown` is its section under the heading."""

    version: str
    date: str
    markdown: str


def sections(text: str) -> tuple[ReleaseNotes, ...]:
    """Each released version's notes in RELEASE-NOTES.md's `text`, in the
    file's order (newest first). Unreleased, and anything before the first
    version, isn't one."""
    found: list[ReleaseNotes] = []
    heading: re.Match[str] | None = None
    body: list[str] = []

    def close() -> None:
        if heading is not None:
            found.append(
                ReleaseNotes(
                    heading["version"], heading["date"], "\n".join(body).strip()
                )
            )

    for line in text.splitlines():
        if line.startswith("## "):
            close()
            heading, body = _HEADING.match(line), []
        elif heading is not None:
            body.append(line)
    close()
    return tuple(found)


def version_order(version: str) -> tuple[int, int, int] | None:
    """A version's place in order (`0.1.5`, `v0.1.5`, `0.1.6-rc1` as
    0.1.6); None for one that isn't X.Y.Z."""
    found = _VERSION.match(version.strip())
    if found is None:
        return None
    return int(found["major"]), int(found["minor"]), int(found["patch"])


def newest_released(notes: tuple[ReleaseNotes, ...]) -> str | None:
    """The newest version the notes name as released, as `MAJOR.MINOR.PATCH`
    with no leading zeros (`0.1.7`); None when they name none. What a copy
    run from source tells the server it is (decision 0224): its code holds
    every change up to that release."""
    found = [at for each in notes if (at := version_order(each.version)) is not None]
    if not found:
        return None
    return ".".join(str(part) for part in max(found))


def seen_at_start(seen: str | None, current: str, fresh: bool) -> str | None:
    """The version whose notes count as seen, at this start: a fresh
    install's first run has seen this version's (it shows none); otherwise
    what was kept."""
    return current if fresh else seen


def unseen(
    seen: str | None, current: str, notes: tuple[ReleaseNotes, ...]
) -> tuple[ReleaseNotes, ...]:
    """The notes to show on Home, newest first: each version after `seen`
    up to this one (`current`). `seen` None - a copy updated from a version
    that kept nothing - this version's only. () when they're seen, or this
    version has no place in order (run from source)."""
    now = version_order(current)
    if now is None:
        return ()
    after = version_order(seen) if seen is not None else None
    if seen is not None and after is None:
        return ()
    shown: list[tuple[tuple[int, int, int], ReleaseNotes]] = []
    for each in notes:
        at = version_order(each.version)
        if (
            at is not None
            and at <= now
            and (at == now if after is None else at > after)
        ):
            shown.append((at, each))
    shown.sort(key=lambda found: found[0], reverse=True)
    return tuple(each for _, each in shown)


def plain_items(markdown: str) -> list[str]:
    """A section's items (`- ...`, an item's lines that go on joined), in
    plain text: links' words only, no bold or code marks."""
    items: list[list[str]] = []
    for line in markdown.splitlines():
        found = _ITEM.match(line)
        if found:
            items.append([found["text"].strip()])
        elif items and line[:1] in (" ", "\t") and line.strip():
            items[-1].append(line.strip())  # the item goes on
    return [_plain(" ".join(item)) for item in items]


def plain(markdown: str) -> str:
    """A section in plain text, for Help: each group's name (New, Better,
    Fixed) on a line of its own with its items under it as "• ...", a
    paragraph as one line - with links' words only and no bold or code
    marks. Groups are a blank line apart."""
    blocks: list[list[str]] = [[]]
    said: list[str] = []  # the item or paragraph being read

    def said_ends() -> None:
        if said:
            blocks[-1].append(_plain(" ".join(said)))
            said.clear()

    for line in markdown.splitlines():
        group, item = _GROUP.match(line), _ITEM.match(line)
        if group:
            said_ends()
            blocks.append([group["name"]])
        elif item:
            said_ends()
            said.append("• " + item["text"].strip())
        elif not line.strip():
            said_ends()
        else:  # an item's or a paragraph's next line
            said.append(line.strip())
    said_ends()
    return "\n\n".join("\n".join(block) for block in blocks if block)


def _plain(text: str) -> str:
    return _MARKS.sub("", _LINK.sub(r"\1", text)).strip()
