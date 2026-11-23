"""A file can reduce its count; an update cannot silently raise the ceiling."""

import json
from pathlib import Path

import pytest

from tools import literals


def test_flags_numbers_colours_tuples_and_function_values() -> None:
    rows = literals.findings("""
A = -5
B: str = '#aabbcc'
C = (0, 2)
D = tunable('area.d', 30, 'pixels', (2, 100))
E = 5  # constant: wire format
def f():
    return -2, -1, 1, 2, 0.5, 100, 34, 3  # no reason
""")
    assert [(row.value, row.scope) for row in rows] == [
        ("-5", "module"),
        ("'#aabbcc'", "module"),
        ("(0, 2)", "module"),
        ("-2", "f"),
        ("34", "f"),
        ("3", "f"),
    ]


def test_warning_and_update_only_lower_a_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    for part in ("ui", "core/lexicon", "connection"):
        (literals.PACKAGE / part).mkdir(parents=True)
    for name in (
        "ui/view.py",
        "core/lexicon/data.py",
        "connection/tls.py",
        "ui/glyphs.py",
    ):
        (literals.PACKAGE / name).write_text("A = 35\nB = 22\n")
    (literals.PACKAGE / "main.py").write_text("")
    literals.BASELINE.parent.mkdir()
    literals.BASELINE.write_text('{"ui/view.py": 1, "ui/removed.py": 3}')
    assert literals.main(["--warn"]) == 0
    assert "ui/view.py" in capsys.readouterr().out
    assert literals.main(["--update"]) == 1
    assert json.loads(literals.BASELINE.read_text()) == {"ui/view.py": 1}
    (literals.PACKAGE / "ui/view.py").write_text("")
    assert literals.main(["--update"]) == 0
    assert json.loads(literals.BASELINE.read_text()) == {}


def test_a_baseline_increase_cannot_hide_a_new_literal_on_a_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import subprocess

    monkeypatch.chdir(tmp_path)
    (literals.PACKAGE / "ui").mkdir(parents=True)
    (literals.PACKAGE / "main.py").write_text("")
    feature = literals.PACKAGE / "ui" / "view.py"
    feature.write_text("OLD = 35\n")
    subprocess.run(["git", "init", "--quiet"], check=True)
    subprocess.run(["git", "add", "src"], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "base",
        ],
        check=True,
    )
    feature.write_text("OLD = 35\nNEW = 22\n")
    literals.BASELINE.parent.mkdir()
    literals.BASELINE.write_text('{"ui/view.py": 2}')
    assert literals.main(["--base", "HEAD"]) == 1
    printed = capsys.readouterr().out
    assert "22 in module" in printed and "35 in module" not in printed
