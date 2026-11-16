"""Decision records (docs/decisions/) each have a number of their own
(polyglotic-hq 213; 179 and 209 found it: two pull requests both claimed
desktop's 0035 and nothing caught it until a merge). Each file is
`NNNN-short-name.md`, no two share a number, and each is headed by its
own number - so a record renumbered to settle a collision says so in its
title too. The same check is in polyglotic-server."""

import re
from collections import defaultdict
from pathlib import Path

DECISIONS = Path(__file__).resolve().parent.parent / "docs" / "decisions"
NAMED = re.compile(r"(\d{4})-[a-z0-9-]+\.md")


def records(folder: Path) -> list[Path]:
    """The decision records in `folder` - not its template."""
    return sorted(each for each in folder.glob("*.md") if each.name != "template.md")


def shared_numbers(folder: Path) -> dict[str, list[str]]:
    """The numbers more than one record in `folder` has, with their files."""
    by_number: dict[str, list[str]] = defaultdict(list)
    for each in records(folder):
        by_number[each.name[:4]].append(each.name)
    return {number: names for number, names in by_number.items() if len(names) > 1}


def test_the_check_finds_two_records_of_one_number(tmp_path: Path) -> None:
    for name in (
        "0034-earlier.md",
        "0035-one-pull-request.md",
        "0035-another-pull-request.md",
        "template.md",
    ):
        (tmp_path / name).write_text("# ...\n", encoding="utf-8")
    assert shared_numbers(tmp_path) == {
        "0035": ["0035-another-pull-request.md", "0035-one-pull-request.md"]
    }


def test_no_two_decision_records_share_a_number() -> None:
    found = records(DECISIONS)
    assert found, DECISIONS
    shared = shared_numbers(DECISIONS)
    assert not shared, (
        f"two decision records with one number: {shared}. Give the newer the"
        " next free number, in its file name, its title and wherever it's cited."
    )


def test_each_record_is_named_and_headed_by_its_number() -> None:
    wrong = []
    for each in records(DECISIONS):
        named = NAMED.fullmatch(each.name)
        heading = each.read_text(encoding="utf-8").splitlines()[0]
        if named is None or not heading.startswith(f"# {named.group(1)} "):
            wrong.append(f"{each.name}: {heading[:60]!r}")
    assert not wrong, wrong
