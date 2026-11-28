"""The window theme: colours and the heading face, for the main window,
the transcripts and today's dialogs (each window's stylesheet is the new
interface's own, from these colours: `main.window_theme`).

The window has a theme - Margin (the default), Glaze or Signal: polyglotic-hq
project 091's three directions (project 098, decision 0029) - each light
and dark, and the learner's choice of light, dark or like Windows (project
054) applies within it. A theme is its colours and its heading face, used
for page titles only; interface text stays on Windows' own fonts. Margin's
rule: buttons are ink, and pink only ever marks - the focus ring, a
selection. The caption windows stay near-black glass whatever the theme
(projects 049 and 087): their colours are the caption settings'.

`use(mode, name)` swaps the window's colours: the module's colour names
(BG, TEXT, ...) follow it, so code that reads them when it draws follows
too; `apply(choice, name)` also loads the theme's heading face. No
stylesheet is set on the whole app (decision 0031)."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    BG: str  # window
    SIDEBAR: str
    SURFACE: str  # cards, popups
    SURFACE_2: str  # inputs, buttons, hover
    SURFACE_3: str  # pressed, selected, tracks
    BORDER: str
    TEXT: str
    TEXT_DIM: str
    TEXT_FAINT: str
    ACCENT: str  # primary buttons, switches, sliders - and text on surfaces
    ACCENT_HOVER: str
    ACCENT_TEXT: str  # on ACCENT
    SUCCESS: str  # ok
    WARNING: str  # warn
    DANGER: str  # bad
    FOCUS: str  # the focus ring: a mark, at least 3:1 on the surfaces
    MARKER: str  # a highlighter's fill behind TEXT: a text selection
    NAV_HOME: str  # sidebar Home hue (blue; >=3:1 on SIDEBAR)
    NAV_WORDS: str  # sidebar Words hue (amber; >=3:1 on SIDEBAR)
    NAV_LEARNING: str  # sidebar Learning hue (green; >=3:1 on SIDEBAR)
    NAV_ACCOUNT: str  # sidebar Account hue (violet; >=3:1 on SIDEBAR)


# Sidebar section hues (polyglotic-hq 964): desaturated from ui_next's word-link
# palette (caption_marks.LINK_COLORS: blue #5c9dff, amber #ff9f43, green #3ddc97,
# violet #b388ff) so they sit quietly in both themes while clearing WCAG 1.4.11
# (>= 3:1) against SIDEBAR at rest (alpha 0.80), hover (0.92), and selected (1.0).
# Contrast against Margin's SIDEBAR (#eceef2 light / #141922 dark):
#   light (full / rest): Home 5.56 / 3.75, Words 4.93 / 3.44,
#                        Learning 5.30 / 3.63, Account 6.41 / 4.21
#   dark  (full / rest): Home 6.81 / 4.80, Words 8.08 / 5.58,
#                        Learning 8.50 / 5.87, Account 6.65 / 4.72
NAV_HUES_LIGHT: dict[str, str] = {
    "NAV_HOME": "#265dad",
    "NAV_WORDS": "#965710",
    "NAV_LEARNING": "#196f4a",
    "NAV_ACCOUNT": "#663ab3",
}
NAV_HUES_DARK: dict[str, str] = {
    "NAV_HOME": "#6fa3eb",
    "NAV_WORDS": "#e0a45c",
    "NAV_LEARNING": "#5ac896",
    "NAV_ACCOUNT": "#b28ee8",
}


@dataclass(frozen=True)
class Theme:
    """A look for the window: its colours, light and dark, and the face its
    page titles are set in (one static weight cut to Latin, bundled with its
    OFL text in `assets/fonts`)."""

    name: str  # as the learner sees it
    light: Palette
    dark: Palette
    heading_family: str  # the family inside `heading_file`
    heading_file: str


# Project 091's palettes (its brand page's light and dark values), with the
# steps it didn't give (SURFACE_2, TEXT_FAINT, ACCENT_HOVER) made to fit.
# Every text pair is at least 4.5:1 (tests/ui/test_window_theme.py).
MARGIN = Theme(
    "Margin",  # ink on paper and a pink marker: the learner's notebook
    light=Palette(
        BG="#f5f6f7",
        SIDEBAR="#eceef2",
        SURFACE="#ffffff",
        SURFACE_2="#eef0f4",
        SURFACE_3="#e1e5ee",
        BORDER="#d8dce3",
        TEXT="#172033",
        TEXT_DIM="#4b5568",
        TEXT_FAINT="#5d6678",
        ACCENT="#172033",  # buttons are ink
        ACCENT_HOVER="#2b3753",
        ACCENT_TEXT="#f5f6f7",
        SUCCESS="#1d6b45",
        WARNING="#8a5a00",
        DANGER="#b42318",
        FOCUS="#b0185a",  # marker ink
        MARKER="#ffa8cc",
        **NAV_HUES_LIGHT,
    ),
    dark=Palette(
        BG="#11151d",
        SIDEBAR="#141922",
        SURFACE="#181d27",
        SURFACE_2="#1f2532",
        SURFACE_3="#232b3a",
        BORDER="#2a3140",
        TEXT="#e9ecf1",
        TEXT_DIM="#a3abb9",
        TEXT_FAINT="#8c95a5",
        ACCENT="#e9ecf1",  # buttons are paper
        ACCENT_HOVER="#ffffff",
        ACCENT_TEXT="#11151d",
        SUCCESS="#6fcf97",
        WARNING="#f2c14e",
        DANGER="#ff8a80",
        FOCUS="#ff8fbe",
        MARKER="#5c2440",
        **NAV_HUES_DARK,
    ),
    heading_family="Literata",
    heading_file="Literata-SemiBold.ttf",
)
GLAZE = Theme(
    "Glaze",  # celadon and cobalt
    light=Palette(
        BG="#f2f5f3",
        SIDEBAR="#e8efeb",
        SURFACE="#ffffff",
        SURFACE_2="#ebf1ee",
        SURFACE_3="#d6e8df",
        BORDER="#d3ddd8",
        TEXT="#14201d",
        TEXT_DIM="#4a5954",
        TEXT_FAINT="#5a6964",
        ACCENT="#1d5a4c",  # pine
        ACCENT_HOVER="#174a3e",
        ACCENT_TEXT="#ffffff",
        SUCCESS="#2e7d32",
        WARNING="#8a5a00",
        DANGER="#b42318",
        FOCUS="#2a4c9c",  # cobalt
        MARKER="#a9cdbc",  # celadon
        **NAV_HUES_LIGHT,
    ),
    dark=Palette(
        BG="#0e1614",
        SIDEBAR="#111b18",
        SURFACE="#15201d",
        SURFACE_2="#1a2824",
        SURFACE_3="#1e302a",
        BORDER="#26342f",
        TEXT="#e4eee9",
        TEXT_DIM="#9fb2ab",
        TEXT_FAINT="#879a93",
        ACCENT="#8fcab2",  # celadon
        ACCENT_HOVER="#a5d7c2",
        ACCENT_TEXT="#0e1614",
        SUCCESS="#7bd88f",
        WARNING="#f2c14e",
        DANGER="#ff8a80",
        FOCUS="#a3b8f2",
        MARKER="#2f5a4c",  # pine
        **NAV_HUES_DARK,
    ),
    heading_family="Source Serif 4",
    heading_file="SourceSerif4-SemiBold.ttf",
)
SIGNAL = Theme(
    "Signal",  # graphite and amber
    light=Palette(
        BG="#f4f5f6",
        SIDEBAR="#eceef0",
        SURFACE="#ffffff",
        SURFACE_2="#eef0f2",
        SURFACE_3="#e0e3e7",
        BORDER="#d9dce1",
        TEXT="#16181b",
        TEXT_DIM="#50555e",
        TEXT_FAINT="#5d626b",
        ACCENT="#22252a",  # graphite
        ACCENT_HOVER="#383c43",
        ACCENT_TEXT="#f4f5f6",
        SUCCESS="#1d6b45",
        WARNING="#c2410c",
        DANGER="#b42318",
        FOCUS="#8a5800",
        MARKER="#f3ab14",  # amber
        **NAV_HUES_LIGHT,
    ),
    dark=Palette(
        BG="#111317",
        SIDEBAR="#15181c",
        SURFACE="#1a1d22",
        SURFACE_2="#20242a",
        SURFACE_3="#262a31",
        BORDER="#2b2f36",
        TEXT="#ebedf0",
        TEXT_DIM="#a2a8b2",
        TEXT_FAINT="#8e949e",
        ACCENT="#f5b82e",  # amber
        ACCENT_HOVER="#f7c655",
        ACCENT_TEXT="#111317",
        SUCCESS="#6fcf97",
        WARNING="#ff9a62",
        DANGER="#ff8a80",
        FOCUS="#f5b82e",
        MARKER="#5c4512",
        **NAV_HUES_DARK,
    ),
    heading_family="Overpass",
    heading_file="Overpass-SemiBold.ttf",
)
THEMES = {"margin": MARGIN, "glaze": GLAZE, "signal": SIGNAL}
DEFAULT_THEME = "margin"  # the user, 2026-11-06 (polyglotic-hq project 098)
WINDOW_THEMES = ("system", "light", "dark")  # the learner's choice of mode

FONTS = Path(str(files("polyglotic_desktop.ui") / "assets" / "fonts"))

_START = MARGIN.dark  # until `use`: the default theme, dark as before
BG = _START.BG
SIDEBAR = _START.SIDEBAR
SURFACE = _START.SURFACE
SURFACE_2 = _START.SURFACE_2
SURFACE_3 = _START.SURFACE_3
BORDER = _START.BORDER
TEXT = _START.TEXT
TEXT_DIM = _START.TEXT_DIM
TEXT_FAINT = _START.TEXT_FAINT
ACCENT = _START.ACCENT
ACCENT_HOVER = _START.ACCENT_HOVER
ACCENT_TEXT = _START.ACCENT_TEXT
SUCCESS = _START.SUCCESS
WARNING = _START.WARNING
DANGER = _START.DANGER
FOCUS = _START.FOCUS
MARKER = _START.MARKER
NAV_HOME = _START.NAV_HOME
NAV_WORDS = _START.NAV_WORDS
NAV_LEARNING = _START.NAV_LEARNING
NAV_ACCOUNT = _START.NAV_ACCOUNT
HEADING_FAMILY = MARGIN.heading_family
current = "dark"  # the mode now: "light" or "dark"
current_theme = DEFAULT_THEME

# A source's colour on its captions' label row (the learner picks one per
# source): bright enough on the caption windows' near-black panel - every
# one at least 7:1 against it (tests/ui/test_source_labels.py) - and none
# white or the translation's yellow, which mean something already.
SOURCE_COLORS = (
    "#7c9cff",  # blue - the mic's ("You") by default, as before
    "#4dd0e1",  # cyan
    "#a5d66f",  # green
    "#ff9f43",  # orange
    "#ff6e9c",  # pink
    "#b388ff",  # purple
    "#3ddc97",  # mint
    "#f4a8ff",  # lilac
)


os_mode: Callable[[], str | None] | None = None
"""The OS's own light or dark where Qt doesn't read it - Linux's settings
portal (polyglotic-hq 571: Qt said light on a GNOME that prefers dark) -
"light", "dark" or None (no preference: Qt's). `main` sets it; None: Qt's."""


def system_theme() -> str:
    """The OS's own app mode: "light" or "dark" (dark if it doesn't say) -
    `os_mode`'s where it says one, else Qt's (Windows', a Mac's)."""
    if os_mode is not None:
        found = os_mode()
        if found in ("light", "dark"):
            return found
    hints = QGuiApplication.styleHints()
    return "light" if hints.colorScheme() is Qt.ColorScheme.Light else "dark"


def palette(mode: str, name: str = DEFAULT_THEME) -> Palette:
    """Theme `name`'s colours in `mode` ("light" or "dark")."""
    look = THEMES[name]
    return look.light if mode == "light" else look.dark


def use(mode: str, name: str = DEFAULT_THEME) -> None:
    """The window's colours become theme `name`'s in `mode` ("dark" or
    "light")."""
    global current, current_theme, HEADING_FAMILY
    current, current_theme = mode, name
    globals().update(asdict(palette(mode, name)))
    HEADING_FAMILY = THEMES[name].heading_family


_loaded_fonts: dict[str, list[str]] = {}


def load_heading_face(name: str) -> list[str]:
    """Theme `name`'s heading face, added to the app's fonts once: the
    families it holds (none if its file is missing - page titles then fall
    back to Windows' own font). Needs the QGuiApplication."""
    file = THEMES[name].heading_file
    if file not in _loaded_fonts:
        found = QFontDatabase.addApplicationFont(str(FONTS / file))
        _loaded_fonts[file] = (
            QFontDatabase.applicationFontFamilies(found) if found >= 0 else []
        )
    return _loaded_fonts[file]


def apply(choice: str, name: str = DEFAULT_THEME) -> None:
    """The learner's choice - theme `name` ("margin", "glaze" or "signal")
    and mode `choice` ("system", "light" or "dark") - applied: its colours
    and heading face. Each window takes them into a stylesheet of its own
    (`DesktopApp.themed`)."""
    mode = system_theme() if choice == "system" else choice
    if mode not in ("light", "dark"):
        mode = "dark"
    if name not in THEMES:
        name = DEFAULT_THEME
    use(mode, name)
    if isinstance(QApplication.instance(), QApplication):
        load_heading_face(name)
