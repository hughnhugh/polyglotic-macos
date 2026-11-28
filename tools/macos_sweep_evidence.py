"""Run the settings sweep and collect its evidence on the hosted Mac."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tools.macos_ui_lab import hosted_mac

REPORT_WAIT_SECONDS = 30
"""Maximum wait after a fatal signal. macOS writes the report asynchronously."""


def report_pid(report: Path) -> int | None:
    """Read the crashed process ID from a modern or legacy macOS report."""
    try:
        contents = report.read_text(encoding="utf-8")
        if report.suffix == ".ips":
            # A metadata JSON line precedes the crash payload.
            metadata, _, payload = contents.partition("\n")
            if json.loads(metadata)["bug_type"] == "309":
                return int(json.loads(payload)["pid"])
            return None
        match = re.search(r"^Process:.*\[(\d+)\]\s*$", contents, re.MULTILINE)
        return int(match[1]) if match else None
    except (OSError, ValueError, KeyError, TypeError):
        # An unfinished report, or another kind of diagnostic.
        return None


def collect_report(reports: Path, before: set[Path], pid: int, out: Path) -> None:
    deadline = time.monotonic() + REPORT_WAIT_SECONDS
    while True:
        for report in {*reports.glob("*.ips"), *reports.glob("*.crash")} - before:
            if report_pid(report) == pid:
                shutil.copyfile(report, out / f"native-crash{report.suffix}")
                return
        if time.monotonic() >= deadline:
            print(f"No macOS crash report appeared for sweep PID {pid}", flush=True)
            return
        time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--dictionaries", type=Path)
    parser.add_argument("--limit", type=float, help="sweep time limit in seconds")
    args = parser.parse_args(argv)
    if not hosted_mac():
        raise SystemExit("Requires a GitHub-hosted Mac")
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="settings-qa-") as temp:
        folder = Path(temp)
        dictionaries = args.dictionaries
        if dictionaries is None:
            from tests.ui.test_check_install import sample_dictionaries

            dictionaries = sample_dictionaries(folder / "dictionaries")
        command = [
            sys.executable,
            "-m",
            "tools.macos_settings_sweep",
            str(folder),
            "--dictionaries",
            str(dictionaries),
        ]
        if args.limit is not None:
            command.extend(["--limit", str(args.limit)])
        reports = Path.home() / "Library/Logs/DiagnosticReports"
        before = set(reports.iterdir()) if reports.is_dir() else set()
        with subprocess.Popen(command) as sweep:
            code = sweep.wait()
        for name in ("*.png", "sweep-checks.json", "checks.json", "sweep.json"):
            for file in folder.glob(name):
                shutil.copyfile(file, out / file.name)
        if code:
            for name in ("stacks.txt", "data/logs/crash.log"):
                stack = folder / name
                if stack.is_file() and stack.stat().st_size:
                    shutil.copyfile(stack, out / stack.name)
        if code < 0:
            collect_report(reports, before, sweep.pid, out)
            return 128 - code
        return code


if __name__ == "__main__":
    raise SystemExit(main())
