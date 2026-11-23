"""Sign in against a stand-in and inspect the actual caption typefaces on Cocoa."""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QFont, QTextLayout
from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QWidget

from polyglotic_desktop.ports.open_beta import Region
from polyglotic_desktop.ui.open_beta import EmailSignIn
from polyglotic_desktop.ui_next import caption_faces, fonts
from tools import app_tour as kit
from tools.macos_quartz import SETTLE, Evidence, Pointer, centre

SAMPLES = {
    "en": "Good morning. Café, déjà vu.",
    "el": "Καλημέρα",
    "zh": "今天天气很好",
    "zh-hant": "繁體中文",
    "yue": "廣東話",
    "ja": "日本語の字幕",
    "ko": "한국어 자막",
    "th": "สวัสดี",
    "vi": "Tiếng Việt",
    "ar": "مرحبا بالعالم",
    "hi": "नमस्ते दुनिया",
    "ru": "Добрый день",
}


def anki(evidence: Evidence, pointer: Pointer, home: Any) -> kit.Step:
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    from PySide6.QtWidgets import QFileDialog
    from tests.test_anki_package import read_apkg

    from polyglotic_desktop.core.learning.lookups import LookupContext
    from polyglotic_desktop.core.learning.vocabulary import EntryText
    from polyglotic_desktop.core.shared import EntryId

    home.go_to("words")
    page = kit.hub().words
    words = page.first
    words.learner.vocabulary.learn(
        EntryId("cedict:qa-example"),
        EntryText("example", "", "", "QA fixture"),
        LookupContext("This is an example."),
    )
    with TemporaryDirectory(prefix="anki-export-") as folder:
        for ext, button in (("csv", words.export_csv), ("apkg", words.export_deck)):
            path = Path(folder) / ("words." + ext)
            page.ensureWidgetVisible(button)
            yield kit.pause(SETTLE)
            # The first export can move when a lazily built Words section finishes sizing.
            page.ensureWidgetVisible(button)
            yield kit.pause(SETTLE)
            before = home.frameGeometry()
            with patch.object(
                QFileDialog, "getSaveFileName", return_value=(str(path), "")
            ):
                yield from pointer.click(centre(button))

            def exported(path: Path = path) -> bool:
                return path.is_file() and words.exporting is None

            yield kit.wait(
                exported,
                15,
                "Words writes the " + ext + " export",
            )
            if ext == "csv":
                ok = path.exists() and "QA fixture" in path.read_text(encoding="utf-8")
            else:
                notes = read_apkg(path.read_bytes()).notes if path.exists() else {}
                ok = any("QA fixture" in fields.values() for fields in notes.values())
            page.ensureWidgetVisible(words.export_result)
            yield kit.pause(SETTLE)
            evidence.record(
                "words-export-" + ext,
                home,
                before,
                "reopened export contains the seeded word's definition",
                ok and words.export_result.isVisible(),
                bytes=path.stat().st_size if path.exists() else 0,
            )


def font_sheet(evidence: Evidence, parent: QWidget) -> kit.Step:
    caption_faces.load()
    panel = QDialog(parent)
    panel.setWindowTitle("Caption fonts")
    grid = QGridLayout(panel)
    measurements: dict[str, Any] = {}
    try:
        for row, (language, sample) in enumerate(SAMPLES.items()):
            grid.addWidget(QLabel(language, panel), row, 0)
            font = QFont()
            font.setFamilies(list(fonts.caption_families(language)))
            font.setPixelSize(round(22 * fonts.size(language)))
            label = QLabel(sample, panel)
            label.setFont(font)
            grid.addWidget(label, row, 1)
            layout = QTextLayout(sample, font)
            layout.beginLayout()
            layout.createLine().setLineWidth(500)
            layout.endLayout()
            runs = layout.glyphRuns()
            indices = [g for run in runs for g in run.glyphIndexes()]
            measurements[language] = {
                "glyphs": len(indices),
                "missing": indices.count(0),
                "families": [run.rawFont().familyName() for run in runs],
            }
        panel.show()
        yield kit.pause(SETTLE)
        covered = {fonts.script(lang) for lang in SAMPLES}
        evidence.record(
            "caption-fonts",
            panel,
            panel.frameGeometry(),
            "every configured script represented and zero missing glyphs in its sample",
            covered == set(fonts.DEFAULTS)
            and all(
                m["glyphs"] > 0 and m["missing"] == 0 for m in measurements.values()
            ),
            languages=measurements,
        )
    finally:
        panel.close()
        panel.deleteLater()


def sign_in(evidence: Evidence, pointer: Pointer, home: QWidget) -> kit.Step:
    from tools.ui_lab.open_beta import ACCOUNT

    asked: list[tuple[str, str]] = []

    def begin(email: str, _marketing: bool, _cross_border: bool, _timezone: str) -> str:
        asked.append(("start", email))
        return "qa-challenge"

    def verify(challenge: str, code: str) -> Any:
        assert challenge == "qa-challenge"
        asked.append(("verify", code))
        return ACCOUNT

    dialog = EmailSignIn(lambda: Region("AU"), begin, verify, None, home)
    try:
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        yield kit.pause(SETTLE)
        dialog.email.setText("learner@example.test")
        before = dialog.frameGeometry()
        yield from pointer.click(centre(dialog.ok))
        yield kit.wait(dialog.code.isVisible, 5, "verification field")
        evidence.record(
            "sign-in-code",
            dialog,
            before,
            "one challenge and one visible code field",
            asked == [("start", "learner@example.test")] and dialog.code.isVisible(),
        )
        dialog.code.setText("123456")
        yield from pointer.click(centre(dialog.ok))
        yield kit.wait(
            lambda: dialog.result() == QDialog.DialogCode.Accepted,
            5,
            "account verified",
        )
        evidence.record(
            "sign-in-verified",
            home,
            home.frameGeometry(),
            "one verified synthetic account",
            dialog.account == ACCOUNT
            and dialog.result() == QDialog.DialogCode.Accepted
            and asked[-1] == ("verify", "123456"),
        )
    finally:
        dialog.close()
        dialog.deleteLater()
