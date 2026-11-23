"""Independent caption and translation sizes (polyglotic-hq 305, 655):

- **Caption size** (what was said) and **Translation size** are completely
  independent (60 to 400 %, `CAPTION_TEXT_SIZES`): changing one never changes
  the other.
- Both appear in the gear menu and in Settings > Look with A-, a 5 % slider
  and A+, labelled with the window's languages ("150%", "120%"),
  and a small "Match" action that sets translation equal to caption.
- Script-matched base scales are registered tunables measured from the bundled
  fonts' heights so 100 % reads at a matched visual size across scripts.
- Ruby readings (pinyin and the like) scale with their base characters.
- Per-preset defaults (Video, Everyday, Conversation equal; Learning original a
  little larger) are registered tunables with reasons.
- Migration turns a single size (or pre-655 relative share) into independent
  sizes keeping the exact rendered look on update.
- A window's pair applies to every source in it, own speech included.
"""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import finished_updates, live_update
from tests.ui_next.test_caption_window import areas, place, window_of
from tests.ui_next.test_reading_lines import made_up as made_up_readings

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.core.listening.preset_reading import preset_sizes
from polyglotic_desktop.core.shared.tunables import declarations
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui_next import caption_faces, fonts
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, CaptionStyle
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, caption_style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_page import TranslationSizeCard
from polyglotic_desktop.ui_next.settings_popover import (
    COLUMN_ROWS,
    ROWS,
    SettingsPopover,
    SizeSlider,
)
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import (
    TRANSLATION_SIZES,
    CaptionLook,
    StoredWindows,
    WindowChoices,
    stepped,
    text_size,
)
from polyglotic_desktop.ui_next.views.captions import CAPTION_TEXT_SIZES, TEXT_SIZES
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.transcript import TranscriptChoices


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    yield shown
    shown.close()
    shown.deleteLater()


def sizes(window: CaptionWindow) -> dict[RowKind, set[int]]:
    """The pixel sizes each kind of row is drawn at, in the lines in view."""
    found: dict[RowKind, set[int]] = {kind: set() for kind in RowKind}
    window.canvas.repaint()
    for _, laid, _ in window.canvas.placed:
        for row in laid.rows:
            found[row.row.kind].add(row.layout.font().pixelSize())
    return found


def popover_of(window: CaptionWindow) -> SettingsPopover:
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    return popover


def test_100_percent_is_todays_window() -> None:
    assert WindowChoices().text_size == 1.0
    assert WindowChoices().translation_size == 1.0
    assert caption_style(CaptionLook()).translation_size is None
    assert caption_style(CaptionLook(), 1.0).translation_size == 1.0
    stored = WindowChoices().to_stored()
    del stored["translation_text_size"]
    del stored["translation_size"]  # a window saved before 305
    assert WindowChoices.from_stored(stored, WindowChoices()).translation_size == 1.0


@pytest.mark.parametrize("size", [0.6, 0.8, 1.5, 2.5, 4.0])
def test_changing_translation_size_never_changes_caption_size(
    window: CaptionWindow, size: float
) -> None:
    before = sizes(window)
    place_before = place(window)
    newest = window.view.lines[-1].key
    window.set_translation_size(size)
    after = sizes(window)
    assert after[RowKind.ORIGINAL] == before[RowKind.ORIGINAL]
    assert window.choices.text_size == window.view.text_size == 1.0
    for full, now in zip(
        sorted(before[RowKind.TRANSLATION]),
        sorted(after[RowKind.TRANSLATION]),
        strict=True,
    ):
        assert now == round(full * size)
    assert place(window) == place_before  # the window keeps its size
    assert window.canvas.placed[-1][0].key == newest  # still at the bottom
    assert window.choices.translation_size == size


@pytest.mark.parametrize("caption", [0.6, 0.8, 1.5, 2.5, 4.0])
def test_changing_caption_size_never_changes_translation_size(
    window: CaptionWindow, caption: float
) -> None:
    """Atomic independence (655): changing caption size leaves translation
    size and drawn translation pixel sizes untouched."""
    window.set_translation_size(1.2)
    before = sizes(window)
    window.set_text_size(caption)
    after = sizes(window)
    assert window.choices.translation_size == 1.2
    assert after[RowKind.TRANSLATION] == before[RowKind.TRANSLATION]
    assert after[RowKind.ORIGINAL] != before[RowKind.ORIGINAL]


def test_it_goes_from_60_to_400_percent_and_matches_caption_in_one_click(
    window: CaptionWindow,
) -> None:
    smaller = window.controls["translation_smaller"]
    bigger = window.controls["translation_bigger"]
    same = window.controls["translation_same"]
    assert smaller.isEnabled() and bigger.isEnabled() and not same.isEnabled()
    for _ in range(10):
        smaller.trigger()
    assert window.choices.translation_size == TRANSLATION_SIZES[0] == 0.6
    assert not smaller.isEnabled() and same.isEnabled()
    for _ in range(40):
        bigger.trigger()
    assert window.choices.translation_size == TRANSLATION_SIZES[1] == 4.0
    assert not bigger.isEnabled()
    window.set_translation_size(0.3)  # out of range: kept within it
    assert window.choices.translation_size == 0.6
    window.set_text_size(1.5)
    assert window.choices.translation_size == 0.6  # atomic
    assert same.isEnabled()
    same.trigger()  # "Match" sets translation equal to caption (1.5)
    assert window.choices.translation_size == 1.5
    assert window.choices.text_size == 1.5
    assert not same.isEnabled()


def test_what_was_said_goes_from_60_to_400_percent() -> None:
    assert CAPTION_TEXT_SIZES == (0.6, 4.0) == TRANSLATION_SIZES
    assert TEXT_SIZES == (0.7, 2.0)
    assert stepped(3.95, 1, CAPTION_TEXT_SIZES) == 4.0
    assert stepped(0.65, -1, CAPTION_TEXT_SIZES) == 0.6
    assert stepped(1.95, 1) == 2.0  # a transcript's: as it was
    assert text_size(0.6) == 0.6 and text_size(4.0) == 4.0
    assert text_size(0.5) is None and text_size(4.1) is None
    # a transcript keeps its 70-200 %
    assert TranscriptChoices.from_stored({"text_size": 3.0}).text_size == 1.0
    assert TranscriptChoices.from_stored({"text_size": 2.0}).text_size == 2.0


def test_no_line_is_drawn_outside_the_text_sizes_range(qapp: QApplication) -> None:
    window = window_of(qapp, captions=2)
    try:
        line = window.view.lines[-1]
        for trans, cap, wanted in ((0.6, 0.6, 0.6), (4.0, 1.0, 4.0), (1.2, 2.0, 1.2)):
            laid = CaptionLayout(CaptionStyle(translation_size=trans)).laid(
                line, 1800, cap
            )
            plain = CaptionLayout().laid(line, 1800, wanted)
            for a, b in zip(laid.rows, plain.rows, strict=True):
                if a.row.kind is RowKind.TRANSLATION:
                    assert a.layout.font().pixelSize() == b.layout.font().pixelSize()
                    assert a.layout.font().pixelSize() >= 12
    finally:
        window.close()
        window.deleteLater()


def test_arrows_curves_keep_their_thickness_at_any_translation_size(
    qapp: QApplication,
) -> None:
    """A curve runs on from what was said's underline: as thick at 60 or
    200 % translation size as at the original's size (`LaidRow.full_px`)."""
    window = window_of(qapp, captions=2)
    try:
        line = window.view.lines[-1]
        full = CaptionLayout().laid(line, 900, 1.0)
        for trans in (0.6, 2.0):
            laid = CaptionLayout(CaptionStyle(translation_size=trans)).laid(
                line, 900, 1.0
            )
            assert [r.full_px for r in laid.rows] == [
                r.layout.font().pixelSize() for r in full.rows
            ]
    finally:
        window.close()
        window.deleteLater()


def test_the_gear_menu_and_look_have_both_independent_sizes_labelled_by_role(
    qapp: QApplication, window: CaptionWindow
) -> None:
    """655: both the gear menu and Settings > Look show Caption size and
    Translation size, each with A-, a 5 % slider and A+,
    a percentage readout, and Match."""
    assert "translation_size" in ROWS and "translation_size" in COLUMN_ROWS
    assert "languages" not in ROWS and "languages" not in COLUMN_ROWS
    window.set_spoken_language("zh")
    window.set_language("en")
    window.set_text_size(1.5)
    window.set_translation_size(1.2)
    popover = popover_of(window)
    assert popover.text_size.text().endswith(">150%</span>")
    assert popover.translation_size.text().endswith(">120%</span>")
    window.set_spoken_language("yue")
    window.set_language("de")
    assert popover.text_size.text().endswith(">150%</span>")
    assert popover.translation_size.text().endswith(">120%</span>")
    assert popover.translation_match.text() == "Match"
    assert popover.translation_match.isEnabled()
    assert (
        popover.translation_match.accessibleName()
        == "Match translation size to caption size"
    )
    text = popover.rows["text_size"].findChild(
        SizeSlider, "settings_popover.text_size_slider"
    )
    trans = popover.rows["translation_size"].findChild(
        SizeSlider, "settings_popover.translation_size_slider"
    )
    assert text is not None and (text.minimum(), text.maximum()) == (0, 68)
    assert trans is not None and (trans.minimum(), trans.maximum()) == (0, 68)
    assert text.accessibleName() == "Caption size"
    assert trans.accessibleName() == "Translation size"

    # Moving caption slider leaves translation untouched
    text.setValue(20)  # 60 % + 20 * 5 % = 160 %
    assert window.view.text_size == 1.6 == window.choices.text_size
    assert window.choices.translation_size == 1.2
    # Moving translation slider leaves caption untouched
    trans.setValue(14)  # 60 % + 14 * 5 % = 130 %
    assert window.choices.translation_size == 1.3
    assert window.choices.text_size == 1.6
    # Match sets translation equal to caption
    popover.translation_match.click()
    assert window.choices.translation_size == 1.6
    assert window.choices.text_size == 1.6
    assert not popover.translation_match.isEnabled()

    # Original only hides Translation size in the gear menu
    window.set_language("")
    popover.refresh()
    assert not popover.rows["translation_size"].isVisible()
    window.set_language("en")
    window.close_settings()

    # Settings > Look card has both sizes, A-/slider/A+, role labels, Match
    card = TranslationSizeCard(1.2, 1.5)
    try:
        card.show_sizes(1.5, 1.2)
        cap_chosen: list[float] = []
        trans_chosen: list[float] = []
        card.caption_chosen.connect(cap_chosen.append)
        card.chosen.connect(trans_chosen.append)
        assert card.caption_shown.text() == "150%"
        assert card.shown.text() == "120%"
        assert card.same.text() == "Match" and card.same.isEnabled()
        assert (card.caption_slider.minimum(), card.caption_slider.maximum()) == (0, 68)
        assert (card.slider.minimum(), card.slider.maximum()) == (0, 68)
        card.caption_bigger.click()
        assert cap_chosen == [1.6] and trans_chosen == []
        assert card.caption_shown.text() == "160%"
        assert card.shown.text() == "120%"
        card.translation_smaller.click()
        assert trans_chosen == [1.1] and cap_chosen == [1.6]
        assert card.shown.text() == "110%"
        card.same.click()
        assert trans_chosen == [1.1, 1.6] and cap_chosen == [1.6]
        assert not card.same.isEnabled()
        card.show_size(2.0)  # as the windows have it: said, not asked for
        assert card.slider.chosen() == 2.0 and trans_chosen == [1.1, 1.6]
    finally:
        card.deleteLater()


def test_keyboard_reaches_both_sliders_and_match_in_gear_menu(
    qapp: QApplication, window: CaptionWindow
) -> None:
    window.hovered = True
    window._show_band(True)
    window.set_text_size(1.5)
    window.set_translation_size(1.2)
    window.toggle_settings(keyboard=True)
    popover = window.popover
    assert popover is not None and popover.isVisible()
    for control in (
        popover.text_slider,
        popover.translation_slider,
        popover.translation_match,
    ):
        assert control.focusPolicy() == Qt.FocusPolicy.StrongFocus
    popover.translation_match.setFocus()
    qapp.processEvents()
    QTest.keyClick(popover.translation_match, Qt.Key.Key_Return)
    assert window.choices.translation_size == 1.5
    window.close_settings()


def test_the_wheel_never_moves_the_sliders(window: CaptionWindow) -> None:
    popover = popover_of(window)
    for slider in popover.findChildren(SizeSlider):
        before = slider.value()
        wheel = QWheelEvent(
            QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 240),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )  # fmt: skip
        QApplication.sendEvent(slider, wheel)
        assert slider.value() == before
    assert (window.view.text_size, window.choices.translation_size) == (1.0, 1.0)
    window.close_settings()


def test_migration_keeps_the_exact_look_and_round_trips(qapp: QApplication) -> None:
    # 1. Legacy flat settings (single text_scale) -> both sizes equal
    migrated = stored_windows(
        {"text_scale": 1.4, "targets": ["en"], "whole_system": True}
    )
    assert migrated.last.text_size == 1.4
    assert migrated.last.translation_size == 1.4
    assert migrated.by_key["system"].text_size == 1.4
    assert migrated.by_key["system"].translation_size == 1.4

    # 2. Pre-655 caption_windows with single text_size (default share 1.0 or absent)
    pre_single = {"text_size": 1.5, "translate_into": "en"}
    read_single = WindowChoices.from_stored(pre_single, WindowChoices())
    assert (read_single.text_size, read_single.translation_size) == (1.5, 1.5)

    # 3. Pre-655 caption_windows with relative share (1.5 * 0.8 = 1.2)
    pre_share = {"text_size": 1.5, "translation_size": 0.8, "translate_into": "en"}
    read_share = WindowChoices.from_stored(pre_share, WindowChoices())
    assert (read_share.text_size, read_share.translation_size) == (1.5, 1.2)

    # Rendered pixel sizes match the pre-655 single-size look identically
    win = window_of(qapp, captions=2)
    try:
        line = win.view.lines[-1]
        before = CaptionLayout().laid(line, 900, 1.5)
        after = CaptionLayout(
            CaptionStyle(translation_size=read_single.translation_size)
        ).laid(line, 900, read_single.text_size)
        assert [r.layout.font().pixelSize() for r in after.rows] == [
            r.layout.font().pixelSize() for r in before.rows
        ]
    finally:
        win.close()
        win.deleteLater()

    # 4. Post-655 independent round-trip & invalid handling
    for size in (0.6, 0.7, 2.0, 4.0):
        chosen = WindowChoices(text_size=3.5, translation_size=size)
        assert WindowChoices.from_stored(chosen.to_stored(), WindowChoices()) == chosen
    chosen = WindowChoices(translation_size=0.7)
    for wrong in (0.4, 4.1, True, "0.8", None):
        stored = {**chosen.to_stored(), "translation_text_size": wrong}
        read = WindowChoices.from_stored(stored, WindowChoices())
        assert read.translation_size == 1.0  # not valid: the base's
    new = StoredWindows(last=WindowChoices(text_size=3.0, translation_size=0.7))
    assert (new.for_new(1).text_size, new.for_new(1).translation_size) == (3.0, 0.7)


def test_script_scales_are_tunables_and_match_bundled_fonts_within_tolerance(
    qapp: QApplication,
) -> None:
    """655: each script's base scale is a registered tunable measured from
    the bundled fonts' heights so 100 % matches Latin within tolerance."""
    caption_faces.load()
    registered = declarations()
    for script_key, item in fonts.SCRIPT_SCALES.items():
        assert item.name in registered, script_key
        assert item.source and item.unit == "scale"

    def font_at(lang: str) -> QFont:
        f = QFont()
        f.setFamilies(list(fonts.caption_families(lang)))
        f.setPixelSize(round(100 * fonts.size(lang)))
        f.setWeight(QFont.Weight.Medium)
        return f

    latin_m = QFontMetricsF(font_at("en"))
    latin_cap = latin_m.capHeight()
    latin_x = latin_m.xHeight()
    latin_line = latin_m.tightBoundingRect(
        "The quick brown fox jumps over the lazy dog"
    ).height()

    # Bicameral bundled scripts match Latin x-height & cap-height within 10 %
    for lang in ("vi", "ru"):
        m = QFontMetricsF(font_at(lang))
        assert abs(m.xHeight() / latin_x - 1.0) <= 0.10, lang
        assert abs(m.capHeight() / latin_cap - 1.0) <= 0.10, lang

    # Bundled CJK (Ma Shan Zheng) sentence ink height matches Latin within 10 %
    zh_m = QFontMetricsF(font_at("zh"))
    zh_line = zh_m.tightBoundingRect("我们今天去公园散步天气很好").height()
    assert abs(zh_line / latin_line - 1.0) <= 0.10

    # Bundled Devanagari consonant body matches Latin cap-height within 10 %
    hi_m = QFontMetricsF(font_at("hi"))
    hi_body = hi_m.tightBoundingRect("कम").height()
    assert abs(hi_body / latin_cap - 1.0) <= 0.10

    # Bundled Thai x-height and cap-height match Latin within 10 %
    th_m = QFontMetricsF(font_at("th"))
    assert abs(th_m.xHeight() / latin_x - 1.0) <= 0.10
    assert abs(th_m.capHeight() / latin_cap - 1.0) <= 0.10

    # Bundled Arabic x-height (body) matches Latin x-height within 25 %
    ar_m = QFontMetricsF(font_at("ar"))
    assert abs(ar_m.xHeight() / latin_x - 1.0) <= 0.25


def test_readings_scale_with_their_own_base_characters(qapp: QApplication) -> None:
    """655: ruby readings (pinyin) follow their base row's size on both
    original and translation rows without being affected by the other size."""
    source = made_up_readings
    style_base = CaptionStyle(reading_lines=frozenset({"zh"}), translation_size=1.0)
    style_big_trans = CaptionStyle(
        reading_lines=frozenset({"zh"}), translation_size=2.0
    )

    # 1. Chinese as Original, English as Translation
    win = window_of(qapp, captions=0)
    try:
        win.view.apply(
            finished("r1", clause("我们今天", "We today"), language=Language("zh"))
        )
        line_zh_orig = win.view.lines[-1]
        small = CaptionLayout(style_base, readings=source).laid(line_zh_orig, 900, 1.0)
        big_orig = CaptionLayout(style_base, readings=source).laid(
            line_zh_orig, 900, 2.0
        )
        big_trans = CaptionLayout(style_big_trans, readings=source).laid(
            line_zh_orig, 900, 1.0
        )
        orig_small = next(r for r in small.rows if r.row.kind is RowKind.ORIGINAL)
        orig_big = next(r for r in big_orig.rows if r.row.kind is RowKind.ORIGINAL)
        orig_other = next(r for r in big_trans.rows if r.row.kind is RowKind.ORIGINAL)
        assert orig_small.above_font is not None and orig_big.above_font is not None
        assert orig_other.above_font is not None
        assert orig_big.above_font.pixelSize() > orig_small.above_font.pixelSize()
        # Changing translation size never changes original's ruby size
        assert orig_other.above_font.pixelSize() == orig_small.above_font.pixelSize()
    finally:
        win.close()
        win.deleteLater()

    # 2. English as Original, Chinese as Translation
    win2 = window_of(qapp, captions=0, translate_into="zh")
    try:
        win2.view.apply(
            finished(
                "r2",
                clause("We today", "我们今天", into=Language("zh")),
                language=Language("en"),
            )
        )
        line_zh_trans = win2.view.lines[-1]
        small = CaptionLayout(style_base, readings=source).laid(line_zh_trans, 900, 1.0)
        big_orig = CaptionLayout(style_base, readings=source).laid(
            line_zh_trans, 900, 2.0
        )
        big_trans = CaptionLayout(style_big_trans, readings=source).laid(
            line_zh_trans, 900, 1.0
        )
        trans_small = next(r for r in small.rows if r.row.kind is RowKind.TRANSLATION)
        trans_other = next(
            r for r in big_orig.rows if r.row.kind is RowKind.TRANSLATION
        )
        trans_big = next(r for r in big_trans.rows if r.row.kind is RowKind.TRANSLATION)
        assert trans_small.above_font is not None and trans_big.above_font is not None
        assert trans_other.above_font is not None
        assert trans_big.above_font.pixelSize() > trans_small.above_font.pixelSize()
        # Changing caption size never changes translation's ruby size
        assert trans_other.above_font.pixelSize() == trans_small.above_font.pixelSize()
    finally:
        win2.close()
        win2.deleteLater()


def test_per_preset_defaults_are_tunables_and_apply_on_switch(
    qapp: QApplication,
) -> None:
    """655: Video, Everyday and Conversation default equal; Learning defaults
    the original a little larger. All are registered tunables with reasons."""
    registered = declarations()
    for preset in ("everyday", "conversation", "video", "learning"):
        for field in ("caption_size", "translation_size"):
            key = f"presets.{preset}.{field}"
            assert key in registered and registered[key].source
    assert preset_sizes("everyday") == (1.0, 1.0)
    assert preset_sizes("conversation") == (1.0, 1.0)
    assert preset_sizes("video") == (1.0, 1.0)
    learn_cap, learn_trans = preset_sizes("learning")
    assert learn_cap > learn_trans

    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("a", APP)])
        win = windows.windows["a"]
        win.set_text_size(1.5)
        win.set_translation_size(1.5)
        # Startup records active preset without overwriting migrated/saved sizes
        windows.set_preset_sizes("everyday")
        assert (win.choices.text_size, win.choices.translation_size) == (1.5, 1.5)
        # Switching to Learning applies Learning's tuned default pair
        windows.set_preset_sizes("learning")
        assert (win.choices.text_size, win.choices.translation_size) == (
            learn_cap,
            learn_trans,
        )
        # Switching back to Everyday restores Everyday's remembered pair
        windows.set_preset_sizes("everyday")
        assert (win.choices.text_size, win.choices.translation_size) == (1.5, 1.5)
        # Video subtitles set equal sizes and restore both sizes on exit
        windows.set_subtitles((0.045, 0.8))
        assert win.choices.text_size == win.choices.translation_size
        windows.set_subtitles(None)
        assert (win.choices.text_size, win.choices.translation_size) == (1.5, 1.5)
    finally:
        windows.close()


def test_the_windows_pair_applies_to_every_source_own_speech_included(
    qapp: QApplication,
) -> None:
    """655: a window's caption/translation pair applies to both the app's
    captions and the learner's own speech ("You") in that window."""
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("app", APP)])
        shown = windows.windows["app"]
        shown.resize(900, 320)
        shown.show()
        shown.set_show_mic(True)
        shown.set_text_size(1.6)
        shown.set_translation_size(1.1)
        windows.apply(finished("c1", clause("我们今天", "We today"), source=APP))
        windows.apply(finished("c2", clause("你好吗", "How are you"), source=MIC))
        qapp.processEvents()
        shown.canvas.repaint()
        by_source: dict[bool, dict[RowKind, set[int]]] = {
            False: {RowKind.ORIGINAL: set(), RowKind.TRANSLATION: set()},
            True: {RowKind.ORIGINAL: set(), RowKind.TRANSLATION: set()},
        }
        for line, laid, _ in shown.canvas.placed:
            for row in laid.rows:
                by_source[line.by_you][row.row.kind].add(row.layout.font().pixelSize())
        assert by_source[True][RowKind.ORIGINAL]
        assert by_source[True][RowKind.ORIGINAL] == by_source[False][RowKind.ORIGINAL]
        assert (
            by_source[True][RowKind.TRANSLATION]
            == by_source[False][RowKind.TRANSLATION]
        )
        assert min(by_source[True][RowKind.ORIGINAL]) > max(
            by_source[True][RowKind.TRANSLATION]
        )
    finally:
        windows.close()


def test_a_change_lays_out_again_only_the_translation(qapp: QApplication) -> None:
    window = window_of(qapp, captions=3)
    try:
        line = window.view.lines[-1]
        full = CaptionLayout().laid(line, 900, 1.0)
        for trans, smaller in ((0.6, True), (2.0, False)):
            laid = CaptionLayout(CaptionStyle(translation_size=trans)).laid(
                line, 900, 1.0
            )
            assert (laid.height < full.height) is smaller
            for a, b in zip(full.rows, laid.rows, strict=True):
                pa, pb = a.layout.font().pixelSize(), b.layout.font().pixelSize()
                if a.row.kind is RowKind.ORIGINAL:
                    assert pa == pb
                else:
                    assert (pb < pa) is smaller
    finally:
        window.close()
        window.deleteLater()


def bottom_whole(window: CaptionWindow) -> bool:
    """The newest caption's last row is above the window's bottom edge."""
    canvas = window.canvas
    canvas.repaint()
    return canvas.placed[-1][2].bottom() <= canvas.height() - PAD + 0.5


@pytest.mark.parametrize("trans", [0.6, 2.0])
def test_live_updates_and_the_finished_caption_at_rest_whole(
    qapp: QApplication, trans: float
) -> None:
    """A live update growing, then its finished caption: at rest, nothing
    below the window's bottom edge, with independent caption and translation sizes."""
    window = window_of(
        qapp,
        captions=4,
        look=CaptionLook(arrival=Arrival.STEP),
        translation_size=trans,
        text_size=1.6,
    )
    try:
        live = live_update("growing")
        window.view.apply(live)
        window.apply_changed(new_caption=True)
        assert bottom_whole(window)
        (done,) = finished_updates(1, start=7)
        window.view.apply(replace(done, replaces=(live.caption_id,)))
        window.apply_changed(new_caption=True)
        assert bottom_whole(window)
        assert window.view.lines[-1].caption_id == done.caption_id
    finally:
        window.close()
        window.deleteLater()


def test_joined_columns_each_keep_their_own_independent_sizes(
    qapp: QApplication,
) -> None:
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("a", APP), ("b", MIC)])
        windows.windows["a"].set_translation_size(2.0)
        windows.windows["b"].set_translation_size(0.6)
        for update in finished_updates(6, APP):
            windows.apply(update)
        windows.join()
        joined = windows.joined_window
        assert joined is not None
        joined.show()
        qapp.processEvents()
        column = windows.windows["a"]
        assert column.host is not None
        assert column.canvas.engine.style.translation_size == 2.0
        assert windows.windows["b"].canvas.engine.style.translation_size == 0.6
        column.always_shown = True
        column.canvas.repaint()
        assert column.canvas.placed  # captions in view
        assert bottom_whole(column)
    finally:
        windows.close()


def test_looks_sizes_set_every_window_independently(qapp: QApplication) -> None:
    """Settings > Look's caption and translation sizes set each window's own
    independently, and a window opened after starts at them."""
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("a", APP), ("b", MIC)])
        windows.windows["b"].set_translation_size(0.6)
        windows.set_translation_sizes(1.5)
        assert {w.choices.translation_size for w in windows.windows.values()} == {1.5}
        assert {w.choices.text_size for w in windows.windows.values()} == {1.0}
        assert windows.stored.last.translation_size == 1.5
        assert windows.stored.for_new(3).translation_size == 1.5

        windows.set_caption_sizes(1.8)
        assert {w.choices.text_size for w in windows.windows.values()} == {1.8}
        assert {w.choices.translation_size for w in windows.windows.values()} == {1.5}
        assert windows.stored.for_new(3).text_size == 1.8
        assert windows.stored.for_new(3).translation_size == 1.5
    finally:
        windows.close()


def test_the_lookup_card_is_anchored_on_a_word_of_a_larger_translation(
    qapp: QApplication,
) -> None:
    """At 200 % the translation row is the bigger one: a click on its word
    pins the card to that word, above its row."""
    from tests.ui_next.test_lookup_card import AREA, click, find

    tools = chinese_tools()
    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=tools)
    try:
        windows.set_captioned([("app", APP)])
        shown = windows.windows["app"]
        shown.set_translation_size(2.0)
        shown.set_look(CaptionLook(word_links=WordLinks.OFF, arrival=Arrival.STEP))
        for update in finished_updates(6):
            windows.apply(update)
        shown.setGeometry(480, 500, 960, 460)
        qapp.processEvents()
        shown.canvas.repaint()
        newest = shown.view.lines[-1]
        english = next(r.text for r in newest.rows if r.kind is RowKind.TRANSLATION)
        word = next(w.strip(",.?!") for w in english.split() if len(w) > 3)
        marked, point = find(shown, word)
        line = next(p for p in shown.canvas.placed if p[0].key == marked.key)
        assert line[1].rows[marked.row].row.kind is RowKind.TRANSLATION
        click(shown, point)
        card = windows.card
        assert card is not None and card.isVisible()
        request = card.request
        assert request is not None and request.word == word
        at = shown.mapToGlobal(point.toPoint())
        assert request.rect.x <= at.x() <= request.rect.x + request.rect.width
        assert card.above and card.geometry().bottom() < request.row.y
    finally:
        windows.close()


def test_video_uses_the_configured_pixels_for_mandarin_and_english(
    qapp: QApplication,
) -> None:
    window = window_of(qapp, captions=1, text_size=1.0, translation_size=0.8)
    try:
        window.set_video(True)
        engine = window.canvas.engine
        line = window.view.lines[-1]
        for language in ("zh", "en"):
            rows = tuple(replace(row, language=Language(language)) for row in line.rows)
            laid = engine.laid(replace(line, rows=rows), 760, 1.0)
            for row in laid.rows:
                size = 1.0 if row.row.kind is RowKind.ORIGINAL else 0.8
                assert row.layout.font().pixelSize() == round(
                    engine.style.text_px * size
                )
    finally:
        window.close()
        window.deleteLater()
