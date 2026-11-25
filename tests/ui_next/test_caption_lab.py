"""Settings > Captions > Lab (polyglotic-hq 284): experimental caption
settings the user and testers tune by feel - each applies at once to the
caption windows and the preview, is saved, and "Reset the Lab" puts them
all back. First: how long a caption stays new, how it dims, and how far
older captions step back (the user's live testing, 270's FEEDBACK.md line
19: "Lines stay recent for x seconds (configurable), right now multiple
lines coming in you can't tell which ones are new")."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPaintEvent
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.made_up import finished_updates, live_update
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_newest_line_brighter import _inks
from tests.ui_next.test_settings_captions_page import MADE as PAGES
from tests.ui_next.test_settings_captions_page import page_with
from tools.ui_lab.lab import SCENE

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import LinkLine
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_layout import LINK_PX, CaptionLayout, Ink
from polyglotic_desktop.ui_next.caption_window import (
    MARK_LENGTH,
    CaptionWindow,
    caption_style,
    dot_inks,
    paint_loading,
    unfinished_ink,
)
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.arrivals import (
    OLDER_ALPHA,
    OLDER_TRANSLATION_ALPHA,
    Arrival,
)
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import (
    FADE_BACK_SEC,
    OLDER_RANGE,
    CaptionLab,
    Loading,
    NewFade,
    Unfinished,
    newness,
    older_translation,
)
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import _mix, contrast, contrast_alpha

MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each panel and page deleted when its test ends (261)."""
    yield
    while MADE or PAGES:
        made: QWidget = MADE.pop() if MADE else PAGES.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def lab_of(view: LookView) -> LabPanel:
    panel = LabPanel(view)
    MADE.append(panel)
    return panel


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def arrived(qapp: QApplication, lab: CaptionLab, clock: Clock) -> CaptionWindow:
    """A window of 3 captions, then 3 more arriving together at `clock`."""
    look = CaptionLook(lab=lab, arrival=Arrival.STEP)  # in place, not sliding in
    window = window_of(qapp, captions=3, look=look)
    window.clock = clock
    for update in finished_updates(3, start=3):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    return window


def older_alpha(window: CaptionWindow) -> float:
    ink = window._ink()
    assert ink.panel is not None
    return contrast_alpha(ink.original.name(), ink.panel, window.look.lab.older)


# -- the values ---------------------------------------------------------------------


def test_an_untouched_lab_is_the_app_as_it_was() -> None:
    lab = CaptionLab()
    assert (lab.new_for, lab.new_fade, lab.older) == (3.0, NewFade.GRADUAL, 0.85)
    assert older_translation(lab.older) == pytest.approx(OLDER_TRANSLATION_ALPHA)
    assert lab.to_stored() == {}
    assert CaptionLab.from_stored({}) == lab


def test_it_is_saved_and_read_back_leniently() -> None:
    lab = CaptionLab(new_for=3.5, new_fade=NewFade.GRADUAL, older=0.5)
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    odd = {"new_for": 99, "new_fade": "sideways", "older": True, "unknown": 1}
    assert CaptionLab.from_stored(odd) == CaptionLab()
    assert CaptionLab.from_stored("not a lab") == CaptionLab()


def test_the_settings_keep_it_and_the_look_reads_it() -> None:
    lab = CaptionLab(new_for=2.0)
    stored = look_settings(CaptionLook(lab=lab))["caption_lab"]
    value = AppSettings.from_stored({"caption_lab": stored})
    assert caption_look(value).lab == lab
    assert AppSettings.from_stored({"caption_lab": [1, 2]}).caption_lab == {}


def test_a_caption_is_new_for_its_time_then_steps_back_or_fades() -> None:
    at_once = CaptionLab(new_for=3.0, new_fade=NewFade.INSTANT)
    assert newness(0.0, at_once) == newness(2.9, at_once) == 1.0
    assert newness(3.0, at_once) == 0.0
    gradual = replace(at_once, new_fade=NewFade.GRADUAL)
    assert newness(3.0 + FADE_BACK_SEC / 2, gradual) == pytest.approx(0.5)
    assert newness(3.0 + FADE_BACK_SEC, gradual) == 0.0
    assert newness(None, gradual) == 0.0  # one the window opened with
    assert newness(1.0, CaptionLab(new_for=0.0)) == 0.0


@pytest.mark.parametrize("scene", [SCENE.name(), "#f3f5f7"])  # the lab's; light video
def test_the_dimmest_older_caption_stays_readable(scene: str) -> None:
    """OLDER_RANGE's floor: 3:1 on Classic's panel over a dark or light
    video - WCAG's floor for large text (the measured end of the slider)."""
    look = CaptionLook()
    panel = _mix(scene, look.background, look.opacity)
    low = OLDER_RANGE[0]
    for colour, ink in (
        (look.original, low),
        (look.translation, older_translation(low)),
    ):
        assert contrast(_mix(panel, colour, ink), panel) >= 3.0, (colour, scene)


# -- the caption window -------------------------------------------------------------


def test_captions_arriving_together_all_stay_bright_for_their_time(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    window = arrived(
        qapp,
        CaptionLab(new_for=4.0, new_fade=NewFade.INSTANT, older_steps=1),
        clock,
    )
    try:
        keys = [line.key for line in window.view.lines]
        drawn = _inks(window, monkeypatch)
        new = [k for k in keys[-3:] if k in drawn]
        assert len(new) >= 2  # the window shows two of them at least
        assert [drawn[k].alpha for k in new] == [1.0] * len(new)
        assert all(
            drawn[k].alpha == older_alpha(window) for k in keys[:3] if k in drawn
        )
        clock.now += 4.0  # their time is up: all but the newest step back
        drawn = _inks(window, monkeypatch)
        assert [drawn[k].alpha for k in new] == [older_alpha(window)] * (
            len(new) - 1
        ) + [1.0]
    finally:
        window.close()


def test_without_the_lab_only_the_newest_is_bright(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Today's step (DECISIONS.md #104): fails if New for applies at 0."""
    window = arrived(qapp, CaptionLab(new_for=0.0, older_steps=1), Clock())
    try:
        keys = [line.key for line in window.view.lines]
        drawn = _inks(window, monkeypatch)
        new = [k for k in keys[-3:] if k in drawn]
        assert len(new) >= 2
        assert [drawn[k].alpha for k in new] == [older_alpha(window)] * (
            len(new) - 1
        ) + [1.0]
    finally:
        window.close()


def test_a_gradual_step_back_fades_and_the_window_draws_each_frame(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    lab = CaptionLab(new_for=2.0, new_fade=NewFade.GRADUAL, older_steps=1)
    window = arrived(qapp, lab, clock)
    try:
        key = window.view.lines[-2].key
        clock.now += 2.0 + FADE_BACK_SEC / 2
        fading, _ = window._newness(clock.now)
        assert fading
        alpha = _inks(window, monkeypatch)[key].alpha
        floor = older_alpha(window)
        assert floor < alpha < 1.0
        assert alpha == pytest.approx((floor + 1.0) / 2)
    finally:
        window.close()


def test_the_window_wakes_when_a_caption_steps_back(qapp: QApplication) -> None:
    """Nothing moves while captions are new: the window sleeps until the
    first one's time is up, then draws it stepped back."""
    clock = Clock()
    window = arrived(qapp, CaptionLab(new_for=3.0), clock)
    try:
        fading, due = window._newness(clock.now)
        assert not fading and due == pytest.approx(3.0)
        clock.now += 1.0
        assert window._newness(clock.now)[1] == pytest.approx(2.0)
    finally:
        window.close()


def test_older_captions_step_back_as_far_as_the_lab_says(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = window_of(qapp, captions=4)
    try:
        window.set_look(replace(window.look, lab=CaptionLab(older=0.5, older_steps=1)))
        keys = [line.key for line in window.view.lines]
        drawn = _inks(window, monkeypatch)
        older = drawn[keys[-2]]
        assert older.alpha == older_alpha(window)
        ink = window._ink()
        assert ink.panel is not None
        assert older.alpha * older.translation_alpha == pytest.approx(
            contrast_alpha(ink.translation.name(), ink.panel, older_translation(0.5))
        )
        window.set_look(replace(window.look, lab=CaptionLab(older=1.0)))
        drawn = _inks(window, monkeypatch)
        assert {(i.alpha, i.translation_alpha) for i in drawn.values()} == {(1.0, 1.0)}
    finally:
        window.close()


# -- the Lab's card -----------------------------------------------------------------


def test_the_lab_changes_the_look_at_once_and_resets(qapp: QApplication) -> None:
    changes: list[CaptionLook] = []
    view = LookView(CaptionLook(), changes.append)
    panel = lab_of(view)
    assert panel.new_fade.isEnabled() is True
    panel.new_for.slider.setValue(4)  # 2 s
    assert view.value.lab.new_for == 2.0 and changes[-1].lab.new_for == 2.0
    assert panel.new_fade.isEnabled()
    panel.new_fade.choose(NewFade.GRADUAL)
    panel.older.slider.setValue(panel.older.slider.maximum())
    assert view.value.lab == CaptionLab(2.0, NewFade.GRADUAL, 1.0)
    assert panel.older.shown.text() == "No dimming"
    assert panel.preview.surface.older is not None
    assert panel.preview.surface.older.alpha == 1.0  # the preview follows
    panel.reset.click()
    assert view.value.lab == CaptionLab()
    assert panel.new_for.slider.value() == 6
    assert panel.preview.surface.older.alpha == OLDER_ALPHA


def test_resetting_the_look_keeps_the_lab() -> None:
    lab = CaptionLab(new_for=2.0)
    view = LookView(CaptionLook(original="#eeeeee", lab=lab))
    view.reset()
    assert view.value.original == CaptionLook().original
    assert view.value.lab == lab


def test_the_settings_page_has_the_lab_in_its_own_section_last(
    qapp: QApplication,
) -> None:
    page = page_with()
    assert list(page.section)[-1] == "lab"  # its own, last (304)
    page.show_section("lab")  # its card made when it's first shown (544)
    column = page.section["lab"].layout()
    assert column is not None
    last = column.itemAt(column.count() - 1)
    assert last is not None and last.widget() is page.lab
    assert page.lab.title is not None
    assert page.lab.title.text() == "Lab - experimental"  # marked as such


def test_the_window_steps_a_caption_back_on_its_own_when_its_time_is_up(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With real time and the window's own timers (no clock stepped): a
    caption new for 0.2 s is drawn stepped back once that's passed."""
    import time

    look = CaptionLook(
        lab=CaptionLab(new_for=0.2, new_fade=NewFade.INSTANT, older_steps=1),
        arrival=Arrival.STEP,
    )
    window = window_of(qapp, captions=2, look=look)
    try:
        for update in finished_updates(2, start=2):
            window.view.apply(update)
        window.apply_changed(new_caption=True)
        before_key = window.view.lines[-2].key
        assert _inks(window, monkeypatch)[before_key].alpha == 1.0
        drawn: list[int] = []
        paint = window.canvas.paintEvent

        def counted(event: QPaintEvent) -> None:
            drawn.append(1)
            paint(event)

        monkeypatch.setattr(window.canvas, "paintEvent", counted)
        until = time.monotonic() + 0.6
        while time.monotonic() < until:
            qapp.processEvents()
            time.sleep(0.01)
        assert drawn  # the window woke and drew it, unasked
        assert window._newness_drawn == ()  # nothing new any more
        monkeypatch.undo()
        assert _inks(window, monkeypatch)[before_key].alpha == older_alpha(window)
    finally:
        window.close()


# -- text still being spoken ---------------------------------------------------------


@pytest.mark.parametrize(
    ("unfinished", "italic", "alphas", "coloured"),
    [
        (Unfinished.AS_NOW, (True, False), (0.6, 0.85), False),
        (Unfinished.SAME, (False, False), (1.0, 1.0), False),
        (Unfinished.DIMMER, (False, False), (0.6, 0.6), False),
        (Unfinished.ITALIC, (True, True), (1.0, 1.0), False),
        (Unfinished.COLOUR, (False, False), (1.0, 1.0), True),
    ],
)
def test_text_still_being_spoken_looks_as_the_lab_says(
    unfinished: Unfinished,
    italic: tuple[bool, bool],
    alphas: tuple[float, float],
    coloured: bool,
) -> None:
    """A provisional line and a live caption (270's FEEDBACK.md line 20):
    as now - the provisional line dim and italic, the live one a little
    dim - or like finished text, dimmer, italic, or in the accent."""
    look = CaptionLook(lab=CaptionLab(unfinished=unfinished))
    style = caption_style(look)
    assert (style.italic_provisional, style.italic_live) == italic
    ink = unfinished_ink(Ink(), look)
    assert (ink.provisional_alpha, ink.live_alpha) == alphas
    assert (ink.unfinished is not None) is coloured
    if ink.unfinished is not None:
        assert contrast(ink.unfinished.name(), look.background) >= 4.5


def test_a_live_caption_is_laid_out_italic_and_upright_once_finished(
    qapp: QApplication,
) -> None:
    # in Chinese's sans, which slanted before 526, not its calligraphy (532)
    look = CaptionLook(
        lab=CaptionLab(unfinished=Unfinished.ITALIC),
        faces=(("zh", "Noto Sans SC Captions"),),
    )
    engine = CaptionLayout(caption_style(look))
    window = window_of(qapp, captions=1, look=look)
    try:
        window.view.apply(live_update("app-live"))
        line = window.view.lines[-1]
        assert line.live and not line.provisional
        laid = engine.laid(line, 600, 1.0)
        slanted = {row.row.language: row.layout.font().italic() for row in laid.rows}
        assert not slanted[Language("zh")]  # Chinese is never slanted (526)
        assert slanted[Language("en")]
        finished = engine.laid(replace(line, live=False), 600, 1.0)
        assert not any(row.layout.font().italic() for row in finished.rows)
    finally:
        window.close()


def test_the_window_draws_live_text_in_the_accent(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    look = CaptionLook(lab=CaptionLab(unfinished=Unfinished.COLOUR))
    window = window_of(qapp, captions=2, look=look)
    try:
        assert window.canvas.ink.unfinished is not None
        window.set_look(replace(window.look, lab=CaptionLab()))
        assert window.canvas.ink.unfinished is None  # at once, no restart
    finally:
        window.close()


def test_the_labs_preview_shows_a_caption_still_being_spoken(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook(preview=True))
    panel = lab_of(view)
    lines = panel.preview.lines.lines
    assert len(lines) == 3 and lines[-1].provisional
    older = panel.preview.surface.ink_for(lines[0])
    assert older.alpha == OLDER_ALPHA  # the newest finished one is the second
    assert panel.preview.surface.ink_for(lines[1]).alpha == 1.0
    panel.unfinished.choose(Unfinished.COLOUR)
    assert view.value.lab.unfinished is Unfinished.COLOUR
    assert panel.preview.surface.ink.unfinished is not None


# -- the underline's thickness and the spacing ---------------------------------------


def test_the_underline_thickness_is_the_labs_until_word_links_picks_a_step() -> None:
    """A slider in place of Thin / Medium / Thick (270's FEEDBACK.md line
    21); picking one of those in Word links again puts the steps back."""
    view = LookView(CaptionLook(link_line=LinkLine.MEDIUM))
    assert caption_style(view.value).link_px == LINK_PX[LinkLine.MEDIUM]
    view.set_lab(replace(view.value.lab, link_px=5.0))
    assert caption_style(view.value).link_px == 5.0
    view.set_link_line(LinkLine.THIN)
    assert view.value.lab.link_px is None
    assert caption_style(view.value).link_px == LINK_PX[LinkLine.THIN]


def test_the_spacing_moves_the_translation_and_the_next_caption(
    qapp: QApplication,
) -> None:
    """270's FEEDBACK.md line 24: the gap between what was said and its
    translation, and between captions - with the gap between clauses
    growing so a translation stays nearer its own original."""
    window = window_of(qapp, captions=4)
    try:
        line = window.view.lines[-1]
        before = window.canvas.laid_at(line, 600).rows[1].top
        gap_before = window.canvas._gap()
        window.set_look(
            replace(window.look, lab=CaptionLab(row_gap=10.0, caption_gap=30.0))
        )
        assert window.canvas.laid_at(line, 600).rows[1].top == pytest.approx(
            before + 8.0
        )
        assert window.canvas._gap() == 30.0 and gap_before == 10.0
        style = window.canvas.engine.style
        assert style.clause_gap == 16.0 > style.row_gap
    finally:
        window.close()


@pytest.mark.parametrize(
    "name", ["new_for", "older", "row_gap", "caption_gap", "arrival_gap"]
)
def test_a_slider_moved_away_and_back_is_the_lab_untouched_again(
    qapp: QApplication, name: str
) -> None:
    """287: Older captions' default (72 %) isn't on its 5 % scale from 45 %:
    one notch down and back up gave 70 %, never 72 % again, and the Lab
    stayed "changed" - stored, so a later default wouldn't reach it."""
    view = LookView(CaptionLook())
    panel = lab_of(view)
    slider = getattr(panel, name).slider
    start = slider.value()
    slider.setValue(start + 1 if start < slider.maximum() else start - 1)
    assert view.value.lab != CaptionLab()
    slider.setValue(start)
    assert view.value.lab == CaptionLab()
    assert view.value.lab.to_stored() == {}


def test_older_captions_read_their_default_where_the_slider_starts(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = lab_of(view)
    assert panel.older.shown.text() == "85%"
    panel.older.slider.setValue(panel.older.slider.value() - 1)
    assert view.value.lab.older == 0.8
    panel.older.slider.setValue(panel.older.slider.value() + 2)
    assert view.value.lab.older == 0.9


def test_the_lab_card_moves_the_thickness_and_spacing(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = lab_of(view)
    assert panel.link_px.shown.text() == "2.2 px"  # Word links' Medium
    panel.link_px.slider.setValue(panel.link_px.slider.maximum())
    panel.row_gap.slider.setValue(0)
    panel.caption_gap.slider.setValue(panel.caption_gap.slider.maximum())
    lab = view.value.lab
    assert (lab.link_px, lab.row_gap, lab.caption_gap) == (6.0, 0.0, 40.0)
    assert panel.preview.surface.engine.style.caption_gap == 40.0  # the preview too
    stored = CaptionLab.from_stored({"link_px": 0.2, "row_gap": 99, "caption_gap": 2})
    assert stored == CaptionLab()  # out of the measured ranges: the defaults


# -- the loading sign -----------------------------------------------------------------


def _drawn(
    loading: Loading, newest_live: bool = False, now: float | None = 0.3
) -> QImage:
    image = QImage(200, 60, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    paint_loading(
        painter, loading, QPointF(10, 30), 1.0, QColor("#ffffff"), now, newest_live
    )
    painter.end()
    return image


def _lit(image: QImage) -> int:
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).lightness() > 40
    )


@pytest.mark.parametrize("loading", list(Loading))
def test_each_loading_sign_draws_something(loading: Loading) -> None:
    """270's FEEDBACK.md line 27: the bar, three dots, or an ellipsis -
    moving, and standing still with Windows' animations off."""
    assert _lit(_drawn(loading)) > 10
    assert _lit(_drawn(loading, now=None)) > 10


def test_the_ellipsis_leaves_it_to_a_live_lines_own() -> None:
    """A caption still being spoken already ends in " …" (the display's
    LIVE_TRAIL): the ellipsis sign adds nothing then."""
    assert _lit(_drawn(Loading.ELLIPSIS, newest_live=True)) == 0
    assert _lit(_drawn(Loading.BAR, newest_live=True)) > 10


def test_the_dots_light_up_in_turn() -> None:
    first = dot_inks(0.0)
    assert first[0] == max(first) and first[1] < first[0]
    assert dot_inks(1 / 3)[1] == max(dot_inks(1 / 3))


def test_the_lab_picks_the_sign_and_the_window_draws_it(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    panel = lab_of(view)
    panel.loading.choose(Loading.DOTS)
    assert view.value.lab.loading is Loading.DOTS
    window = window_of(qapp, captions=2, look=view.value)
    try:
        window.set_listening(True)
        window.canvas.repaint()
        rect = window.canvas.mark_rect
        assert rect is not None and rect.width() < MARK_LENGTH  # dots, not the bar
    finally:
        window.close()
