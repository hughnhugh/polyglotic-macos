"""Drafting a language (tools/i18n/draft.py, keep.py; polyglotic-hq 294,
decision 0087): the work holds only what has no translation, the answers
come back checked by machine, and a count has as many forms as Qt gives
the language."""

import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QTranslator
from tools.i18n import __main__ as i18n
from tools.i18n import draft, extract, keep, ts


@pytest.mark.parametrize(
    ("source", "forms", "language", "wrong"),
    [
        ("Caption {app}", ("Untertitel für {app}",), "de", ""),
        ("Caption {app}", ("Untertitel",), "de", "keep {app}"),
        ("Caption {app}", ("Untertitel {name}",), "de", "keep {app}"),
        ("%n caption(s)", ("%n Untertitel", "%n Untertitel"), "de", ""),
        ("%n caption(s)", ("%n Untertitel",), "de", "2 form(s)"),
        ("%n caption(s)", ("%n 字幕",), "ja", ""),
        ("%n caption(s)", ("%n napis", "%n napisy", "%n napisów"), "pl", ""),
        ("%n caption(s)", ("napis", "napisy", "napisów"), "pl", "keep the count"),
        ("Press <b>Start</b>", ("Drücke <b>Start</b>",), "de", ""),
        ("Press <b>Start</b>", ("Drücke <i>Start</i>",), "de", "keep the tags"),
        ("Press <b>Start</b>", ("Drücke Start",), "de", "keep the tags"),
        ("Start", ("",), "de", "empty"),
        ("Start", ("Los\tgeht's",), "de", "no tab"),
    ],
)
def test_what_a_translation_keeps(
    source: str, forms: tuple[str, ...], language: str, wrong: str
) -> None:
    found = keep.broken(source, forms, language)
    assert (wrong in found) if wrong else found == ""


def _forms_qt_uses(language: str, tmp_path: Path) -> set[str]:
    """The forms Qt picks for counts 0-200 from a count given one form more
    than `keep.PLURAL_FORMS` says the language has."""
    forms = keep.PLURAL_FORMS[language] + 1
    numerus = "".join(f"<numerusform>F{i} %n</numerusform>" for i in range(forms))
    source = tmp_path / f"{language}.ts"
    source.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n'
        f'<TS version="2.1" language="{language}" sourcelanguage="en">'
        '<context><name>C</name><message numerus="yes"><source>%n x(s)</source>'
        f"<translation>{numerus}</translation></message></context></TS>\n",
        encoding="utf-8",
    )
    compiled = tmp_path / f"{language}.qm"
    subprocess.run(
        [str(i18n.LRELEASE), "-silent", str(source), "-qm", str(compiled)],
        check=True,
        capture_output=True,
    )
    translator = QTranslator()
    assert translator.load(str(compiled))
    return {
        (translator.translate("C", "%n x(s)", None, n) or "").split(" ")[0]
        for n in range(201)
    }


@pytest.mark.parametrize("language", sorted(keep.PLURAL_FORMS))
def test_each_languages_count_forms_are_qts(language: str, tmp_path: Path) -> None:
    """Qt uses every form `PLURAL_FORMS` gives the language, and never one
    more: a wrong number shows the wrong form, or none (Russian's "5 слова")."""
    used = _forms_qt_uses(language, tmp_path)
    assert used == {f"F{i}" for i in range(keep.PLURAL_FORMS[language])}


def test_every_strings_id_is_its_own() -> None:
    messages = extract.read().messages
    assert len({draft.message_id(m.key) for m in messages}) == len(messages)


@pytest.fixture
def german(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A language not offered yet, its file and work in `tmp_path`."""
    monkeypatch.setattr(i18n, "TS_DIR", tmp_path)
    monkeypatch.setattr(draft, "WORK", tmp_path / "work")
    monkeypatch.setitem(keep.PLURAL_FORMS, "xx", 2)  # one, and the rest
    return tmp_path


def _work(folder: Path) -> list[list[str]]:
    lines = (folder / "work" / "draft-xx.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "id\tcontext\tforms\tenglish\tnote"
    return [line.split("\t") for line in lines[1:]]


def test_a_draft_goes_out_and_comes_back_checked(
    german: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert i18n.draft_work("xx") == 0
    work = _work(german)
    messages = extract.read().messages
    assert len(work) == len(messages)  # nothing translated yet: all of it
    by_key = {(row[1], row[3]): row for row in work}
    plain = by_key["CaptionWindow", "Original only"]
    named = by_key["CaptionWindow", "{app}'s captions appear here"]
    counted = by_key["ProblemReport", "%n caption(s)"]
    assert counted[2] == "2"  # German: one, and the rest
    answers = german / "answers.tsv"
    answers.write_text(
        f"{plain[0]}\tNur Original\n"
        f"{named[0]}\tHier erscheinen die Untertitel\n"  # lost {app}
        f"{counted[0]}\t%n Untertitel | %n Untertitel\n"
        "0000000000\tVerwaist\n",
        encoding="utf-8",
    )
    assert i18n.draft_answers("xx", answers) == 1  # one refused
    said = capsys.readouterr().out
    assert "refused:" in said and "{app}" in said
    assert "not in the work any more" in said
    assert "2 drafted; 1 refused" in said
    file = ts.read(i18n.ts_path("xx"))
    original = file.translations[("CaptionWindow", "Original only", "")]
    assert original == ts.Translation(("Nur Original",), done=False)  # a draft
    assert file.translations[("ProblemReport", "%n caption(s)", "")].forms == (
        "%n Untertitel",
        "%n Untertitel",
    )
    assert file.translations[
        ("CaptionWindow", "{app}'s captions appear here", "")
    ].empty
    # the next run hands out only what's still without a translation
    i18n.draft_work("xx")
    rows = _work(german)
    again = {(row[1], row[3]) for row in rows}
    assert ("CaptionWindow", "{app}'s captions appear here") in again
    assert ("CaptionWindow", "Original only") not in again
    assert ("ProblemReport", "%n caption(s)") not in again
    assert len(rows) == len(messages) - 2


def test_a_language_with_unknown_count_rules_isnt_drafted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert i18n.main(["draft", "xx"]) == 2
    assert "plural forms" in capsys.readouterr().out


def test_the_glossary_is_read_from_its_table(
    german: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extract, "REPO", german.parent)
    (german.parent / "translations").mkdir(exist_ok=True)
    (german.parent / "translations" / "GLOSSARY-de.md").write_text(
        "| English | Deutsch | Note |\n|---|---|---|\n"
        "| caption | Untertitel | |\n| lookup | Nachschlagen | a note |\n"
        "| Sign in / Sign out | Anmelden / Abmelden | |\n",
        encoding="utf-8",
    )
    assert draft.glossary("de") == [
        ("caption", "Untertitel"),
        ("lookup", "Nachschlagen"),
    ]


def test_the_glossarys_terms_are_hinted_not_refused(
    german: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(draft, "glossary", lambda language: [("caption", "Untertitel")])
    drafted = {
        ("C", "Caption timing", ""): ts.Translation(("Zeitpunkt",)),
        ("C", "Every caption", ""): ts.Translation(("Jeder Untertitel",)),
    }
    assert draft.unglossed("de", drafted) == [
        "'caption' -> 'Untertitel': 'Caption timing'"
    ]
