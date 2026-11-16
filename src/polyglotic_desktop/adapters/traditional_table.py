"""The Simplified -> Traditional table, read from the app's own data
(`data/zh_traditional.txt.gz`, gzipped text: OpenCC's, under the Apache
License 2.0 - its text beside it; made by `tools/traditional_table.py`): what
`core.lexicon.traditional.TraditionalChinese` converts with (polyglotic-hq
375; decision 0164). About 53,000 pairs, 1 MB: read once, when Traditional
is first wanted."""

import gzip
from pathlib import Path

TABLE = Path(__file__).with_name("data") / "zh_traditional.txt.gz"


def read_table(path: Path = TABLE) -> dict[str, str]:
    """The table's pairs, Simplified -> Traditional. Lines starting "#"
    are notes."""
    pairs = {}
    with gzip.open(path, "rt", encoding="utf-8") as lines:
        for line in lines:
            if line.startswith("#"):
                continue
            simplified, _, traditional = line.rstrip("\n").partition("\t")
            if simplified:
                pairs[simplified] = traditional
    return pairs
