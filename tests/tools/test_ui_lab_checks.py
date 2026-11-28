"""The UI lab's code checks (project 119): each finds what it should and
nothing else, a caption surface's words are never written down, and a
finding on a new part fails the gate - unless waived, with a reason."""

import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QPainter,
    QPaintEvent,
    QTextLayout,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tools.ui_lab import __main__ as cli
from tools.ui_lab import checks, goldens, lab, new_parts
from tools.ui_lab.checks import Finding, Waiver

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import LATIN_FAMILIES


@pytest.fixture
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication(["test"])
    assert isinstance(app, QApplication)
    yield app


@pytest.fixture
def page(qapp: QApplication) -> Iterator[QWidget]:
    """A plain window, dark text on light, that takes the keyboard."""
    shown = QWidget()
    shown.setObjectName("page")
    shown.setStyleSheet("QWidget { background: #ffffff; color: #111111; }")
    shown.setMinimumSize(200, 100)
    shown.resize(400, 200)
    yield shown
    shown.close()
    shown.deleteLater()


def inspect(widget: QWidget) -> checks.Inspection:
    widget.show()
    QApplication.processEvents()
    return checks.inspect(
        "ui_next.test", widget, lambda w: lab.photograph(w, False), windows=[widget]
    )


def found(widget: QWidget, check: str) -> list[Finding]:
    return [f for f in inspect(widget).findings if f.check == check]


def test_a_page_that_fits_has_no_findings(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    label = QLabel("Captions appear here", page)
    label.setObjectName("page.hint")
    rows.addWidget(label)
    button = QPushButton("Start", page)
    rows.addWidget(button)
    result = inspect(page)
    assert result.findings == []
    assert "Captions appear here" in result.words and "Start" in result.words
    assert any(note.startswith("tab order:") for note in result.notes)


def test_text_cut_off_by_its_label_is_found(page: QWidget) -> None:
    label = QLabel("A rather long label that will not fit in its width", page)
    label.setObjectName("page.long")
    label.setGeometry(10, 10, 120, 24)
    (finding,) = found(page, "clipped_text")
    assert finding.where == "page.long (QLabel)"
    assert "past the right" in finding.detail and "A rather long" in finding.detail


def test_a_word_recoloured_by_drawing_it_again_cut_to_the_word_is_not_cut_off(
    page: QWidget,
) -> None:
    class Picked(QWidget):
        def paintEvent(self, event: QPaintEvent) -> None:
            painter = QPainter(self)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(10, 30, "the whole line")
            painter.setClipRect(QRectF(40, 0, 30, 50))  # one word, picked out
            painter.setPen(Qt.GlobalColor.darkBlue)
            painter.drawText(10, 30, "the whole line")
            painter.end()

    Picked(page).setGeometry(0, 0, 300, 60)
    assert found(page, "clipped_text") == []


def test_text_under_12_px_is_found_and_icon_fonts_are_not(page: QWidget) -> None:
    small = QLabel("Fine print", page)
    small.setObjectName("page.small")
    font = QFont()
    font.setPixelSize(11)
    small.setFont(font)
    small.setGeometry(10, 10, 200, 20)
    icon = QLabel("", page)
    icon_font = QFont()
    icon_font.setFamilies(list(checks.ICON_FONTS))
    icon_font.setPixelSize(10)
    icon.setFont(icon_font)
    icon.setGeometry(10, 40, 30, 20)
    (finding,) = found(page, "small_text")
    assert finding.where == "page.small (QLabel)"
    assert finding.detail.startswith("11 px text")


def test_low_contrast_is_found_and_a_disabled_control_is_exempt(page: QWidget) -> None:
    faint = QLabel("Faint words", page)
    faint.setObjectName("page.faint")
    faint.setStyleSheet("color: #aaaaaa;")  # 2.3:1 on white
    faint.setGeometry(10, 10, 200, 24)
    off = QPushButton("Not now", page)
    off.setStyleSheet("color: #cccccc;")
    off.setEnabled(False)
    off.setGeometry(10, 40, 120, 28)
    (finding,) = found(page, "contrast")
    assert finding.where == "page.faint (QLabel)"
    assert finding.detail.startswith("2.32:1, needs 4.5:1 - #aaaaaa on #ffffff")


def test_large_text_needs_only_3_to_1(page: QWidget) -> None:
    for n, px in enumerate((24, 14)):
        label = QLabel("Grey words", page)
        label.setObjectName(f"page.grey{px}")
        label.setStyleSheet(f"color: #949494; font-size: {px}px;")  # 3.03:1
        label.setGeometry(10, 10 + n * 50, 300, 40)
    (finding,) = found(page, "contrast")
    assert finding.where == "page.grey14 (QLabel)"


def test_a_control_without_a_readable_name_is_found(page: QWidget) -> None:
    row = QHBoxLayout(page)
    glyph = QToolButton(page)
    glyph.setObjectName("page.settings")
    glyph.setText("")  # an icon font's glyph
    named = QToolButton(page)
    named.setText("")
    named.setAccessibleName("Close")
    row.addWidget(glyph)
    row.addWidget(named)
    (finding,) = found(page, "accessible_name")
    assert finding.where == "page.settings (QToolButton)"
    assert checks.readable("A-") and not checks.readable(" ")


def test_a_control_tab_never_reaches_is_found(page: QWidget) -> None:
    row = QHBoxLayout(page)
    reached = QPushButton("Reached", page)
    missed = QPushButton("Missed", page)
    missed.setObjectName("page.missed")
    missed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    row.addWidget(reached)
    row.addWidget(missed)
    (finding,) = found(page, "keyboard")
    assert finding.where == "page.missed (QPushButton)"


def test_a_window_that_never_takes_the_focus_is_exempt_from_the_keyboard(
    qapp: QApplication,
) -> None:
    shown = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
    shown.setObjectName("caption_window")
    button = QPushButton("Lock", shown)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    result = inspect(shown)
    assert [f for f in result.findings if f.check == "keyboard"] == []
    assert any("exempt" in note for note in result.notes)
    shown.close()


def test_a_horizontal_scrollbar_is_found(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    scroller = QScrollArea(page)
    wide = QWidget()
    wide.setMinimumSize(1200, 50)
    scroller.setWidget(wide)
    rows.addWidget(scroller)
    assert [f.check for f in found(page, "horizontal_scrollbar")] == [
        "horizontal_scrollbar"
    ]


def test_a_squashed_layout_is_found(page: QWidget) -> None:
    row = QHBoxLayout(page)
    for n in range(4):
        button = QPushButton(f"Choice {n}", page)
        button.setMinimumWidth(120)
        row.addWidget(button)
    page.setFixedSize(300, 60)  # the layout needs about 500
    (finding,) = found(page, "minimum_size")
    assert finding.where == "page (QWidget)"
    assert finding.detail.startswith("300 x 60, its layout needs at least")


def test_a_window_with_controls_and_no_minimum_size_is_found(
    qapp: QApplication,
) -> None:
    shown = QWidget()
    shown.setObjectName("bare")
    QPushButton("Go", shown).setGeometry(10, 10, 80, 30)
    shown.resize(200, 80)
    (finding,) = found(shown, "minimum_size")
    assert finding.detail == "a window with controls declares no minimum size"
    shown.close()


def test_a_caption_surfaces_words_are_never_written_down(
    qapp: QApplication, tmp_path: Path
) -> None:
    state = next(s for s in new_parts.STATES if s.name == "ui_next.caption_window_1000")
    (result,) = lab.run([state], tmp_path)
    shown = [
        text
        for update in new_parts.finished(1_000)[-20:]
        for clause in update.clauses
        for text in (clause.original, *clause.translations.values())
    ]
    assert shown
    written = (tmp_path / f"{state.name}.json").read_text(encoding="utf-8")
    written += (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert result.words == []
    for text in shown:
        assert text.strip(" ,.。，") not in written


def test_a_finding_on_a_new_part_fails_the_gate_unless_waived(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unnamed(lab_: lab.Lab) -> QWidget:
        shown = QWidget()
        shown.setObjectName("lab_page")
        shown.setMinimumSize(100, 50)
        row = QHBoxLayout(shown)
        row.setContentsMargins(8, 8, 8, 8)  # not Qt's 11: the design detector's grid
        row.addWidget(QToolButton(shown))  # no name at all
        shown.show()
        return shown

    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(goldens, "GOLDENS", tmp_path / "goldens")
    # only these states, whatever the lab gains later (not each module's list)
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.setattr(
        new_parts, "STATES", [lab.State("ui_next.unnamed", unnamed, True)]
    )
    assert (
        cli.main(["approve", "--reason", "a test", "--out", str(tmp_path / "approve")])
        == 0
    )
    for gated, waivers, fails in (
        (True, (), 1),
        (False, (), 0),
        (True, (Waiver("accessible_name", "ui_next.*", "lab_page > *", "a test"),), 0),
    ):
        name = "ui_next.unnamed" if gated else "ui.unnamed"
        monkeypatch.setattr(new_parts, "STATES", [lab.State(name, unnamed, gated)])
        monkeypatch.setattr(checks, "WAIVERS", waivers)
        out = tmp_path / f"{gated}{len(waivers)}"
        assert cli.main(["--gate", "--out", str(out)]) == fails
        written = json.loads((out / f"{name}.json").read_text(encoding="utf-8"))
        (finding,) = written["findings"]
        assert finding["check"] == "accessible_name"
        assert ("waived" in finding) == bool(waivers)
        assert "## Code checks" in (out / "summary.md").read_text(encoding="utf-8")


class _Rows(QWidget):
    """A painted list, like a transcript's: rows from y = -10, and maybe a
    scrollbar of its own."""

    def __init__(self, parent: QWidget, scrolls: bool) -> None:
        super().__init__(parent)
        self.setObjectName("rows")
        if scrolls:
            QScrollBar(Qt.Orientation.Vertical, self).setGeometry(290, 0, 10, 60)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.GlobalColor.black)
        for n, row in enumerate(("secret words one", "secret words two")):
            painter.drawText(10, 4 + 30 * n, row)  # the first row cut at the top
        painter.end()


@pytest.mark.parametrize("scrolls", [True, False])
def test_painted_text_is_never_written_and_rows_that_scroll_may_be_cut(
    page: QWidget, scrolls: bool
) -> None:
    _Rows(page, scrolls).setGeometry(0, 0, 300, 60)
    result = inspect(page)
    cut = [f for f in result.findings if f.check == "clipped_text"]
    if scrolls:
        assert cut == []
    else:
        (finding,) = cut
        assert finding.detail.startswith("painted text at 10,")
    written = repr(result.findings) + repr(result.words) + repr(result.notes)
    assert "secret" not in written


def test_what_the_learner_types_is_never_written(page: QWidget) -> None:
    field = QLineEdit(page)
    field.setObjectName("page.search")
    field.setPlaceholderText("Search")
    field.setText("typed words")
    field.setGeometry(10, 10, 60, 24)  # too narrow: its text is cut
    result = inspect(page)
    assert "Search" in result.words
    assert "typed words" not in repr(result.findings) + repr(result.words)


def test_a_symbol_is_an_icon_and_a_colour_emoji_has_no_pen_contrast(
    page: QWidget,
) -> None:
    for n, text in enumerate(("×", "\U0001f3a4", "Close")):
        button = QToolButton(page)
        button.setObjectName(f"page.b{n}")
        button.setText(text)
        button.setAccessibleName("named")
        button.setStyleSheet("color: #8c8c8c; background: #ffffff;")  # 3.4:1
        button.setGeometry(10 + 60 * n, 10, 50, 30)
    assert [f.where for f in found(page, "contrast")] == ["page.b2 (QToolButton)"]


class _Painted(QWidget):
    """Text a widget paints itself in one font list: drawn, it comes in a
    piece per font (the lookup card's "Save to ▾")."""

    def __init__(self, parent: QWidget, text: str, families: list[str]) -> None:
        super().__init__(parent)
        self.setObjectName("painted")
        self.text = text
        self.families = families

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        font = QFont()
        font.setFamilies(self.families)
        # a size no other test draws: Qt keeps a font's fallbacks as it first
        # found them, so this test's must be its own (QFont.removeSubstitutions)
        font.setPixelSize(19)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(10, 20, self.text)
        painter.end()


@contextmanager
def _windows_fonts() -> Iterator[None]:
    """Windows' fonts, as the lab has them (`QT_QPA_FONTDIR` and
    `lab.use_windows_fonts`) - whichever test runs first - and behind a
    list with no Chinese face, what Windows finds (MS UI Gothic) while the
    test runs: the interface's Chinese faces, which a lab run puts behind
    every font as the app does (`style.use_chinese_behind_every_font`,
    215), are taken away for the checks' own tests. Set up late in a long
    run, after many other tests have drawn text (`pytest tests/ui_next
    tests/tools`), Qt doesn't take Windows' fonts (198): skipped then. In
    CI's order the lab's tests come first, and
    `test_the_lab_draws_in_windows_fonts` checks them in a process of its
    own."""
    lab.application()
    if not {"Segoe UI", "Segoe UI Symbol", "Microsoft YaHei UI"} <= set(
        QFontDatabase.families()
    ):
        pytest.skip("needs Windows' fonts")
    behind = {f: QFont.substitutes(f) for f in QFontDatabase.families()}
    for family, faces in behind.items():
        QFont.removeSubstitutions(family)
        QFont.insertSubstitutions(
            family, [f for f in faces if f not in style.CHINESE_FACES]
        )
    try:
        font = _font(["Segoe UI"])
        font.setPixelSize(41)  # its own size (`_font`)
        if _faces("收", font) != ["MS UI Gothic"]:
            pytest.skip("Windows' fonts were set up after other tests drew text")
        yield
    finally:
        for family, faces in behind.items():
            QFont.removeSubstitutions(family)
            QFont.insertSubstitutions(family, faces)


def _faces(text: str, font: QFont) -> list[str]:
    layout = QTextLayout(text, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    return [r.rawFont().familyName() for r in layout.glyphRuns()]


def test_a_character_no_font_has_is_found_as_a_box(page: QWidget) -> None:
    label = QLabel("Save ͸", page)  # U+0378: no character, so no font's
    label.setObjectName("page.save")
    label.setGeometry(10, 10, 200, 24)
    (finding,) = found(page, "missing_glyph")
    assert finding.where == "page.save (QLabel)"
    assert finding.detail == "a character drawn as a box in 'Save ͸'"


def test_a_symbol_after_chinese_is_checked_with_the_chinese(page: QWidget) -> None:
    """170: "收藏到 ▾" drew a box. Drawn, it comes in two pieces, one per
    font; "▾" alone found a font that has it, after Chinese it didn't. In
    Windows' fonts (198) "▾" after Chinese comes from MS UI Gothic, as on
    Windows; "⏷" still doesn't. The painted text isn't written down."""
    with _windows_fonts():
        saved = QFont.substitutes("Segoe UI")
        QFont.removeSubstitutions("Segoe UI")  # as before style.use_symbols
        try:
            _Painted(page, "收藏到 ⏷", ["Segoe UI"]).setGeometry(0, 0, 200, 40)
            (finding,) = found(page, "missing_glyph")
            assert finding.where == "painted (_Painted)"
            assert finding.detail.startswith(
                "a character drawn as a box in painted text at 10,"
            )
            alone = _font(["Segoe UI"])
            alone.setPixelSize(43)  # its own size (`_font`)
            assert checks.missing_glyphs("⏷", alone) == 0  # alone: found
        finally:
            QFont.insertSubstitutions("Segoe UI", saved)


def test_the_interfaces_symbols_come_from_segoe_ui_symbol_after_any_text(
    qapp: QApplication,
) -> None:
    """176: Segoe UI Symbol behind every font the interface names, so a
    symbol after Chinese is never a box - the lookup card's Latin fonts,
    the interface's list and its Chinese fonts alike."""
    with _windows_fonts():
        style.use_symbols()
        for families in (
            list(LATIN_FAMILIES),  # the lookup card's "Save to ▾"
            list(style.UI_FAMILIES),  # the transcript's "稳定 ▾", Help's "▸"
            ["Microsoft YaHei UI"],
        ):
            for text in ("收藏到 ▾", "底部居中 ▴", "▸ 帮助", "⚙ 设置", "Save to ▾"):
                assert checks.missing_glyphs(text, _font(families)) == 0, (
                    families,
                    text,
                )


def _font(families: list[str]) -> QFont:
    """At a size no window draws: Qt keeps a font's fallbacks as it first
    found them, so one made before `use_symbols` (another test's, in the
    same run) would hide what this one checks. The app calls it first."""
    font = QFont()
    font.setFamilies(families)
    font.setPixelSize(23)
    return font


def test_chinese_in_a_japanese_face_is_found(page: QWidget) -> None:
    """176, 198: Chinese a font list has no face for is drawn in MS UI
    Gothic on Windows in an English locale - Japan's glyph shapes - and in
    the lab. A list with a Chinese face, Japanese text (kana) and a list
    that names a Japanese face itself are fine."""
    with _windows_fonts():
        for n, (text, families) in enumerate(
            (
                ("收藏到", ["Segoe UI"]),  # the lookup card's Save to, in Chinese
                ("收藏到", ["Segoe UI", "Microsoft YaHei UI"]),
                ("頑張って", ["Segoe UI"]),
                ("漢字", ["Yu Gothic UI", "Segoe UI"]),
            )
        ):
            label = QLabel(text, page)
            label.setObjectName(f"page.label{n}")
            font = QFont()
            font.setFamilies(families)
            # a size of its own: Qt keeps the fonts behind a family as they were
            # first asked for at a size, whatever list asks next (`_font`)
            font.setPixelSize(17 + n)
            label.setFont(font)
            label.setGeometry(10, 10 + 40 * n, 200, 30)
        (finding,) = found(page, "japanese_font")
        assert finding.where == "page.label0 (QLabel)"
        assert finding.detail == (
            "Chinese drawn in MS UI Gothic, a Japanese face its fonts don't name: '收藏到'"
        )


def test_japanese_in_a_chinese_face_is_found(page: QWidget) -> None:
    """215: Japanese (it has kana) whose kanji are drawn in a Chinese face
    - in a list that names YaHei, as the interface's own list does - is
    found; Japanese in a Japanese face, Chinese in a Chinese face and kana
    alone aren't."""
    with _windows_fonts():
        for n, (text, families) in enumerate(
            (
                ("日本語を勉強します", ["Segoe UI", "Microsoft YaHei UI"]),
                ("日本語を勉強します", ["Yu Gothic UI", "Segoe UI"]),
                ("我们学习汉字", ["Segoe UI", "Microsoft YaHei UI"]),
                ("ひらがなだけ", ["Segoe UI", "Microsoft YaHei UI"]),
            )
        ):
            label = QLabel(text, page)
            label.setObjectName(f"page.label{n}")
            font = QFont()
            font.setFamilies(families)
            font.setPixelSize(33 + n)  # a size of its own (`_font`)
            label.setFont(font)
            label.setGeometry(10, 10 + 40 * n, 260, 36)
        (finding,) = found(page, "chinese_font")
    assert finding.where == "page.label0 (QLabel)"
    assert finding.detail == (
        "Japanese drawn in Microsoft YaHei UI, a Chinese face: '日本語を勉強します'"
    )


def test_a_chinese_example_in_japanese_has_no_japanese_shape(page: QWidget) -> None:
    """294: a Japanese interface explains Chinese with Chinese examples
    ("代名詞、是、这个"); a Simplified-only character (这) has no Japanese
    shape, so a Chinese face drawing it isn't a fault - kanji Japanese has
    in a Chinese face still are."""
    with _windows_fonts():
        label = QLabel("这です", page)
        label.setObjectName("page.example")
        font = QFont()
        font.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
        font.setPixelSize(31)
        label.setFont(font)
        label.setGeometry(10, 10, 260, 36)
        assert found(page, "chinese_font") == []


def test_a_chinese_sentence_after_a_japanese_label_is_not_japanese_misdrawn(
    page: QWidget,
) -> None:
    """472: Saved words' "Heard in" line in a Japanese interface - its
    label, then a Chinese sentence - draws only the Simplified-only 风 in
    YaHei; the kanji Japanese has are in Yu Gothic. Qt's run named 风 as
    文, and the check found Japanese in a Chinese face."""
    with _windows_fonts():
        label = QLabel("聞いた文：日风天水", page)
        label.setObjectName("page.heard_in")
        font = QFont()
        font.setFamilies(["Segoe UI", "Yu Gothic UI", "Microsoft YaHei UI"])
        font.setPixelSize(35)  # a size of its own (`_font`)
        label.setFont(font)
        label.setGeometry(10, 10, 300, 40)
        assert found(page, "chinese_font") == []


def test_a_japanese_interfaces_own_kanji_are_japanese(
    page: QWidget, qapp: QApplication
) -> None:
    """294: in a Japanese interface, its own words with no kana (設定, 終了)
    are Japanese: drawn in a Japanese face, they aren't Chinese in the
    wrong face."""
    with _windows_fonts():
        label = QLabel("終了", page)
        label.setObjectName("page.quit")
        font = QFont()
        font.setFamilies(["Segoe UI"])
        font.setPixelSize(32)
        label.setFont(font)
        label.setGeometry(10, 10, 260, 36)
        assert [f.check for f in found(page, "japanese_font")] == ["japanese_font"]
        before = qapp.property("interface_language")
        qapp.setProperty("interface_language", "ja")
        try:
            assert found(page, "japanese_font") == []
        finally:
            qapp.setProperty("interface_language", before)


_LAB_FONTS = """
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QTextLayout
from tools.ui_lab import lab
from polyglotic_desktop.ui_next import style
app = lab.application()
assert app.font().family() == "Segoe UI", app.font().family()
assert QFontInfo(app.font()).family() == "Segoe UI"
assert app.font().pointSizeF() == style.DEFAULT_POINTS
families = set(QFontDatabase.families())
assert {"Microsoft JhengHei UI", "MS UI Gothic", "Yu Gothic UI"} <= families
for px, chosen, face in (
    (29, ["Segoe UI"], "MS UI Gothic"),
    (30, ["Segoe UI", "Microsoft YaHei UI"], "Microsoft YaHei UI"),
    (31, ["Segoe UI", "Microsoft JhengHei UI"], "Microsoft JhengHei UI"),
):
    font = QFont()
    font.setFamilies(chosen)
    font.setPixelSize(px)  # each its own: Qt keeps a family's fallbacks per size
    layout = QTextLayout("收藏到", font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    faces = [r.rawFont().familyName() for r in layout.glyphRuns()]
    assert faces == [face], (chosen, faces)
print("ok")
"""


def test_the_lab_draws_in_windows_fonts() -> None:
    """198: offscreen, what names no font is in Segoe UI 9 pt (not Qt's "Sans
    Serif", Agency FB); Windows' font collections are there (Microsoft
    YaHei UI...); Chinese a list has no face for is in MS UI Gothic. In a
    process of its own: the lab sets its fonts up first, as it starts."""
    if not lab.WINDOWS_FONTS.is_dir():
        pytest.skip("needs Windows' fonts")
    done = subprocess.run(
        [sys.executable, "-c", _LAB_FONTS],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).parents[2],
    )
    assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr[-2000:]


_LAB_HEADING_FACE = """
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QFontDatabase, QFontInfo
from PySide6.QtWidgets import QLabel
from tools.ui_lab import lab
from polyglotic_desktop.ui import theme
family = theme.THEMES[theme.DEFAULT_THEME].heading_family
app = lab.application()
assert family not in QFontDatabase.families(), "a pytest session's fonts changed"
lab.as_the_app_starts()
app = lab.application()
assert family in QFontDatabase.families(), family
title = QLabel("Report a problem")
title.setStyleSheet(f'font-family: "{family}"; font-size: 22pt;')
title.ensurePolished()
assert QFontInfo(title.font()).family() == family, QFontInfo(title.font()).family()
print("ok")
"""


def test_a_page_title_is_in_the_heading_face_whatever_ran_before() -> None:
    """polyglotic-hq 1004: the app loads the default theme's heading face
    as it starts, so every page title (Report a problem, Sign in...) is in
    it. The lab loaded it only for the main window's states, once per
    process, so a dialog state's title was in it or in Windows' font by
    which states ran before it in that process: on the 0.1.13 train's full
    run qt_problem_report and qt_feedback_suggestion drew Literata, alone
    Segoe UI. In a process of its own, before any state: the face is there
    for the lab command (`as_the_app_starts`), and not for a plain
    `application()` - a pytest session's fonts stay as they were (Literata
    there moved test_translation_size's Chinese line on gpubox)."""
    if not lab.WINDOWS_FONTS.is_dir():
        pytest.skip("needs Windows' fonts")
    done = subprocess.run(
        [sys.executable, "-c", _LAB_HEADING_FACE],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).parents[2],
    )
    assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr[-2000:]


def _box(
    pen: tuple[int, int, int], behind: tuple[int, int, int], pen_share: float
) -> Any:
    """A 10 x 10 box of RGBA pixels: `pen_share` of it the text's colour,
    the rest what's behind it."""
    import numpy as np

    pixels = np.zeros((10, 10, 4), dtype=np.uint8)
    pixels[:, :, 3] = 255
    pixels[:, :, :3] = behind
    covered = round(100 * pen_share)
    flat = pixels.reshape(-1, 4)
    flat[:covered, :3] = pen
    return pixels


def test_whats_behind_text_is_never_its_own_colour_while_another_shows() -> None:
    """A short run of bold, dense script covers more of its box than what's
    behind it: Hindi at the app's Normal (1.3) read "#e9ecf1 on #e9ecf1"
    (polyglotic-hq 524). What's behind is the most of the rest; text on
    its own colour still shows only that."""
    from PySide6.QtGui import QColor

    pen, dark = (233, 236, 241), (17, 21, 29)
    whole = QRectF(0, 0, 10, 10)
    dense = checks._behind(_box(pen, dark, 0.6), whole, QColor(*pen))
    assert dense is not None and dense.name() == QColor(*dark).name()
    alone = checks._behind(_box(pen, pen, 1.0), whole, QColor(*pen))
    assert alone is not None and alone.name() == QColor(*pen).name()
    sparse = checks._behind(_box(pen, dark, 0.3), whole, QColor(*pen))
    assert sparse is not None and sparse.name() == QColor(*dark).name()


@pytest.mark.parametrize("label", ["Mandarin · 21:43", "普通话"])
def test_outlined_text_on_transparent_scene_is_recognised_by_its_halo(
    qapp: QApplication,
    label: str,
) -> None:
    """Outlined small labels on a transparent panel have no solid box; the
    contrast check reads their immediate outline halo, while un-outlined text
    on the same low-contrast scene still fails."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextLayout

    from polyglotic_desktop.ui_next.caption_layout import draw_text_edge
    from polyglotic_desktop.ui_next.views.caption_window import TextEdge

    def render(outlined: bool) -> QImage:
        image = QImage(160, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor("#4a5a6a"))
        painter = QPainter(image)
        font = QFont("Segoe UI")
        font.setPixelSize(12)
        layout = QTextLayout(label, font)
        layout.beginLayout()
        layout.createLine()
        layout.endLayout()
        pen = QColor("#aab2c0")
        at = QPointF(12, 10)
        if outlined:
            draw_text_edge(painter, layout, at, pen, TextEdge.OUTLINE)
        painter.setPen(pen)
        layout.draw(painter, at)
        painter.end()
        return image

    rect = QRectF(12, 10, 120, 18)
    pen = QColor("#aab2c0")
    scene = QColor("#4a5a6a")
    outlined_halo = checks._outline_halo(checks._array(render(True)), rect, pen, scene)
    plain_halo = checks._outline_halo(checks._array(render(False)), rect, pen, scene)
    assert outlined_halo is not None and outlined_halo.name() == "#000000"
    assert plain_halo is None


def test_only_a_surrounding_edge_counts_as_a_halo_on_a_thick_stroke() -> None:
    from PySide6.QtGui import QColor

    pen, scene = (170, 178, 192), (74, 90, 106)
    pixels = _box(pen, scene, 0.0)
    pixels[2:8, 2:8, :3] = pen
    rect = QRectF(0, 0, 10, 10)
    # A shadow on two sides still leaves the stroke against the scene.
    pixels[8, 2:9, :3] = pixels[2:8, 8, :3] = 0
    assert checks._outline_halo(pixels, rect, QColor(*pen), QColor(*scene)) is None
    pixels[1, 1:9, :3] = pixels[2:9, 1, :3] = 0
    halo = checks._outline_halo(pixels, rect, QColor(*pen), QColor(*scene))
    assert halo is not None and halo.name() == "#000000"
