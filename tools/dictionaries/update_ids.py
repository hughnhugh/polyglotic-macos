"""Carry entry IDs from one release of a dictionary to the next.

Run when a source's pinned version changes, before building (decision
0007), with both releases on disk:

    uv run python -m tools.dictionaries.update_ids cedict OLD.txt.gz NEW.txt.gz
    uv run python -m tools.dictionaries.update_ids ecdict OLD.csv NEW.csv

It updates `tools/dictionaries/registry/<dictionary>.tsv` and prints what changed,
with examples to check by eye. Commit the registry with the new pin.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.dictionaries import cedict, ecdict
from tools.dictionaries.entry_ids import Changes, Registry, SourceEntry, carry_forward

REGISTRY = Path(__file__).parent / "registry"


def read_entries(dictionary: str, path: Path) -> tuple[list[SourceEntry], str]:
    """A release's entries for carry-forward, and its release name."""
    if dictionary == "cedict":
        release = cedict.release_date(path)[:10] or path.name
        return [e.source_entry() for e in cedict.read(path)], release
    # ECDICT has no release date in the file: name it by the file.
    return [row.source_entry() for row in ecdict.cut(ecdict.read(path))], path.name


def thresholds(dictionary: str) -> Sequence[float]:
    return cedict.THRESHOLDS if dictionary == "cedict" else ecdict.THRESHOLDS


def summary(changes: Changes, show: int) -> str:
    counts = (
        f"unchanged {changes.unchanged}, carried {len(changes.carried)}, "
        f"merged {len(changes.merged)}, removed {len(changes.removed)}, "
        f"added {len(changes.added)}"
    )
    lines = [counts]
    for title, rows in (
        ("carried (old -> new key)", [f"{a}  ->  {b}" for a, b in changes.carried]),
        ("merged (old -> into)", [f"{a}  ->  {b}" for a, b in changes.merged]),
        ("removed", changes.removed),
    ):
        if rows:
            lines.append(f"{title}, first {min(show, len(rows))}:")
            lines += [f"  {row}" for row in rows[:show]]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dictionary", choices=["cedict", "ecdict"])
    parser.add_argument("old", type=Path, help="the release the IDs were built from")
    parser.add_argument("new", type=Path, help="the release being pinned")
    parser.add_argument(
        "--registry", type=Path, help="default: registry/<dictionary>.tsv"
    )
    parser.add_argument("--show", type=int, default=15, help="examples of each change")
    args = parser.parse_args(argv)

    path = args.registry or REGISTRY / f"{args.dictionary}.tsv"
    registry = Registry.load(path, args.dictionary)
    old, old_release = read_entries(args.dictionary, args.old)
    new, new_release = read_entries(args.dictionary, args.new)
    changes = carry_forward(
        registry,
        old,
        new,
        thresholds(args.dictionary),
        f"{old_release} to {new_release}",
    )
    registry.save(path)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(f"{args.dictionary}: {old_release} -> {new_release}")
    print(summary(changes, args.show))
    print(f"registry: {path} ({len(registry.ids)} ids, {len(registry.merged)} merged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
