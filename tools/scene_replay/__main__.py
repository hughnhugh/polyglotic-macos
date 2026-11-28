"""The display's replay and rulebook (polyglotic-hq 933, ADR-009; unit display-0).

    uv run python -m tools.scene_replay record            # play the matrix once
    uv run python -m tools.scene_replay diff --base origin/main --candidate .
    uv run python -m tools.scene_replay frames lines/a@panel
    uv run python -m tools.scene_replay paths             # modes against layout paths
    uv run python -m tools.scene_replay deciding --check  # the deciding functions
    uv run python -m tools.scene_replay rulebook --check  # the rulebook and its net

`record` plays every caption stream into every surface and set-up
(`matrix`) on the patched clock and keeps a digest of each run's frames.
`diff` records two trees and says whether a learner could see a difference,
to 1/64 px. Both open real Qt windows offscreen: run them under the Qt lock
(`tools/qt_lock.py`; polyglotic-hq RULES #42).
"""

import argparse
import fnmatch
import io
import itertools
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
JOBS = 2
"""Worker processes for one tree's recording. A diff records two trees at
once, so four processes: the most a long CPU run may use (RULES #49)."""
BELOW_NORMAL = 0x00004000
"""Windows' below-normal priority class, for the workers (RULES #49)."""


def matrix() -> list[str]:
    """Every run, as `stream@setup`: each stream into each surface, with
    readings off and on, at the stream's width and narrow, and in both
    Long lines arrangements (which the transcript does not have)."""
    from tools.scene_replay import streams
    from tools.scene_replay.drive import SURFACES, Setup

    runs = []
    for stream in streams.names():
        for surface in SURFACES:
            for readings, narrow, paired in itertools.product((False, True), repeat=3):
                if paired and surface == "transcript":
                    continue
                runs.append(f"{stream}@{Setup(surface, readings, narrow, paired).name}")
    return runs


def _chosen(only: Sequence[str]) -> list[str]:
    runs = matrix()
    if not only:
        return runs
    return [run for run in runs if any(fnmatch.fnmatch(run, each) for each in only)]


def _use_src(src: str | None) -> str:
    """Make `polyglotic_desktop` come from `src` (None: wherever it is
    installed from), and say where it came from."""
    if src:
        sys.path.insert(0, str(Path(src).resolve()))
    import polyglotic_desktop

    found = Path(polyglotic_desktop.__file__).resolve().parent.parent
    if src and found != Path(src).resolve():
        raise SystemExit(f"asked for {src}, but polyglotic_desktop is {found}")
    return str(found)


def _made_with() -> dict[str, str]:
    import PySide6
    from PySide6.QtCore import qVersion

    return {
        "os": platform.system(),
        "python": platform.python_version(),
        "PySide6": PySide6.__version__,
        "Qt": qVersion(),
    }


def _play(
    run: str, plant: str | None, properties: bool, full: Path | None
) -> dict[str, Any]:
    from tools.scene_replay import drive, frames, plants, streams
    from tools.scene_replay.properties import PROPERTIES

    stream_name, _, setup_name = run.partition("@")
    paths: set[str] = set()
    with plants.planted(plant):
        played = list(
            drive.play(
                streams.load(stream_name), drive.Setup.named(setup_name), paths=paths
            )
        )
    summary = frames.summarise(run, played, sorted(paths)).to_plain()
    if properties:
        found = {rule: check(played) for rule, check in PROPERTIES.items()}
        summary["broken"] = {
            rule: [str(b) for b in broken[:3]]
            for rule, broken in found.items()
            if broken
        }
    if full is not None:
        full.mkdir(parents=True, exist_ok=True)
        name = run.replace("/", "_").replace("@", "__") + ".jsonl"
        with (full / name).open("w", encoding="utf-8", newline="\n") as out:
            before = None
            for frame in played:
                body = frames.body(frame)
                if body != before:
                    out.write(frames.to_json(frame) + "\n")
                    before = body
    return summary


def record(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    if args.shard is None and args.jobs > 1:
        return _record_in_workers(args)
    src = _use_src(args.src)
    runs = _chosen(args.only)
    if args.shard is not None:
        k, n = (int(x) for x in args.shard.split("/"))
        runs = runs[k::n]
    full = Path(args.full) if args.full else None
    done = [_play(run, args.plant, args.properties, full) for run in runs]
    result = {"made_with": _made_with() | {"src": src}, "runs": done}
    _write(args.out, result)
    if args.shard is None:
        _say_recorded(result, time.perf_counter() - started)
    return 0


def _write(out: str | None, result: dict[str, Any]) -> None:
    if out:
        Path(out).write_text(json.dumps(result, indent=1) + "\n", "utf-8", newline="\n")


def _say_recorded(result: dict[str, Any], took: float) -> None:
    runs = result["runs"]
    frames = sum(run["frames"] for run in runs)
    print(f"recorded {len(runs)} runs, {frames} frames, in {took:.0f} s")


def _worker(args: argparse.Namespace, shard: str, out: Path) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-m", "tools.scene_replay", "record"]
    command += ["--shard", shard, "--out", str(out), "--jobs", "1"]
    command += ["--src", args.src] if args.src else []
    command += ["--plant", args.plant] if args.plant else []
    command += ["--properties"] if args.properties else []
    command += ["--full", args.full] if args.full else []
    for each in args.only:
        command += ["--only", each]
    flags = BELOW_NORMAL if sys.platform == "win32" else 0
    return subprocess.Popen(command, cwd=ROOT, creationflags=flags)


def _record_in_workers(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="scene-replay-") as temp:
        outs = [Path(temp) / f"{k}.json" for k in range(args.jobs)]
        workers = [_worker(args, f"{k}/{args.jobs}", out) for k, out in enumerate(outs)]
        codes = [worker.wait() for worker in workers]
        if any(codes):
            print(f"a recording worker failed: exit codes {codes}", file=sys.stderr)
            return 1
        parts = [json.loads(out.read_text("utf-8")) for out in outs]
    order = {run: n for n, run in enumerate(_chosen(args.only))}
    runs = sorted(
        (run for part in parts for run in part["runs"]), key=lambda r: order[r["run"]]
    )
    result = {"made_with": parts[0]["made_with"], "runs": runs}
    _write(args.out, result)
    _say_recorded(result, time.perf_counter() - started)
    return 0


def _tree(where: str, temp: Path, name: str) -> Path:
    """The `src` folder of `where`: a checkout's, or a git revision's,
    unpacked into `temp`."""
    if Path(where, "src", "polyglotic_desktop").is_dir():
        return Path(where, "src").resolve()
    archive = subprocess.run(
        ["git", "archive", "--format=tar", where, "src"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    target = temp / name
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(target, filter="data")
    return target / "src"


def _record_tree(
    src: Path, out: Path, args: argparse.Namespace, plant: str | None
) -> subprocess.Popen[bytes]:
    command = [sys.executable, "-m", "tools.scene_replay", "record"]
    command += ["--src", str(src), "--out", str(out), "--jobs", str(args.jobs)]
    command += ["--plant", plant] if plant else []
    for each in args.only:
        command += ["--only", each]
    return subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL)


def _compare(base: dict[str, Any], candidate: dict[str, Any]) -> list[Any]:
    from tools.scene_replay.frames import Summary, first_difference

    theirs = {run["run"]: Summary.from_plain(run) for run in candidate["runs"]}
    found = []
    for run in base["runs"]:
        mine = Summary.from_plain(run)
        other = theirs.get(mine.run)
        if other is None:
            continue
        difference = first_difference(mine, other)
        if difference is not None:
            found.append(difference)
    return found


def diff(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    rounds = 2 if args.twice else 1
    with tempfile.TemporaryDirectory(prefix="scene-replay-") as name:
        temp = Path(name)
        trees = {
            "base": _tree(args.base, temp, "base"),
            "candidate": _tree(args.candidate, temp, "candidate"),
        }
        recorded: dict[str, list[dict[str, Any]]] = {"base": [], "candidate": []}
        for n in range(rounds):
            outs = {side: temp / f"{side}-{n}.json" for side in trees}
            workers = [
                _record_tree(
                    trees[side],
                    outs[side],
                    args,
                    args.plant if side == "candidate" else None,
                )
                for side in trees
            ]
            if any(worker.wait() for worker in workers):
                print("a recording failed", file=sys.stderr)
                return 2
            for side in trees:
                recorded[side].append(json.loads(outs[side].read_text("utf-8")))
        failed = False
        for side, takes in recorded.items():
            if len(takes) == 2:
                unsteady = _compare(takes[0], takes[1])
                if unsteady:
                    failed = True
                    print(f"NOT THE SAME TWICE: the {side} differs from itself")
                    for each in unsteady[:5]:
                        print("  " + each.describe())
        differences = _compare(recorded["base"][0], recorded["candidate"][0])
        runs = recorded["base"][0]["runs"]
        frames = sum(run["frames"] for run in runs)
        took = time.perf_counter() - started
        made = recorded["candidate"][0]["made_with"]
        where = f"{made['os']}, Qt {made['Qt']}"
        if differences:
            print(
                f"DIFFERENT: {len(differences)} of {len(runs)} runs differ"
                f" ({where}; {took:.0f} s)"
            )
            for each in differences[:10]:
                print("  " + each.describe())
            _explain(differences[0], trees, args, temp)
            return 1
        if failed:
            return 1
        twice = ", the same twice" if args.twice else ""
        print(
            f"identical: {len(runs)} runs, {frames} frames, to 1/64 px{twice}"
            f" ({where}; {took:.0f} s)"
        )
        return 0


def _explain(
    first: Any, trees: dict[str, Path], args: argparse.Namespace, temp: Path
) -> None:
    """Record the first differing run again in full on both sides, and say
    what differs in its first differing frame."""
    from tools.scene_replay import frames

    played: dict[str, dict[int, frames.Frame]] = {}
    for side, src in trees.items():
        full = temp / f"full-{side}"
        command = [sys.executable, "-m", "tools.scene_replay", "record", "--jobs", "1"]
        command += ["--src", str(src), "--only", first.run, "--full", str(full)]
        command += ["--plant", args.plant] if args.plant and side == "candidate" else []
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        (file,) = full.glob("*.jsonl")
        kept = [frames.from_json(line) for line in file.read_text("utf-8").splitlines()]
        played[side] = {frame.n: frame for frame in kept}

    def at(side: str, n: int) -> frames.Frame | None:
        earlier = [m for m in played[side] if m <= n]
        return played[side][max(earlier)] if earlier else None

    base, candidate = at("base", first.frame), at("candidate", first.frame)
    if base is None or candidate is None:
        return
    print(f"  in {first.run} at frame {first.frame}:")
    for line in itertools.islice(frames.explain(base, candidate), 8):
        print("    " + line)


def show_frames(args: argparse.Namespace) -> int:
    _use_src(args.src)
    from tools.scene_replay import drive, frames, plants, streams

    stream_name, _, setup_name = args.run.partition("@")
    before = None
    with plants.planted(args.plant):
        for frame in drive.play(
            streams.load(stream_name), drive.Setup.named(setup_name or "panel")
        ):
            body = frames.body(frame)
            if body != before:
                print(frames.to_json(frame))
                before = body
    return 0


def judge(args: argparse.Namespace) -> int:
    """Every rule over the whole matrix: it holds on each run of a surface
    it applies on, except the runs the rulebook says fail today - and those
    do fail (a fixed one is taken off the list, not left to rot)."""
    from tools.scene_replay import rulebook as book
    from tools.scene_replay.drive import Setup

    if args.recording:
        recorded = json.loads(Path(args.recording).read_text("utf-8"))
    else:
        with tempfile.TemporaryDirectory(prefix="scene-replay-") as temp:
            out = Path(temp) / "judged.json"
            command = [sys.executable, "-m", "tools.scene_replay", "record"]
            command += ["--properties", "--out", str(out), "--jobs", str(args.jobs)]
            subprocess.run(command, cwd=ROOT, check=True)
            recorded = json.loads(out.read_text("utf-8"))
    wrong = []
    for rule in book.load():
        held = failed = 0
        for run in recorded["runs"]:
            if Setup.named(run["run"].partition("@")[2]).surface not in rule.applies:
                continue
            broke = rule.id in run.get("broken", {})
            known = any(fnmatch.fnmatch(run["run"], each) for each in rule.fails_today)
            held += not broke
            failed += broke
            if broke and not known:
                wrong.append(
                    f"{rule.id}: broken in {run['run']}: {run['broken'][rule.id][0]}"
                )
        for each in rule.fails_today:
            hits = [
                run
                for run in recorded["runs"]
                if fnmatch.fnmatch(run["run"], each)
                and Setup.named(run["run"].partition("@")[2]).surface in rule.applies
            ]
            if hits and not any(rule.id in run.get("broken", {}) for run in hits):
                wrong.append(f"{rule.id}: {each} is listed as failing today, and holds")
        print(
            f"{rule.id}: held in {held} runs, broken in {failed} listed as failing today"
        )
    for each in wrong:
        print(each)
    return 1 if wrong else 0


def paths(args: argparse.Namespace) -> int:
    from tools.scene_replay import report

    recorded = json.loads(Path(args.recording).read_text("utf-8"))
    print(report.paths_table(recorded), end="")
    return 0


def deciding(args: argparse.Namespace) -> int:
    from tools.scene_replay import deciding as listing

    kept = ROOT / "tests" / "ui_next" / "rules" / "deciding.json"
    now = listing.as_json(ROOT)
    if args.write:
        kept.write_text(now, "utf-8", newline="\n")
        print(f"wrote {kept.relative_to(ROOT)}")
        return 0
    if args.check:
        if not kept.exists() or kept.read_text("utf-8") != now:
            print(
                "the deciding functions changed: run"
                " `python -m tools.scene_replay deciding --write` and see what joined"
            )
            return 1
        print("the deciding functions are as listed")
        return 0
    print(listing.table(ROOT), end="")
    return 0


def rulebook(args: argparse.Namespace) -> int:
    from tools.scene_replay import rulebook as book

    return book.main(args)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.scene_replay")
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--only", action="append", default=[], metavar="PATTERN")
        command.add_argument(
            "--plant", help="a planted fault (tools/scene_replay/plants.py)"
        )
        command.add_argument("--jobs", type=int, default=JOBS)

    one = commands.add_parser("record", help="play the matrix and keep its digests")
    common(one)
    one.add_argument(
        "--src", help="the src folder to play (default: the installed one)"
    )
    one.add_argument("--out", help="where to write the digests, as JSON")
    one.add_argument("--shard", help="K/N: only every Nth run from the Kth")
    one.add_argument("--full", help="a folder for each run's frames, as JSON lines")
    one.add_argument(
        "--properties", action="store_true", help="judge each run by the rules"
    )
    one.set_defaults(run=record)

    two = commands.add_parser("diff", help="compare two trees' replays to 1/64 px")
    common(two)
    two.add_argument("--base", required=True, help="a git revision or a checkout")
    two.add_argument("--candidate", required=True, help="a checkout or a git revision")
    two.add_argument(
        "--twice", action="store_true", help="and each side against itself"
    )
    two.set_defaults(run=diff)

    three = commands.add_parser("frames", help="print one run's frames")
    three.add_argument("run", help="stream@setup, such as lines/a@panel+narrow")
    three.add_argument("--src")
    three.add_argument("--plant")
    three.set_defaults(run=show_frames)

    four = commands.add_parser("paths", help="the modes against the layout paths")
    four.add_argument("recording", help="a `record --out` file")
    four.set_defaults(run=paths)

    seven = commands.add_parser("judge", help="every rule over the whole matrix")
    seven.add_argument("--recording", help="a `record --properties --out` file")
    seven.add_argument("--jobs", type=int, default=JOBS)
    seven.set_defaults(run=judge)

    five = commands.add_parser("deciding", help="the display's deciding functions")
    five.add_argument("--check", action="store_true")
    five.add_argument("--write", action="store_true")
    five.set_defaults(run=deciding)

    six = commands.add_parser("rulebook", help="the rulebook: write it or check it")
    six.add_argument("--check", action="store_true")
    six.add_argument("--write", action="store_true")
    six.add_argument(
        "--pictures", action="store_true", help="with --write: retake them"
    )
    six.add_argument("--rules", help="another rules.toml (the tests' planted faults)")
    six.add_argument("--book", help="another RULEBOOK.md folder")
    six.set_defaults(run=rulebook)

    args = parser.parse_args()
    os.chdir(ROOT)
    return int(args.run(args))


if __name__ == "__main__":
    raise SystemExit(main())
