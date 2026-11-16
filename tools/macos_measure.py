"""What a GitHub macOS machine allows, measured for Mac capture (polyglotic-hq
410, for 411 and the project after it): reported, never failing the job.

    uv run --no-sync python -m tools.macos_measure OUT.json [--app dist/Polyglotic.app]
    uv run --no-sync python -m tools.macos_measure OUT.json --dry-run   # any OS: the commands

1. The machine: macOS's version, the chip, System Integrity Protection.
2. Sound devices before and after installing BlackHole (a virtual sound
   device: the image has none of its own, 408) and restarting Core Audio
   (`launchctl kickstart`, never a kill by name).
3. Whether a system-audio permission (`kTCCServiceAudioCapture`, what a
   Core Audio tap needs) can be written to the permission databases
   (TCC) - the system's with sudo, the user's without - for the runner's
   agent (what a program started from the job counts as) and for the
   packed app's identifier, read back after. The image writes its own
   grants that way (actions/runner-images' configure-tccdb-macos.sh);
   whether macOS then honours one is for a tap to show (411).
4. With `--app`: the packed app's designated requirement (what macOS keeps
   a permission under: an ad-hoc build's hash changes with every build)
   and Gatekeeper's verdict on it.

Nothing here touches a microphone or records anything.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tools.package.build import BUNDLE_ID

SYSTEM_TCC = "/Library/Application Support/com.apple.TCC/TCC.db"
USER_TCC = str(Path.home() / "Library/Application Support/com.apple.TCC/TCC.db")
SERVICE = "kTCCServiceAudioCapture"
AGENT = "/opt/hca/hosted-compute-agent"
"""The runner's agent: the process macOS holds responsible for what a job
starts (the image grants it the microphone)."""
CLIENTS = ((AGENT, 1), (BUNDLE_ID, 0))
COREAUDIO = "system/com.apple.audio.coreaudiod"
GRANTED = (
    "SELECT service, client, auth_value FROM access"
    f" WHERE service IN ('{SERVICE}', 'kTCCServiceMicrophone');"
)
"""The grants already there: the image's, for the microphone."""  # (client, 1 for a path, 0 for a bundle ID)


def grant(client: str, client_type: int, now: int, allowed: bool = True) -> str:
    """An `access` row allowing `SERVICE` - or denying it, `allowed` False,
    as a learner's "Don't Allow" leaves it - in the image's own form (17
    columns: service, client, client type, allowed (2) or denied (0), the
    reason (4, set by the system; 2, the user's answer), version, no code
    requirement, ..., the time)."""
    answer = "2,4" if allowed else "0,2"
    values = (
        f"'{SERVICE}','{client}',{client_type},{answer},1,NULL,NULL,NULL,'UNUSED',"
        f"NULL,0,{now},NULL,NULL,'UNUSED',{now}"
    )
    return f"INSERT OR REPLACE INTO access VALUES({values});"


def read_back(client: str) -> str:
    return (
        "SELECT service, client, auth_value FROM access"
        f" WHERE service = '{SERVICE}' AND client = '{client}';"
    )


def plan(app: Path | None, now: int) -> list[tuple[str, list[str], int]]:
    """Each step: its name, its command, its time limit in seconds."""
    restart = ["sudo", "launchctl", "kickstart", "-k", COREAUDIO]
    already = ["sudo", "sqlite3", SYSTEM_TCC, GRANTED]
    steps: list[tuple[str, list[str], int]] = [
        ("macos", ["sw_vers"], 20),
        ("chip", ["uname", "-m"], 20),
        ("sip", ["csrutil", "status"], 20),
        ("devices_before", ["system_profiler", "SPAudioDataType", "-json"], 120),
        ("blackhole", ["brew", "install", "--cask", "blackhole-2ch"], 600),
        ("coreaudio_restart", restart, 60),
        ("devices_after", ["system_profiler", "SPAudioDataType", "-json"], 120),
        ("tcc_before", already, 30),
    ]
    for client, kind in CLIENTS:
        name = "agent" if kind == 1 else "app"
        steps += [
            (f"tcc_system_write_{name}",
             ["sudo", "sqlite3", SYSTEM_TCC, grant(client, kind, now)], 30),
            (f"tcc_system_read_{name}",
             ["sudo", "sqlite3", SYSTEM_TCC, read_back(client)], 30),
            (f"tcc_user_write_{name}", ["sqlite3", USER_TCC, grant(client, kind, now)], 30),
            (f"tcc_user_read_{name}", ["sqlite3", USER_TCC, read_back(client)], 30),
        ]  # fmt: skip
    if app is not None:
        steps += [
            ("app_requirement", ["codesign", "--display", "--requirements", "-", str(app)], 30),
            ("app_gatekeeper", ["spctl", "--assess", "--type", "execute", "-vv", str(app)], 60),
        ]  # fmt: skip
    return steps


def run(command: list[str], seconds: int) -> dict[str, Any]:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=seconds,
                              check=False)  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as problem:
        return {"ok": False, "said": f"{type(problem).__name__}: {problem}"}
    return {
        "ok": done.returncode == 0,
        "code": done.returncode,
        "out": done.stdout.strip()[-3000:],
        "said": done.stderr.strip()[-1500:],
    }


def device_names(profile: str) -> list[str]:
    """The sound devices `system_profiler SPAudioDataType -json` lists."""
    try:
        found = json.loads(profile)
    except ValueError:
        return []
    names = []
    for group in found.get("SPAudioDataType", []):
        for item in group.get("_items", []):
            names.append(str(item.get("_name", "?")))
    return names


def summary(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The answers 411 needs, from the steps' results."""

    def written(name: str) -> bool:
        return steps.get(f"tcc_{name}", {}).get("ok", False) and SERVICE in steps.get(
            f"tcc_{name.replace('write', 'read')}", {}
        ).get("out", "")

    after = device_names(steps.get("devices_after", {}).get("out", ""))
    return {
        "sip": steps.get("sip", {}).get("out"),
        "devices_before": device_names(steps.get("devices_before", {}).get("out", "")),
        "devices_after": after,
        "blackhole": any("BlackHole" in name for name in after),
        "system_audio_grant_written": {
            f"{db}_{who}": written(f"{db}_write_{who}")
            for db in ("system", "user")
            for who in ("agent", "app")
        },
        "app_requirement": steps.get("app_requirement", {}).get("said")
        or steps.get("app_requirement", {}).get("out"),
        "app_gatekeeper": steps.get("app_gatekeeper", {}).get("said"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.macos_measure")
    parser.add_argument("out", type=Path)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print the commands")
    args = parser.parse_args(argv)
    steps = plan(args.app, int(time.time()))
    if args.dry_run:
        for name, command, seconds in steps:
            print(f"{name} ({seconds} s): {' '.join(command)}")
        return 0
    results: dict[str, dict[str, Any]] = {}
    for name, command, seconds in steps:
        results[name] = run(command, seconds)
        if name == "coreaudio_restart":
            time.sleep(5)  # Core Audio back, and BlackHole's driver loaded
        print(f"{name}: {'ok' if results[name]['ok'] else 'not ok'}", flush=True)
    report = {"summary": summary(results), "steps": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report["summary"], indent=1))
    return 0  # measured, never failed


if __name__ == "__main__":
    sys.exit(main())
