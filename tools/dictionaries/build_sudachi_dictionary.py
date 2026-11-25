"""Build the pinned Japanese dictionary upload from the locked wheel."""

import gzip
import hashlib
from pathlib import Path

import sudachidict_small

from polyglotic_desktop.adapters.japanese_dictionary import OBJECT_NAME


def main(out: Path) -> None:
    source = Path(sudachidict_small.__file__).parent / "resources" / "system.dic"
    out.parent.mkdir(parents=True, exist_ok=True)
    with (
        source.open("rb") as incoming,
        out.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed,
    ):
        while block := incoming.read(1 << 20):
            packed.write(block)
    print(f"object: {OBJECT_NAME}")
    print(f"size: {out.stat().st_size}")
    print(f"sha256: {hashlib.sha256(out.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    main(parser.parse_args().out)
