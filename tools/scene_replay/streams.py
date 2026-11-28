"""The caption streams the replay plays: two fixture formats, one shape.

- `tests/fixtures/lines/*.json` (827): the line replay's own events, each a
  time, a caption key, a source and its clauses.
- `fixtures/rebuild/*.json` (749): protocol v1 messages with the time each
  arrived, as the server sends them.

Both become a `Stream`: timed `CaptionUpdate`s from at most two sources,
the first seen and one other. Every text in them is made up or public
(RULES #26, #30).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
    WordTime,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

ROOT = Path(__file__).resolve().parents[2]
LINES = ROOT / "tests" / "fixtures" / "lines"
REBUILD = ROOT / "fixtures" / "rebuild"
RULES = ROOT / "tests" / "ui_next" / "rules" / "streams"
"""Short streams written for one rule each (`rules/<name>`): played by the
rule's test and its picture, not by the matrix."""

FIRST = SourceId("app")
OTHER = SourceId("mic")
"""The two sources a stream speaks from: the captioned app and the
learner's own mic (the ids the app's recorded captions use)."""

EN = Language("en")

MADE_UP_READINGS = ("yi", "shan", "zhuang", "a")
"""Readings for a stream that brings none, so "readings on" has something
to draw over every Han character: short, middling and long, picked by the
character's code point. They are not real pinyin and are never shown to a
learner."""


@dataclass(frozen=True)
class Stream:
    name: str
    events: tuple[tuple[float, CaptionUpdate], ...]
    given: dict[str, tuple[Reading, ...]]
    """Readings the fixture itself gives, by the clause's text."""
    width: int
    height: int
    arrows: bool = False

    @property
    def seconds(self) -> float:
        return self.events[-1][0] if self.events else 0.0

    def readings(self, made_up: bool) -> Callable[[str, object], list[Reading] | None]:
        """The engine's reading lookup for this stream: the fixture's own,
        and with `made_up` one over every other Han character."""

        def find(text: str, _language: object) -> list[Reading] | None:
            found = self.given.get(text)
            if found is not None:
                return list(found)
            if not made_up:
                return None
            made = [
                Reading(i, i + 1, MADE_UP_READINGS[ord(c) % len(MADE_UP_READINGS)])
                for i, c in enumerate(text)
                if _han(c)
            ]
            return made or None

        return find


def _han(char: str) -> bool:
    return "㐀" <= char <= "鿿"


def names() -> list[str]:
    """Every stream, by name: `lines/a`, `rebuild/late_translation`. The
    four `lines` files with a hyphen are the composer's own step cases
    (827's unit 3), not caption streams, and are not played."""
    found = [
        f"lines/{p.stem}" for p in sorted(LINES.glob("*.json")) if "-" not in p.stem
    ]
    found += [f"rebuild/{p.stem}" for p in sorted(REBUILD.glob("*.json"))]
    return found


def load(name: str) -> Stream:
    family, _, stem = name.partition("/")
    if family == "lines":
        return _lines(name, json.loads((LINES / f"{stem}.json").read_text("utf-8")))
    if family == "rules":  # a rule's own short stream, in the lines format
        return _lines(name, json.loads((RULES / f"{stem}.json").read_text("utf-8")))
    if family == "rebuild":
        return _rebuild(name, json.loads((REBUILD / f"{stem}.json").read_text("utf-8")))
    raise ValueError(f"no stream called {name}")


def line_update(event: dict[str, Any]) -> CaptionUpdate:
    """One event of the line replay's format as the app's caption update."""
    clauses = []
    for item in event["clauses"]:
        text = item["said"]
        start = 0
        words = []
        for word in item["words"]:
            start = text.index(word, start)
            end = start + len(word)
            words.append(WordTime((start, end), event["t"], event["t"]))
            start = end
        links = tuple(
            WordLink(tuple(link["original"]), tuple(link["translation"]), True, 1.0)
            for link in item["links"]
        )
        clauses.append(
            Clause(
                text,
                {EN: item["translation"]} if item["translation"] else {},
                {EN: links},
                words=tuple(words),
            )
        )
    language = Language(event.get("language", "zh"))
    return CaptionUpdate(
        CaptionId(str(event["key"])),
        OTHER if event["source"] == "you" else FIRST,
        CaptionKind.LIVE if event["live"] else CaptionKind.FINISHED,
        tuple(clauses),
        language,
        (language,),
    )


def _lines(name: str, data: dict[str, Any]) -> Stream:
    given: dict[str, tuple[Reading, ...]] = {}
    for event in data["events"]:
        for clause in event["clauses"]:
            if clause["reading"]:
                text = clause["said"]
                han = [i for i, c in enumerate(text) if _han(c)]
                given[text] = tuple(
                    Reading(i, i + 1, r)
                    for i, r in zip(han, clause["reading"], strict=True)
                )
    options = data.get("window", {})
    return Stream(
        name,
        tuple((float(e["t"]), line_update(e)) for e in data["events"]),
        given,
        int(options.get("width", 1000)),
        int(options.get("height", 420)),
        bool(options.get("arrows", False)),
    )


def _rebuild(name: str, data: dict[str, Any]) -> Stream:
    sources: dict[str, SourceId] = {}
    events = []
    for event in data["events"]:
        decoded = protocol.decode(json.dumps(event["message"]))
        if not isinstance(decoded, protocol.CaptionUpdate):
            raise TypeError(f"{name}: not a caption_update")
        update = listening.caption_update(decoded)
        source = sources.setdefault(
            str(update.source_id), FIRST if not sources else OTHER
        )
        events.append((float(event["at_seconds"]), replace(update, source_id=source)))
    return Stream(name, tuple(events), {}, 1000, 420)
