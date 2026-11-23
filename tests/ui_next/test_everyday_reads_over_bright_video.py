"""Everyday's look reads over a bright, busy video (polyglotic-hq 584; the
user, 2026-11-21: "Default brightness / vibrance / contrast for everyday
mode is not readable enough").

The panel is see-through: what's behind it shows at 1 - its opacity. The
worst scene for light text is a white one (snow, a bright kitchen, a
white sign in a street). Over it, the new learner's look keeps what was
said, its translation and the pinyin above them at 7:1 against the panel
(WCAG 2.2's AAA for normal text, 1.4.6), and the fainter text - the
words still to come, an older caption stepped back - at 4.5:1. Before
584 (the panel at 72 %, the readings' grey 60 % of the way to the text,
the words to come at 38 %): the translation 5.8:1, the pinyin 2.9:1, the
words to come 2.6:1. Colours blend as Qt and Windows blend them, in sRGB."""

from PySide6.QtGui import QColor

from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_layout import Ink, grey, link_ink
from polyglotic_desktop.ui_next.caption_window import AHEAD_ALPHA, look_ink
from polyglotic_desktop.ui_next.views.arrivals import (
    OLDER_ALPHA,
    OLDER_TRANSLATION_ALPHA,
)
from polyglotic_desktop.ui_next.views.presets import BY_KEY, _mix, contrast

WHITE_SCENE = "#ffffff"
TEXT = 7.0
FAINT = 4.5


def _ink() -> Ink:
    return look_ink(Ink(), caption_look(AppSettings()))


def _backing(ink: Ink) -> str:
    assert ink.panel is not None
    return _mix(WHITE_SCENE, ink.panel, ink.panel_opacity)


def _ratio(colour: QColor, alpha: float, backing: str) -> float:
    drawn = _mix(backing, colour.name(), alpha * colour.alphaF())
    return contrast(drawn, backing)


def _pinyin(ink: Ink) -> QColor:
    """A reading as drawn over what was said, in the readings' grey."""
    shaded = link_ink(grey(ink), ink, QColor(ink.original), reading_lines.ALPHA)
    return reading_lines.faint(shaded)


def test_what_was_said_its_translation_and_pinyin_read_at_7_to_1() -> None:
    ink = _ink()
    backing = _backing(ink)
    found = {
        "said": _ratio(ink.original, 1.0, backing),
        "translation": _ratio(ink.translation, 1.0, backing),
        "pinyin": _ratio(_pinyin(ink), 1.0, backing),
    }
    assert all(ratio >= TEXT for ratio in found.values()), found


def test_fainter_text_reads_at_4_5_to_1() -> None:
    ink = _ink()
    backing = _backing(ink)
    found = {
        "words to come": _ratio(ink.original, AHEAD_ALPHA, backing),
        "older": _ratio(ink.original, OLDER_ALPHA, backing),
        "older translation": _ratio(ink.translation, OLDER_TRANSLATION_ALPHA, backing),
        "older pinyin": _ratio(_pinyin(ink), OLDER_ALPHA, backing),
    }
    assert all(ratio >= FAINT for ratio in found.values()), found


def test_the_default_look_is_classic() -> None:
    """The app's look is still Classic's colours and panel: picking Classic
    gives what a new learner has."""
    value, classic = AppSettings(), BY_KEY["classic"]
    assert (value.original_color, value.translation_color) == (
        classic.original,
        classic.translation,
    )
    assert (value.background_color, value.opacity) == (
        classic.background,
        classic.opacity,
    )
