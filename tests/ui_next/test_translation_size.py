"""A caption window's text and translation sizes (polyglotic-hq 305; the
user, 2026-11-13: "need to a way to make the translation font size
smaller"; 2026-11-14: "can you just give maximal logical customisation for
caption and translation text sizes").

- **Text size** (what was said): 60 to 400 % (`CAPTION_TEXT_SIZES`), A- and
  A+ (and Ctrl+wheel) in 10 % steps, the popover's slider in 5 % steps.
- **Translation size**: its translation's text as a share of what was
  said's, 50 to 200 % in 10 % steps, the window's own like its text size,
  in its settings popover under Text size, with "Same as what was said".
  Either line is drawn within the text size's range.
- 100 % - the default - is today's window. A transcript keeps 70-200 %.

Offscreen, made-up captions. The slide and steps (`test_arrivals`), a long
caption in a small window (`test_caption_window`), word links' underlines
and Arrows' curves (`tests/ui/test_link_underline`, `test_arrows_back`) are
tested at 50, 100 and 200 % in their own files."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import finished_updates, live_update
from tests.ui_next.test_caption_window import areas, place, window_of

from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, CaptionStyle
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, caption_style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_popover import (
    COLUMN_ROWS,
    ROWS,
    SettingsPopover,
    SizeSlider,
)
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import (
    ORIGINAL_ONLY,
    TRANSLATION_SIZES,
    CaptionLook,
    StoredWindows,
    WindowChoices,
    stepped,
    text_size,
)
from polyglotic_desktop.ui_next.views.captions import CAPTION_TEXT_SIZES, TEXT_SIZES
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
    assert WindowChoices().translation_size == 1.0
    assert (
        caption_style(CaptionLook()).translation_size
        == CaptionStyle().translation_size
        == 1.0
    )
    assert caption_style(CaptionLook()) == caption_style(CaptionLook(), 1.0)
    stored = WindowChoices().to_stored()
    del stored["translation_size"]  # a window saved before 305
    assert WindowChoices.from_stored(stored, WindowChoices()).translation_size == 1.0


@pytest.mark.parametrize("share", [0.5, 0.6, 1.5, 2.0])
def test_the_translation_is_drawn_at_its_share_and_what_was_said_is_not(
    window: CaptionWindow, share: float
) -> None:
    before = sizes(window)
    place_before = place(window)
    newest = window.view.lines[-1].key
    window.set_translation_size(share)
    after = sizes(window)
    assert after[RowKind.ORIGINAL] == before[RowKind.ORIGINAL]
    for full, now in zip(
        sorted(before[RowKind.TRANSLATION]),
        sorted(after[RowKind.TRANSLATION]),
        strict=True,
    ):
        low = round(full * CAPTION_TEXT_SIZES[0])  # never under 60 % of the base
        assert now == max(low, round(full * share))
    assert place(window) == place_before  # the window keeps its size
    assert window.canvas.placed[-1][0].key == newest  # still at the bottom
    assert window.choices.translation_size == share


def test_it_goes_from_50_to_200_percent_in_tens_and_back_in_one_click(
    window: CaptionWindow,
) -> None:
    smaller = window.controls["translation_smaller"]
    bigger = window.controls["translation_bigger"]
    same = window.controls["translation_same"]
    assert smaller.isEnabled() and bigger.isEnabled() and not same.isEnabled()
    for _ in range(10):
        smaller.trigger()
    assert window.choices.translation_size == TRANSLATION_SIZES[0] == 0.5
    assert not smaller.isEnabled() and same.isEnabled()
    for _ in range(20):
        bigger.trigger()
    assert window.choices.translation_size == TRANSLATION_SIZES[1] == 2.0
    assert not bigger.isEnabled()
    window.set_translation_size(0.3)  # out of range: kept within it
    assert window.choices.translation_size == 0.5
    same.trigger()  # "Same as what was said"
    assert window.choices.translation_size == 1.0 and not same.isEnabled()


def test_what_was_said_goes_from_60_to_400_percent() -> None:
    assert CAPTION_TEXT_SIZES == (0.6, 4.0) and TEXT_SIZES == (0.7, 2.0)
    assert stepped(3.95, 1, CAPTION_TEXT_SIZES) == 4.0
    assert stepped(0.65, -1, CAPTION_TEXT_SIZES) == 0.6
    assert stepped(1.95, 1) == 2.0  # a transcript's: as it was
    assert text_size(0.6) == 0.6 and text_size(4.0) == 4.0
    assert text_size(0.5) is None and text_size(4.1) is None
    # a transcript keeps its 70-200 %
    assert TranscriptChoices.from_stored({"text_size": 3.0}).text_size == 1.0
    assert TranscriptChoices.from_stored({"text_size": 2.0}).text_size == 2.0


def test_no_line_is_drawn_outside_the_text_sizes_range(qapp: QApplication) -> None:
    """50 % of 60 % is drawn at 60 % (13 px, never under the app's 12 px);
    200 % of 400 % at 400 % (84 px): a translation never smaller or larger
    than what was said may be."""
    window = window_of(qapp, captions=2)
    try:
        line = window.view.lines[-1]
        for share, size, wanted in ((0.5, 0.6, 0.6), (2.0, 4.0, 4.0), (2.0, 1.0, 2.0)):
            laid = CaptionLayout(CaptionStyle(translation_size=share)).laid(
                line, 1800, size
            )
            plain = CaptionLayout().laid(line, 1800, wanted)
            for a, b in zip(laid.rows, plain.rows, strict=True):
                if a.row.kind is RowKind.TRANSLATION:
                    assert a.layout.font().pixelSize() == b.layout.font().pixelSize()
                    assert a.layout.font().pixelSize() >= 12
    finally:
        window.close()
        window.deleteLater()


def test_arrows_curves_keep_their_thickness_at_any_share(qapp: QApplication) -> None:
    """A curve runs on from what was said's underline: as thick at 50 or
    200 % as at 100 % (`LaidRow.full_px`)."""
    window = window_of(qapp, captions=2)
    try:
        line = window.view.lines[-1]
        full = CaptionLayout().laid(line, 900, 1.0)
        for share in (0.5, 2.0):
            laid = CaptionLayout(CaptionStyle(translation_size=share)).laid(
                line, 900, 1.0
            )
            assert [r.full_px for r in laid.rows] == [
                r.layout.font().pixelSize() for r in full.rows
            ]
    finally:
        window.close()
        window.deleteLater()


def test_the_popover_has_both_under_each_other_with_sliders(
    window: CaptionWindow,
) -> None:
    assert ROWS[ROWS.index("text_size") + 1] == "translation_size"
    assert COLUMN_ROWS[COLUMN_ROWS.index("text_size") + 1] == "translation_size"
    popover = popover_of(window)
    row = popover.rows["translation_size"]
    said = row.findChild(QLabel)
    assert said is not None and "100%" in said.text()
    smaller = row.findChild(
        QPushButton, "settings_popover.caption_window.translation_smaller"
    )
    assert smaller is not None and smaller.accessibleName() == "Smaller translation"
    smaller.click()
    smaller.click()
    assert window.choices.translation_size == 0.8 and "80%" in said.text()
    slider = row.findChild(SizeSlider, "settings_popover.translation_slider")
    assert slider is not None and slider.chosen() == 0.8
    assert (slider.minimum(), slider.maximum()) == (0, 15)  # 50-200 % in tens
    slider.setValue(slider.maximum())
    assert window.choices.translation_size == 2.0 and "200%" in said.text()
    same = row.findChild(
        QPushButton, "settings_popover.caption_window.translation_same"
    )
    assert same is not None and same.text() == "Same as what was said"
    same.click()
    assert window.choices.translation_size == 1.0 and slider.chosen() == 1.0
    text = popover.rows["text_size"].findChild(
        SizeSlider, "settings_popover.text_size_slider"
    )
    assert text is not None and (text.minimum(), text.maximum()) == (0, 68)
    text.setValue(9)  # 60 % and nine 5 % steps
    assert window.view.text_size == 1.05 == window.choices.text_size
    window.step_text(1)  # A+: a 10 % step, the slider following
    assert window.view.text_size == 1.15 and text.chosen() == 1.15
    window.set_language(ORIGINAL_ONLY)
    popover.refresh()
    assert row.isHidden()  # no translation, nothing to size
    window.set_language("en")
    popover.refresh()
    assert not row.isHidden()
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


def test_it_is_kept_and_a_new_window_takes_the_last_ones() -> None:
    for share in (0.5, 0.7, 2.0):
        chosen = WindowChoices(text_size=3.5, translation_size=share)
        assert WindowChoices.from_stored(chosen.to_stored(), WindowChoices()) == chosen
    chosen = WindowChoices(translation_size=0.7)
    for wrong in (0.4, 2.1, True, "0.8", None):
        stored = {**chosen.to_stored(), "translation_size": wrong}
        read = WindowChoices.from_stored(stored, WindowChoices())
        assert read.translation_size == 1.0  # not valid: the base's
    new = StoredWindows(last=WindowChoices(text_size=3.0, translation_size=0.7))
    assert (new.for_new(1).text_size, new.for_new(1).translation_size) == (3.0, 0.7)


def test_a_change_lays_out_again_only_the_translation(qapp: QApplication) -> None:
    window = window_of(qapp, captions=3)
    try:
        line = window.view.lines[-1]
        full = CaptionLayout().laid(line, 900, 1.0)
        for share, smaller in ((0.6, True), (2.0, False)):
            laid = CaptionLayout(CaptionStyle(translation_size=share)).laid(
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


@pytest.mark.parametrize("share", [0.5, 2.0])
def test_live_updates_and_the_finished_caption_at_rest_whole(
    qapp: QApplication, share: float
) -> None:
    """A live update growing, then its finished caption: at rest, nothing
    below the window's bottom edge, at half and twice the size."""
    window = window_of(
        qapp,
        captions=4,
        look=CaptionLook(arrival=Arrival.STEP),
        translation_size=share,
        text_size=1.6,
    )
    try:
        live = live_update("growing")
        window.view.apply(live)
        window.apply_changed(new_caption=True)
        assert bottom_whole(window)
        (done,) = finished_updates(1, start=7)
        from dataclasses import replace

        window.view.apply(replace(done, replaces=(live.caption_id,)))
        window.apply_changed(new_caption=True)
        assert bottom_whole(window)
        assert window.view.lines[-1].caption_id == done.caption_id
    finally:
        window.close()
        window.deleteLater()


def test_joined_columns_each_keep_their_own_share(qapp: QApplication) -> None:
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("a", APP), ("b", MIC)])
        windows.windows["a"].set_translation_size(2.0)
        windows.windows["b"].set_translation_size(0.5)
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
        assert windows.windows["b"].canvas.engine.style.translation_size == 0.5
        column.always_shown = True
        column.canvas.repaint()
        assert column.canvas.placed  # captions in view
        assert bottom_whole(column)
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
