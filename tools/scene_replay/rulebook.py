"""The display rulebook: read from `rules.toml`, written for the founder, checked.

A rule has eleven parts (ADR-009, item 2). Ten are in
`tests/ui_next/rules/rules.toml`; the eleventh, the test that pins it and
the planted break that proves the test, is declared on the tests themselves
(`@pins("rule.id")`, `@breaks("rule.id")`) and read from there, so the book
cannot name a test that is not there.

    uv run python -m tools.scene_replay rulebook --write [--pictures]
    uv run python -m tools.scene_replay rulebook --check

`--check` fails on: a rule with no test or no planted break; a test in a
family's module that names no rule; a `RULEBOOK.md` or `DECIDING.md` that is
not what `--write` gives; a marked rule whose statement has changed since
the founder marked it; a rule that names a deciding function that is not on
the list; and a picture that is missing, made from another recipe or, on
the machine that made the pictures, no longer comes out the same.
"""

import argparse
import ast
import hashlib
import json
import tomllib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from tools.scene_replay import deciding

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "tests" / "ui_next" / "rules"
BOOK = ROOT / "docs" / "display"

FAMILIES = {
    "wrapping": "Wrapping and line breaks",
    "movement": "Movement: what moves, falls, slides, glides or fades, and what waits",
    "ink": "Ink: colours, word links, known words, highlights",
    "readings": "Readings and underlines",
    "cards": "The card stack and zones",
    "pacing": "What triggers a repaint, and pacing",
    "pointing": "Pointing: hover, what a point hits, selection",
    "transcript": "The transcript and the joined window",
    "video": "Video",
}
"""The nine families (ADR-009, item 1). A family's tests are in
`tests/ui_next/rules/test_<family>.py`."""

SURFACES = {
    "panel": "caption windows (Everyday, Conversation, Learning)",
    "zones": "Steady's transcript and live zone",
    "cards": "Steady's card stack",
    "joined": "the joined window",
    "video-instant": "Video, Instant",
    "video-scrolling": "Video, Scrolling",
    "transcript": "the transcript window",
}
MARKS = ("keep", "change", "drop")

F = TypeVar("F", bound=Callable[..., object])


def pins(rule: str) -> Callable[[F], F]:
    """Marks a test as the one that holds `rule` (an id in `rules.toml`)."""

    def mark(test: F) -> F:
        test.pins = rule  # type: ignore[attr-defined]
        return test

    return mark


def breaks(rule: str) -> Callable[[F], F]:
    """Marks a test as `rule`'s planted break: it breaks the rule on
    purpose and shows the rule's property sees it."""

    def mark(test: F) -> F:
        test.breaks = rule  # type: ignore[attr-defined]
        return test

    return mark


@dataclass(frozen=True)
class Picture:
    file: str
    stream: str
    setup: str
    frames: tuple[int, ...]
    caption: str
    plant: str = ""

    def recipe(self) -> str:
        """What the picture is made from: a change here is a new picture."""
        stream = _stream_file(self.stream)
        made = [self.stream, self.setup, list(self.frames), self.plant]
        text = stream.read_bytes().replace(b"\r\n", b"\n")  # as Git stores it
        made.append(hashlib.sha256(text).hexdigest())
        return hashlib.sha256(json.dumps(made).encode()).hexdigest()[:16]


def _stream_file(name: str) -> Path:
    family, _, stem = name.partition("/")
    folder = {
        "lines": ROOT / "tests" / "fixtures" / "lines",
        "rebuild": ROOT / "fixtures" / "rebuild",
        "rules": RULES / "streams",
    }[family]
    return folder / f"{stem}.json"


@dataclass(frozen=True)
class Conflict:
    other: str
    what: str
    wins: str
    picture: Picture | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    statement: str
    applies: tuple[str, ...]
    not_here: dict[str, str]
    trigger: str
    decided: tuple[dict[str, Any], ...]
    picture: Picture | None
    shaped_by: tuple[str, ...]
    conflicts: tuple[Conflict, ...]
    said_before: tuple[str, ...]
    recommendation: str
    why: str
    mark: str = ""
    marked_on: str = ""
    his_words: str = ""
    marked_statement: str = ""
    fails_today: tuple[str, ...] = ()
    """Runs (`stream@setup` patterns) on a surface it applies on where the
    code does not do what the rule says. Each is one of its conflicts."""
    tests: tuple[str, ...] = field(default=(), compare=False)
    planted: tuple[str, ...] = field(default=(), compare=False)

    @property
    def family(self) -> str:
        return self.id.partition(".")[0]

    def statement_digest(self) -> str:
        return hashlib.sha256(" ".join(self.statement.split()).encode()).hexdigest()[
            :12
        ]


def _picture(plain: dict[str, Any] | None) -> Picture | None:
    if not plain:
        return None
    return Picture(
        plain["file"],
        plain["stream"],
        plain["setup"],
        tuple(plain["frames"]),
        plain.get("caption", ""),
        plain.get("plant", ""),
    )


def declared(
    rules_dir: Path,
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """What the family test modules declare: tests by the rule they pin,
    planted breaks by rule, and the tests that name no rule."""
    pinned: dict[str, list[str]] = {}
    planted: dict[str, list[str]] = {}
    nameless = []
    for family in FAMILIES:
        path = rules_dir / f"test_{family}.py"
        if not path.exists():
            continue
        where = path.relative_to(rules_dir.parents[2]).as_posix()
        for node in ast.parse(path.read_text("utf-8")).body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith(
                "test_"
            ):
                continue
            named = False
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id in ("pins", "breaks")
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                ):
                    named = True
                    book = pinned if decorator.func.id == "pins" else planted
                    book.setdefault(str(decorator.args[0].value), []).append(
                        f"{where}::{node.name}"
                    )
            if not named:
                nameless.append(f"{where}::{node.name}")
    return pinned, planted, nameless


def load(rules_dir: Path = RULES) -> list[Rule]:
    plain = tomllib.loads((rules_dir / "rules.toml").read_text("utf-8"))
    pinned, planted, _ = declared(rules_dir)
    rules = []
    for item in plain.get("rule", []):
        rules.append(
            Rule(
                item["id"],
                item["title"],
                item["statement"].strip(),
                tuple(item["applies"]),
                dict(item.get("not_here", {})),
                item["trigger"].strip(),
                tuple(item["decided"]),
                _picture(item.get("picture")),
                tuple(item.get("shaped_by", ())),
                tuple(
                    Conflict(
                        c["with"], c["what"], c["wins"], _picture(c.get("picture"))
                    )
                    for c in item.get("conflicts", ())
                ),
                tuple(item.get("said_before", ())),
                item["recommendation"],
                item["why"].strip(),
                item.get("mark", ""),
                item.get("marked_on", ""),
                item.get("his_words", ""),
                item.get("marked_statement", ""),
                tuple(item.get("fails_today", ())),
                tuple(pinned.get(item["id"], ())),
                tuple(planted.get(item["id"], ())),
            )
        )
    return rules


def _order(rule: Rule) -> tuple[int, str]:
    """The founder's edition: conflicts first, then rules that differ
    between surfaces, then the rest (ADR-009, item 4)."""
    if rule.conflicts:
        return (0, rule.id)
    if rule.not_here:
        return (1, rule.id)
    return (2, rule.id)


def _where(rule: Rule) -> str:
    here = ", ".join(SURFACES[s] for s in rule.applies)
    lines = [f"**Where.** In {here}."]
    for surface, reason in rule.not_here.items():
        lines.append(f"Not in {SURFACES[surface]}: {reason}")
    return " ".join(lines)


def _mark(rule: Rule) -> str:
    if rule.mark:
        words = f' - "{rule.his_words}"' if rule.his_words else ""
        return f"**Your mark.** {rule.mark}, {rule.marked_on}{words}"
    return "**Your mark.** [ ] keep [ ] change [ ] drop"


def render(rules: list[Rule]) -> str:
    ordered = sorted(rules, key=_order)
    out = [
        "# The display rulebook",
        "",
        (
            "<!-- Generated by `python -m tools.scene_replay rulebook --write` from"
            " tests/ui_next/rules/rules.toml and the tests beside it. Edit those,"
            " not this file. -->"
        ),
        "",
        (
            "Every rule the caption display applies, one entry each: what you see,"
            " when, where, a picture, what it conflicts with, what was said about"
            " it before, and a recommendation. Each rule is held by a named test"
            " that fails when the rule is broken on purpose. Mark each one keep,"
            " change or drop; a change is recorded in your words."
        ),
        "",
        (
            f"**So far:** {len(rules)} rules, the ones you have already ruled on,"
            " written out as the pattern. The nine families follow, one at a time:"
        ),
        "",
        "| Family | Rules written |",
        "|---|---:|",
    ]
    for family, title in FAMILIES.items():
        count = sum(rule.family == family for rule in rules)
        out.append(f"| {title} | {count} |")
    out += [
        "",
        (
            "Order: rules that conflict with another come first, then rules that"
            " differ from one kind of window to another, then the rest."
        ),
        "",
    ]
    for n, rule in enumerate(ordered, 1):
        out += [f"## {n}. {rule.title}", "", f"**What you see.** {rule.statement}", ""]
        if rule.picture is not None:
            out += [
                f"![{rule.title}](pictures/{rule.picture.file})",
                "",
                f"*{rule.picture.caption}*",
                "",
            ]
        out += [f"**When.** {rule.trigger}", "", _where(rule), ""]
        if rule.conflicts:
            out.append("**Conflicts with.**")
            out.append("")
            for conflict in rule.conflicts:
                out.append(
                    f"- *{_title(rules, conflict.other)}*: {conflict.what}"
                    f" **Which wins:** {conflict.wins}"
                )
                if conflict.picture is not None:
                    out += [
                        "",
                        f"  ![both firing](pictures/{conflict.picture.file})",
                        "",
                        f"  *{conflict.picture.caption}*",
                    ]
            out.append("")
        else:
            out += [
                "**Conflicts with.** None found among the rules written so far.",
                "",
            ]
        if rule.said_before:
            out.append("**What was said before.**")
            out.append("")
            out += [f"- {each}" for each in rule.said_before]
            out.append("")
        out += [
            f"**Recommendation.** {rule.recommendation.capitalize()}. {rule.why}",
            "",
            _mark(rule),
            "",
            "<details><summary>For engineers</summary>",
            "",
            f"- Rule id: `{rule.id}`",
        ]
        for each in rule.decided:
            inside = "inside the paint" if each.get("in_paint") else "outside the paint"
            note = f" - {each['note']}" if each.get("note") else ""
            out.append(f"- Decided in `{each['function']}` ({inside}){note}")
        if rule.shaped_by:
            out.append("- Shaped by: " + "; ".join(rule.shaped_by))
        out += [f"- Test: `{test}`" for test in rule.tests]
        out += [f"- Planted break: `{test}`" for test in rule.planted]
        out += ["", "</details>", ""]
    return "\n".join(out).rstrip() + "\n"


def _title(rules: list[Rule], rule_id: str) -> str:
    return next((rule.title for rule in rules if rule.id == rule_id), rule_id)


def render_deciding() -> str:
    found = deciding.scan(ROOT)
    out = [
        "# The display's deciding functions",
        "",
        (
            "<!-- Generated by `python -m tools.scene_replay rulebook --write`."
            " The list itself is tests/ui_next/rules/deciding.json. -->"
        ),
        "",
        (
            "Every function in the display's files that makes a choice about a"
            " caption's look: what is drawn, where, in which ink or when. How a"
            " function gets on the list, and what is set aside, is in"
            ' `tools/scene_replay/deciding.py`. "In the paint" means reachable from'
            " a `paintEvent` in the same file by calls the syntax tree can follow;"
            " the layout, the marks and Video's flow are called from the paint"
            " through objects and are not counted there."
        ),
        "",
        deciding.table(ROOT),
        "## The functions",
        "",
    ]
    for file in (*deciding.FILES, *deciding.LATER):
        mine = [d for d in found.listed if d.file == file]
        if not mine:
            continue
        out += [f"### `{file}` ({len(mine)})", ""]
        for d in mine:
            kinds = ", ".join(d.kinds) or "unsorted"
            paint = "; in the paint" if d.in_paint else ""
            out.append(f"- `{d.name}`: {d.choices} choice(s); {kinds}{paint}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def problems(rules_dir: Path = RULES, book: Path = BOOK) -> Iterator[str]:
    """Everything `--check` fails on, except pictures that must be drawn
    again to be judged (`pictures.problems`)."""
    rules = load(rules_dir)
    pinned, planted, nameless = declared(rules_dir)
    known = {rule.id for rule in rules}
    listed = {d.key for d in deciding.scan(ROOT).listed}
    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            yield f"{rule.id}: written twice"
        seen.add(rule.id)
        if rule.family not in FAMILIES:
            yield f"{rule.id}: no family called {rule.family}"
        if not rule.tests:
            yield f"{rule.id}: a rule with no test (no test is marked @pins for it)"
        if not rule.planted:
            yield f"{rule.id}: no planted break (no test is marked @breaks for it)"
        if rule.recommendation not in MARKS:
            yield f"{rule.id}: the recommendation is keep, change or drop"
        if rule.mark and rule.mark not in MARKS:
            yield f"{rule.id}: a mark is keep, change or drop"
        if rule.mark and rule.marked_statement != rule.statement_digest():
            yield (
                f"{rule.id}: its statement changed after the founder marked it"
                f" {rule.mark} on {rule.marked_on}: clear `mark` in rules.toml, and"
                " he marks it again"
            )
        for surface in (*rule.applies, *rule.not_here):
            if surface not in SURFACES:
                yield f"{rule.id}: no surface called {surface}"
        for each in rule.decided:
            if each["function"] not in listed:
                yield (
                    f"{rule.id}: decided in {each['function']}, which is not on"
                    " the list of deciding functions"
                )
        if rule.fails_today and not rule.conflicts:
            yield f"{rule.id}: it fails somewhere today, so it has a conflict to show"
        for conflict in rule.conflicts:
            if conflict.other not in known and not conflict.other.startswith(
                "unwritten:"
            ):
                yield f"{rule.id}: conflicts with {conflict.other}, which is not a rule"
        for picture in _pictures(rule):
            if not (book / "pictures" / picture.file).exists():
                yield f"{rule.id}: its picture {picture.file} is missing"
    for rule_id in sorted((pinned.keys() | planted.keys()) - known):
        tests = pinned.get(rule_id, []) + planted.get(rule_id, [])
        yield f"{tests[0]}: names {rule_id}, which is not a rule"
    for test in nameless:
        yield f"{test}: a test that names no rule (mark it @pins or @breaks)"
    written = book / "RULEBOOK.md"
    if not written.exists() or written.read_text("utf-8") != render(rules):
        yield "RULEBOOK.md is stale: run rulebook --write"


def deciding_note() -> str:
    """Whether the kept list of deciding functions is today's. A note, not a
    failure: the list is a dated count until every function on it belongs to
    a rule (display-1 onward), and failing here would stop every change to
    the display's files for a list nothing yet rests on. A rule that names a
    function no longer on today's list does fail (`problems`)."""
    kept = RULES / "deciding.json"
    if kept.exists() and kept.read_text("utf-8") == deciding.as_json(ROOT):
        return ""
    return (
        "the list of deciding functions (deciding.json, DECIDING.md) is not"
        " today's: rulebook --write brings it up to date"
    )


def _pictures(rule: Rule) -> list[Picture]:
    found = [rule.picture] if rule.picture else []
    found += [c.picture for c in rule.conflicts if c.picture]
    return found


def all_pictures(rules: list[Rule]) -> list[Picture]:
    return [picture for rule in rules for picture in _pictures(rule)]


def main(args: argparse.Namespace) -> int:
    rules_dir = Path(args.rules).resolve() if args.rules else RULES
    book = Path(args.book).resolve() if args.book else BOOK
    if args.write:
        rules = load(rules_dir)
        book.mkdir(parents=True, exist_ok=True)
        if args.pictures:
            from tools.scene_replay import pictures

            pictures.take(all_pictures(rules), book)
        (book / "RULEBOOK.md").write_text(render(rules), "utf-8", newline="\n")
        if rules_dir == RULES:
            (rules_dir / "deciding.json").write_text(
                deciding.as_json(ROOT), "utf-8", newline="\n"
            )
            (book / "DECIDING.md").write_text(render_deciding(), "utf-8", newline="\n")
        print(f"wrote the rulebook: {len(rules)} rules")
        return 0
    found = list(problems(rules_dir, book))
    note = ""
    if not found:
        from tools.scene_replay import pictures

        again, note = pictures.problems(all_pictures(load(rules_dir)), book)
        found += again
    for each in found:
        print(each)
    if found:
        print(f"the rulebook does not hold: {len(found)} problem(s)")
        return 1
    rules = load(rules_dir)
    print(
        f"the rulebook holds: {len(rules)} rules, each with a test and a planted break"
    )
    for each in (note, deciding_note() if rules_dir == RULES else ""):
        if each:
            print(each)
    return 0
