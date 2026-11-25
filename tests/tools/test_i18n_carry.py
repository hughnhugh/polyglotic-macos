"""Translations carried across an English rewrite remain safe drafts."""

import io
import subprocess
import sys
from pathlib import Path

import pytest
from tools.i18n import __main__ as i18n
from tools.i18n import carry, extract, ts


def _write(path: Path) -> None:
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
        '<TS version="2.1" language="de" sourcelanguage="en">\n'
        "<context><name>Home</name>\n"
        '<message><location filename="../src/home.py"/><source>Old wording</source>'
        "<translation>Alte Wörter</translation></message>\n"
        '<message><location filename="../src/home.py"/><source>Hello {name}</source>'
        "<translation>Hallo {name}</translation></message>\n"
        '<message><location filename="../src/home.py"/><source>Already new</source>'
        "<translation>Schon neu</translation></message>\n"
        '<message><location filename="../src/home.py"/><source>Old conflict</source>'
        "<translation>Alter Konflikt</translation></message>\n"
        "</context></TS>\n",
        encoding="utf-8",
    )


def test_carries_as_a_draft_keeps_finished_and_drops_broken_placeholders(
    tmp_path: Path,
) -> None:
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    changes = [
        carry.Change(("Home", "Old wording", ""), ("Home", "New wording", "")),
        carry.Change(("Home", "Hello {name}", ""), ("Home", "Hello {person}", "")),
        carry.Change(("Home", "Old conflict", ""), ("Home", "Already new", "")),
    ]
    counts = carry.carry_file(path, changes, 0, False)
    assert (counts.carried, counts.kept, counts.dropped) == (1, 1, 1)
    translations = ts.read(path).translations
    assert translations[("Home", "New wording", "")] == ts.Translation(
        ("Alte Wörter",), done=False
    )
    assert translations[("Home", "Already new", "")].done
    assert ("Home", "Hello {person}", "") not in translations


def test_carry_is_idempotent_and_dry_run_does_not_write(tmp_path: Path) -> None:
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    change = carry.Change(("Home", "Old wording", ""), ("Home", "New wording", ""))
    before = path.read_bytes()
    assert carry.carry_file(path, [change], 0, True).carried == 1
    assert path.read_bytes() == before
    assert carry.carry_file(path, [change], 0, False).carried == 1
    changed = path.read_bytes()
    assert carry.carry_file(path, [change], 0, False).carried == 0
    assert path.read_bytes() == changed


def test_map_format_and_moved_context(tmp_path: Path) -> None:
    mapping = tmp_path / "map.json"
    mapping.write_text('{"Home": {"Before": "After"}}', encoding="utf-8")
    assert carry.read_map(mapping) == [
        carry.Change(("Home", "Before", ""), ("Home", "After", ""))
    ]
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    moved = carry.Change(("Home", "Old wording", ""), ("Welcome", "New wording", ""))
    assert carry.carry_file(path, [moved], 0, False).carried == 1
    assert ts.read(path).translations[("Welcome", "New wording", "")].forms == (
        "Alte Wörter",
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, encoding="utf-8"
    )


def _tracked_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, before: str
) -> Path:
    source = tmp_path / "src" / "polyglotic_desktop"
    source.mkdir(parents=True)
    module = source / "home.py"
    module.write_text(before, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "base",
    )
    monkeypatch.setattr(extract, "REPO", tmp_path)
    monkeypatch.setattr(extract, "SOURCE", source)
    return module


_WRAPPER = (
    "from PySide6.QtCore import QCoreApplication\n"
    "def _tr(text: str) -> str:\n"
    '    return QCoreApplication.translate("Home", text)\n'
)


def _change(old: str, new: str) -> carry.Change:
    return carry.Change(("Home", old, ""), ("Home", new, ""))


def test_from_diff_matches_a_context_move_by_source_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _WRAPPER + 'def label():\n    return _tr("Old wording")\n'
    module = _tracked_module(tmp_path, monkeypatch, before)
    module.write_text(
        before.replace('"Home"', '"Welcome"').replace("Old wording", "New wording"),
        encoding="utf-8",
    )
    assert carry.from_diff("HEAD") == (
        [carry.Change(("Home", "Old wording", ""), ("Welcome", "New wording", ""))],
        [],
    )
    module.write_text(
        before.replace('"Home", text', '"Welcome",\n        text'),
        encoding="utf-8",
    )
    assert carry.from_diff("HEAD") == (
        [carry.Change(("Home", "Old wording", ""), ("Welcome", "Old wording", ""))],
        [],
    )


def test_from_diff_pairs_845_hunks_in_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _WRAPPER + (
        "def mic_button_tip(on: bool) -> str:\n"
        '    return _tr("Caption what I say: on") if on else _tr("Caption what I say: off")\n'
        "\ndef quiet_tip() -> str:\n"
        "    return _tr(\n"
        '        "Quiet view on or off: captions in quiet grey and gold, only your chosen "\n'
        '        "words in blue, no underlines - point at a word to see its partner"\n'
        "    )\n"
    )
    module = _tracked_module(tmp_path, monkeypatch, before)
    module.write_text(
        _WRAPPER
        + (
            "def mic_button_tip(on: bool) -> str:\n"
            '    return _tr("Show my speech here: on") if on else _tr("Show my speech here: off")\n'
            "\ndef quiet_tip() -> str:\n"
            "    return _tr(\n"
            '        "Quiet view: captions in grey and gold, only your chosen words in blue, no "\n'
            '        "underlines. Point at a word to see the word it\'s linked to"\n'
            "    )\n"
        ),
        encoding="utf-8",
    )
    assert carry.from_diff("HEAD") == (
        [
            _change("Caption what I say: on", "Show my speech here: on"),
            _change("Caption what I say: off", "Show my speech here: off"),
            _change(
                "Quiet view on or off: captions in quiet grey and gold, only your chosen "
                "words in blue, no underlines - point at a word to see its partner",
                "Quiet view: captions in grey and gold, only your chosen words in blue, no "
                "underlines. Point at a word to see the word it's linked to",
            ),
        ],
        [],
    )


def test_git_reads_utf8_from_a_renamed_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _WRAPPER + 'def label():\n    return _tr("日本語の設定")\n'
    module = _tracked_module(tmp_path, monkeypatch, before)
    renamed = module.with_name("新 home.py")
    _git(tmp_path, "mv", str(module), str(renamed))
    renamed.write_text(before.replace("日本語の設定", "日本語の表示"), encoding="utf-8")
    old_path = module.relative_to(tmp_path).as_posix()
    new_path = renamed.relative_to(tmp_path).as_posix()
    assert carry._changed_ranges("HEAD")[new_path].old_path == old_path
    assert [m.source for m in carry._base_messages("HEAD", [old_path])] == [
        "日本語の設定"
    ]
    assert carry.from_diff("HEAD") == ([_change("日本語の設定", "日本語の表示")], [])


def test_ambiguous_diff_is_refused_and_counted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _tracked_module(
        tmp_path,
        monkeypatch,
        _WRAPPER + 'def label():\n    return _tr("PC label"), _tr("Mac label")\n',
    )
    module.write_text(
        _WRAPPER + 'def label():\n    return _tr("Shared label")\n', encoding="utf-8"
    )
    changes, ambiguous = carry.from_diff("HEAD")
    assert changes == []
    assert len(ambiguous) == 1
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    assert carry.run(tmp_path, changes, ambiguous, False) == 1
    output = capsys.readouterr().out
    assert "no unique old source for Home: 'Shared label'" in output
    assert "ambiguous 1, total 1" in output


def test_run_finishes_every_catalog_with_cp1252_stdout_and_skips_english(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    german = tmp_path / "polyglotic_de.ts"
    french = tmp_path / "polyglotic_fr.ts"
    english = tmp_path / "polyglotic_en.ts"
    for path in (german, french, english):
        _write(path)
    before_english = english.read_bytes()
    output = io.BytesIO()
    stdout = io.TextIOWrapper(output, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)

    change = _change("Old wording", "New wording ⌘")
    assert carry.run(tmp_path, [change], ["New wording ⌘ is ambiguous"], False) == 1
    stdout.flush()

    assert change.new in ts.read(german).translations
    assert change.new in ts.read(french).translations
    assert english.read_bytes() == before_english
    report = output.getvalue().decode("cp1252")
    assert "de: carried 1" in report
    assert "fr: carried 1" in report
    assert "New wording \\u2318" in report
    assert "en:" not in report


def test_hunk_order_requires_matching_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _tracked_module(
        tmp_path,
        monkeypatch,
        _WRAPPER + 'def label():\n    return _tr("First {a}"), _tr("Second {b}")\n',
    )
    module.write_text(
        _WRAPPER + 'def label():\n    return _tr("New {b}"), _tr("New {a}")\n',
        encoding="utf-8",
    )
    changes, ambiguous = carry.from_diff("HEAD")
    assert changes == []
    assert len(ambiguous) == 2


def test_carry_then_update_is_clean_for_a_fixture_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    current = [extract.Message("Home", "New wording", file="src/home.py")]
    mapping = tmp_path / "map.json"
    mapping.write_text('{"Home": {"Old wording": "New wording"}}', encoding="utf-8")
    monkeypatch.setattr(i18n, "TS_DIR", tmp_path)
    monkeypatch.setattr(i18n, "LANGUAGES", {"de": False})
    monkeypatch.setattr(extract, "REPO", tmp_path)
    monkeypatch.setattr(extract, "read", lambda: extract.Found(messages=current))
    build = i18n.build
    monkeypatch.setattr(i18n, "build", lambda: build(tmp_path / "qm"))
    assert i18n.main(["carry", "--map", str(mapping)]) == 0
    assert i18n.main(["update"]) == 0
    assert i18n.main(["check"]) == 0
    assert ts.read(path).translations[("Home", "New wording", "")] == ts.Translation(
        ("Alte Wörter",), done=False
    )


def test_catalog_counts_missing_and_already_carried_translations(
    tmp_path: Path,
) -> None:
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    changes = [
        _change("Old wording", "New wording"),
        _change("Missing", "Missing rewrite"),
        _change("Missing", "Already new"),
    ]
    counts = carry.carry_file(path, changes, 1, False)
    assert (counts.carried, counts.kept, counts.dropped, counts.ambiguous) == (
        1,
        1,
        1,
        1,
    )
    assert counts.total == 4
    assert "dropped Home: 'Missing rewrite': no old translation" in counts.details
    counts = carry.carry_file(path, changes, 1, False)
    assert (counts.carried, counts.kept, counts.dropped, counts.ambiguous) == (
        0,
        2,
        1,
        1,
    )
    assert counts.total == 4


def test_one_form_plural_is_dropped_if_new_english_has_no_count(tmp_path: Path) -> None:
    path = tmp_path / "polyglotic_ja.ts"
    message = extract.Message("Home", "%n window(s)", numerus=True)
    translations = ts.TsFile("ja", {message.key: ts.Translation(("%n 個の窓",), True)})
    path.write_text(ts.write(path, "ja", [message], translations), encoding="utf-8")
    change = _change(message.source, "All windows")
    counts = carry.carry_file(path, [change], 0, False)
    assert counts.dropped == counts.total == 1
    assert "unexpected count" in counts.details[0]
    assert change.new not in ts.read(path).translations


def test_diff_keeps_translations_of_sources_still_in_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _WRAPPER + (
        'def label():\n    return _tr("Old wording")\n'
        '\ndef alternate():\n    return _tr("Old wording")\n'
    )
    module = _tracked_module(tmp_path, monkeypatch, before)
    module.write_text(before.replace("Old wording", "New wording", 1), encoding="utf-8")
    changes, ambiguous = carry.from_diff("HEAD")
    assert len(changes) == 1
    assert ambiguous == []
    path = tmp_path / "polyglotic_de.ts"
    _write(path)
    assert carry.carry_file(path, changes, 0, False).carried == 1
    translations = ts.read(path).translations
    assert translations[changes[0].old] == ts.Translation(("Alte Wörter",), done=True)
    assert translations[changes[0].new] == ts.Translation(("Alte Wörter",), done=False)
    carried = path.read_bytes()
    assert carry.carry_file(path, changes, 0, False).kept == 1
    assert path.read_bytes() == carried
