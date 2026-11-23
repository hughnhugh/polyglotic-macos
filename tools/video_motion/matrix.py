"""Run the full Video release comparison or one timeline, preserving every result."""

import argparse
import csv
import json
import os
import subprocess
from itertools import product
from pathlib import Path

from tools.video_motion.app import replay
from tools.video_motion.compare import compare, counts, invariants
from tools.video_motion.ink import audit, late, queue_ms

from tools import qt_lock

HERE = Path(__file__).resolve().parent
TIMELINES = ("cooking", "bonewars", "fleurs-zh")
PRESETS = ("tiny", "small", "medium", "large")
MODES = {"Instant": "instant", "Scrolling": "scrolling"}
ADDITIONAL = (
    ("cooking", "narrow", None),
    ("fast", "medium", HERE / "fast.json"),
    ("toggles", "medium", HERE / "toggles.json"),
    ("mode-switch", "medium", HERE / "mode-switch.json"),
)


def fixture(timeline: str) -> Path | None:
    return HERE / f"{timeline}.json" if timeline != "cooking" else None


def run(
    output: Path,
    timelines: list[str],
    presets: list[str],
    pictures: Path | None,
    *,
    additional: bool = True,
) -> bool:
    results = []
    cases = []
    passed = True
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    cases_to_run = [(t, p, fixture(t)) for t, p in product(timelines, presets)]
    if additional:
        cases_to_run.extend(ADDITIONAL)
    configurations = [
        (timeline, preset, recording, mode)
        for (timeline, preset, recording), mode in product(cases_to_run, MODES.items())
    ]
    for timeline, preset, recording, (_, mode) in configurations:
        folder = output / f"{timeline}-{preset}-{mode}"
        args = ["node", str(HERE / "reference.mjs"), str(folder), preset, mode]
        if recording is not None:
            args.append(str(recording))
        subprocess.run(args, check=True)

    # Prepare the browser reference before acquiring the shared Qt lock.
    with qt_lock.held("Video frame comparison"):
        for timeline, preset, _, (_, mode) in configurations:
            folder = output / f"{timeline}-{preset}-{mode}"
            replay(
                folder,
                pictures
                if timeline == "cooking" and preset in {"medium", "tiny"}
                else None,
                motion_only=True,
                reference_geometry=True,
            )

    for timeline, preset, _, (label, mode) in configurations:
        folder = output / f"{timeline}-{preset}-{mode}"
        reference = json.loads((folder / "reference.json").read_text(encoding="utf-8"))
        actual = json.loads((folder / "app.json").read_text(encoding="utf-8"))
        failures = {
            "reference": counts(invariants(reference, reference["settings"])),
            "app": counts(compare(reference, actual)),
        }
        (folder / "comparison.json").write_text(
            json.dumps(failures, indent=2), encoding="utf-8"
        )
        passed &= not any(failures.values())
        for side, issues in failures.items():
            data = reference if side == "reference" else actual
            exposures, queues = audit(data)
            misses = list(late(exposures, reference["settings"]["catchupMs"] / 1000))
            cases.append(
                (
                    timeline,
                    preset,
                    label,
                    side,
                    not issues,
                    len(exposures),
                    len(misses),
                    *queue_ms(queues),
                )
            )
            for rule, stats in issues.items():
                results.append(
                    (
                        timeline,
                        preset,
                        label,
                        side,
                        rule,
                        stats["frames"],
                        stats["first"],
                    )
                )
        print(
            f"{timeline} {preset} {label}: {len(reference['frames'])} frames, "
            f"reference {len(failures['reference'])} failed checks, app {len(failures['app'])}",
            flush=True,
        )
    with (output / "critics.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "timeline",
                "preset",
                "mode",
                "side",
                "failed_check",
                "frames",
                "first_frame",
            )
        )
        writer.writerows(results)
    with (output / "pass-table.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "timeline",
                "size",
                "mode",
                "renderer",
                "passed",
                "word_arrivals",
                "missed_200ms",
                "queue_median_ms",
                "queue_max_ms",
            )
        )
        writer.writerows(cases)
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--timeline", choices=TIMELINES, action="append")
    parser.add_argument("--preset", choices=PRESETS, action="append")
    parser.add_argument("--pictures", type=Path)
    args = parser.parse_args()
    raise SystemExit(
        0
        if run(
            args.output,
            args.timeline or list(TIMELINES),
            args.preset or list(PRESETS),
            args.pictures,
            additional=not (args.timeline or args.preset),
        )
        else 1
    )
