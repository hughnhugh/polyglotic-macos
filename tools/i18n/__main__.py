"""The interface's translations (decision 0034).

python -m tools.i18n update   # every .ts from the code, then every .qm
python -m tools.i18n build    # every .qm from its .ts (tests and builds do it too)
python -m tools.i18n check    # what the tests check: exit 1 on a problem
python -m tools.i18n carry --from-diff BASE  # rewrites keep draft translations
python -m tools.i18n sheet zh_CN review.csv   # a spreadsheet for a reviewer
python -m tools.i18n sheet de review.csv --most-seen 60   # the 60 seen most
python -m tools.i18n apply zh_CN review.csv   # its corrections back in
python -m tools.i18n draft de                 # what has no translation, to draft
python -m tools.i18n draft de --answers a.tsv # the drafter's answers in, checked

`update` after changing any text the interface shows: new messages go into
each language's `.ts` (empty, or English's two forms of a count), changed
ones lose their old translation, and the `.qm` files the app loads are
compiled again. Then draft the new messages in each language with `draft`
(they stay drafts until a native speaker reviews them -
translations/README.md, `tools/i18n/draft.py`).

The `.qm` files are built, not committed (decision 0034, amended
2026-11-08): the tests, the UI lab, CI and the package build compile them
from the `.ts` files with `build()`, so two pull requests that change
text never conflict in a binary.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import PySide6

from polyglotic_desktop.ui import interface_language
from tools.i18n import carry, draft, extract, keep, review, ts

TS_DIR = extract.REPO / "translations"
QM_DIR = extract.SOURCE / "ui" / "assets" / "translations"
# each interface language offered has a file; English's holds only its
# counts' two forms (-> True: plurals only)
LANGUAGES = {
    code: code == interface_language.ENGLISH for code in interface_language.OFFERED
}
# PySide6's own copy, beside the package on every platform
LRELEASE = Path(PySide6.__file__).parent / (
    "lrelease.exe" if sys.platform == "win32" else "lrelease"
)


def ts_path(language: str) -> Path:
    return TS_DIR / f"polyglotic_{language}.ts"


def qm_path(language: str) -> Path:
    return QM_DIR / f"polyglotic_{language}.qm"


def expected_ts(language: str, found: extract.Found) -> str:
    path = ts_path(language)
    old = ts.read(path) if path.exists() else ts.TsFile(language)
    return ts.write(path, language, found.messages, old, LANGUAGES[language])


def compile_qm(source: Path, target: Path) -> None:
    subprocess.run(
        [str(LRELEASE), "-silent", str(source), "-qm", str(target)],
        check=True,
        capture_output=True,
    )


def build(folder: Path = QM_DIR) -> list[Path]:
    """Every language's `.qm`, compiled from its `.ts` into `folder` (the
    app's, by default). A file already the same isn't rewritten, so an app
    running from this checkout keeps the one it has open."""
    folder.mkdir(parents=True, exist_ok=True)
    built = []
    with tempfile.TemporaryDirectory() as scratch:
        for language in LANGUAGES:
            fresh = Path(scratch) / f"{language}.qm"
            compile_qm(ts_path(language), fresh)
            target = folder / qm_path(language).name
            if not target.exists() or target.read_bytes() != fresh.read_bytes():
                target.write_bytes(fresh.read_bytes())
            built.append(target)
    return built


def update() -> int:
    found = extract.read()
    for problem in found.problems:
        print(problem)
    TS_DIR.mkdir(exist_ok=True)
    for language in LANGUAGES:
        ts_path(language).write_text(expected_ts(language, found), encoding="utf-8")
        print(ts_path(language).relative_to(extract.REPO))
    build()
    return 1 if found.problems else 0


def problems() -> list[str]:
    """What's wrong: text the translations can't reach, a `.ts` behind the
    code. (The `.qm` files are built from the `.ts`, not committed.)"""
    found = extract.read()
    wrong = list(found.problems)
    for language in LANGUAGES:
        path = ts_path(language)
        if not path.exists() or path.read_text(encoding="utf-8") != expected_ts(
            language, found
        ):
            wrong.append(f"{path.name} isn't up to date with the code")
    for path in sorted(TS_DIR.glob("polyglotic_*.ts")):
        if path.stem.removeprefix("polyglotic_") not in LANGUAGES:
            wrong.append(
                f"{path.name}: a language not offered (ui.interface_language.OFFERED)"
            )
    return wrong


def draft_work(language: str) -> int:
    """`language`'s strings with no translation, in the drafter's work file
    (`draft`); its `.ts` made first if it has none."""
    found = extract.read()
    path = ts_path(language)
    old = ts.read(path) if path.exists() else ts.TsFile(language)
    path.write_text(
        ts.write(path, language, found.messages, old, LANGUAGES.get(language, False)),
        encoding="utf-8",
    )
    todo = draft.to_draft(found.messages, ts.read(path))
    work = draft.WORK / f"draft-{language}.tsv"
    draft.write_work(language, todo, work)
    terms = TS_DIR / f"GLOSSARY-{language}.md"
    print(f"{work}: {len(todo)} strings to draft")
    print(
        f"glossary: {terms}" + ("" if terms.exists() else " - none yet: write it first")
    )
    return 0


def draft_answers(language: str, answers: Path) -> int:
    """The drafter's `answers` into `language`'s `.ts`, as drafts, checked."""
    path = ts_path(language)
    if not path.exists():
        print(f"{path.name} isn't there: run `draft {language}` first")
        return 2
    messages = extract.read().messages
    file = ts.read(path)
    found = draft.read_answers(answers, language, messages)
    file.translations.update(found.drafted)
    path.write_text(
        ts.write(path, language, messages, file, LANGUAGES.get(language, False)),
        encoding="utf-8",
    )
    if language in LANGUAGES:
        build()
    for line in found.refused:
        print("refused:", line)
    for line in found.unknown:
        print("not in the work any more:", line)
    for line in draft.unglossed(language, found.drafted):
        print("glossary?", line)
    left = len(draft.to_draft(messages, ts.read(path)))
    print(
        f"{len(found.drafted)} drafted; {len(found.refused)} refused; {left} still to draft"
    )
    return 1 if found.refused else 0


def apply(language: str, sheet: Path) -> int:
    """A reviewer's sheet's corrections and "ok"s into `language`'s file,
    reviewed; its `.qm` compiled again."""
    path = ts_path(language)
    file = ts.read(path)
    reviewed, refused = review.read_sheet(sheet, file)
    file.translations.update(reviewed)
    messages = extract.read().messages
    path.write_text(
        ts.write(path, language, messages, file, LANGUAGES[language]), encoding="utf-8"
    )
    build()
    for line in refused:
        print("refused:", line)
    print(f"{len(reviewed)} reviewed; {len(refused)} refused")
    return 1 if refused else 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "carry":
        dry_run = "--dry-run" in argv
        args = [arg for arg in argv[1:] if arg != "--dry-run"]
        try:
            ambiguous: list[str]
            if len(args) == 2 and args[0] == "--map":
                changes, ambiguous = carry.read_map(Path(args[1])), []
            elif len(args) == 2 and args[0] == "--from-diff":
                changes, ambiguous = carry.from_diff(args[1])
            else:
                print(__doc__)
                return 2
        except (TypeError, ValueError, OSError, subprocess.CalledProcessError) as error:
            print(f"carry: {error}")
            return 2
        return carry.run(TS_DIR, changes, ambiguous, dry_run)
    if argv == ["update"]:
        return update()
    if argv == ["build"]:
        for path in build():
            print(path.relative_to(extract.REPO))
        return 0
    if len(argv) == 3 and argv[0] == "apply" and argv[1] in LANGUAGES:
        return apply(argv[1], Path(argv[2]))
    if len(argv) in (3, 5) and argv[0] == "sheet" and argv[1] in LANGUAGES:
        most = None
        if len(argv) == 5:
            if argv[3] != "--most-seen" or not argv[4].isdigit():
                print(__doc__)
                return 2
            most = int(argv[4])
        rows = review.write_sheet(ts_path(argv[1]), Path(argv[2]), most)
        print(f"{argv[2]}: {rows} strings to review")
        return 0
    if len(argv) in (2, 4) and argv[0] == "draft":
        if argv[1] not in keep.PLURAL_FORMS:
            print(f"{argv[1]}: add its plural forms to tools/i18n/keep.py first")
            return 2
        if len(argv) == 2:
            return draft_work(argv[1])
        if argv[2] == "--answers":
            return draft_answers(argv[1], Path(argv[3]))
    if argv == ["check"]:
        wrong = problems()
        for line in wrong:
            print(line)
        if wrong:
            print("Run: uv run python -m tools.i18n update (translations/README.md)")
        return 1 if wrong else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
