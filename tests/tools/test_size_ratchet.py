from pathlib import Path

from tools import size_ratchet


def test_warns_only_for_large_files_over_growth_allowance() -> None:
    baseline = {
        "src/already_large.py": 900,
        "src/became_large.py": 790,
        "src/small.py": 100,
    }
    sizes = {
        "src/already_large.py": 951,
        "src/became_large.py": 841,
        "src/exactly_allowed.py": 850,
        "src/small.py": 700,
    }

    messages = size_ratchet.warnings(sizes, {**baseline, "src/exactly_allowed.py": 800})

    assert messages == [
        "src/already_large.py grew by 51 lines, from 900 to 951 (growth allowance 50)",
        "src/became_large.py grew by 51 lines, from 790 to 841 (growth allowance 50)",
    ]


def test_warns_when_a_new_file_passes_large_file_limit() -> None:
    assert size_ratchet.warnings(
        {"src/new_large.py": 801, "src/new_at_limit.py": 800}, {}
    ) == ["src/new_large.py is a new large file at 801 lines (limit 800)"]


def test_update_rewrites_baseline_and_command_remains_warn_only(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "small.py").write_text("one\ntwo\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(size_ratchet, "SOURCE_ROOT", source)
    monkeypatch.setattr(size_ratchet, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(size_ratchet, "BASELINE", baseline)

    assert size_ratchet.main(["--update"]) == 0
    assert baseline.read_text(encoding="utf-8") == '{\n  "src/small.py": 2\n}\n'
    assert "Top 1 Python source files by size:" in capsys.readouterr().out

    (source / "small.py").write_text("line\n" * 801, encoding="utf-8")
    assert size_ratchet.main([]) == 0
    assert "::warning file=src/small.py::" in capsys.readouterr().out


def test_report_prints_annotation_and_largest_files_first(capsys) -> None:
    size_ratchet.print_report({"src/b.py": 801, "src/a.py": 900}, {"src/a.py": 849})

    output = capsys.readouterr().out.splitlines()
    assert output[0].startswith("::warning file=src/a.py::")
    assert output[-2:] == ["   900  src/a.py", "   801  src/b.py"]
