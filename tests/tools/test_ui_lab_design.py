"""The UI lab's design detector (polyglotic-hq 347, decision 0140): each of
Impeccable's rules, translated for Qt, finds what it should on a window
built to break it and nothing on one that keeps it; the gate fails on new
findings only."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from tools.ui_lab import design, lab
from tools.ui_lab.checks import Finding, TextPiece

from polyglotic_desktop.ui_next import style


@pytest.fixture
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication(["test"])
    assert isinstance(app, QApplication)
    yield app


@pytest.fixture
def page(qapp: QApplication) -> Iterator[QWidget]:
    """A plain window, dark text on light."""
    shown = QWidget()
    shown.setObjectName("page")
    shown.setStyleSheet("QWidget { background: #ffffff; color: #111111; }")
    shown.resize(420, 240)
    yield shown
    shown.close()
    shown.deleteLater()


def found(widget: QWidget, rule: str) -> list[Finding]:
    widget.show()
    QApplication.processEvents()
    every = design.inspect(widget, lambda w: lab.photograph(w, False), windows=[widget])
    return [f for f in every if f.check == rule]


def label(parent: QWidget, text: str, name: str, px: int = 13) -> QLabel:
    shown = QLabel(text, parent)
    shown.setObjectName(name)
    font = QFont("Segoe UI")
    font.setPixelSize(px)
    shown.setFont(font)
    return shown


def test_text_on_the_type_scale_passes_and_off_it_is_found(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    rows.addWidget(label(page, "On the scale", "page.on", 13))
    rows.addWidget(label(page, "Off the scale", "page.off", 19))
    findings = found(page, "type_scale")
    assert [f.where for f in findings] == ["page.off (QLabel)"]
    assert "19 px" in findings[0].detail


def test_a_family_the_interface_doesnt_use_is_found(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    rows.addWidget(label(page, "Segoe UI", "page.ours"))
    odd = label(page, "Comic", "page.odd")
    font = odd.font()
    font.setFamilies(["Comic Sans MS"])
    odd.setFont(font)
    rows.addWidget(odd)
    assert [f.where for f in found(page, "font_family")] == ["page.odd (QLabel)"]


def test_text_that_names_no_family_is_in_the_applications_font(
    qapp: QApplication, page: QWidget
) -> None:
    """Offscreen on Linux the application's font is "Sans Serif", not
    Segoe UI: a button that named no font was a finding there, and the
    lab's gate failed on any window with one (357, CI on #679)."""
    before = QApplication.font()
    platform = QFont(before)
    platform.setFamilies(["Courier New"])  # not one the interface names
    QApplication.setFont(platform)
    QApplication.processEvents()  # the page has it too
    try:
        rows = QVBoxLayout(page)
        rows.addWidget(QPushButton("Start", page))
        odd = label(page, "Comic", "page.odd")
        font = odd.font()
        font.setFamilies(["Comic Sans MS"])
        odd.setFont(font)
        rows.addWidget(odd)
        assert [f.where for f in found(page, "font_family")] == ["page.odd (QLabel)"]
    finally:
        QApplication.setFont(before)


def test_text_over_text_is_found(page: QWidget) -> None:
    under = label(page, "Underneath here", "page.under")
    over = label(page, "Drawn over it", "page.over")
    under.move(10, 10)
    over.move(12, 11)
    assert found(page, "text_overlap")
    over.move(10, 60)
    assert not found(page, "text_overlap")


def test_text_hidden_by_an_opaque_pinned_heading_is_not_an_overlap(
    page: QWidget,
) -> None:
    under = label(page, "Its colours and headings.", "page.under")
    under.move(10, 10)
    pinned = QFrame(page)
    pinned.setObjectName("PinnedCard")
    pinned.setStyleSheet("background: #ffffff")
    pinned.setGeometry(8, 8, 220, 32)
    over = label(pinned, "Appearance", "page.pinned")
    over.move(4, 4)
    assert not found(page, "text_overlap")


def test_overlapping_children_of_the_same_pinned_card_are_found(page: QWidget) -> None:
    pinned = QFrame(page)
    pinned.setObjectName("PinnedCard")
    pinned.setGeometry(8, 8, 220, 40)
    first = label(pinned, "Appearance", "page.first")
    second = label(pinned, "Light or dark", "page.second")
    first.move(4, 4)
    second.move(5, 5)
    assert found(page, "text_overlap")


def test_control_raised_above_a_pinned_card_is_still_an_overlap(page: QWidget) -> None:
    pinned = QFrame(page)
    pinned.setObjectName("PinnedCard")
    pinned.setGeometry(8, 8, 220, 40)
    heading = label(pinned, "Appearance", "page.heading")
    heading.move(4, 4)
    neighbor = label(page, "Light or dark", "page.neighbor")
    neighbor.move(12, 12)
    neighbor.raise_()
    assert found(page, "text_overlap")


def test_a_list_row_scrolled_past_its_edge_isnt_over_the_text_above(
    page: QWidget,
) -> None:
    """The transcript's painted list draws its top row from above its own
    edge with no clip recorded (an empty `shown`), as the lab saw it at
    Largest: only the part inside the list's box counts."""
    tag = label(page, "Discord", "page.tag")
    tag.setGeometry(10, 30, 120, 24)
    rows = QWidget(page)
    rows.setObjectName("page.list")
    rows.setGeometry(0, 58, 400, 150)
    page.show()
    QApplication.processEvents()
    piece = TextPiece(
        rows,
        QRectF(16, 34, 131, 16),
        QRectF(),
        16.0,
        False,
        False,
        QColor("#e9ecf1"),
        None,
    )
    own = TextPiece(
        tag,
        QRectF(12, 34, 60, 16),
        QRectF(10, 30, 120, 24),
        13.0,
        False,
        False,
        QColor("#e9ecf1"),
        "Discord",
    )
    assert design._overlaps(page, [own, piece]) == []
    inside = TextPiece(
        rows,
        QRectF(16, 60, 131, 16),
        QRectF(),
        16.0,
        False,
        False,
        QColor("#e9ecf1"),
        None,
    )
    cover = QWidget(page)  # a second widget over the list, its text on a row
    cover.setObjectName("page.cover")
    cover.setGeometry(10, 55, 200, 40)
    over = TextPiece(
        cover,
        QRectF(12, 62, 60, 16),
        QRectF(),
        13.0,
        False,
        False,
        QColor("#e9ecf1"),
        "x",
    )
    assert len(design._overlaps(page, [over, inside])) == 1


def test_a_small_target_crowded_by_another_is_found(page: QWidget) -> None:
    small = QPushButton("x", page)
    small.setObjectName("page.small")
    small.setGeometry(10, 10, 40, 18)
    near = QPushButton("y", page)
    near.setObjectName("page.near")
    near.setGeometry(10, 30, 40, 30)
    assert [f.where for f in found(page, "target_size")] == ["page.small (QPushButton)"]
    near.move(10, 90)  # WCAG's spacing exception: a 24 px box touches nothing
    assert not found(page, "target_size")


def test_a_card_in_a_card_is_found(page: QWidget) -> None:
    outer = QFrame(page)
    outer.setObjectName("Card")
    inner = QFrame(outer)
    inner.setObjectName("Card")
    rows = QVBoxLayout(page)
    rows.addWidget(outer)
    QVBoxLayout(outer).addWidget(inner)
    assert len(found(page, "nested_cards")) == 1


def test_stray_strokes_find_both_edges_but_allow_field_borders(page: QWidget) -> None:
    page.setObjectName("Content")
    page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    field = QLineEdit(page)
    field.setGeometry(20, 20, 240, 30)
    border = style.current()["BORDER"]
    field.setStyleSheet(f"QLineEdit {{ border: 1px solid {border}; }}")
    page.show()
    page.setFocus()
    assert not found(page, "stray_stroke")

    for geometry in ((20, 90, 120, 1), (280, 90, 1, 100)):
        stroke = QFrame(page)
        stroke.setStyleSheet(f"QFrame {{ background: {border}; }}")
        stroke.setGeometry(*geometry)
        stroke.show()
    assert [finding.box for finding in found(page, "stray_stroke")] == [
        (20, 90, 120, 1),
        (280, 90, 1, 100),
    ]


def test_text_cramped_in_its_button_is_found(page: QWidget) -> None:
    tight = QPushButton("Export to Anki", page)
    tight.setObjectName("page.tight")
    tight.setStyleSheet("QPushButton { padding: 0px; border: 1px solid #888; }")
    tight.adjustSize()
    tight.setFixedWidth(tight.fontMetrics().horizontalAdvance("Export to Anki") + 2)
    roomy = QPushButton("Export", page)
    roomy.setObjectName("page.roomy")
    roomy.setStyleSheet("QPushButton { padding: 4px 12px; border: 1px solid #888; }")
    roomy.move(0, 60)
    assert [f.where for f in found(page, "cramped")] == ["page.tight (QPushButton)"]


def test_an_odd_margin_off_the_grid_is_found(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    rows.setContentsMargins(11, 12, 12, 12)
    rows.setSpacing(3)  # an optical inset: any value
    rows.addWidget(label(page, "Row", "page.row"))
    findings = found(page, "spacing_grid")
    assert len(findings) == 1
    assert "11" in findings[0].detail
    rows.setContentsMargins(12, 12, 12, 12)
    assert not found(page, "spacing_grid")


def test_a_near_miss_left_edge_is_found(page: QWidget) -> None:
    label(page, "Title", "page.title").move(16, 10)
    label(page, "Note under it", "page.note").move(19, 32)
    assert [f.where for f in found(page, "misaligned")] == ["page.note (QLabel)"]


def test_a_long_wrapped_line_is_found(page: QWidget) -> None:
    page.resize(1200, 200)
    text = " ".join(["word"] * 60)
    long = label(page, text, "page.long")
    long.setWordWrap(True)
    long.setGeometry(0, 0, 1180, 100)
    assert found(page, "line_length")
    long.setGeometry(0, 0, 420, 140)
    assert not found(page, "line_length")


def test_a_passage_in_capitals_is_found(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    rows.addWidget(label(page, "SECTION LABEL", "page.label"))
    rows.addWidget(
        label(page, "THIS WHOLE SENTENCE IS SHOUTED AT THE READER", "page.shout")
    )
    assert [f.where for f in found(page, "all_caps")] == ["page.shout (QLabel)"]


def test_wide_tracking_on_long_text_is_found(page: QWidget) -> None:
    spaced = label(page, "Letters spaced far apart in a sentence", "page.spaced")
    font = spaced.font()
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)  # 0.15 em at 13 px
    spaced.setFont(font)
    QVBoxLayout(page).addWidget(spaced)
    assert [f.where for f in found(page, "wide_tracking")] == ["page.spaced (QLabel)"]


def test_grey_text_on_a_saturated_background_is_found(page: QWidget) -> None:
    grey = label(page, "Grey on pink", "page.grey")
    grey.setStyleSheet("QLabel { background: #e0287a; color: #8a8a8a; }")
    QVBoxLayout(page).addWidget(grey)
    assert [f.where for f in found(page, "gray_on_color")] == ["page.grey (QLabel)"]


class Rounded(QWidget):
    """Draws rounded boxes with the radii it's given."""

    def __init__(self, parent: QWidget, radii: list[float]) -> None:
        super().__init__(parent)
        self.setObjectName("page.rounded")
        self.radii = radii
        self.resize(400, 60)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setBrush(self.palette().text())
        for i, radius in enumerate(self.radii):
            painter.drawRoundedRect(QRectF(4 + i * 50, 4, 44, 44), radius, radius)
        painter.end()


def test_a_radius_off_the_scale_and_too_many_radii_are_found(page: QWidget) -> None:
    Rounded(page, [8, 5])
    details = [f.detail for f in found(page, "corner_radius")]
    assert any("5 px corners" in d for d in details)
    assert not any("radii in one window" in d for d in details)


def test_a_fill_is_judged_by_its_border_beside_a_rounder_frame(page: QWidget) -> None:
    # polyglotic-hq 376: a 9 px frame paired with a tile's 8 px border, and
    # the 7 px fill inside that border was left alone, and flagged
    Rounded(page, [9, 8, 7])
    assert not found(page, "corner_radius")


def test_a_radius_a_pixel_under_nothing_is_still_found(page: QWidget) -> None:
    Rounded(page, [9, 7])
    details = [f.detail for f in found(page, "corner_radius")]
    assert any("7 px corners" in d for d in details)


def test_too_many_radii_in_one_window_are_found(page: QWidget) -> None:
    Rounded(
        page, [2, 4, 6, 8, 10, 12]
    )  # not 1 px apart: 2 and 3 would read as one border
    details = [f.detail for f in found(page, "corner_radius")]
    assert any("6 corner radii in one window" in d for d in details)


def test_a_circle_has_no_corner() -> None:
    circle = QPainterPath()
    circle.addEllipse(QRectF(0, 0, 20, 20))
    assert design.corner_radius(circle) is None
    rounded = QPainterPath()
    rounded.addRoundedRect(QRectF(0, 0, 40, 30), 6, 6)
    radius = design.corner_radius(rounded)
    assert radius is not None and abs(radius - 6) < 0.6


def test_an_icons_outline_has_no_corner() -> None:
    """A drawing in several pieces - a lock's body and its shackle, a
    speaker and its wave - has curves and no corner to hold to the scale
    (polyglotic-hq 376)."""
    icon = QPainterPath()
    icon.addRoundedRect(QRectF(3, 7, 10, 7), 1.5, 1.5)  # the body
    icon.moveTo(5, 7)
    icon.cubicTo(5, 2, 11, 2, 11, 7)  # the shackle
    assert design.corner_radius(icon) is None
    wave = QPainterPath()
    wave.moveTo(0, 0)
    for step in range(5):  # one piece, more curves than a box has corners
        wave.cubicTo(step * 10 + 3, 5, step * 10 + 6, 5, step * 10 + 10, 0)
    assert design.corner_radius(wave) is None


def test_a_finding_says_where_it_is_on_the_picture(page: QWidget) -> None:
    """Each rule boxes what it found (polyglotic-hq 376), so the judge's
    kit can draw it on the state's picture."""
    odd = label(page, "Odd", "page.odd", px=19)
    odd.move(120, 80)
    Rounded(page, [8, 5]).move(0, 150)
    page.show()
    QApplication.processEvents()
    every = design.inspect(page, lambda w: lab.photograph(w, False), windows=[page])
    off = next(f for f in every if f.check == "type_scale")
    assert off.box is not None
    x, y, width, height = off.box
    assert odd.geometry().adjusted(-1, -1, 1, 1).contains(QRect(x, y, width, height))
    corner = next(f for f in every if "5 px corners" in f.detail)
    assert corner.box is not None
    assert QRect(*corner.box).intersects(QRect(54, 154, 44, 44))  # the second shape
    assert off.to_json()["box"] == list(off.box)


def test_a_box_isnt_part_of_what_a_finding_is() -> None:
    one = Finding("type_scale", "page.odd (QLabel)", "19 px", box=(1, 2, 3, 4))
    other = Finding("type_scale", "page.odd (QLabel)", "19 px")
    assert one == other and len({one, other}) == 1
    assert "box" not in other.to_json()


class _Drawn(QWidget):
    """A picture of windows drawn together, as the lab's are."""

    def __init__(self, window: QWidget, at: QPoint, scale: float) -> None:
        super().__init__()
        self.drawn = (window, at, scale)
        self.resize(600, 400)

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        return [self.drawn]


def test_a_finding_on_a_window_drawn_in_a_picture_is_boxed_there(
    page: QWidget,
) -> None:
    odd = label(page, "Odd", "page.odd", px=19)
    odd.move(120, 80)
    picture = _Drawn(page, QPoint(100, 50), 0.5)
    page.show()
    QApplication.processEvents()
    every = design.inspect(picture, lambda w: lab.photograph(w, False), windows=[page])
    off = next(f for f in every if f.check == "type_scale")
    assert off.box is not None
    assert QRect(100 + 60 - 1, 50 + 40 - 1, odd.width(), odd.height()).contains(
        QRect(*off.box)
    )
    picture.deleteLater()


def test_a_finding_on_a_window_the_picture_doesnt_show_has_no_box(
    page: QWidget, qapp: QApplication
) -> None:
    label(page, "Odd", "page.odd", px=19).move(120, 80)
    elsewhere = QWidget()  # the state's picture: another window
    elsewhere.resize(200, 100)
    page.show()
    QApplication.processEvents()
    every = design.inspect(
        elsewhere, lambda w: lab.photograph(w, False), windows=[page]
    )
    assert next(f for f in every if f.check == "type_scale").box is None
    elsewhere.deleteLater()


def test_a_window_that_keeps_the_rules_has_no_findings(page: QWidget) -> None:
    rows = QVBoxLayout(page)
    rows.setContentsMargins(16, 16, 16, 16)
    rows.setSpacing(8)
    rows.addWidget(label(page, "Captions appear here", "page.hint"))
    buttons = QHBoxLayout()
    start = QPushButton("Start", page)
    start.setObjectName("page.start")
    start.setStyleSheet("QPushButton { padding: 6px 12px; }")
    buttons.addWidget(start)
    rows.addLayout(buttons)
    page.show()
    QApplication.processEvents()
    every = design.inspect(page, lambda w: lab.photograph(w, False), windows=[page])
    assert every == []


def test_the_gate_fails_on_new_findings_only(tmp_path: Path) -> None:
    old = Finding("target_size", "picker.name.2 (QPushButton)", "319 x 21 px")
    moved = Finding("target_size", "picker.name.3 (QPushButton)", "300 x 21 px")
    fresh = Finding("type_scale", "page.off (QLabel)", "19 px")
    baseline = tmp_path / "baseline.json"
    assert design.accept([("ui_next.w4_home", old)], baseline) == 1
    accepted = design.baseline(baseline)
    # the same rule on the same widget (numbers in its name aside) is not new
    assert design.new([("ui_next.w4_home", moved)], accepted) == []
    new = design.new([("ui_next.w4_home", fresh), ("ui_next.w4_other", old)], accepted)
    assert len(new) == 2
    assert json.loads(baseline.read_text(encoding="utf-8")) == [
        "ui_next.w4_home | target_size | picker.name.# (QPushButton)"
    ]


class _Renamed(QLabel):
    """A label of the interface's own (343's `Text`)."""


class _RenamedAgain(QLabel):
    """The same label, its class renamed."""


class _Layout(QHBoxLayout):
    pass


def test_a_baseline_survives_renaming_a_widgets_class(tmp_path: Path) -> None:
    """343 turned QLabels into its own `Text`: 124 known findings looked new
    (polyglotic-hq 357). A widget is keyed by its name and Qt's class."""
    baseline = tmp_path / "baseline.json"
    kept = [
        "s | line_length | page.note (QLabel)",  # as kept before 360
        "s | line_length | page.hint (_Renamed)",
        "s | corner_radius | caption_window.# > _Renamed",
        "s | spacing_grid | page.row (QWidget) _Layout",
        "s | spacing_grid | _Renamed QHBoxLayout",
    ]
    baseline.write_text(json.dumps(kept), encoding="utf-8")
    accepted = design.baseline(baseline)
    found = [
        Finding("line_length", "page.note (_Renamed)", "lines of ~90"),
        Finding("line_length", "page.hint (_RenamedAgain)", "lines of ~90"),
        Finding("corner_radius", "caption_window.2 > _RenamedAgain", "5 radii"),
        Finding("spacing_grid", "page.row (QWidget) QHBoxLayout", "spacing 9"),
        Finding("spacing_grid", "QLabel QHBoxLayout", "spacing 9"),
    ]
    assert design.new([("s", f) for f in found], accepted) == []
    # another Qt class, or another widget, is still new
    other = [
        Finding("line_length", "page.note (QPushButton)", "lines of ~90"),
        Finding("line_length", "page.other (_Renamed)", "lines of ~90"),
    ]
    assert len(design.new([("s", f) for f in other], accepted)) == 2
    # and kept as Qt's
    design.accept([("s", f) for f in found], baseline)
    assert json.loads(baseline.read_text(encoding="utf-8")) == sorted(
        [
            "s | line_length | page.note (QLabel)",
            "s | line_length | page.hint (QLabel)",
            "s | corner_radius | caption_window.# > QLabel",
            "s | spacing_grid | page.row (QWidget) QHBoxLayout",
            "s | spacing_grid | QLabel QHBoxLayout",
        ]
    )


def test_a_class_name_on_two_qt_classes_is_kept_as_it_is() -> None:
    twice = (type("_Twice", (QLabel,), {}), type("_Twice", (QPushButton,), {}))
    classes = design.qt_classes()
    assert classes["_Renamed"] == "QLabel" and "_Twice" not in classes
    assert design.on_qt("a (_Twice)", classes) == "a (_Twice)"
    # an object name is never read as a class
    assert design.on_qt("painted (QWidget)", {"painted": "QLabel"}) == (
        "painted (QWidget)"
    )
    assert twice


def test_the_report_marks_new_findings() -> None:
    accepted = frozenset({design.key("s", Finding("cramped", "a", "x"))})
    text = design.markdown(
        [("s", Finding("cramped", "a", "x")), ("s", Finding("cramped", "b", "y"))],
        accepted,
    )
    assert "- s · a · x\n" in text
    assert "- s · b · y **new**" in text


def test_the_labs_gate_fails_on_a_new_design_finding_until_accepted(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.ui_lab import __main__ as cli
    from tools.ui_lab import goldens, new_parts

    def odd(lab_: lab.Lab) -> QWidget:
        shown = QWidget()
        shown.setObjectName("lab_page")
        shown.setMinimumSize(100, 50)
        row = QHBoxLayout(shown)  # Qt's margins: 11 px, off the grid
        button = QPushButton("Start", shown)
        button.setObjectName("lab_page.start")
        row.addWidget(button)
        shown.show()
        return shown

    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(goldens, "GOLDENS", tmp_path / "goldens")
    monkeypatch.setattr(design, "BASELINE", tmp_path / "baseline.json")
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.setattr(new_parts, "STATES", [lab.State("ui_next.odd", odd, True)])
    assert (
        cli.main(["approve", "--reason", "a test", "--out", str(tmp_path / "approve")])
        == 0
    )
    capsys.readouterr()
    assert cli.main(["--gate", "--checks-only", "--out", str(tmp_path / "a")]) == 1
    said = capsys.readouterr().err.splitlines()
    assert said[-1] == (  # one line, last (polyglotic-hq 357)
        "gate failed: 0 over budget, 0 checks failed, 0 goldens differ,"
        " 1 new design finding"
    )
    report = (tmp_path / "a" / "design.md").read_text(encoding="utf-8")
    assert any(
        line.startswith("- ui_next.odd") and line.endswith("**new**")
        for line in report.splitlines()
    )
    assert cli.main(["design", "--accept", "--out", str(tmp_path / "b")]) == 0
    assert cli.main(["--gate", "--checks-only", "--out", str(tmp_path / "c")]) == 0
    assert "gate failed" not in capsys.readouterr().err


def test_the_gates_line_counts_every_reason_it_failed() -> None:
    from tools.ui_lab import __main__ as cli

    assert cli.gate_failed([], [], [], []) is None
    assert cli.gate_failed(["a"], ["b", "c"], ["d"], ["e", "f", "g"]) == (
        "gate failed: 1 over budget, 2 checks failed, 1 golden differs,"
        " 3 new design findings"
    )
