"""Run the settings sweep and collect its pictures and verdicts on the hosted Mac."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.macos_ui_lab import hosted_mac


def main(out: Path) -> int:
    if not hosted_mac():
        raise SystemExit("Requires a GitHub-hosted Mac")
    with tempfile.TemporaryDirectory(prefix="settings-qa-") as temp:
        folder = Path(temp)
        from tests.ui.test_check_install import sample_dictionaries

        dictionaries = sample_dictionaries(folder / "dictionaries")
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.macos_settings_sweep",
                str(folder),
                "--dictionaries",
                str(dictionaries),
            ],
            check=False,
        )
        out.mkdir(parents=True, exist_ok=True)
        for name in ("*.png", "sweep-checks.json", "checks.json", "sweep.json"):
            for file in folder.glob(name):
                shutil.copyfile(file, out / file.name)
        return run.returncode


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
