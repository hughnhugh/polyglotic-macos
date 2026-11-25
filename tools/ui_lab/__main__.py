"""The UI lab's command line (see the package's docstring).

python -m tools.ui_lab [--out DIR] [--gate] [--text-size PERCENT] [--language CODE]
python -m tools.ui_lab --app-text-size largest --out DIR   # the app's own: no goldens
python -m tools.ui_lab --language zh_CN --out DIR   # in another language: no goldens
python -m tools.ui_lab approve [--out DIR]   # the new parts' goldens
python -m tools.ui_lab approve --only STATE...   # only these states' (or patterns: ui_next.w4_*)
python -m tools.ui_lab prune                 # remove the goldens whose state is gone
python -m tools.ui_lab judge [--out DIR]     # the judge's kit (JUDGE.md)
python -m tools.ui_lab design [--accept]     # the design detector's findings (design.py)
python -m tools.ui_lab seen                  # the strings shown most: build/ui-lab/seen.tsv
python -m tools.ui_lab languages [--jobs 4]  # every other language, its checks gated

Approving never removes a golden; `prune` is the only step that does
(polyglotic-hq 258). On the user's PC, off CI, the command waits for the
shared Qt lock and 3.0 GB free, and holds the lock while it runs
(`tools/qt_lock.py`, polyglotic-hq 563).
"""

import argparse
import fnmatch
import os
import statistics
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial
from pathlib import Path

from PySide6.QtWidgets import QWidget

from polyglotic_desktop.ui import interface_language
from polyglotic_desktop.ui_next import languages, style
from tools import busy_pc, qt_lock, start_record, timing_record
from tools.i18n import __main__ as i18n
from tools.ui_lab import (
    bar_timing,
    caption_window,
    design,
    first_run,
    goldens,
    home,
    joined_window,
    judge,
    known,
    lab,
    learner_captions,
    lookup,
    new_parts,
    open_beta,
    pages,
    panels,
    presets,
    qt_parts,
    reference,
    seen,
    sidebar,
    text_sizes,
    transcript,
    typing_holds,
    use_presets,
)

COMMANDS = ("approve", "prune", "judge", "seen", "languages", "design")


def new_states() -> list[lab.State]:
    """Every state of the new interface (`ui_next`)."""
    new = new_parts.STATES + caption_window.STATES + lookup.STATES
    new += known.STATES + known.MAP_STATES
    new += joined_window.STATES + transcript.STATES
    new += panels.STATES + presets.STATES
    new += home.STATES + pages.STATES + qt_parts.STATES + first_run.STATES
    new += open_beta.STATES
    new += use_presets.STATES + bar_timing.STATES + learner_captions.STATES
    new += typing_holds.STATES
    return new + sidebar.STATES + text_sizes.STATES


def visual_states() -> list[lab.State]:
    """States used by checks, golden approval and the strings inventory."""
    return [state for state in new_states() if state.visual_checks]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv and argv[0] in COMMANDS else None
    parser = argparse.ArgumentParser(prog="python -m tools.ui_lab")
    parser.add_argument(
        "--out", type=Path, help="default build/ui-lab (the judge: build/ui-lab/judge)"
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="fail if a new part is over budget or fails a code check",
    )
    parser.add_argument(
        "--require-timings",
        action="store_true",
        help="with --gate: fail if busy PC load leaves any budget unmeasured",
    )
    parser.add_argument(
        "--text-size",
        type=int,
        default=100,
        help="Windows' Text size to simulate, 100-225 (the goldens are at 100)",
    )
    parser.add_argument(
        "--app-text-size",
        default="normal",
        choices=list(style.APP_TEXT_SIZES),
        help="the app's own text size, Settings > App (the goldens are at normal)",
    )
    parser.add_argument(
        "--language",
        default=interface_language.ENGLISH,
        choices=sorted(interface_language.OFFERED),
        help="the interface's language (the goldens are English's: compared only in it)",
    )
    parser.add_argument(
        "--checks-only",
        action="store_true",
        help="with --gate: fail on the code checks (and goldens), not the budgets",
    )
    parser.add_argument(
        "--at-normal",
        action="store_true",
        help="leave out the states built at the app's other text sizes (text_sizes)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="languages: how many languages' runs at once (default 4)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="STATE",
        help="approve: only these states (names, or patterns such as ui_next.w4_words_*)",
    )
    parser.add_argument(
        "--accept",
        action="store_true",
        help="design: make every finding now the baseline (design_baseline.json)",
    )
    args = parser.parse_args(argv)
    if args.require_timings and not args.gate:
        parser.error("--require-timings needs --gate")
    if args.accept and command != "design":
        parser.error("--accept is for design")
    if args.only and command != "approve":
        parser.error("--only is for approve")
    if command == "approve" and args.app_text_size != "normal":
        parser.error("the goldens are at the app's normal text size")
    if command == "prune":
        return prune()
    i18n.build()  # the .qm files the states' text comes from (not committed: 0034)
    # the learner's own languages as the interface language's, never this
    # PC's: the pictures are the same on any machine and say nothing of
    # whose it is (polyglotic-hq 293)
    own = languages.own_targets([args.language.replace("_", "-")])
    languages.own_languages = lambda: own
    english = args.language == interface_language.ENGLISH
    out = args.out or Path("build/ui-lab")
    if args.text_size != 100:
        lab.use_text_size(args.text_size)
    if command == "approve":
        return approve(out, args.only)
    if command == "judge":
        out = args.out or Path("build/ui-lab/judge")
        judge.run(new_states(), out)
        print(f"The judge's kit: {out / 'judge.md'}")
        return 0
    if command == "design":
        return design_run(args.out or Path("build/ui-lab/design"), args.accept)
    if command == "seen":
        if args.language != interface_language.ENGLISH:
            parser.error("seen runs in English: the strings are matched as written")
        return see(args.out or Path("build/ui-lab/seen"))
    if command == "languages":
        return every_language(
            args.out or Path("build/ui-lab/languages"), args.jobs, args.app_text_size
        )
    at_100 = args.text_size == 100 and args.app_text_size == "normal"
    golden_store = goldens.GOLDENS if at_100 and english else None
    selected = visual_states() if args.checks_only else new_states()
    states = at_app_text_size(selected, args.app_text_size)
    if args.at_normal:  # not text_sizes' own states, built at the other sizes
        other_sizes = {s.name for s in text_sizes.STATES}
        states = [s for s in states if s.name not in other_sizes]
    results = lab.run(states, out, golden_store, args.language)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:  # in CI: the table on the run's page
        with open(summary, "a", encoding="utf-8") as page:
            page.write(lab.markdown(results))
    unmeasured = [result.state for result in results if result.timing_unmeasured]
    for state in unmeasured:
        line = f"{state}: timing not measured (busy); every try was at or above {busy_pc.UI_TIMING_MAX_BUSY:.0%} PC load"
        print(line, file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=UI timing not measured (busy)::{line}")
    over = [
        f"{result.state}: {action}"
        for result in results
        if result.gated
        for action in result.over_budget()
    ]
    if args.gate and not args.checks_only:
        of = timing_record.kind(args.text_size, args.app_text_size, args.language)
        over = judged_beside_main(results, over, of)
    failed = [
        f"{result.state}: {finding.check} - {finding.where}: {finding.detail}"
        for result in results
        if result.gated
        for finding in result.failed_checks()
    ]
    differ = [
        f"{result.state}: {result.golden.describe()}"
        for result in results
        if result.gated and result.golden is not None and result.golden.failed
    ]
    for line in over:
        print(f"over budget - {line}", file=sys.stderr)
    for line in failed:
        print(f"check failed - {line}", file=sys.stderr)
    for line in differ:
        print(f"golden - {line}", file=sys.stderr)
    # the design detector, gated where its baseline was made: English at 100 %
    # and the app's Normal
    new_design = design_gate(results) if golden_store is not None else []
    for line in new_design:
        print(f"design - {line}", file=sys.stderr)
    (out / "design.md").write_text(judge.design_markdown(results), encoding="utf-8")
    if differ:
        note = goldens.machine_note()
        print(
            "If intended: `uv run python -m tools.ui_lab approve` on the user's PC,"
            " then commit tools/ui_lab/goldens/." + (f" Note: {note}." if note else ""),
            file=sys.stderr,
        )
    gated_over = [] if args.checks_only else over
    required_unmeasured = unmeasured if args.require_timings else []
    said = (
        gate_failed(gated_over, failed, differ, new_design, required_unmeasured)
        if args.gate
        else None
    )
    if said:  # last, so a golden's long note doesn't hide the rest (357)
        print(said, file=sys.stderr)
    return 1 if said else 0


def gate_failed(
    over: list[str],
    failed: list[str],
    differ: list[str],
    new_design: list[str],
    required_unmeasured: list[str] | None = None,
) -> str | None:
    """The gate's one line when it fails, every reason counted - or None
    when it passes. A golden that differed hid the design findings that
    failed beside it (polyglotic-hq 357)."""
    required_unmeasured = required_unmeasured or []
    if not (over or failed or differ or new_design or required_unmeasured):
        return None

    def counted(items: list[str], one: str, many: str) -> str:
        return f"{len(items)} {one if len(items) == 1 else many}"

    reasons = [
        counted(over, "over budget", "over budget"),
        counted(failed, "check failed", "checks failed"),
        counted(differ, "golden differs", "goldens differ"),
        counted(new_design, "new design finding", "new design findings"),
    ]
    if required_unmeasured:
        reasons.append(
            counted(
                required_unmeasured,
                "required timing not measured",
                "required timings not measured",
            )
        )
    return "gate failed: " + ", ".join(reasons)


def design_gate(results: list[lab.Result]) -> list[str]:
    """The design detector's findings on gated states that its baseline
    doesn't hold (decision 0140): new ones fail the gate, old ones are
    worked down."""
    found = [(r.state, f) for r in results if r.gated for f in r.design]
    return design.new(found, design.baseline())


def design_run(out: Path, accept: bool) -> int:
    """Every state, and `out/design.md`: the design detector's findings,
    new ones marked. `accept`: every finding now becomes the baseline. At
    the app's Normal text size, as the gate judges them (`design_gate`)."""
    results = lab.run(at_app_text_size(visual_states(), "normal"), out)
    (out / "design.md").write_text(judge.design_markdown(results), encoding="utf-8")
    found = [(r.state, f) for r in results if r.gated for f in r.design]
    if accept:
        print(f"{design.accept(found)} finding(s) in {design.BASELINE}")
    new = design.new(found, design.baseline())
    print(f"{len(found)} design finding(s), {len(new)} new: {out / 'design.md'}")
    return 0


def every_language(out: Path, jobs: int, app_text_size: str) -> int:
    """Every interface language but English, each in its own process (a
    language is installed once per process: `lab.run`), `jobs` at a time:
    every state's code checks gated - text clipped at the size its widget
    gives it, a glyph drawn as a box, Chinese in a Japanese face - not the
    budgets, which runs side by side would make slow (polyglotic-hq 294).
    At `app_text_size` only (Normal by default): the states `text_sizes`
    builds at the other sizes are left out - a language's fit is judged at
    Normal, and CI's Largest runs judge English and Chinese there. Each
    language's output is in `out/<code>.log`; what failed is printed."""
    out.mkdir(parents=True, exist_ok=True)
    others = [c for c in interface_language.OFFERED if c != interface_language.ENGLISH]

    def one(code: str) -> tuple[str, int, list[str]]:
        with (out / f"{code}.log").open("w", encoding="utf-8") as log:
            done = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.ui_lab",
                    "--gate",
                    "--checks-only",
                    "--at-normal",
                    "--language",
                    code,
                    "--app-text-size",
                    app_text_size,
                    "--out",
                    str(out / code),
                ],
                stdout=log,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        failures = [line for line in done.stderr.splitlines() if "check failed" in line]
        return code, done.returncode, failures or done.stderr.splitlines()[-3:]

    failed = []
    with ThreadPoolExecutor(max(1, jobs)) as pool:
        for code, returned, lines in pool.map(one, others):
            print(f"{code:6s} {'ok' if returned == 0 else 'FAILED'}", flush=True)
            if returned:
                failed.append(code)
                for line in lines:
                    print(f"  {code}: {line}", file=sys.stderr)
    return 1 if failed else 0


def see(out: Path) -> int:
    """Every state in English, and which strings each shows (`seen`):
    `build/ui-lab/seen.tsv`, the strings shown most first - the order of a
    reviewer's sheet (`python -m tools.i18n sheet ... --most-seen 60`)."""
    app = lab.application()
    app.setProperty("interface_language", interface_language.ENGLISH)
    interface_language.install(app, interface_language.ENGLISH)
    style.use_interface_language(interface_language.ENGLISH)
    _asked, found, shown = seen.recorder(app)  # installed last: asked first
    lab.run(visual_states(), out, shown=shown)
    print(f"{seen.SEEN}: {seen.write(found)} strings shown")
    return 0


def gated_timings(results: list[lab.Result]) -> dict[str, timing_record.Timing]:
    """Each gated action's median and longest run, by "state: action" - and
    each gated state's reference step (`reference.NAME`), timed just before
    its actions (decision 0169)."""
    found = {
        f"{result.state}: {action}": timing_record.Timing(
            statistics.median(timed.samples), max(timed.samples)
        )
        for result in results
        if result.gated and not result.timing_unmeasured
        for action, timed in result.actions.items()
        if timed.budget is not None and timed.samples
    }
    for result in results:
        if result.gated and result.reference_ms:
            step = result.reference_ms
            found[f"{result.state}: {reference.NAME}"] = timing_record.Timing(
                step, step
            )
    return found


LOAD_WINDOW = 5
"""The states either side of a state whose reference steps are taken with
its own for its load scale: a state's step alone varies by about a fifth
on one load (2026-11-16, polyglotic-hq 381), and eleven states are about
10-20 seconds of a run, short beside a busy spell of other jobs."""


def load_scales(
    timings: dict[str, timing_record.Timing], record: timing_record.Record
) -> dict[str, float]:
    """How much slower the PC is for each gated state, by name, than it
    was for main's run of it (decision 0169): the median reference step of
    the state and its `LOAD_WINDOW` neighbours either side, in the run's
    order, now - over the same states' median in main's record. A state
    missing from either has none: it is compared as 0136 has it."""
    suffix = f": {reference.NAME}"
    both = [
        (name.removesuffix(suffix), now.median_ms, record.timings[name].median_ms)
        for name, now in timings.items()
        if name.endswith(suffix) and name in record.timings
    ]
    scales = {}
    for i, (state, _now, _then) in enumerate(both):
        near = both[max(0, i - LOAD_WINDOW) : i + LOAD_WINDOW + 1]
        then = statistics.median(t for _s, _n, t in near)
        if then > 0:
            scales[state] = statistics.median(n for _s, n, _t in near) / then
    return scales


def judged_beside_main(
    results: list[lab.Result], over: list[str], of: str
) -> list[str]:
    """The actions over budget that fail the gate (decision 0136). On main,
    every one, and main's timings are kept as its record. On a pull
    request, those slower than main's record (`timing_record.SLOWER`) at
    like load - main's timings scaled by the reference steps now over then
    (`load_scales`, decision 0169) - or with none; the rest are over their
    budget as main is: said, as a warning on the run's page, and not
    failed."""
    timings = gated_timings(results)
    if start_record.on_main():
        timing_record.save(of, timings, os.environ.get("GITHUB_SHA", ""))
        return over
    record = timing_record.load(of)
    if record is None:
        return over
    scales = load_scales(timings, record)
    failing, as_main = [], []
    for name in over:
        main = record.timings.get(name)
        scale = scales.get(name.split(": ", 1)[0], 1.0)
        if main is None or timings[name].slower_than(main.scaled(scale)):
            failing.append(name)
            if main is not None:
                line = _beside(name, timings, record, scale)
                print(f"slower than main's - {line}", file=sys.stderr)
        else:
            as_main.append(_beside(name, timings, record, scale))
    for line in as_main:
        print(f"over its budget as main is - {line}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=Over its budget as main is::{line}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and as_main:
        with open(summary, "a", encoding="utf-8") as page:
            page.write(
                "\n### Over its budget as main is (not this change: decision 0136)\n\n"
                + "".join(f"- {line}\n" for line in as_main)
            )
    return failing


def _beside(
    name: str,
    timings: dict[str, timing_record.Timing],
    record: timing_record.Record,
    scale: float,
) -> str:
    """`name`'s timing now beside main's record of it, and the load scale."""
    now, main = timings[name], record.timings[name]
    return (
        f"{name} - median {now.median_ms:.1f} ms, longest"
        f" {now.longest_ms:.1f}; main's ({record.commit[:8]}) median"
        f" {main.median_ms:.1f}, longest {main.longest_ms:.1f}; the PC"
        f" {scale:.2f}x as slow as for main's (the reference step)"
    )


def at_app_text_size(states: list[lab.State], size: str) -> list[lab.State]:
    """`states`, each begun at the app's text size `size` (Settings > App):
    set again before every state, so none runs at what one before it left
    (a state of `text_sizes` sets its own, and leaves Normal behind it)."""

    def begun(run: Callable[[lab.Lab], QWidget], each: lab.Lab) -> QWidget:
        style.use_app_text_size(size)
        return run(each)

    return [replace(s, run=partial(begun, s.run)) for s in states]


def chosen(states: list[lab.State], only: list[str] | None) -> list[lab.State]:
    """The states `only` names (names or patterns), or all of them. A name
    or pattern that matches no state is an error: nothing is run."""
    if not only:
        return states
    unmatched = [
        name for name in only if not fnmatch.filter([s.name for s in states], name)
    ]
    if unmatched:
        raise SystemExit(f"no state is called {', '.join(unmatched)}")
    return [s for s in states if any(fnmatch.fnmatchcase(s.name, n) for n in only)]


def approve(out: Path, only: list[str] | None = None) -> int:
    """Every state of the new interface run - or only those `only` names -
    and each picture that differs from its golden (or has none) becomes its
    golden. No golden is removed: `prune` does that. At the app's Normal
    text size, as the gate photographs them, whatever this process had."""
    states = visual_states()
    results = lab.run(at_app_text_size(chosen(states, only), "normal"), out)
    pictures = {r.state: r.photo for r in results if r.photo is not None}
    changes = goldens.approve(pictures)
    for line in changes:
        print(line)
    print(
        f"{len(changes)} golden(s) changed in {goldens.GOLDENS}"
        if changes
        else "Every golden already matches."
    )
    if gone := goldens.stale(s.name for s in states):
        print(
            f"{len(gone)} golden(s) whose state is gone, kept: "
            "`python -m tools.ui_lab prune` removes them."
        )
    return 0


def prune() -> int:
    """The goldens whose state is gone, removed - by the states' names, so
    nothing is drawn and a state that failed to draw keeps its golden."""
    changes = goldens.remove_stale(s.name for s in visual_states())
    for line in changes:
        print(line)
    print(f"{len(changes)} golden(s) removed." if changes else "No golden is stale.")
    return 0


def locked(argv: list[str] | None = None) -> int:
    """`main`, holding the shared Qt lock on the user's PC once it's free
    and the PC has 3.0 GB free (`tools/qt_lock.py`, polyglotic-hq 563);
    `languages`' runs, each its own process, run under it. Off the PC, or
    on CI, `main` at once."""
    args = sys.argv[1:] if argv is None else argv
    try:
        with qt_lock.held(" ".join(["tools.ui_lab", *args])):
            return main(argv)
    except qt_lock.GaveUp as why:
        print(why, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(locked())
