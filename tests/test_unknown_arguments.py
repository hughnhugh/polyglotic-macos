"""An option the app doesn't know ends it at once, with code 2 and a line
in its log - never a box, and nothing opened (polyglotic-hq 569). On
2026-11-20 a packed 0.1.9 was given 0.1.10's `--check-release`: argparse's
own refusal went to a console the installed app hasn't got, so nothing
said why it stopped."""

import os
import subprocess
import sys
from pathlib import Path

from polyglotic_desktop import main


def test_an_option_it_doesnt_know_ends_it_with_a_log_line(tmp_path: Path) -> None:
    data = tmp_path / "data"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "polyglotic_desktop.main",
            "--data",
            str(data),
            # nothing real, should it start after all
            "--server",
            "http://127.0.0.1:9",
            "--credentials",
            "Polyglotic-test-never-written",
            "--updates",
            str(tmp_path / "no-feed"),
            # one a later version might add (0.1.10 knows `--check-release`,
            # 563, the one 0.1.9 was given)
            "--check-from-the-future",
            str(tmp_path / "secret-569" / "report.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        timeout=120,  # a box would wait for a click
    )

    assert run.returncode == 2, run.stderr[-2000:]
    log = (data / "logs" / "polyglotic.log").read_text(encoding="utf-8")
    said = (
        "not started: the command line has --check-from-the-future this version"
        " doesn't know (2 arguments it doesn't know in all; exit 2)"
    )
    assert said in log
    assert said in run.stderr  # from source, the console too
    assert "secret-569" not in log  # a value may be a path or text: never logged
    assert not (data / "settings.json").exists()  # nothing opened


def test_known_options_and_the_installers_hooks_go_on(tmp_path: Path) -> None:
    for given in (
        [],
        ["--in-tray", "--data", str(tmp_path), "--basic-dictionaries"],
        ["--check-release", str(tmp_path / "report.json")],  # 563's, known here
        ["--veloapp-install", "0.1.10"],  # Velopack's, for run_installer_hooks
    ):
        main.refuse_unknown_arguments(given)  # returns: no SystemExit
