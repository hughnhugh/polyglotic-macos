"""Probe the hosted Mac's existing audio permissions using only synthetic or public audio."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from tools.macos_capture_checks import PASS, Run
from tools.macos_ui_lab import hosted_mac


def main(out: Path) -> int:
    if not hosted_mac():
        raise SystemExit("Requires a GitHub-hosted Mac")
    out.mkdir(parents=True, exist_ok=True)
    bench = Run(out / "capture.json", None, 1)
    for check in (
        bench.blackhole,
        bench.one_app,
        bench.everything_else,
        bench.while_looped,
    ):
        if check == bench.blackhole or bench.blackhole_uid:
            check()
        (out / "capture.json").write_text(
            json.dumps([asdict(r) for r in bench.results], indent=1), encoding="utf-8"
        )
    return int(not bench.results or any(r.outcome != PASS for r in bench.results))


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
