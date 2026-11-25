"""The new interface's look for its own windows: a theme's colours as
tokens, and a stylesheet scoped to one window - never the application's
(decision 0031: `QApplication.setStyleSheet` restyled every widget in the
app on a theme change, 180 ms).

The theme itself - Margin, Glaze or Signal, light or dark (decision 0029)
- is today's `ui.theme`'s: `main` hands its colours over as a `Theme`
(this package can't import `ui`). The stylesheet is today's, in the
theme's colours, with the same object names (`Card`, `PageTitle`,
`Segmented`, `kind="primary"`, ...) - so today's pages, handed to the new
main window until they move over (109's step 6), look as they did - plus
the new parts' few. Painted parts (a switch, a status dot) read
`current()` when they paint, so a theme change repaints them and lays out
nothing.

**Text size** follows Windows' (Settings > Accessibility > Text size; 135's
proposal A) times the app's own (Settings > App > Text size: Smaller,
Normal, Larger, Largest - polyglotic-hq 292, decision 0084; its steps
since decision 0244, Normal 1.3 times the text before there was a
choice): one factor,
`text_scale()`. `main` reads Windows' from the system font as Qt reads it
(`text_scale_of`) and the app's from the settings (`use_app_text_size`).
Every size the interface sets for its text, or for room that holds text,
goes through `px()` - this stylesheet's, the painted fonts', the columns'
and the minimum window's. Paddings, borders and gaps stay as they are, as
Windows' own do. Captions keep their own size (a caption window's A- /
A+): neither factor touches them.
"""

import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QToolTip

from polyglotic_desktop.ui_next import caption_faces, fonts
from polyglotic_desktop.ui_next.views.presets import readable_on


def button_text(text: str) -> str:
    """Show literal ampersands in a Qt button or menu action."""
    return text.replace("&", "&&")


def _chinese(traditional: bool) -> tuple[list[str], list[str]]:
    """The interface's Chinese faces: Windows' - Traditional's (JhengHei)
    first for a Traditional interface - and another OS's own (`fonts`)."""
    chinese = ["Microsoft YaHei UI", "Microsoft JhengHei UI"]
    others = [*fonts.also("zh"), *fonts.also("zh-hant")]
    if traditional:
        chinese.reverse()
        others = [*fonts.also("zh-hant"), *fonts.also("zh")]
    return chinese, others


SCRIPT_FACES = {
    "ja": ["Yu Gothic UI", "Meiryo UI"],
    "ko": ["Malgun Gothic"],
    "th": ["Leelawadee UI"],
    "hi": ["Nirmala UI"],
}
"""An interface language's own script's faces on Windows, put before the
Chinese ones (polyglotic-hq 294): a Japanese interface's kanji in a
Japanese face, never YaHei's Chinese shapes; Hangul, Thai and Devanagari
in Windows' own interface faces for them."""

INTERFACE_SCRIPTS = {"ja": "ja", "ko": "ko", "th": "th", "hi": "deva"}
"""An interface language's script, for another OS's own faces for it
(`fonts.also`)."""


def script_faces(language: str, system: str = sys.platform) -> list[str]:
    """An interface language's own script's faces, before the Chinese ones:
    Windows' (`SCRIPT_FACES`), then this OS's (`fonts.also`) - on Linux a
    Japanese interface's kanji in Noto Sans CJK JP, never in the Chinese
    face its list names next (Noto Sans CJK SC), whose shapes are China's
    (polyglotic-hq 571); on a Mac in Hiragino Sans."""
    script = INTERFACE_SCRIPTS.get(language, "")
    return [*SCRIPT_FACES.get(language, []), *fonts.also(script, system)]


def _ui_families(traditional: bool, language: str = "") -> list[str]:
    """Windows' interface font and another OS's own Latin one (`fonts`),
    then the interface language's own script's faces (`script_faces`), then
    its Chinese (`_chinese`, and another OS's). Another OS's Latin face
    comes before the script's, as Segoe UI does on Windows: on Linux a
    Japanese or Korean interface's Latin letters were in Noto Sans CJK's,
    and a Hindi one's in Noto Sans Devanagari's, beside Noto Sans
    (polyglotic-hq 571's fonts check)."""
    chinese, others = _chinese(traditional)
    return [
        "Segoe UI Variable Text",
        "Segoe UI",
        *fonts.also("latin"),
        *script_faces(language),
        *chinese,
        *others,
    ]


UI_FAMILIES = _ui_families(traditional=False)
_UI_FAMILY_CSS = ", ".join(f"'{f}'" for f in UI_FAMILIES)
SYMBOLS = "Segoe UI Symbol"
"""Where a symbol in the interface's text (▾ ▴ ▸ ⚙) comes from when the
text's own fonts lack it: in every Windows since 7."""
_WITH_SYMBOLS = (
    *UI_FAMILIES,
    "Segoe UI Variable Display",  # the lookup card's and captions' Latin
    "Microsoft YaHei",
    "Microsoft JhengHei",
)


def use_interface_language(language: str, listed: bool = True) -> None:
    """The interface's Chinese in its own script's font: Traditional's
    (JhengHei, Taiwan's glyph shapes) before Simplified's (YaHei) for a
    Traditional interface. Set once at start, before the first window
    (polyglotic-hq 156). And its symbols from SYMBOLS (`use_symbols`), and
    its Chinese faces behind every font (`use_chinese_behind_every_font`).

    `listed=False`: behind the fonts the interface names only, which asks
    nothing of Windows' fonts - `main` at start, while they're read on a
    thread of their own (`fonts_ahead`); it calls this again, whole, once
    they're read and before any text is drawn (polyglotic-hq 322)."""
    global _UI_FAMILY_CSS
    traditional = language == "zh_TW"
    use_symbols()
    use_chinese_behind_every_font(traditional, script_faces(language), listed)
    if listed:
        caption_faces.log_missing_cjk_fonts()
    UI_FAMILIES[:] = _ui_families(traditional, language)
    _UI_FAMILY_CSS = ", ".join(f"'{f}'" for f in UI_FAMILIES)


CHINESE_FACES = frozenset(
    face.lower()
    for faces in (
        *(_chinese(False)),
        *(_chinese(True)),
        *(script_faces(language) for language in INTERFACE_SCRIPTS),
    )
    for face in faces
)
"""Every face `use_chinese_behind_every_font` may put behind a family, as
Qt keeps the faces behind one: in lower case."""


def use_chinese_behind_every_font(
    traditional: bool, own: Sequence[str] = (), listed: bool = True
) -> None:
    """The interface's Chinese faces (`_chinese`) behind every family Qt
    has and every one the interface names (`QFont.insertSubstitution`), so
    Chinese in a font list with no Chinese face of its own - what names no
    font (Qt's own Segoe UI), a menu, a tooltip, a dialog, today's pages,
    any new widget - is in the interface's Chinese face, not whatever
    Windows finds: MS UI Gothic, a Japanese one, in a Windows locale that
    isn't Chinese, Japanese or Korean (polyglotic-hq 176, 198, 215). Set at
    start, before any text is drawn: Qt keeps the fonts behind a family as
    it first found them.

    What a font list names always comes first, so Japanese text keeps the
    Japanese face its list names (`caption_layout.CJK_FAMILIES["ja"]`: the
    captions, the lookup card). Han characters are one script in Chinese
    and Japanese, so no font fallback can tell them apart: text whose
    language isn't known is Japanese when it has kana (`caption_layout`).

    Behind the symbols' face (`use_symbols`, which comes first) and before
    anything else behind a family; the faces' order follows the interface
    (changed, the old order goes). `own`: the interface language's own
    script's faces (`script_faces`), before the Chinese ones - a Japanese
    interface's menus draw their kanji in a Japanese face (polyglotic-hq
    294).

    `listed=False`: only the families the interface names. Listing Qt's
    families is the first use of Windows' fonts, and waits for them to be
    read (about 0.1 s, `fonts_ahead`); the names need no such look."""
    chinese, others = _chinese(traditional)
    named = {*_WITH_SYMBOLS, *QGuiApplication.font().families()}
    for family in {*QFontDatabase.families(), *named} if listed else named:
        kept = [f for f in QFont.substitutes(family) if f not in CHINESE_FACES]
        symbols = SYMBOLS.lower()  # Qt keeps them in lower case
        at = kept.index(symbols) + 1 if symbols in kept else 0
        QFont.removeSubstitutions(family)
        QFont.insertSubstitutions(
            family, [*kept[:at], *own, *chinese, *others, *kept[at:]]
        )


def ui_font() -> QFont:
    """The interface's fonts (`UI_FAMILIES`, the interface's Chinese face
    among them) for a window that has no stylesheet naming them - a caption
    window, its settings popover: its widgets and what it paints take them,
    at whatever size they set. Qt's own for a widget that names no font is
    Windows' Segoe UI alone, so Chinese came from whatever face Windows
    found: MS UI Gothic, a Japanese one, in an English locale
    (polyglotic-hq 176, 198). Only the families: the size is still the
    widget's or the application's."""
    font = QFont()
    font.setFamilies(list(UI_FAMILIES))
    return font


def use_symbols() -> None:
    """SYMBOLS behind every font the interface names
    (`QFont.insertSubstitution`). A symbol takes the script of the text
    before it, and the fonts tried for it are that script's: after
    Chinese text, Chinese fonts, which lack ▾ - so "收藏到 ▾" drew a box
    offscreen (the UI lab), and on Windows came from whatever font
    Windows found (MS UI Gothic, a Japanese one, on the user's PC)
    (polyglotic-hq 170, 176). Never twice: Qt keeps one of each."""
    for family in _WITH_SYMBOLS:
        QFont.insertSubstitution(family, SYMBOLS)


# Margin, dark: today's default window theme (ui.theme.MARGIN.dark)
MARGIN_DARK = {
    "BG": "#11151d",
    "SIDEBAR": "#141922",
    "SURFACE": "#181d27",
    "SURFACE_2": "#1f2532",
    "SURFACE_3": "#232b3a",
    "BORDER": "#2a3140",
    "TEXT": "#e9ecf1",
    "TEXT_DIM": "#a3abb9",
    "TEXT_FAINT": "#8c95a5",
    "ACCENT": "#e9ecf1",
    "ACCENT_HOVER": "#ffffff",
    "ACCENT_TEXT": "#11151d",
    "SUCCESS": "#6fcf97",
    "WARNING": "#f2c14e",
    "DANGER": "#ff8a80",
    "FOCUS": "#ff8fbe",
    "MARKER": "#5c2440",
}


@dataclass(frozen=True)
class Theme:
    """A window theme's colours by token (`BG`, `TEXT`, `ACCENT`, ...: the
    names of today's `ui.theme.Palette`) and its heading face."""

    tokens: Mapping[str, str] = field(default_factory=lambda: dict(MARGIN_DARK))
    heading_family: str = "Literata"
    dark: bool = True

    def __getitem__(self, token: str) -> str:
        return self.tokens.get(token) or MARGIN_DARK[token]


_current = Theme()


def current() -> Theme:
    """The theme the new interface's windows are in now."""
    return _current


def use(theme: Theme) -> None:
    global _current
    _current = theme


DEFAULT_POINTS = 9.0
"""Windows' interface font at 100 % text size: Segoe UI, 9 pt (Qt 6 takes
the application's font from Windows' message font, which Text size makes
larger)."""
COCOA_DEFAULT_POINTS = 13.0
"""Standard Qt application font on Cocoa, in points (macOS 15).
Compare larger system fonts with the native default before applying the app's text size."""
TEXT_SCALES = (1.0, 2.25)
"""Windows' Text size runs from 100 % to 225 %; a smaller system font
doesn't shrink the interface (text never under 12 px: the UI lab)."""
APP_TEXT_SIZES = {"smaller": 1.0, "normal": 1.3, "larger": 1.45, "largest": 1.75}
"""Settings > App > Text size: each step's factor, on top of Windows'
(decision 0084), the base 13 px text at 13, 17, 19 and 23 px. Shifted up
by decision 0244 (polyglotic-hq 524, the user, 2026-11-19: "normal should
be between larger to largest"): Normal, the default, between 0.1.9's
Larger (1.2) and Largest (1.45); Smaller is 0.1.9's Normal, the interface
as it was before there was a choice; Larger is 0.1.9's Largest; Largest
is new, and still fits the main window's floor (a 1366 x 768 laptop at
150 %: the UI lab's `w4_pages_at_floor`, up to its `FLOOR_SCALE`, 1.8)."""
SMALLEST_PX = 12
"""No text is drawn smaller, at any text size (the UI lab's `small_text`).
No step is under 1.0 since decision 0244 (0.1.9's Smaller was 0.9), so
this only holds if one ever is again."""

_text_scale = 1.0
_app_text_size = APP_TEXT_SIZES["normal"]


def text_scale() -> float:
    """How much larger the interface's text is than at 100 %: Windows' Text
    size times the app's own - at most Windows' largest (`TEXT_SCALES`),
    the range the interface is laid out for: at Windows' 200 % and Largest
    (2.9) a picker's text and a caption window's notices were cut off."""
    return min(_text_scale * _app_text_size, TEXT_SCALES[1])


def windows_text_scale() -> float:
    """Windows' Text size alone, as a factor (`use_text_scale`)."""
    return _text_scale


def use_text_scale(scale: float) -> None:
    """Windows' Text size from now on, as a factor (`text_scale_of`).
    Windows built from now on use it; `main` restyles the open ones."""
    global _text_scale
    _text_scale = min(max(scale, TEXT_SCALES[0]), TEXT_SCALES[1])


def app_text_size() -> float:
    """The app's own text size (Settings > App), as a factor."""
    return _app_text_size


def use_app_text_size(size: str) -> None:
    """The app's own text size from now on: an `APP_TEXT_SIZES` key - one
    it doesn't know is Normal. Windows built from now on use it; `main`
    restyles the open ones."""
    global _app_text_size
    _app_text_size = APP_TEXT_SIZES.get(size, APP_TEXT_SIZES["normal"])


def text_scale_of(font: QFont) -> float:
    """Scale the system font against the platform's standard point size."""
    points = font.pointSizeF()
    if points <= 0:  # set in pixels
        points = font.pixelSize() * 0.75
    normal = (
        COCOA_DEFAULT_POINTS
        if QGuiApplication.platformName() == "cocoa"
        else DEFAULT_POINTS
    )
    scale = round(points / normal, 2)
    return min(max(scale, TEXT_SCALES[0]), TEXT_SCALES[1])


def px(size: float) -> int:
    """`size` (in px at a factor of 1.0: Windows' 100 % and the app's
    Smaller) at the text size now. Never under `SMALLEST_PX`, nor shrinks
    what is already under it (a gap, an icon's offset)."""
    return max(round(size * text_scale()), min(round(size), SMALLEST_PX))


def at_app_text_size(font: QFont) -> QFont:
    """A font of Qt's own (the tray's menu's, a tooltip's: Windows', which
    already follows Windows' Text size) at the app's own text size too -
    its share of `text_scale()`, so within the same range - never under
    `SMALLEST_PX` unless it already was."""
    font = QFont(font)
    share = text_scale() / _text_scale
    smallest = SMALLEST_PX * 0.75  # in points, at 96 dpi: Qt's logical
    points = font.pointSizeF()
    if points > 0:
        font.setPointSizeF(max(points * share, min(points, smallest)))
    elif font.pixelSize() > 0:  # set in pixels
        pixels = font.pixelSize()
        font.setPixelSize(max(round(pixels * share), min(pixels, SMALLEST_PX)))
    return font


def size_qt_parts(menu: QMenu) -> None:
    """Qt's own parts that no window's stylesheet sizes - the tray's `menu`
    and its submenus (Transcript, Dictation language), and the tooltips of
    a window with no stylesheet (a caption window's) - at the app's own
    text size (`at_app_text_size`). From Windows' fonts as Qt has them each
    time, so it's never applied twice."""
    menus = [menu, *(action.menu() for action in menu.actions())]
    for each in (m for m in menus if isinstance(m, QMenu)):
        each.setFont(at_app_text_size(QApplication.font(each)))
    QToolTip.setFont(at_app_text_size(QApplication.font()))


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.3f})"


QUIET_ROLES = ("PageSubtitle", "Dim", "Faint", "Warning")
"""A label's roles (`controls.label`) the stylesheet also finds by the
label's `role` property: a note keeps its colour and size when it's given
an object name of its own."""


def _role(role: str) -> str:
    assert role in QUIET_ROLES
    return f'QLabel[role="{role}"]'


TICK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<path d="M3.5 8.5l3 3 6-7" fill="none" stroke="{colour}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
"""A check box's tick (`tick`), drawn in the indicator's 16 x 16."""
_ticks: tempfile.TemporaryDirectory[str] | None = None


def tick(colour: str) -> str:
    """A check box's tick in `colour`, as a file: a stylesheet's `image`
    reads one only from a file. Written once per colour, into a folder of
    this run's own that goes when it ends. "" if it can't be written: the
    box is then filled without its tick, its state still plain."""
    global _ticks
    try:
        if _ticks is None:
            _ticks = tempfile.TemporaryDirectory(prefix="polyglotic-")
        path = Path(_ticks.name) / f"tick-{QColor(colour).name()[1:]}.svg"
        if not path.exists():
            path.write_text(TICK_SVG.format(colour=colour), encoding="utf-8")
    except OSError:
        return ""
    return path.as_posix()


def _indicators(t: Theme) -> str:
    """Check boxes' and radio buttons' boxes in the theme's colours, not
    Windows' (polyglotic-hq 425: the consent screen's were drawn for
    Windows' light or dark mode - on a window in the other, 1.1:1 against
    its background, unseen). Their edge is TEXT_DIM and a checked one is
    filled with ACCENT, each at least 3:1 against the window and its cards
    (WCAG 2.2's 1.4.11; tests/ui/test_check_boxes.py). As big as Windows
    11's own: 20 px with the edge, at 100 %."""
    box = px(18)
    ring = (box + 2) // 2  # a radio button's round
    checked = tick(t["ACCENT_TEXT"])
    image = f' image: url("{checked}");' if checked else ""
    ACCENT, ACCENT_TEXT = t["ACCENT"], t["ACCENT_TEXT"]
    TEXT, TEXT_DIM, TEXT_FAINT = t["TEXT"], t["TEXT_DIM"], t["TEXT_FAINT"]
    dot = (
        "qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, "
        f"stop:0 {ACCENT_TEXT}, stop:0.38 {ACCENT_TEXT}, stop:0.46 {ACCENT}, "
        f"stop:1 {ACCENT})"
    )
    return f"""
QCheckBox::indicator, QRadioButton::indicator {{
    width: {box}px; height: {box}px; border: 1px solid {TEXT_DIM}; background: transparent;
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: {ring}px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {TEXT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT};{image} }}
QRadioButton::indicator:checked {{ background: {dot}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {TEXT_FAINT}; }}
QCheckBox::indicator:checked:disabled {{ background: {TEXT_FAINT}; border-color: {TEXT_FAINT}; }}
"""


CAPTION_BADGE_RADIUS = 8
CAPTION_BADGE_INSET = (3, 8)
"""Logical pixels, 0–12. Round the state badge and leave space around its words."""


def stylesheet(t: Theme) -> str:
    """A window's stylesheet in theme `t`'s colours, its text at the text
    size now (`px`): today's, and the new parts'."""
    BG, SIDEBAR, SURFACE = t["BG"], t["SIDEBAR"], t["SURFACE"]
    SURFACE_2, SURFACE_3, BORDER = t["SURFACE_2"], t["SURFACE_3"], t["BORDER"]
    TEXT, TEXT_DIM, TEXT_FAINT = t["TEXT"], t["TEXT_DIM"], t["TEXT_FAINT"]
    ACCENT, ACCENT_HOVER, ACCENT_TEXT = t["ACCENT"], t["ACCENT_HOVER"], t["ACCENT_TEXT"]
    FOCUS, MARKER, WARNING = t["FOCUS"], t["MARKER"], t["WARNING"]
    content = BG if t.dark else SURFACE
    return f"""
* {{ outline: none; }}
QWidget {{ color: {TEXT}; font-size: {px(13)}px; font-family: {_UI_FAMILY_CSS}; }}
QMainWindow, QDialog, QTabWidget {{ background: {BG}; }}
#Page, #Content {{ background: {content}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}
#Card {{ background: transparent; border: none; }}
#CaptionIdle {{
    color: {readable_on(BG, WARNING)}; background: {WARNING};
    border-radius: {CAPTION_BADGE_RADIUS}px; font-weight: 600;
    padding: {CAPTION_BADGE_INSET[0]}px {CAPTION_BADGE_INSET[1]}px;
}}
#CaptionActive {{ color: {readable_on(t["SUCCESS"], SURFACE)}; font-weight: 600; }}
#PageTitle {{ font-size: {px(24)}px; font-weight: 600; font-family: '{t.heading_family}', {_UI_FAMILY_CSS}; }}
#PageSubtitle, #Dim, {_role("PageSubtitle")}, {_role("Dim")} {{ color: {TEXT_DIM}; }}
#Faint, #machine_made, {_role("Faint")} {{ color: {TEXT_FAINT}; font-size: {px(12)}px; }}
#Warning, {_role("Warning")} {{ color: {WARNING}; }}
#Banner {{
    background: {rgba(WARNING, 0.14)}; border: 1px solid {rgba(WARNING, 0.5)};
    border-radius: 8px; padding: 6px 10px;
}}
#CardTitle {{ font-size: {px(14)}px; font-weight: 600; }}
#CardTitle[heading="true"] {{ font-size: {px(16)}px; }}
#PinnedCard {{ background: {content}; border: none; }}
#settings\\.preset_line {{ background: transparent; border: none; }}
#Brand {{ font-size: {px(15)}px; font-weight: 600; }}
#RowTitle {{ font-weight: 600; }}
#StateTitle {{ font-size: {px(20)}px; font-weight: 600; }}
#Stat {{ font-size: {px(28)}px; font-weight: 600; }}
#SectionLabel {{ color: {TEXT_FAINT}; font-size: {px(12)}px; font-weight: 600; letter-spacing: 0.6px; }}
QPushButton, QToolButton {{
    background: {SURFACE_2}; border: none; border-radius: 8px;
    padding: 6px 12px; color: {TEXT};
}}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_3}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {TEXT_FAINT}; }}
QPushButton[kind="primary"], QToolButton[kind="primary"] {{
    background: {ACCENT}; color: {ACCENT_TEXT}; border: none; font-weight: 600;
}}
QPushButton[kind="primary"]:hover, QToolButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QToolButton:checked {{
    background: {rgba(ACCENT, 0.22)}; color: {ACCENT}; font-weight: 600;
}}
QToolButton[kind="primary"]:checked {{ background: {ACCENT}; color: {ACCENT_TEXT}; border: none; }}
QToolButton[kind="primary"]:checked:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[kind="ghost"], QToolButton[kind="ghost"] {{
    background: transparent; border: none; color: {TEXT_DIM}; padding: 5px 9px;
}}
QPushButton[kind="ghost"]:hover, QToolButton[kind="ghost"]:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton[kind="ghost"]:disabled, QToolButton[kind="ghost"]:disabled {{ color: {TEXT_FAINT}; }}
QPushButton[kind="small"] {{ padding: 3px 9px; border-radius: 6px; }}
QPushButton[kind="name"] {{
    background: transparent; border: none; text-align: left; padding: 2px 4px; font-weight: 600;
}}
QPushButton[kind="name"]:hover {{ background: {SURFACE_2}; }}
QPushButton[kind="section"] {{
    background: transparent; border: none; text-align: left; padding: 4px 8px;
    font-size: {px(17)}px; font-weight: 600;
}}
QPushButton[kind="section"]:hover {{ background: {SURFACE_2}; }}
QLineEdit, QComboBox, QPlainTextEdit {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 10px; selection-background-color: {MARKER}; selection-color: {TEXT};
}}
QLineEdit {{ placeholder-text-color: {TEXT_DIM}; }}
QLabel {{ selection-background-color: {MARKER}; selection-color: {TEXT}; }}
QComboBox[kind="chip"] {{ padding: 2px 8px; border-radius: 10px; }}
QComboBox[drop="own"]::drop-down {{ border: none; background: transparent; width: {px(22)}px; }}
QComboBox[drop="own"]::down-arrow {{ image: none; width: 0px; height: 0px; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {FOCUS}; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; }}
QTextBrowser {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px;
    selection-background-color: {MARKER}; selection-color: {TEXT};
}}
QScrollArea {{ background: transparent; border: none; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 8px 16px; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTableWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {SURFACE_2}; color: {TEXT_DIM}; border: none; padding: 5px; }}
QFileDialog QTreeView, QFileDialog QListView {{
    background: {SURFACE}; alternate-background-color: {SURFACE_2};
    color: {TEXT}; border: 1px solid {BORDER};
}}
QFileDialog QTreeView::item:hover, QFileDialog QListView::item:hover {{ background: {SURFACE_3}; }}
QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected {{
    background: {rgba(ACCENT, 0.22)}; color: {TEXT};
}}
QFileDialog QHeaderView {{ background: {SURFACE_2}; }}
QFileDialog QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QFileDialog QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 3px; min-width: 30px; }}
QFileDialog QScrollBar::handle:horizontal:hover {{ background: {TEXT_FAINT}; }}
QCheckBox {{ spacing: 8px; }}
{_indicators(t)}
/* the first run's code box and language list: their edges at least 3:1 (425, 658) */
#SignInDialog QLineEdit {{ border-color: {TEXT_FAINT}; }}
#SignInDialog QLineEdit:focus {{ border-color: {FOCUS}; }}
#LanguagePicker QListWidget {{ border-color: {TEXT_FAINT}; }}
#LanguagePicker QListWidget:focus {{ border-color: {FOCUS}; }}
#Sidebar {{ background: {SIDEBAR}; }}
#NavButton {{
    background: transparent; border: none; border-radius: 8px; text-align: left;
    padding: 9px 12px 9px {px(38)}px; color: {TEXT_DIM}; font-size: {px(13)}px;
}}
#NavButton:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
#NavButton:checked {{ background: {SURFACE_3}; color: {TEXT}; font-weight: 600; }}
#FootButton {{
    background: transparent; border: none; border-radius: 8px; text-align: left;
    padding: 5px 12px 5px {px(34)}px; color: {TEXT_FAINT}; font-size: {px(12)}px;
}}
#FootButton:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
#FootButton:checked {{ background: {SURFACE_3}; color: {TEXT}; font-weight: 600; }}
#SidebarQuitButton {{ padding-left: {px(34)}px; }}
QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: {TEXT};
}}
QListWidget {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {SURFACE_3}; }}
QListWidget::item:selected {{ background: {rgba(ACCENT, 0.22)}; color: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; height: 0;
}}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_2}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 4px; }}
QFrame[banner="true"] {{ background: {SURFACE_2}; border: none; border-radius: 9px; }}
#Segmented, QFrame[segmented="true"] {{ background: {SURFACE_2}; border: none; border-radius: 9px; }}
#Segmented QPushButton {{
    background: transparent; border: none; border-radius: 6px; padding: 6px 12px; color: {TEXT_DIM};
}}
QFrame[segmented="true"] QPushButton {{
    background: transparent; border: none; border-radius: 6px; padding: 4px 6px; color: {TEXT_DIM};
}}
#Segmented QPushButton:hover, QFrame[segmented="true"] QPushButton:hover {{ color: {TEXT}; }}
#Segmented QPushButton:checked, QFrame[segmented="true"] QPushButton:checked {{
    background: {SURFACE_3}; color: {TEXT};
}}
QFrame[segmented="true"] QPushButton:disabled {{ color: {TEXT_FAINT}; }}
QToolButton[chip="true"] {{ padding: 3px 8px; border-radius: 10px; }}
QToolButton[chip="true"]::menu-indicator {{ image: none; width: 0px; }}
QToolButton[mark="true"] {{ padding: 3px 6px; border-radius: 10px; color: {TEXT_FAINT}; }}
QPushButton[switch="true"] {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    text-align: left; padding: 3px 42px 3px 8px; font-weight: 600;
}}
QPushButton[switch="true"]:hover {{ background: {SURFACE_2}; }}
#AppRow {{ background: transparent; border: none; }}
#AddRow {{ background: transparent; border-radius: 6px; }}
#AddRow:hover {{ background: {SURFACE_2}; }}
#AddRow:disabled QLabel {{ color: {TEXT_FAINT}; }}
#AddRow QPushButton[kind="primary"]:disabled {{ background: {SURFACE_2}; color: {TEXT_FAINT}; }}
"""
