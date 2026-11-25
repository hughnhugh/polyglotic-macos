"""Warn when an already-large Python source file grows substantially."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
BASELINE = PROJECT_ROOT / "tools/size_baseline.json"
LARGE_FILE_LINES = 800
ALLOWED_GROWTH_LINES = 50
TOP_FILE_COUNT = 10


def source_sizes(source_root: Path | None = None) -> dict[str, int]:
    """Return line counts for every Python source file, relative to the project."""
    source_root = source_root or SOURCE_ROOT
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): len(
            path.read_text(encoding="utf-8").splitlines()
        )
        for path in sorted(source_root.rglob("*.py"))
    }


def read_baseline(path: Path | None = None) -> dict[str, int]:
    path = path or BASELINE
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(sizes: dict[str, int], path: Path | None = None) -> None:
    path = path or BASELINE
    path.write_text(
        json.dumps(sizes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def warnings(sizes: dict[str, int], baseline: dict[str, int]) -> list[str]:
    messages = []
    for name, lines in sorted(sizes.items()):
        previous = baseline.get(name)
        if previous is None and lines > LARGE_FILE_LINES:
            messages.append(
                f"{name} is a new large file at {lines} lines (limit {LARGE_FILE_LINES})"
            )
        elif (
            previous is not None
            and lines > LARGE_FILE_LINES
            and lines - previous > ALLOWED_GROWTH_LINES
        ):
            messages.append(
                f"{name} grew by {lines - previous} lines, from {previous} to {lines} "
                f"(growth allowance {ALLOWED_GROWTH_LINES})"
            )
    return messages


def print_report(sizes: dict[str, int], baseline: dict[str, int]) -> None:
    for message in warnings(sizes, baseline):
        name = message.split(" ", 1)[0]
        print(f"::warning file={name}::{message}")

    print(f"Top {min(TOP_FILE_COUNT, len(sizes))} Python source files by size:")
    for name, lines in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))[
        :TOP_FILE_COUNT
    ]:
        print(f"{lines:>6}  {name}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="replace the baseline with current sizes"
    )
    args = parser.parse_args(argv)

    sizes = source_sizes()
    if args.update:
        write_baseline(sizes)
        baseline = sizes
        print(f"Updated {BASELINE.relative_to(PROJECT_ROOT)} ({len(sizes)} files).")
    else:
        baseline = read_baseline()
    print_report(sizes, baseline)
    # This ratchet is deliberately a tripwire, not a gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
