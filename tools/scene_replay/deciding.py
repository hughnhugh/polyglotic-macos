"""The display's deciding functions, listed from the source by a stated test.

ADR-009 (polyglotic-hq project 933): the rulebook is complete only when its
rule tests cover every branch of "the listed deciding functions". This is
the list. A function is on it when it is in one of the display's files,
makes at least one choice, and the names it reads or writes say that the
choice is about what is drawn, where, in which ink or when.

- **A choice** is an `if`, a conditional expression, a `while`, a `match`
  arm, an `and`/`or`, a filtered comprehension, or a `min`/`max`/`sorted`
  call. A function with none cannot decide anything.
- **What, where, ink, when** are read off the function's own identifiers
  (`KINDS` below). It is a reading aid, not a proof: a function tagged
  `where` is one whose choices touch geometry names.
- **In the paint** means reachable from a `paintEvent` in the same file
  through calls the syntax tree can follow (`self.name(...)` within the
  class and its bases in the file, and module-level functions).
- **Not the caption display** (`ASIDE` below) are the window's chrome,
  its interface text and its settings plumbing: they choose, but not what a
  caption looks like. They are counted, not listed.

The list is generated (`python -m tools.scene_replay deciding --write`) and
checked (`... deciding --check`), so a new deciding function cannot join
the display unlisted.
"""

import ast
import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

PACKAGE = "src/polyglotic_desktop"

FILES = (
    # the six surface and renderer files (ADR-009's context)
    "ui_next/caption_window.py",
    "ui_next/caption_layout.py",
    "ui_next/video.py",
    "ui_next/transcript_window.py",
    "ui_next/reading_lines.py",
    "ui_next/caption_marks.py",
    # the caption rows before any window sees them
    "core/listening/display.py",
    # the plain views the six import to decide a caption's look
    "ui_next/views/arrivals.py",
    "ui_next/views/caption_window.py",
    "ui_next/views/captions.py",
    "ui_next/views/card_window_defaults.py",
    "ui_next/views/cards.py",
    "ui_next/views/dwell.py",
    "ui_next/views/flow.py",
    "ui_next/views/known_colours.py",
    "ui_next/views/lab.py",
    "ui_next/views/links.py",
    "ui_next/views/pacing.py",
    "ui_next/views/placement.py",
    "ui_next/views/pour.py",
    "ui_next/views/reveal.py",
    "ui_next/views/scroll.py",
    "ui_next/views/sentences.py",
    "ui_next/views/tone.py",
    "ui_next/views/zones.py",
    # three smaller files
    "ui_next/caption_surface.py",
    "ui_next/caption_selection.py",
    "ui_next/joined_window.py",
)
"""The display's 28 files, as ADR-009 names them: six surface files, the
caption rows in core, 18 view modules and three smaller files. Files that
join the display later (969's `views/row_positions.py`) are in `LATER`."""

LATER = ("ui_next/views/row_positions.py",)
"""Display files newer than ADR-009's count; listed the same way."""

KINDS: dict[str, frozenset[str]] = {
    "what": frozenset(
        [
            "rows",
            "lines",
            "clauses",
            "text",
            "elide",
            "elided",
            "ellipsis",
            "shown",
            "visible",
            "hidden",
            "hide",
            "show",
            "lines_in_view",
            "caption",
            "captions",
            "provisional",
            "live",
            "finished",
            "withdrawn",
            "label",
            "labels",
            "translation",
            "original",
            "reading",
            "readings",
            "wrap",
            "wrapped",
            "breaks",
            "split",
            "overflow",
            "lines_shown",
            "cards",
            "card",
            "deck",
            "zone",
            "placed",
            "turning",
            "keep",
            "kept",
            "drop",
            "dropped",
            "trim",
        ]
    ),
    "where": frozenset(
        [
            "top",
            "bottom",
            "left",
            "right",
            "x",
            "y",
            "rect",
            "height",
            "width",
            "translate",
            "translated",
            "moveTo",
            "setPosition",
            "lineAt",
            "offset",
            "pad",
            "gap",
            "indent",
            "slot",
            "at_rest",
            "rest",
            "baseline",
            "anchor",
            "scroll",
            "scrolled",
            "clear_top",
            "position",
            "positions",
            "geometry",
            "margin",
            "align",
            "alignment",
            "centre",
            "center",
            "lift",
            "rise",
        ]
    ),
    "ink": frozenset(
        [
            "color",
            "colour",
            "ink",
            "pen",
            "brush",
            "setPen",
            "setBrush",
            "opacity",
            "setOpacity",
            "alpha",
            "tone",
            "toned",
            "fill",
            "fillRect",
            "drawText",
            "draw",
            "highlight",
            "lit",
            "dim",
            "bright",
            "brightness",
            "underline",
            "mark",
            "marks",
            "marked",
            "link",
            "links",
            "known",
            "contrast",
            "shade",
            "background",
            "foreground",
        ]
    ),
    "when": frozenset(
        [
            "clock",
            "now",
            "time",
            "timer",
            "start",
            "stop",
            "singleShot",
            "elapsed",
            "due",
            "hold",
            "held",
            "delay",
            "fade",
            "fading",
            "glide",
            "gliding",
            "arriving",
            "arrival",
            "arrivals",
            "settle",
            "settled",
            "dwell",
            "pace",
            "pacing",
            "tick",
            "frame",
            "animate",
            "animation",
            "spring",
            "duration",
            "interval",
            "wait",
            "waiting",
            "pending",
            "update",
            "repaint",
        ]
    ),
}

ASIDE: tuple[tuple[str, str, str], ...] = (
    # (file ending, pattern on the qualified name, why it is not a caption rule)
    (
        "caption_window.py",
        (
            r"^(live_tip|mic_button_tip|quiet_tip|reading_hint|word_hint|"
            r"whose_captions|notice_text|locked_text|first_locked_text|lock_tip|"
            r"preset_name|language_chip_label|chip_text|dropdown_label|"
            r"_caption_pace_text|spoken_in|CaptionWindow\.theme_words)$"
        ),
        "interface text",
    ),
    (
        "caption_window.py",
        (
            r"^(SourceTag|PaceRow|PaceLabel|MicButton|_OverlayScrollBar)\.|"
            r"^(bar_ink|band_alpha|_paint_glyph|band_style|card_bar_style|"
            r"pill_style|notice_style|laid_width|fit_glyph|shade)$|"
            r"^CaptionWindow\.(toggle_\w+|_?(sync|place|step|schedule|on|hide|reveal|"
            r"update)_(scroll_)?bar\w*|_bar_\w+|_\w*band\w*|_chip_\w+|"
            r"_strip_\w+|_draw_glyphs|_sync_controls|_style_line_actions|_action|"
            r"open_bar_controls|_on_label|_tip_text_size|set_usage|set_mic_level|"
            r"set_respeaking|set_unlock_keys|_show_links)$"
        ),
        "window chrome: the bar, its buttons and the scroll bar",
    ),
    (
        "caption_window.py",
        (
            r"^CaptionWindow\.(ask_set_up|_show_set_up|suggest_spoken|_nudge_\w+|"
            r"_place_nudge|question_foot|set_spoken_language|heard_language|"
            r"_sync_size_languages|set_capture_message|set_listening|set_connection|"
            r"set_hint|show_notice|_show_notice|_notice_place|notice_foot|"
            r"sync_notice_foot)$"
        ),
        "notices, questions and set-up prompts beside the captions",
    ),
    (
        "caption_window.py",
        (
            r"^CaptionWindow\.(copy_\w+|_copy|save_line|_look_up|_offer_sentence"
            r"(\.\w+)?|use_say_it|_said_now|_speaker|_finished_lines|_line_by_key)$"
        ),
        "actions on a line: copy, save, look up, say it",
    ),
    (
        "caption_window.py",
        (
            r"^(restore_minimised\.restore|work_areas|say_resized|to_qrect|to_rect)$|"
            r"^CaptionWindow\.(_primary|_area|area_at|area_now|_start_place|_set_place|"
            r"_minimum|move_by|_edges|take_place|set_host|changeEvent|batch_settings|"
            r"set_path|_path_changed|path_style)$"
        ),
        "where the window itself sits on the screen",
    ),
    (
        "transcript_window.py",
        (
            r"^(SettingsRail|_AppTag)\.|^TranscriptWindow\.(_tool|_build_strip|"
            r"_sync_strip|_fold|show_label|\w*rail\w*|\w*popover\w*|_export|"
            r"_copy_line|save_as|save_to|_keep_minimum|set_notice|set_theme|_slid)$|"
            r"^TranscriptList\.(copy_selection|selectedText|select_all|"
            r"_add_\w+|use_say_it|_said_now|better_voice\.done|contextMenuEvent|"
            r"menu_at|line_menu|_speaker|_sync_bar|_bar_moved)$"
        ),
        "the transcript window's strip, rail, menus and exports",
    ),
    (
        "joined_window.py",
        (
            r"^JoinedWindow\.(_action|toggle_settings|_place_bar|place_notice|"
            r"controls_width|area_at|_primary|_area|_minimum|_keep_minimum|"
            r"_set_place|place_at|reset_position|move_by|changeEvent|keyPressEvent)$"
        ),
        "the joined window's bar and its place on the screen",
    ),
)
"""Functions that choose, but not what a caption looks like. Each is set
aside by name with its reason, so the list errs towards listing: anything
this does not name is listed."""


@dataclass(frozen=True)
class Deciding:
    file: str
    name: str
    line: int
    choices: int
    kinds: tuple[str, ...]
    in_paint: bool

    @property
    def key(self) -> str:
        return f"{self.file}::{self.name}"


def _choices(node: ast.AST) -> int:
    count = 0
    for child in _own(node):
        if isinstance(child, ast.If | ast.IfExp | ast.While | ast.match_case):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            count += len(child.ifs)
        elif (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id in {"min", "max", "sorted"}
        ):
            count += 1
    return count


def _own(node: ast.AST) -> Iterator[ast.AST]:
    """`node`'s tree without the functions and classes nested in it."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(
            child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
        ):
            stack.extend(ast.iter_child_nodes(child))


def _names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    for child in _own(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
        elif isinstance(child, ast.keyword | ast.arg) and child.arg:
            found.add(child.arg)
    return found


def _words(names: set[str]) -> set[str]:
    """The names and the lower-case words inside them (`_seen_height` gives
    `seen` and `height`)."""
    words = set(names)
    for name in names:
        words.update(part for part in name.lower().split("_") if part)
    return words


def _calls(node: ast.AST) -> set[str]:
    """Names this function calls that the tree can resolve in its file."""
    found: set[str] = set()
    for child in _own(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            found.add(func.id)
        elif (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in {"self", "cls"}
        ):
            found.add("." + func.attr)
    return found


def _functions(
    tree: ast.Module,
) -> Iterator[tuple[str, str | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every function with its qualified name and its class, if any."""

    def walk(
        body: list[ast.stmt], prefix: str, owner: str | None
    ) -> Iterator[tuple[str, str | None, ast.FunctionDef | ast.AsyncFunctionDef]]:
        for item in body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                yield prefix + item.name, owner, item
                yield from walk(item.body, f"{prefix}{item.name}.", owner)
            elif isinstance(item, ast.ClassDef):
                yield from walk(item.body, f"{prefix}{item.name}.", item.name)

    yield from walk(tree.body, "", None)


def _painted(tree: ast.Module) -> set[str]:
    """Qualified names reachable from a `paintEvent` in this file."""
    bases: dict[str, list[str]] = {}
    for item in tree.body:
        if isinstance(item, ast.ClassDef):
            bases[item.name] = [b.id for b in item.bases if isinstance(b, ast.Name)]
    functions = {name: (owner, node) for name, owner, node in _functions(tree)}

    def method(owner: str, attr: str) -> str | None:
        seen: set[str] = set()
        queue = [owner]
        while queue:
            cls = queue.pop(0)
            if cls in seen:
                continue
            seen.add(cls)
            if f"{cls}.{attr}" in functions:
                return f"{cls}.{attr}"
            queue.extend(bases.get(cls, ()))
        return None

    reached: set[tuple[str, str]] = set()
    todo = [
        (name, owner or "")
        for name, (owner, _) in functions.items()
        if name.endswith(".paintEvent") and name.count(".") == 1
    ]
    while todo:
        name, cls = todo.pop()
        if (name, cls) in reached:
            continue
        reached.add((name, cls))
        _, node = functions[name]
        for call in _calls(node):
            target = method(cls, call[1:]) if call.startswith(".") else call
            if target in functions:
                todo.append((target, cls if call.startswith(".") else ""))
    names = {name for name, _ in reached}
    for name in list(names):  # a nested helper is painted with its parent
        names.update(n for n in functions if n.startswith(name + "."))
    return names


def _aside(file: str, name: str) -> str | None:
    for ending, pattern, reason in ASIDE:
        if file.endswith(ending) and re.search(pattern, name):
            return reason
    return None


@dataclass(frozen=True)
class Scan:
    listed: tuple[Deciding, ...]
    files: dict[str, dict[str, int]]
    """Per file: lines, functions, those that choose, those set aside."""
    aside: dict[str, int]
    """How many choosing functions each reason set aside."""


def scan(root: Path) -> Scan:
    """The deciding functions under `root` (a checkout) and the counts
    behind them."""
    listed: list[Deciding] = []
    files: dict[str, dict[str, int]] = {}
    aside: dict[str, int] = {}
    for file in (*FILES, *LATER):
        path = root / PACKAGE / file
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        painted = _painted(tree)
        tally = {"lines": source.count("\n"), "functions": 0, "choosing": 0, "aside": 0}
        for name, _, node in _functions(tree):
            tally["functions"] += 1
            choices = _choices(node)
            if not choices:
                continue
            tally["choosing"] += 1
            reason = _aside(file, name)
            if reason:
                tally["aside"] += 1
                aside[reason] = aside.get(reason, 0) + 1
                continue
            words = _words(_names(node) | {node.name})
            kinds = tuple(kind for kind, marks in KINDS.items() if words & marks)
            listed.append(
                Deciding(file, name, node.lineno, choices, kinds, name in painted)
            )
        files[file] = tally
    return Scan(tuple(listed), files, aside)


def as_json(root: Path) -> str:
    """The list as the checked file holds it: no line numbers, so an edit
    above a function does not make the list stale."""
    found = scan(root)
    return (
        json.dumps(
            {
                "files": found.files,
                "aside": found.aside,
                "deciding": [
                    {k: v for k, v in asdict(d).items() if k != "line"}
                    for d in found.listed
                ],
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )


def table(root: Path) -> str:
    """The Markdown table of counts by file, for the report and the docs."""
    found = scan(root)
    rows = [
        (
            "| File | Lines | Functions | That choose | Set aside | Deciding |"
            " In the paint | Choices in them |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    total = [0] * 7
    for file, tally in found.files.items():
        mine = [d for d in found.listed if d.file == file]
        row = [
            tally["lines"],
            tally["functions"],
            tally["choosing"],
            tally["aside"],
            len(mine),
            sum(d.in_paint for d in mine),
            sum(d.choices for d in mine),
        ]
        total = [a + b for a, b in zip(total, row, strict=True)]
        rows.append(f"| `{file}` | " + " | ".join(map(str, row)) + " |")
    rows.append("| **All** | " + " | ".join(f"**{n}**" for n in total) + " |")
    rows.append("")
    rows.append("| Set aside because | Functions |")
    rows.append("|---|---:|")
    rows.extend(f"| {reason} | {n} |" for reason, n in sorted(found.aside.items()))
    return "\n".join(rows) + "\n"
