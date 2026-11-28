"""The main window's theme (polyglotic-hq projects 054 and 098): Margin by
default, or Glaze or Signal, each light or dark or like Windows - chosen in
Settings' Appearance card; every text pair readable; page titles in the
theme's heading face. Offscreen."""

from dataclasses import asdict

import pytest
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app

from polyglotic_desktop.main import window_theme
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.transcript_window import TranscriptColors


def _luminance(color: QColor) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in (color.red(), color.green(), color.blue()))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str | QColor, b: str | QColor) -> float:
    """WCAG 2's contrast ratio, 1 to 21."""
    hi, lo = sorted((_luminance(QColor(a)), _luminance(QColor(b))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _over(color: str, alpha: float, under: str) -> QColor:
    """`color` at `alpha` over `under`, as the stylesheet's rgba() draws it."""
    top, bottom = QColor(color), QColor(under)

    def mix(t: int, b: int) -> int:
        return round(t * alpha + b * (1 - alpha))

    return QColor(
        mix(top.red(), bottom.red()),
        mix(top.green(), bottom.green()),
        mix(top.blue(), bottom.blue()),
    )


PALETTES = [
    pytest.param(getattr(look, mode), id=f"{name}-{mode}")
    for name, look in theme.THEMES.items()
    for mode in ("light", "dark")
]


@pytest.mark.parametrize("p", PALETTES)
def test_every_text_pair_is_at_least_4_5_to_1(p: theme.Palette) -> None:
    surfaces = {"BG": p.BG, "SIDEBAR": p.SIDEBAR, "SURFACE": p.SURFACE}
    surfaces["SURFACE_2"] = p.SURFACE_2  # inputs, buttons, hover
    pairs: list[tuple[str, str, str | QColor]] = []
    for bg in surfaces.values():
        pairs += [("TEXT", p.TEXT, bg), ("TEXT_DIM", p.TEXT_DIM, bg)]
        pairs += [("TEXT_FAINT", p.TEXT_FAINT, bg)]
    pairs += [  # selected, pressed and checked things
        ("TEXT", p.TEXT, p.SURFACE_3),
        ("TEXT_DIM", p.TEXT_DIM, p.SURFACE_3),
        ("TEXT on a selection", p.TEXT, p.MARKER),
        ("ACCENT_TEXT", p.ACCENT_TEXT, p.ACCENT),
        ("ACCENT_TEXT hovered", p.ACCENT_TEXT, p.ACCENT_HOVER),
    ]
    for under in (p.SURFACE, p.SURFACE_2):  # a checked tool button, a list's pick
        tint = _over(p.ACCENT, 0.22, under)
        pairs += [("ACCENT on its tint", p.ACCENT, tint), ("TEXT on it", p.TEXT, tint)]
    for under in (p.BG, p.SURFACE):  # readings in ACCENT; Home's state, notices
        for name, color in (
            ("ACCENT", p.ACCENT),
            ("SUCCESS", p.SUCCESS),
            ("WARNING", p.WARNING),
            ("DANGER", p.DANGER),
        ):
            pairs.append((name, color, under))
    low = [
        f"{name} {fg} on {QColor(bg).name()}: {_contrast(fg, bg):.2f}"
        for name, fg, bg in pairs
        if _contrast(fg, bg) < 4.5
    ]
    assert low == []


@pytest.mark.parametrize("p", PALETTES)
def test_the_focus_ring_shows_on_every_surface(p: theme.Palette) -> None:
    for under in (p.BG, p.SURFACE, p.SURFACE_2):  # a mark, not text: 3:1
        assert _contrast(p.FOCUS, under) >= 3, under


@pytest.mark.parametrize("p", PALETTES)
def test_sidebar_section_hues_and_footer_icons_clear_contrast_in_both_themes(
    p: theme.Palette,
) -> None:
    """964: every sidebar icon meets WCAG 1.4.11 (>= 3:1) against the sidebar
    at rest, on hover, and when selected; selected pills keep label text >= 4.5:1
    and footer actions stay neutral and brighter than TEXT_FAINT."""
    hues = {
        section: getattr(p, token)
        for section, token in style.SIDEBAR_SECTION_TOKENS.items()
    }
    assert len(set(hues.values())) == 4  # Home, Words, Learning, Account each distinct
    for section, hue in hues.items():
        rest = _over(hue, style.SIDEBAR_ICON_REST_ALPHA, p.SIDEBAR)
        hovered = _over(hue, style.SIDEBAR_ICON_HOVER_ALPHA, p.SURFACE_2)
        pill = _over(hue, style.SIDEBAR_PILL_ALPHA, p.SIDEBAR)
        assert _contrast(hue, p.SIDEBAR) >= 3.0, (section, "full")
        assert _contrast(rest, p.SIDEBAR) >= 3.0, (section, "rest")
        assert _contrast(hovered, p.SURFACE_2) >= 3.0, (section, "hover")
        assert _contrast(hue, pill) >= 3.0, (section, "selected-icon")
        assert _contrast(p.TEXT, pill) >= 4.5, (section, "selected-label")
    assert _contrast(p.TEXT_DIM, p.SIDEBAR) > _contrast(p.TEXT_FAINT, p.SIDEBAR)
    assert _contrast(p.TEXT_DIM, p.SIDEBAR) >= 3.0
    assert _contrast(p.TEXT, p.SURFACE_2) >= 3.0
    assert _contrast(p.TEXT, p.SURFACE_3) >= 3.0


def test_margin_buttons_are_ink_and_pink_only_marks() -> None:
    light, dark = theme.MARGIN.light, theme.MARGIN.dark
    assert light.ACCENT == light.TEXT == "#172033"  # ink
    assert dark.ACCENT == dark.TEXT  # paper
    assert (light.MARKER, light.FOCUS) == ("#ffa8cc", "#b0185a")
    assert (dark.MARKER, dark.FOCUS) == ("#5c2440", "#ff8fbe")


def test_a_source_colour_reads_on_the_light_window_too() -> None:
    light = TranscriptColors.of(style.Theme(asdict(theme.MARGIN.light), "", False))
    light = TranscriptColors(**{**asdict(light), "light": True})
    for color in theme.SOURCE_COLORS:
        assert _contrast(light.readable(color), theme.MARGIN.light.SURFACE) >= 3, color
    assert TranscriptColors().readable("#4dd0e1") == QColor("#4dd0e1")  # dark: as it is


def test_margin_is_the_default_and_dark_still_the_default_mode() -> None:
    assert AppSettings().theme == "margin" == theme.DEFAULT_THEME
    assert AppSettings().window_theme == "dark"  # as before (project 054)
    assert AppSettings.from_stored({"theme": "glaze"}).theme == "glaze"
    assert AppSettings.from_stored({"theme": "pink"}).theme == "margin"
    assert AppSettings.from_stored({"window_theme": "pink"}).window_theme == "dark"


def test_the_learners_theme_reaches_every_window_and_not_the_whole_app(
    qapp: QApplication,
) -> None:
    """A choice in Settings changes the colours the windows take
    (`main.window_theme`) and says so (`themed`); no stylesheet is set on
    the whole app (decision 0031)."""
    store = MemorySettingsStore()
    app = make_app(store)
    told: list[bool] = []
    app.themed.connect(lambda: told.append(True))
    assert (theme.current_theme, theme.current) == ("margin", "dark")
    assert window_theme()["BG"] == theme.MARGIN.dark.BG
    app.settings.update(window_theme="light")
    assert theme.current == "light" and window_theme()["BG"] == theme.MARGIN.light.BG
    app.settings.update(theme="glaze")
    assert theme.current_theme == "glaze"
    assert window_theme().heading_family == theme.GLAZE.heading_family
    assert len(told) == 2 and qapp.styleSheet() == ""
    app.settings.update(window_theme="system")
    assert theme.current == theme.system_theme()
    app.settings.update(theme="margin", window_theme="dark")
    assert window_theme()["BG"] == theme.MARGIN.dark.BG
    app.close()


@pytest.mark.parametrize("name", list(theme.THEMES))
def test_each_heading_face_loads_and_sets_page_titles_only(
    qapp: QApplication, name: str
) -> None:
    look = theme.THEMES[name]
    assert look.heading_family in theme.load_heading_face(name)
    styles = QFontDatabase.styles(look.heading_family)
    assert any(QFontDatabase.weight(look.heading_family, s) == 600 for s in styles)
    stem = look.heading_file.split("-")[0]
    licence = (theme.FONTS / f"{stem}-OFL.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License, Version 1.1" in licence
    assert (theme.FONTS / look.heading_file).stat().st_size < 100_000  # cut to Latin
    theme.use("light", name)
    try:
        sheet = style.stylesheet(window_theme())  # what each window is given
        assert sheet.count(f"'{look.heading_family}'") == 1  # only #PageTitle
        title_rule = next(r for r in sheet.splitlines() if r.startswith("#PageTitle"))
        assert f"'{look.heading_family}', 'Segoe UI" in title_rule  # then Windows'
    finally:
        theme.use("dark")
