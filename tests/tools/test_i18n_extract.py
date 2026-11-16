"""The translation extractor's checks that aren't in tests/ui/test_translations.py."""

from pathlib import Path

from tools.i18n import extract


def test_tr_on_another_object_is_a_problem(tmp_path: Path) -> None:
    """polyglotic-hq 184: `box.tr("Sign out")` on a QMessageBox is looked up
    under "QMessageBox", where our translations never are - the sign-out
    question stayed English in a Chinese interface, and nothing said so."""
    module = tmp_path / "ask.py"
    module.write_text(
        "def ask(box, name):\n"
        "    box.tr('Sign out')\n"
        "    box.tr(f'Sign out {name}')\n"
        "    box.tr(name)\n"
        "class Page:\n"
        "    def build(self):\n"
        "        self.tr('Open')\n",
        encoding="utf-8",
    )
    found = extract.read_file(module)
    assert [(m.context, m.source) for m in found.messages] == [("Page", "Open")]
    assert [p.split(": ", 1)[0].rsplit(":", 1)[1] for p in found.problems] == ["2", "3"]
    assert all("<object>.tr()" in p for p in found.problems)


def test_the_apps_code_has_no_tr_on_another_object() -> None:
    problems = [p for p in extract.read().problems if "<object>.tr()" in p]
    assert problems == []
