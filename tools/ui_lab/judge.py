"""The judge's kit: what an agent reads to review the new interface (project
108's design, section 5; built in project 119; the loop is in JUDGE.md).

    uv run python -m tools.ui_lab judge            # build/ui-lab/judge/

Runs every state of the new interface (as the gate does), then writes:

- `judge.md` - start here: each surface's states, their verdicts, the
  states 109 asks for and which the lab has, the interface's own words on
  screen (with any the glossary avoids), the checks' notes (Tab order,
  exemptions, elided text), and the checklist (`checklist.md`);
- `sheets/<surface>.png` - a contact sheet: every state of a surface on one
  image, labelled, scaled down (each state's own PNG, full size, is beside
  `judge.md`);
- `annotated/<state>.png` - a state's picture with each finding that has a
  place drawn on it as a numbered box, and the findings listed under it
  (polyglotic-hq 376: Impeccable's overlay, for a window);
- `findings.md` - the code checks' findings; `design.md` - the design
  detector's (Impeccable's rules for Qt, `design.py`); `timings.md` - the
  timings against the budgets; `goldens.md` - the pictures against their
  goldens.

Nothing here judges: it lays out what an agent (Claude or Fable) needs to.
"""

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from tools.ui_lab import design, goldens, lab
from tools.ui_lab.checks import Finding
from tools.ui_lab.lab import Result, State

CHECKLIST = Path(__file__).resolve().parent / "checklist.md"


@dataclass(frozen=True)
class Surface:
    """A part of the interface the judge looks at as one: its states share
    the first word of their name after `ui_next.`."""

    key: str
    title: str
    expected: tuple[str, ...] = ()
    """The states project 109's STRUCTURE.md draws for it, as words a lab
    state's name would hold (read 2026-11-07)."""


SURFACES = {
    surface.key: surface
    for surface in (
        Surface(
            "foundation",
            "The caption surface (foundation): what every caption window,"
            " transcript and joined window stands on",
        ),
        Surface(
            "w1",
            "W1, the caption window (STRUCTURE.md section 2)",
            (
                "idle",
                "hovered",
                "narrow",
                "locked",
                "scrolled_back",
                "paused",
                "notice",
                "fading",
                "hidden",
                "strip",
                "empty",
                "preview_line",
                "listening",
                "original_only",
                "my_speech",
            ),
        ),
        Surface(
            "w1j",
            "W1j, the joined window (STRUCTURE.md section 2a)",
            (
                "idle",
                "hovered",
                "two",
                "three",
                "strip",
                "empty",
                "scrolled_back",
                "locked",
                "notice",
                "separat",
            ),
        ),
        Surface(
            "w2",
            "W2, the transcript (STRUCTURE.md section 3)",
            (
                "following",
                "scrolled_back",
                "search",
                "empty",
                "rail",
                "paused",
                "notice",
                "1000",
                "minimum",
            ),
        ),
        Surface(
            "w3",
            "W3, the lookup card (STRUCTURE.md section 6)",
            ("hover", "pinned", "part", "not_found", "save_to"),
        ),
        Surface(
            "w4",
            "W4, the main window (STRUCTURE.md section 7)",
            (
                "home",
                "words",
                "account",
                "settings",
                "help",
                "first_run",
                "signed_out",
                "paused",
                "notice",
                "light",
                "dark",
                "minimum",
            ),
        ),
        Surface(
            "panel",
            "The three shared panels (STRUCTURE.md section 4)",
            ("languages", "timing", "look"),
        ),
    )
}
FOUNDATION = ("caption", "transcript", "joined")
"""The first words of the foundation's states (`new_parts.py`)."""
AVOID = {
    "overlay": "caption window (109's principle 6; DOMAIN.md keeps it as the term of art)",
    "final": "finished caption",
    "segment": "word split",
}
"""Words the glossary (DOMAIN.md) replaces on screen, and with what."""


def surface_of(state: str) -> Surface:
    first = state.removeprefix("ui_next.").split("_")[0]
    key = "foundation" if first in FOUNDATION else first
    return SURFACES.get(key) or Surface(key, key)


def run(states: list[State], out: Path) -> list[Result]:
    """Every state run into `out`, then the judge's files beside them."""
    results = lab.run(states, out, goldens.GOLDENS)
    write(results, out)
    return results


def write(results: list[Result], out: Path) -> None:
    groups: dict[str, list[Result]] = {}
    for result in results:
        groups.setdefault(surface_of(result.state).key, []).append(result)
    sheets = out / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    for stale in sheets.glob("*.png"):
        stale.unlink()
    for key, members in groups.items():
        contact_sheet(
            surface_of(members[0].state).title, members, sheets / f"{key}.png"
        )
    pictures = out / "annotated"
    pictures.mkdir(parents=True, exist_ok=True)
    for stale in pictures.glob("*.png"):
        stale.unlink()
    for result in results:
        picture = annotated(result)
        if picture is not None:
            picture.save(str(pictures / f"{result.state}.png"))
    (out / "findings.md").write_text(lab.findings_markdown(results), encoding="utf-8")
    (out / "design.md").write_text(design_markdown(results), encoding="utf-8")
    (out / "timings.md").write_text(lab.timings_markdown(results), encoding="utf-8")
    (out / "goldens.md").write_text(
        lab.goldens_markdown(results) or "No goldens compared.\n", encoding="utf-8"
    )
    (out / "judge.md").write_text(index(groups), encoding="utf-8")


def design_markdown(results: list[Result]) -> str:
    """The design detector's findings on the gated states, new ones marked."""
    found = [(r.state, f) for r in results if r.gated for f in r.design]
    return design.markdown(found, design.baseline())


# -- a state's picture with its findings drawn on it ----------------------------------

MARK, MARK_INK = "#ff2d95", "#ffffff"
"""A box's colour and its number's: a pink no window of ours is, so a box
is never taken for the interface (dark or light)."""
LEGEND_WIDTH = 640
"""The narrowest an annotated picture is: its legend's lines stay readable
under a small window's picture."""
LEGEND_PX, LEGEND_LINE, LEGEND_PAD = 13, 18, 10


def placed(result: Result) -> list[Finding]:
    """A state's findings, the design detector's then the code checks' (not
    waived): the order they're numbered in."""
    return [*result.design, *result.failed_checks()]


def annotated(result: Result) -> QImage | None:
    """The state's picture with each finding that has a place (`Finding.box`)
    drawn on it as a numbered box, and every finding listed under it by its
    number - one with no place (a count over a whole window; a window the
    picture doesn't show) too, without a box. None when the state has no
    picture or no finding. A finding's words are the checks': never a
    caption's (`checks._excerpt`)."""
    found = placed(result)
    if result.photo is None or not found:
        return None
    photo = result.photo
    font = QFont()
    font.setPixelSize(LEGEND_PX)
    width = max(photo.width(), LEGEND_WIDTH)
    lines: list[tuple[int, str]] = []
    for number, finding in enumerate(found, start=1):
        said = f"{number}  {finding.check} - {finding.where}: {finding.detail}"
        if finding.box is None:
            said += "  (no place on this picture)"
        for line in _wrapped(said, QFontMetrics(font), width - 2 * LEGEND_PAD):
            lines.append((number, line))
    legend = 2 * LEGEND_PAD + LEGEND_LINE * len(lines)
    picture = QImage(width, photo.height() + legend, QImage.Format.Format_RGB32)
    picture.fill(QColor(SHEET))
    painter = QPainter(picture)
    painter.drawImage(0, 0, photo)
    painter.setFont(font)
    for number, finding in enumerate(found, start=1):
        if finding.box is not None:
            _mark(painter, number, QRect(*finding.box), photo.rect())
    painter.setPen(QColor(INK))
    y = photo.height() + LEGEND_PAD
    for _number, line in lines:
        painter.drawText(
            QRect(LEGEND_PAD, y, width - 2 * LEGEND_PAD, LEGEND_LINE), 0, line
        )
        y += LEGEND_LINE
    painter.end()
    return picture


def _mark(painter: QPainter, number: int, box: QRect, within: QRect) -> None:
    """A finding's box, a pixel outside what it found, with its number on a
    tag at its top left (inside the picture's edges)."""
    around = box.adjusted(-2, -2, 1, 1).intersected(within.adjusted(0, 0, -1, -1))
    painter.setPen(QPen(QColor(MARK), 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(around)
    said = str(number)
    tag = QRect(0, 0, painter.fontMetrics().horizontalAdvance(said) + 8, LEGEND_LINE)
    tag.moveBottomLeft(around.topLeft())
    if tag.top() < within.top():  # no room above: inside its top left corner
        tag.moveTopLeft(around.topLeft())
    if tag.right() > within.right():
        tag.moveRight(within.right())
    painter.fillRect(tag, QColor(MARK))
    painter.setPen(QColor(MARK_INK))
    painter.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), said)


def _wrapped(text: str, metrics: QFontMetrics, width: int) -> list[str]:
    """`text` in lines no wider than `width`, broken between words."""
    lines, line = [], ""
    for word in text.split(" "):
        longer = f"{line} {word}" if line else word
        if line and metrics.horizontalAdvance(longer) > width:
            lines.append(line)
            line = f"    {word}"
        else:
            line = longer
    return [*lines, line]


# -- the contact sheet ----------------------------------------------------------------

COLUMNS = 3
CELL = (480, 320)
"""The most a state's picture takes on a sheet; never scaled up."""
MARGIN, GAP, LABEL = 20, 20, 22
SHEET, INK, DIM, BAD, GOOD = "#1b1e24", "#e9ecf2", "#a0a8b6", "#ff8a80", "#7ee0a8"


def verdict(result: Result) -> tuple[str, str]:
    """A state's verdict in a few words, and its colour."""
    said = []
    if result.over_budget():
        said.append("over budget")
    failed = len(result.failed_checks())
    if failed:
        said.append(f"{failed} finding{'s' if failed > 1 else ''}")
    if result.golden is not None and result.golden.failed:
        said.append(f"golden: {result.golden.status}")
    return (", ".join(said), BAD) if said else ("ok", GOOD)


def contact_sheet(title: str, results: list[Result], path: Path) -> None:
    """Every state on one image, labelled, `COLUMNS` to a row."""
    pictures = [(r, r.photo) for r in results if r.photo is not None]
    scaled = [
        (r, p.scaled(*CELL, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
         if p.width() > CELL[0] or p.height() > CELL[1] else p)
        for r, p in pictures
    ]  # fmt: skip
    rows = [scaled[i : i + COLUMNS] for i in range(0, len(scaled), COLUMNS)]
    heights = [LABEL + max(p.height() for _, p in row) for row in rows]
    width = 2 * MARGIN + COLUMNS * CELL[0] + (COLUMNS - 1) * GAP
    height = 2 * MARGIN + 34 + sum(heights) + GAP * max(0, len(rows) - 1)
    sheet = QImage(width, height, QImage.Format.Format_RGB32)
    sheet.fill(QColor(SHEET))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    heading = QFont()
    heading.setPixelSize(18)
    heading.setBold(True)
    painter.setFont(heading)
    painter.setPen(QColor(INK))
    painter.drawText(QRect(MARGIN, MARGIN, width - 2 * MARGIN, 26), 0, title)
    small = QFont()
    small.setPixelSize(13)
    painter.setFont(small)
    y = MARGIN + 34
    for row, row_height in zip(rows, heights, strict=True):
        for column, (result, picture) in enumerate(row):
            x = MARGIN + column * (CELL[0] + GAP)
            name = result.state.removeprefix("ui_next.")
            said, color = verdict(result)
            painter.setPen(QColor(INK))
            painter.drawText(QRect(x, y, CELL[0], LABEL - 4), 0, name)
            painter.setPen(QColor(color))
            painter.drawText(
                QRect(x, y, CELL[0], LABEL - 4), int(Qt.AlignmentFlag.AlignRight), said
            )
            painter.drawImage(x, y + LABEL, picture)
            painter.setPen(QColor(DIM))
            painter.drawRect(
                x - 1, y + LABEL - 1, picture.width() + 1, picture.height() + 1
            )
        y += row_height + GAP
    painter.end()
    sheet.save(str(path))


# -- judge.md ------------------------------------------------------------------------


def _avoided(words: list[str]) -> list[str]:
    found = []
    for word, instead in AVOID.items():
        pattern = re.compile(rf"\b{word}\b", re.IGNORECASE)
        for text in words:
            if pattern.search(text):
                found.append(
                    f"'{text}' says \"{word}\": the glossary's word is {instead}"
                )
    return found


def _commit() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return done.stdout.strip()


def index(groups: dict[str, list[Result]]) -> str:
    """judge.md: where to start."""
    when = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    machine = goldens.machine_note() or "the machine that made the goldens"
    lines = [
        "# The judge's run",
        "",
        f"{when}, commit {_commit()}, on {machine}. How to use this: `tools/ui_lab/JUDGE.md`.",
        "",
        "| Surface | States | Not ok | Sheet |",
        "|---|---|---|---|",
    ]
    for key, members in groups.items():
        bad = sum(1 for r in members if verdict(r)[0] != "ok")
        title = surface_of(members[0].state).title.split(" (")[0].split(":")[0]
        lines.append(
            f"| {title} | {len(members)} | {bad} | [sheets/{key}.png](sheets/{key}.png) |"
        )
    lines += [
        "",
        (
            "Also here: [findings.md](findings.md) (the code checks),"
            " [design.md](design.md) (the design detector; each state's findings"
            " drawn on its picture: `annotated/<state>.png`),"
            " [timings.md](timings.md) (against the budgets), [goldens.md](goldens.md),"
            " and each state's PNG and JSON, full size."
        ),
        "",
    ]
    for key, members in groups.items():
        lines += _surface_section(key, members)
    lines += ["", CHECKLIST.read_text(encoding="utf-8")]
    return "\n".join(lines) + "\n"


def _surface_section(key: str, members: list[Result]) -> list[str]:
    surface = surface_of(members[0].state)
    lines = [
        f"## {surface.title}",
        "",
        f"Sheet: [sheets/{key}.png](sheets/{key}.png)",
        "",
    ]
    lines += ["| State | Verdict | Picture |", "|---|---|---|"]
    for result in members:
        said, _ = verdict(result)
        lines.append(
            f"| {result.state} | {said} | [{result.state}.png]({result.state}.png) |"
        )
    if surface.expected:
        names = " ".join(r.state for r in members)
        have = [w for w in surface.expected if w in names]
        missing = [w for w in surface.expected if w not in names]
        lines += [
            "",
            (
                f"**States 109 draws:** in the lab: {', '.join(have) or 'none'}."
                f" Not seen: {', '.join(missing) or 'none'}."
            ),
        ]
    words = []
    for result in members:
        words += [w for w in result.words if w not in words]
    if words:
        lines += ["", "**The interface's words here:** " + " · ".join(words)]
        avoided = _avoided(words)
        if avoided:
            lines += [
                "",
                "**Words the glossary avoids:**",
                *[f"- {a}" for a in avoided],
            ]
    notes = []
    for result in members:
        notes += [n for n in result.notes if n not in notes]
    if notes:
        lines += ["", "**The checks' notes:**", *[f"- {n}" for n in notes]]
    return [*lines, ""]
