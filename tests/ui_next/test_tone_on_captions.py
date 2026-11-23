"""Contrast and vibrance on the captions (polyglotic-hq 481; the user,
2026-11-18: "Make a contrast vibrance settings"): two sliders in Settings >
Look, one setting for every caption window and transcript, today's look at
0 on both. The numbers at each slider's ends on every preset's panel, dark
and light (Paper's cream): text never under the floor at the softest, every
line at full ink at the crispest, 477's 5:1 for the quiet view in the
middle; word links' colours told apart at every vibrance (they keep their
colours: muted or vivid, two pairs fell under 13). Offscreen, made-up
captions."""

from collections.abc import Iterator
from dataclasses import replace
from itertools import combinations

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import EN, finished_updates
from tests.ui_next.test_link_colours_told_apart import (
    TOLD_APART,
    _drawn,
    _lab,
    ciede2000,
)

from polyglotic_desktop.core.listening.captions import Language, WordClass
from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import (
    LINK_CONTRAST,
    QUIET_ALPHA,
    Ink,
    drawn_ink,
)
from polyglotic_desktop.ui_next.caption_marks import (
    LINK_COLORS,
    QUIET_BLUE,
    QUIET_CONTRAST,
    CaptionMarks,
)
from polyglotic_desktop.ui_next.caption_window import look_ink, marks_panel
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.views.arrivals import (
    OLDER_ALPHA,
    OLDER_TRANSLATION_ALPHA,
)
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    BY_KEY,
    LARGE_TEXT,
    PRESETS,
    VIDEOS,
    ColourPreset,
    _mix,
    contrast,
    readable_through,
)
from polyglotic_desktop.ui_next.views.tone import FLOOR, SOFTEST, chroma, vibrant
from polyglotic_desktop.ui_next.views.transcript import Transcript, TranscriptChoices
from polyglotic_desktop.ui_next.word_classes import CLASS_ALTERNATES, CLASS_COLOURS

INKS = {
    "newest": 1.0,
    "live": Ink.live_alpha,
    "provisional": Ink.provisional_alpha,
    "older": OLDER_ALPHA,
    "older translation": OLDER_TRANSLATION_ALPHA,
}
"""Today's inks for a line: what the slider moves (`views.arrivals`)."""
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            shiboken6.delete(made)


def _look(
    preset: ColourPreset,
    *,
    quiet: bool = False,
    contrast: int = 0,
    vibrance: int = 0,
) -> CaptionLook:
    return CaptionLook(
        background=preset.background,
        original=preset.original,
        translation=preset.translation,
        opacity=preset.opacity,
        quiet=quiet,
        contrast=contrast,
        vibrance=vibrance,
    )


def _ink(look: CaptionLook) -> Ink:
    return look_ink(Ink(QColor(look.original), QColor(look.translation)), look)


def _backs(preset: ColourPreset) -> list[tuple[str, float]]:
    """Its panel drawn solid, with the floor; seen through at its opacity
    over a light and a black video, with large text's 3:1."""
    found = [(preset.background, FLOOR)]
    if preset.opacity < 1.0:
        found += [
            (_mix(video, preset.background, preset.opacity), LARGE_TEXT)
            for video in VIDEOS
        ]
    return found


def _on(drawn: QColor, under: str) -> float:
    return contrast(_mix(under, drawn.name(), drawn.alphaF()), under)


def _lines(quiet: bool) -> dict[str, float]:
    return {"quiet": QUIET_ALPHA} if quiet else INKS


# -- contrast ----------------------------------------------------------------------


def test_the_softest_is_quick_previews_faintness() -> None:
    assert Ink().provisional_alpha == SOFTEST == QUIET_ALPHA


@pytest.mark.parametrize("quiet", [False, True], ids=["captions", "quiet"])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_contrast_0_draws_every_line_as_today(
    preset: ColourPreset, quiet: bool
) -> None:
    ink = _ink(_look(preset, quiet=quiet))
    for today in _lines(quiet).values():
        for colour in (ink.original, ink.translation):
            drawn = drawn_ink(colour, today, ink)
            if quiet:  # 477: shaded to read at 5:1 at Quick preview's ink
                shade = readable_through(
                    colour.name(), preset.background, preset.opacity, today, 5.0
                )
                assert drawn.name() == shade
            else:
                assert drawn.name() == colour.name()
            assert drawn.alphaF() == pytest.approx(today, abs=0.002)


@pytest.mark.parametrize("quiet", [False, True], ids=["captions", "quiet"])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_the_softest_still_reads_and_is_never_stronger_than_today(
    preset: ColourPreset, quiet: bool
) -> None:
    """Every line at the softest: at least the floor on the panel drawn
    solid (3.7:1) and 3:1 seen through it over a light or a black video -
    or today's, where today's is already under it - and never stronger
    than today's."""
    soft, today_ink = _ink(_look(preset, quiet=quiet, contrast=-100)), None
    today_ink = _ink(_look(preset, quiet=quiet))
    for name, today in _lines(quiet).items():
        for colour, was_colour in (
            (soft.original, today_ink.original),
            (soft.translation, today_ink.translation),
        ):
            drawn = drawn_ink(colour, today, soft)
            was = drawn_ink(was_colour, today, today_ink)
            for under, needs in _backs(preset):
                got, before = _on(drawn, under), _on(was, under)
                assert got >= min(needs, before) - 0.02, (name, under, got)
                assert got <= before + 0.02, (name, under, got, before)


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_the_softest_is_softer_than_today(preset: ColourPreset) -> None:
    soft, today_ink = (
        _ink(_look(preset, contrast=-100)),
        _ink(_look(preset)),
    )
    drawn = drawn_ink(soft.original, 1.0, soft)
    was = drawn_ink(today_ink.original, 1.0, today_ink)
    assert _on(drawn, preset.background) < _on(was, preset.background) - 0.5


@pytest.mark.parametrize("quiet", [False, True], ids=["captions", "quiet"])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_the_crispest_draws_every_line_at_full_ink(
    preset: ColourPreset, quiet: bool
) -> None:
    ink = _ink(_look(preset, quiet=quiet, contrast=100))
    for today in _lines(quiet).values():
        for colour in (ink.original, ink.translation):
            assert drawn_ink(colour, today, ink).alphaF() == 1.0


@pytest.mark.parametrize("key", ["classic", "paper"])
def test_the_quiet_views_numbers_at_each_end(key: str) -> None:
    """477's 5:1 in the middle, the floor at the softest, full ink at the
    crispest - on a dark panel and a light one."""
    preset = BY_KEY[key]
    found = {}
    for end in (-100, 0, 100):
        ink = _ink(_look(preset, quiet=True, contrast=end))
        found[end] = min(
            _on(drawn_ink(colour, QUIET_ALPHA, ink), preset.background)
            for colour in (ink.original, ink.translation)
        )
    assert found[0] >= LINK_CONTRAST - 0.05
    assert FLOOR - 0.05 <= found[-100] < found[0] < found[100]


def test_a_link_coloured_word_comes_down_to_the_floor_with_the_rest() -> None:
    from polyglotic_desktop.ui_next.caption_layout import link_ink

    preset = BY_KEY["classic"]
    found = {}
    for end in (-100, 0):
        ink = _ink(_look(preset, contrast=end))
        row = drawn_ink(ink.original, 1.0, ink)
        word = link_ink(QColor("#5c9dff"), ink, row)
        found[end] = _on(word, preset.background)
    assert FLOOR - 0.05 <= found[-100] < found[0]
    assert found[0] >= LINK_CONTRAST - 0.05


SOFT_APART = 11.5
"""Word links' colours as words, at every soft contrast: over the 11.1 at
which the user found orange and brown "not that distinguishable" (446) -
the 13 of the middle (`TOLD_APART`) isn't kept as everything fades (today's
older captions, at 72 %, have red and pink 7.3 apart on Classic)."""


@pytest.mark.parametrize("end", [-100, -75, -50, -25])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_link_coloured_words_stay_apart_as_contrast_softens(
    preset: ColourPreset, end: int
) -> None:
    from polyglotic_desktop.ui_next.caption_layout import link_ink

    ink = _ink(_look(preset, contrast=end))
    row = drawn_ink(ink.original, 1.0, ink)
    unders = [under for under, _ in _backs(preset)]

    def seen(colour: str) -> list[tuple[float, float, float]]:
        word = link_ink(QColor(colour), ink, row)
        return [_lab(_mix(u, word.name(), word.alphaF())) for u in unders]

    drawn = {c: seen(c) for c in LINK_COLORS}
    close = [
        (a, b, round(found, 1))
        for a, b in combinations(LINK_COLORS, 2)
        if (found := min(map(ciede2000, drawn[a], drawn[b]))) < SOFT_APART
    ]
    assert close == []
    assert min(map(ciede2000, drawn["#ff9f43"], drawn["#acbf60"])) >= 19.0


# -- vibrance ----------------------------------------------------------------------


def test_vibrance_moves_the_looks_colours_and_leaves_white_white() -> None:
    preset = BY_KEY["classic"]
    for end in (-100, 100):
        ink = _ink(_look(preset, vibrance=end))
        assert ink.original.name() == "#ffffff"
        gold = chroma(ink.translation.name())
        assert (gold > chroma(preset.translation)) == (end > 0)
    assert _ink(_look(preset)).translation.name() == preset.translation


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    tools = chinese_tools()
    shown = CaptionWindows(None, MIC, lambda: [Rect(0, 0, 1920, 1040)], learner=tools)
    shown.set_captioned([("app", APP)])
    linked = clause(
        "这个电脑真的很好。",
        "This computer is really good.",
        (("电脑", "computer"), ("真的", "really"), ("很好", "good")),
    )
    en = Language("en")
    classes = (WordClass.NOUN, WordClass.ADVERB, WordClass.ADJECTIVE)
    shown.apply(
        finished(
            "c1",
            replace(
                linked,
                links={
                    en: tuple(
                        replace(link, original_pos=pos, translation_pos=pos)
                        for link, pos in zip(linked.links[en], classes, strict=True)
                    )
                },
            ),
        )
    )
    yield shown
    shown.close()


def _link_colours(windows: CaptionWindows) -> set[str]:
    window = windows.windows["app"]
    found = set()
    for line in window.canvas.lines_in_view():
        for index, _ in enumerate(line.rows):
            for _, _, format_ in window.marks(line, index):
                if format_.underlineColor().isValid():
                    found.add(format_.underlineColor().name())
    return found


@pytest.mark.parametrize("vibrance", [-100, 100])
def test_word_links_keep_their_colours_at_every_vibrance(
    windows: CaptionWindows, vibrance: int
) -> None:
    look = CaptionLook(word_links=WordLinks.COLOURS)
    windows.set_look(look)
    today = _link_colours(windows)
    assert today == {
        CLASS_COLOURS[WordClass.NOUN],
        CLASS_COLOURS[WordClass.ADVERB],
        CLASS_ALTERNATES[WordClass.ADVERB][0],
        CLASS_COLOURS[WordClass.ADJECTIVE],
    }
    windows.set_look(replace(look, vibrance=vibrance))
    assert _link_colours(windows) == today


@pytest.mark.parametrize("vibrance", [-100, 0, 100])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_every_two_link_colours_are_told_apart_at_every_vibrance(
    preset: ColourPreset, vibrance: int
) -> None:
    """As drawn - lines and words - with the colours the marks give at
    `vibrance`: at least 13 apart (446), orange and olive (the user's
    orange and brown) at least 23."""
    marks = CaptionMarks(None)
    marks.set_look(
        WordLinks.COLOURS,
        marks.introductions,
        marks_panel(_look(preset, vibrance=vibrance)),
    )
    colours = [marks._format("link", c, n).underlineColor().name() for n, c in
               enumerate(LINK_COLORS)]  # fmt: skip
    for as_word in (False, True):
        drawn = {c: [_lab(s) for s in _drawn(c, preset, as_word)] for c in colours}
        for a, b in combinations(colours, 2):
            assert min(map(ciede2000, drawn[a], drawn[b])) >= TOLD_APART, (a, b)
        orange, olive = drawn["#ff9f43"], drawn["#acbf60"]
        assert min(map(ciede2000, orange, olive)) >= 23.0


@pytest.mark.parametrize("vibrance", [-100, 100])
@pytest.mark.parametrize("key", ["classic", "paper"])
def test_the_quiet_views_blue_follows_vibrance_and_stays_apart(
    key: str, vibrance: int
) -> None:
    preset = BY_KEY[key]
    marks = CaptionMarks(None)
    look = _look(preset, quiet=True, vibrance=vibrance)
    marks.set_look(WordLinks.HOVER, marks.introductions, marks_panel(look))
    blue = marks._blue().foreground().color().name()
    marks.set_look(WordLinks.HOVER, marks.introductions, marks_panel(_look(preset)))
    was = marks._blue().foreground().color().name()
    assert (chroma(blue) > chroma(was)) == (vibrance > 0), (blue, was)
    assert contrast(blue, preset.background) >= QUIET_CONTRAST - 0.05
    ink = _ink(look)
    for row in (ink.original, ink.translation):
        drawn = drawn_ink(row, QUIET_ALPHA, ink)
        shown = _mix(preset.background, drawn.name(), drawn.alphaF())
        assert ciede2000(_lab(blue), _lab(shown)) >= TOLD_APART


@pytest.mark.parametrize("vibrance", [-100, 100])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_saved_words_colours_follow_vibrance_and_still_read(
    preset: ColourPreset, vibrance: int
) -> None:
    marks = CaptionMarks(None)
    marks.set_look(
        WordLinks.OFF,
        marks.introductions,
        marks_panel(_look(preset, vibrance=vibrance)),
    )
    for colour in ("#6fc3ff", "#ff9f43", "#b388ff", "#36bf13"):
        found = marks._saved(colour, RowKind.ORIGINAL).foreground().color().name()
        assert contrast(found, preset.background) >= AA_TEXT
    assert QUIET_BLUE  # the first category's blue, as above


# -- kept, and on Settings > Look --------------------------------------------------


def test_contrast_and_vibrance_are_kept_and_read_leniently() -> None:
    assert (CaptionLook().contrast, CaptionLook().vibrance) == (0, 0)
    assert caption_look(AppSettings()).contrast == 0  # existing users: as today
    look = replace(CaptionLook(), contrast=-40, vibrance=65)
    stored = AppSettings().to_stored() | look_settings(look)
    again = caption_look(AppSettings.from_stored(stored))
    assert (again.contrast, again.vibrance) == (-40, 65)
    for wrong in (150, -101, True, "50", 2.5, None):
        read = AppSettings.from_stored({"caption_contrast": wrong})
        assert read.caption_contrast == 0
        read = AppSettings.from_stored({"caption_vibrance": wrong})
        assert read.caption_vibrance == 0


def test_the_two_sliders_sit_beside_the_presets_and_follow_the_keyboard(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    MADE.append(panel)
    contrast_, vibrance_ = panel.text.contrast, panel.text.vibrance
    assert contrast_.objectName() == "look.contrast"
    assert (contrast_.value(), vibrance_.value()) == (0, 0)
    assert contrast_.accessibleName() and vibrance_.accessibleName()
    assert contrast_.focusPolicy() & Qt.FocusPolicy.TabFocus
    QTest.keyClick(contrast_, Qt.Key.Key_Right)
    assert view.value.contrast == 5  # live: the windows follow each step
    QTest.keyClick(contrast_, Qt.Key.Key_End)
    assert view.value.contrast == 100
    QTest.keyClick(vibrance_, Qt.Key.Key_Home)
    assert view.value.vibrance == -100
    QTest.keyClick(vibrance_, Qt.Key.Key_PageUp)
    assert view.value.vibrance == -75
    view.set_contrast(-30)  # from elsewhere (a reset): shown
    panel.refresh()
    assert contrast_.value() == -30
    view.reset()  # Reset look: both back to the middle
    panel.refresh()
    assert (contrast_.value(), vibrance_.value()) == (0, 0)


def _brightest(image: QImage) -> int:
    return max(
        image.pixelColor(x, y).lightness()
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
    )


def test_a_transcript_follows_contrast_and_vibrance(qapp: QApplication) -> None:
    transcript = Transcript(APP, EN, mic=MIC)
    for update in finished_updates(4):
        transcript.apply(update)
    window = TranscriptWindow(
        "Discord.exe", transcript, SourceLabel("Discord", "#4dd0e1"),
        TranscriptChoices(), style.current(), chinese_tools(),
    )  # fmt: skip
    MADE.append(window)
    shown = window.list
    shown.resize(600, 400)
    today = _brightest(shown.grab().toImage())
    shown.set_tone(CaptionLook(contrast=-100, vibrance=100))
    assert shown.tone == (-100, 100)
    assert shown._vivid("#acbf60") == vibrant("#acbf60", 100)
    soft = _brightest(shown.grab().toImage())
    assert soft < today


# -- thickness ---------------------------------------------------------------------


@pytest.mark.parametrize("quiet", [False, True], ids=["captions", "quiet"])
def test_thickness_is_the_captions_weight_and_their_readings_a_step_above(
    quiet: bool,
) -> None:
    from polyglotic_desktop.ui_next.caption_window import caption_style

    today = caption_style(CaptionLook(quiet=quiet))
    assert (today.weight, today.reading_weight) == (
        QFont.Weight.Medium,
        QFont.Weight.DemiBold,
    )  # as always
    for weight, reading in ((300, 400), (600, 700), (700, 700)):
        style_ = caption_style(CaptionLook(quiet=quiet, thickness=weight))
        assert (style_.weight.value, style_.reading_weight.value) == (weight, reading)


def test_a_weight_windows_keeps_in_a_face_of_its_own_is_asked_of_it() -> None:
    """Segoe UI Variable Display's Light and Semibold are families of their
    own on Windows: named before it at those weights only - after the
    caption's own faces since 482 - and never for a reading, which asks
    another weight (a made-up one, else: in its face's own only, 479)."""
    from polyglotic_desktop.core.listening.display import CaptionRow
    from polyglotic_desktop.ui_next import caption_faces
    from polyglotic_desktop.ui_next.caption_layout import (
        LATIN_FAMILIES,
        CaptionLayout,
        CaptionStyle,
    )
    from polyglotic_desktop.ui_next.fonts import WEIGHT_FACES, caption_families
    from polyglotic_desktop.ui_next.reading_lines import reading_font

    row = CaptionRow("Hello there", RowKind.ORIGINAL, EN, 0, True)
    for weight in (300, 400, 500, 600, 700):
        layout = CaptionLayout(CaptionStyle(weight=QFont.Weight(weight)))
        font = layout._font(row, 1.0, False)
        faces = WEIGHT_FACES.get(weight, ())
        families = font.families()
        at = families.index(LATIN_FAMILIES[0])  # the OS's own Latin faces
        assert families[at - len(faces) : at] == list(faces)
        assert font.weight().value == weight
        small = reading_font(font, 0.5, QFont.Weight.Bold)
        assert not set(small.families()) & {f for v in WEIGHT_FACES.values() for f in v}
        own_bold = caption_faces.has_weight(small.families()[0], 700)
        assert small.weight() == (QFont.Weight.Bold if own_bold else font.weight())
    today = CaptionLayout(CaptionStyle())._font(row, 1.0, False)
    assert today.families() == list(caption_families("en"))  # 482's faces


def test_thickness_is_kept_and_read_leniently() -> None:
    look = replace(CaptionLook(), thickness=700)
    stored = AppSettings().to_stored() | look_settings(look)
    assert caption_look(AppSettings.from_stored(stored)).thickness == 700
    assert caption_look(AppSettings()).thickness == 500
    for wrong in (450, 800, 200, True, "700", 600.0):
        assert AppSettings.from_stored({"caption_weight": wrong}).caption_weight == 500


def test_the_thickness_slider_steps_through_the_weights_by_name(
    qapp: QApplication,
) -> None:
    view = LookView(CaptionLook())
    panel = LookPanel(view, notes=True)
    MADE.append(panel)
    thickness, now = panel.text.thickness, panel.text.thickness_now
    assert thickness.objectName() == "look.thickness"
    assert now() == "Medium" and thickness.accessibleName()
    assert thickness.accessibleDescription() == "Medium"
    QTest.keyClick(thickness, Qt.Key.Key_Right)
    assert (view.value.thickness, now()) == (600, "Semibold")
    assert thickness.toolTip().startswith("Semibold. ")
    QTest.keyClick(thickness, Qt.Key.Key_Home)
    # the app's faces have nothing lighter: Medium is the light end (532)
    assert (view.value.thickness, now()) == (500, "Medium")
    QTest.keyClick(thickness, Qt.Key.Key_End)
    assert view.value.thickness == 700
    view.reset()
    panel.refresh()
    assert (thickness.value(), now()) == (2, "Medium")


# -- the corners -------------------------------------------------------------------


@pytest.mark.parametrize("vibrance", [-100, 100])
@pytest.mark.parametrize("end", [-100, 0, 100])
@pytest.mark.parametrize("quiet", [False, True], ids=["captions", "quiet"])
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_every_corner_still_reads(
    preset: ColourPreset, quiet: bool, end: int, vibrance: int
) -> None:
    """Vibrance at an end, contrast at either end or the middle, every
    line of today's: at least the floor on the panel drawn solid and 3:1
    seen through it - or today's where today's is under it (thickness
    changes no colour). Vivid moved Paper's brown lighter: its Quick
    preview line fell from 2.85 to 2.68 on the cream until the floor
    held with the vibrance moved too."""
    ink = _ink(_look(preset, quiet=quiet, contrast=end, vibrance=vibrance))
    today_ink = _ink(_look(preset, quiet=quiet))
    for today in _lines(quiet).values():
        for colour, was_colour in (
            (ink.original, today_ink.original),
            (ink.translation, today_ink.translation),
        ):
            drawn = drawn_ink(colour, today, ink)
            was = drawn_ink(was_colour, today, today_ink)
            for under, needs in _backs(preset):
                got = _on(drawn, under)
                assert got >= min(needs, _on(was, under)) - 0.05, (today, under, got)
