"""The display the learner's own (polyglotic-hq project 054), as the
settings keep it: the captions' font and colours, the panel's colour, and
today's overlays' place and width (kept for the settings migration and an
older app - polyglotic-hq RELEASING.md section 5) - read leniently."""

from polyglotic_desktop.ui.settings import ORIGINAL_COLOR, AppSettings


def test_display_settings_are_read_leniently() -> None:
    good = AppSettings.from_stored(
        {
            "caption_font": "Georgia",
            "original_color": "#cfe8ff",
            "translation_color": "#ffb347",
            "background_color": "#1b2a41",
            "overlay_position": "top_centre",
            "overlay_width": 0.8,
        }
    )
    assert (good.caption_font, good.original_color, good.background_color) == (
        "Georgia",
        "#cfe8ff",
        "#1b2a41",
    )
    assert (good.overlay_position, good.overlay_width) == ("top_centre", 0.8)
    bad = AppSettings.from_stored(
        {
            "caption_font": "",
            "original_color": "white",
            "overlay_position": "middle",
            "overlay_width": 3,
        }
    )
    assert bad.caption_font is None and bad.original_color == ORIGINAL_COLOR
    assert (bad.overlay_position, bad.overlay_width) == ("bottom_centre", None)
    # overlays an older version saved where they were dragged stay there
    moved = AppSettings.from_stored({"overlay_geometry": {"en": [1, 2, 400, 200]}})
    assert moved.overlay_position == "custom"
