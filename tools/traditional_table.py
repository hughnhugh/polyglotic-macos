"""The Simplified -> Traditional table "Show Mandarin in: Traditional" uses
(polyglotic-hq 375; decision 0164): OpenCC's own data, as its `s2tw`
conversion uses it - STPhrases and STCharacters (the first candidate of
each), then Taiwan's standard forms (TWVariants) - written as one file,
`adapters/data/zh_traditional.txt.gz` (gzipped: 1 MB as text, 420 KB
packed, under the repo's 500 KB limit for a file), read by
`adapters.traditional_table`.

OpenCC (https://github.com/BYVoid/OpenCC) is under the Apache License 2.0,
its dictionaries too; the licence goes beside the table
(`adapters/data/OpenCC-LICENSE.txt`) and into THIRD_PARTY_NOTICES.md.

    uv run python -m tools.traditional_table DIR   # DIR: OpenCC's data/dictionary
                                                   # and its LICENSE, at TAG

Kept: every phrase (one that converts to itself too: 若干 keeps 干 from
becoming 幹) and every character that changes. A pair that would change a
text's length (none in 1.1.9) or that has anything but Chinese characters
is left out: the app converts runs of Chinese characters only.
"""

import argparse
import gzip
import shutil
from pathlib import Path

from polyglotic_desktop.core.lexicon.chinese import is_han

TAG = "ver.1.1.9"
DATA = Path(__file__).resolve().parents[1] / "src/polyglotic_desktop/adapters/data"
TABLE = DATA / "zh_traditional.txt.gz"
LICENSE = DATA / "OpenCC-LICENSE.txt"


def _pairs(path: Path) -> dict[str, str]:
    """A dictionary file's lines, `simplified<TAB>candidates`, the first
    candidate each."""
    pairs = {}
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            source, candidates = line.split("\t")
            pairs[source] = candidates.split(" ")[0]
    return pairs


def table(folder: Path) -> dict[str, str]:
    taiwan = _pairs(folder / "TWVariants.txt")

    def in_taiwan(text: str) -> str:
        return "".join(taiwan.get(c, c) for c in text)

    found: dict[str, str] = {}
    for name, keep_same in (("STPhrases.txt", True), ("STCharacters.txt", False)):
        for simplified, traditional in _pairs(folder / name).items():
            converted = in_taiwan(traditional)
            if (
                len(converted) == len(simplified)
                and all(is_han(c) for c in simplified + converted)
                and (keep_same or converted != simplified)
            ):
                found.setdefault(simplified, converted)
    for simplified, traditional in taiwan.items():  # 着 -> 著 where OpenCC keeps 着
        if simplified not in found and len(simplified) == len(traditional):
            found[simplified] = traditional
    return found


def write(folder: Path) -> int:
    pairs = table(folder)
    lines = [
        f"# OpenCC {TAG} s2tw: STPhrases, STCharacters, TWVariants (Apache-2.0,",
        "# OpenCC-LICENSE.txt). Made by tools/traditional_table.py - don't edit.",
        *(f"{s}\t{t}" for s, t in sorted(pairs.items())),
    ]
    DATA.mkdir(parents=True, exist_ok=True)
    text = ("\n".join(lines) + "\n").encode("utf-8")
    # mtime=0: the same bytes each time it's made
    TABLE.write_bytes(gzip.compress(text, compresslevel=9, mtime=0))
    shutil.copyfile(folder / "LICENSE", LICENSE)
    return len(pairs)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tools.traditional_table")
    parser.add_argument("folder", type=Path, help="OpenCC's dictionary files")
    args = parser.parse_args()
    print(f"{write(args.folder)} pairs -> {TABLE}")


if __name__ == "__main__":
    main()
