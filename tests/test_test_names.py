"""Two test files of the same name in different folders both run
(polyglotic-hq 213; 209 found it: `tests/learning/test_coverage.py` beside
`tests/tools/test_coverage.py` stopped pytest collecting anything).

The test folders aren't packages, so pytest's default way of importing a
test file - by its bare name, its folder put on `sys.path` - gave both
the same module name. This repo's pytest options (pyproject.toml) import
each by its path instead (`--import-mode=importlib`), whatever folders
are added later. Checked by running pytest on two such files, with those
options and nothing else."""

import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_two_test_files_of_the_same_name_in_two_folders_both_run(
    tmp_path: Path,
) -> None:
    options = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = options["tool"]["pytest"]["ini_options"]["addopts"]
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = " + " ".join(addopts) + "\n", encoding="utf-8"
    )
    for folder in ("learning", "tools"):
        (tmp_path / "tests" / folder).mkdir(parents=True)
        (tmp_path / "tests" / folder / "test_coverage.py").write_text(
            f"def test_{folder}() -> None:\n    pass\n", encoding="utf-8"
        )

    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert ran.returncode == 0, ran.stdout[-2000:]
    assert "2 passed" in ran.stdout
