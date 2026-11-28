"""Tables from a recording: what the replay saw, by surface.

- `paths_table`: which layout path laid captions out on each surface and in
  each Long lines arrangement (827's SPEC, section 1.1, as the code runs
  today rather than as it was read on 2026-11-24).
- `rules_table`: on how many runs of each surface each rule's property
  held, for a recording made with `record --properties`.
"""

from collections import Counter
from typing import Any

from tools.scene_replay.drive import SURFACES, Setup

COLUMNS = (
    "A clause rows (Qt may wrap)",
    "A clause rows (one line)",
    "B the composer",
    "C Video tracks",
    "the pour",
)

MODES = {
    "panel": "Caption window: Everyday, Conversation, Learning (Instant)",
    "cards": "Caption window: Steady, card stack",
    "zones": "Caption window: Steady, settled transcript and live zone",
    "joined": "Joined window (each column a caption window, Instant)",
    "video-instant": "Video, Instant",
    "video-scrolling": "Video, Scrolling",
    "transcript": "Transcript window",
}


def _setup(run: dict[str, Any]) -> Setup:
    return Setup.named(run["run"].partition("@")[2])


def paths_table(recorded: dict[str, Any]) -> str:
    seen: dict[tuple[str, bool], Counter[str]] = {}
    total: Counter[tuple[str, bool]] = Counter()
    for run in recorded["runs"]:
        setup = _setup(run)
        key = (setup.surface, setup.paired)
        total[key] += 1
        seen.setdefault(key, Counter()).update(run.get("paths", ()))
    rows = [
        "| Surface and mode | Long lines | Runs | " + " | ".join(COLUMNS) + " |",
        "|---|---|---:|" + "---:|" * len(COLUMNS),
    ]
    for surface in SURFACES:
        for paired in (False, True):
            key = (surface, paired)
            if key not in total:
                continue
            cells = [str(seen[key].get(column, 0) or "-") for column in COLUMNS]
            rows.append(
                f"| {MODES[surface]} | {'Display new lines' if paired else 'Grouped'}"
                f" | {total[key]} | " + " | ".join(cells) + " |"
            )
    return "\n".join(rows) + "\n"


def rules_table(recorded: dict[str, Any], rules: list[str]) -> str:
    held: dict[str, Counter[str]] = {surface: Counter() for surface in SURFACES}
    total: Counter[str] = Counter()
    for run in recorded["runs"]:
        surface = _setup(run).surface
        total[surface] += 1
        for rule in rules:
            held[surface][rule] += rule not in run.get("broken", {})
    rows = [
        "| Rule | " + " | ".join(SURFACES) + " |",
        "|---|" + "---:|" * len(SURFACES),
    ]
    for rule in rules:
        cells = [f"{held[s][rule]}/{total[s]}" for s in SURFACES]
        rows.append(f"| `{rule}` | " + " | ".join(cells) + " |")
    return "\n".join(rows) + "\n"
