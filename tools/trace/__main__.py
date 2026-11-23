"""`python -m tools.trace <log>`: the caption timelines' page (see the package's docstring)."""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from polyglotic_desktop.perf.trace_summary import Summary, summarise
from tools.trace.page import overview_svg, page
from tools.trace.read import load


def summary_line(found: Summary) -> str:
    """One line of what a stretch says, for a daily summary."""
    causes = ", ".join(f"{c} {n}" for c, n in found.hang_causes().most_common())
    total = found.by_segment.get("total", [])
    p50, p95 = found.p("total", 50), found.p("total", 95)
    return (
        f"{found.updates} updates, {found.shown} shown;"
        f" hangs {len(found.hangs)}"
        + (f" ({causes})" if causes else "")
        + f"; bursts {len(found.bursts)}; drops {sum(found.drops.values())}"
        + (
            f"; sound to screen p50 {round(p50)} ms, p95 {round(p95)} ms"
            if total and p50 is not None and p95 is not None
            else ""
        )
        + f"; {found.unheard.said()}"
    )


def numbers(found: Summary) -> dict[str, Any]:
    """The stretch's numbers as JSON: each segment's p50/p95/p99, and counts."""
    return {
        "updates": found.updates,
        "shown": found.shown,
        "hangs": len(found.hangs),
        "hang_causes": dict(found.hang_causes()),
        "bursts": len(found.bursts),
        "drops": dict(found.drops),
        "held": dict(found.held),
        "sound_unheard": {
            "stretches": found.unheard.stretches,
            "seconds": round(found.unheard.seconds, 1),
            "longest": round(found.unheard.longest, 1),
            "with_reset": found.unheard.with_reset,
            "heard_after_reset": found.unheard.heard_after_reset,
        },
        "segments_ms": {
            name: {f"p{p}": round(found.p(name, p) or 0) for p in (50, 95, 99)}
            for name in found.by_segment
        },
    }


def pictures(closeups: Sequence[tuple[str, str]], folder: Path) -> list[Path]:
    """Each close-up as a PNG, drawn by Qt's SVG renderer offscreen."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if fonts.is_dir():  # offscreen Qt finds no fonts of its own
        os.environ.setdefault("QT_QPA_FONTDIR", str(fonts))
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    _app = QGuiApplication.instance() or QGuiApplication([])
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, svg in closeups:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        size = renderer.defaultSize()
        image = QImage(size.width() * 2, size.height() * 2, QImage.Format.Format_ARGB32)
        image.fill(QColor("#fcfcfb"))
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        path = folder / f"{name}.png"
        image.save(str(path))
        written.append(path)
    del _app
    return written


def wall_offset(path: Path) -> float | None:
    """Seconds to add to the app's clock for the time of day, if the trace
    file's lines carry it (`2026-11-20 15:52:01,123 {...}`); None otherwise."""
    from datetime import datetime

    if not path.exists():
        return None
    files = [path] if path.is_file() else sorted(path.glob("trace.jsonl*"))
    for file in files:
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            head, _, rest = line.partition(" {")
            if not rest:
                continue
            try:
                at = datetime.strptime(head, "%Y-%m-%d %H:%M:%S,%f").timestamp()
                found: Mapping[str, Any] = json.loads("{" + rest)
            except ValueError:
                continue
            times = found.get("t") or {}
            if times:
                return at - max(float(v) for v in times.values())
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.trace", description=__doc__)
    parser.add_argument(
        "log",
        type=Path,
        help="a logs folder, trace.jsonl, captions.log or a report's log",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="the page (default: caption-timelines.html beside the log)",
    )
    parser.add_argument(
        "--pictures", type=Path, help="write the close-ups as PNGs here"
    )
    parser.add_argument(
        "--summary", action="store_true", help="print one line and the numbers as JSON"
    )
    parser.add_argument("--last", type=float, help="only the last this many minutes")
    args = parser.parse_args(argv)
    records, kind = load(args.log)
    if args.last and records:
        end = max(max((r.get("t") or {"_": 0.0}).values()) for r in records)
        records = [
            r
            for r in records
            if max((r.get("t") or {"_": 0.0}).values()) >= end - args.last * 60
        ]
    found = summarise(records)
    if args.summary:
        print(summary_line(found))
        print(json.dumps(numbers(found), separators=(",", ":")))
        return 0
    wall = 0.0 if kind == "caption log" else wall_offset(args.log)
    text, closeups = page(records, found, kind, args.log.name, wall)
    out = (
        args.out
        or (args.log if args.log.is_dir() else args.log.parent)
        / "caption-timelines.html"
    )
    out.write_text(text, encoding="utf-8")
    print(f"{summary_line(found)}\n{out}")
    if args.pictures:
        for path in pictures(
            [("overview", overview_svg(records, found, wall)), *closeups], args.pictures
        ):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
