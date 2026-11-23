r"""The interface's words in every language, laid out in the fonts a Linux
installs (polyglotic-hq 546, 571): run where a distribution's own fonts
are installed - Ubuntu 24.04's desktop's, Fedora 45's - and nothing else.

    python -m tools.linux_fonts_check OUT
    python -m tools.linux_fonts_check --families

Each interface language, in a process of its own (Qt keeps the faces behind
a family as it first finds them: `style.use_interface_language`): every
string its translation holds (English's sources for English), each laid
out in the interface's font (`style.ui_font`) as drawn, and the UI lab's
own checks asked of it (`tools.ui_lab.checks`): characters drawn as the
missing-glyph box; Chinese drawn in a Japanese face; a Japanese sentence's
kanji in a Chinese one. And which faces drew it, by script.

OUT gets `fonts.json` (each language's findings, the families fontconfig
has) and `fonts.md` (a table). Exit 0 when no language has a finding.
`--families` prints only the families installed, one a line.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SCRIPTS = {
    "han": (0x4E00, 0x9FFF),
    "kana": (0x3040, 0x30FF),
    "hangul": (0xAC00, 0xD7AF),
    "thai": (0x0E00, 0x0E7F),
    "devanagari": (0x0900, 0x097F),
    "cyrillic": (0x0400, 0x04FF),
    "latin": (0x0041, 0x024F),
}
"""The scripts whose faces are said, by their main blocks."""


def script_of(character: str) -> str:
    code = ord(character)
    for name, (low, high) in SCRIPTS.items():
        if low <= code <= high:
            return name
    return ""


def texts(language: str) -> list[str]:
    """Every string the interface shows in `language`: its translation's
    forms, or English's sources."""
    from tools.i18n import extract, ts

    folder = extract.REPO / "translations"

    if language == "en":
        file = ts.read(folder / "polyglotic_zh_CN.ts")  # every source is here
        found = [source for (_context, source, _comment) in file.translations]
    else:
        file = ts.read(folder / f"polyglotic_{language}.ts")
        found = [f for t in file.translations.values() for f in t.forms if f]
    return sorted({text.replace("%n", "3").replace("%Ln", "3") for text in found})


def one(language: str) -> dict[str, Any]:
    """`language`'s findings, in this process."""
    from PySide6.QtGui import QTextLayout
    from PySide6.QtWidgets import QApplication

    from polyglotic_desktop.ui import interface_language
    from polyglotic_desktop.ui_next import style
    from tools.ui_lab import checks

    app = QApplication(["polyglotic-fonts-check"])
    interface_language.install(app, language)
    style.use_interface_language(language)
    font = style.ui_font()
    font.setPixelSize(14)
    boxed: list[str] = []
    japanese: list[str] = []
    chinese: list[str] = []
    faces: dict[str, dict[str, int]] = {}
    strings = texts(language)
    for text in strings:
        if checks.missing_glyphs(text, font):
            boxed.append(text[:80])
        if face := checks.japanese_face(text, font):
            japanese.append(f"{face}: {text[:60]}")
        if face := checks.chinese_face(text, font):
            chinese.append(f"{face}: {text[:60]}")
        layout = QTextLayout(text, font)
        layout.beginLayout()
        layout.createLine()
        layout.endLayout()
        at = 0  # UTF-16 code units, as Qt counts
        for character in text:
            length = 2 if ord(character) > 0xFFFF else 1
            if written := script_of(character):
                for run in layout.glyphRuns(at, length):
                    family = run.rawFont().familyName()
                    counted = faces.setdefault(written, {})
                    counted[family] = counted.get(family, 0) + 1
            at += length
    del app
    return {
        "language": language,
        "strings": len(strings),
        "families_listed": list(style.UI_FAMILIES),
        "boxes": boxed[:20],
        "chinese_in_a_japanese_face": japanese[:20],
        "japanese_in_a_chinese_face": chinese[:20],
        "faces_by_script": {
            script: dict(sorted(counted.items(), key=lambda kv: -kv[1]))
            for script, counted in sorted(faces.items())
        },
    }


def findings(result: dict[str, Any]) -> list[str]:
    """What's wrong in one language's result."""
    said = []
    if result.get("error"):
        said.append(f"didn't run: {result['error']}")
    for key in ("boxes", "chinese_in_a_japanese_face", "japanese_in_a_chinese_face"):
        if result.get(key):
            said.append(f"{key}: {len(result[key])}, e.g. {result[key][0]!r}")
    return said


def installed_families() -> list[str]:
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication(["polyglotic-fonts-check"])
    found = sorted(QFontDatabase.families())
    del app
    return found


def main(argv: list[str]) -> int:
    if not sys.platform.startswith("linux"):
        sys.exit("571: Linux's fonts are read on Linux")
    if argv[:1] == ["--one"]:
        print(json.dumps(one(argv[1]), ensure_ascii=False))
        return 0
    if argv[:1] == ["--families"]:
        print("\n".join(installed_families()))
        return 0
    from polyglotic_desktop.ui import interface_language

    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for language in sorted(interface_language.OFFERED):
        done = subprocess.run(
            [sys.executable, "-m", "tools.linux_fonts_check", "--one", language],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
            check=False,
        )
        try:
            results.append(json.loads(done.stdout.strip().splitlines()[-1]))
        except (IndexError, ValueError):
            error = (done.stderr.strip().splitlines() or ["no output"])[-1]
            results.append({"language": language, "error": error[:300]})
    report = {"families_installed": installed_families(), "languages": results}
    (out / "fonts.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    lines = ["| Language | Strings | Findings | Faces by script |", "|---|---|---|---|"]
    failed = 0
    for result in results:
        said = findings(result)
        failed += bool(said)
        faces = "; ".join(
            f"{script}: {', '.join(list(counted)[:3])}"
            for script, counted in result.get("faces_by_script", {}).items()
        )
        lines.append(
            f"| {result['language']} | {result.get('strings', 0)} | "
            f"{'; '.join(said) or 'none'} | {faces} |"
        )
    (out / "fonts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
