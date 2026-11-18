"""Each source labelled and coloured (polyglotic-hq project 054): the
colour each source gets, the palette's contrast on the caption windows'
panel, and each source's label - all on this PC only. How the caption
windows, the transcripts and Home's picker show them: tests/ui_next.
Made-up apps."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore, make_app

from polyglotic_desktop.core.listening.sources import (
    MIC,
    SourceId,
    SourceLabel,
    colors_for,
)
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui.settings import (
    BACKGROUND_COLOR,
    ORIGINAL_COLOR,
    TRANSLATION_COLOR,
    AppSettings,
)
from polyglotic_desktop.ui_next.os_words import pc_or_mac

APP_1, APP_2 = SourceId("app-1"), SourceId("app-2")
PALETTE = ("#111111", "#222222", "#333333")


def test_each_source_gets_the_first_colour_no_other_has() -> None:
    assert colors_for(["mic", "a", "b"], {}, PALETTE) == {
        "mic": "#111111",
        "a": "#222222",
        "b": "#333333",
    }
    # a colour chosen for one is skipped for the others
    assert colors_for(["mic", "a", "b"], {"b": "#111111"}, PALETTE) == {
        "mic": "#222222",
        "a": "#333333",
        "b": "#111111",
    }
    # more sources than colours: they repeat in turn
    assert colors_for(["a", "b", "c", "d", "e"], {}, PALETTE)["d"] == "#111111"


def _luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    color = QColor(hex_color)
    r, g, b = (channel(c) for c in (color.red(), color.green(), color.blue()))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_the_palette_reads_on_the_panel_and_means_nothing_else() -> None:
    """At least 7:1 (WCAG AAA) against the caption windows' panel colour,
    all different, none the original's white or the translation's yellow."""
    panel = _luminance(BACKGROUND_COLOR)
    for color in theme.SOURCE_COLORS:
        assert (_luminance(color) + 0.05) / (panel + 0.05) >= 7, color
    assert len(set(theme.SOURCE_COLORS)) == len(theme.SOURCE_COLORS)
    assert not {ORIGINAL_COLOR, TRANSLATION_COLOR} & set(theme.SOURCE_COLORS)


def test_names_and_colours_are_read_leniently() -> None:
    settings = AppSettings.from_stored(
        {"source_names": {"Chat.exe": "Team"}, "source_colors": {"mic": "#4dd0e1"}}
    )
    assert settings.source_names == {"Chat.exe": "Team"}
    assert settings.source_colors == {"mic": "#4dd0e1"}
    bad = AppSettings.from_stored(
        {"source_names": {"x": ""}, "source_colors": {"mic": "red"}}
    )
    assert bad.source_names == {} and bad.source_colors == {}


def test_each_source_is_labelled_with_its_name_in_its_colour(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({"apps": ["Chat.exe", "Player.exe"]})
    app = make_app(store)
    app.set_app_sources({APP_1: ("Chat.exe", "Chat"), APP_2: ("Player.exe", "Player")})
    labels = app.source_labels()
    blue, cyan, green, orange = theme.SOURCE_COLORS[:4]
    assert labels[MIC] == SourceLabel("You", blue)  # as before: "You", in blue
    assert labels[APP_1] == SourceLabel("Chat", cyan)  # in the order picked
    assert labels[APP_2] == SourceLabel("Player", green)
    this = pc_or_mac("Everything the PC plays", "Everything the Mac plays")  # 484
    assert labels[SourceId("system")] == SourceLabel(this, orange)  # not on
    app.settings.update(
        source_names={"Chat.exe": "Team call"}, source_colors={"Chat.exe": "#ff6e9c"}
    )
    assert app.source_labels()[APP_1] == SourceLabel("Team call", "#ff6e9c")
    app.close()
