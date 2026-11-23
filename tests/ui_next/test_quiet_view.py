"""The quiet view (polyglotic-hq 477; the user, 2026-11-18: "utilising the
blue words on grey surrounding text to be a one click toggle linkage mode
links just that with no underlines"): one button, every caption mode in
Quick preview's grey and gold, italic and a size step bigger, a reading
over every word, only the chosen words in blue (their reading too), no
underline or link colour, and a word's partner lit quietly on hover.
Offscreen, made-up captions, the sample dictionary."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools

from polyglotic_desktop.core.learning.curriculum import ChosenWords
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.listening.display import ReadingColour, WordLinks
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished, live
from polyglotic_desktop.ui_next import caption_window as window_module
from polyglotic_desktop.ui_next.caption_layout import (
    LINK_MARK,
    QUIET_ALPHA,
    QUIET_SCALE,
    QUIET_TRANSLATION,
    CaptionStyle,
    Ink,
)
from polyglotic_desktop.ui_next.caption_marks import QUIET_BLUE
from polyglotic_desktop.ui_next.caption_window import (
    QUIET_HOVERED,
    CaptionWindow,
    Marked,
    caption_style,
    look_ink,
    shade,
    shown_links,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import QuietViewPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LINKS_WHEN_ON, LookView
from polyglotic_desktop.ui_next.views.placement import Rect

AREA = Rect(0, 0, 1920, 1040)
SAID, MEANT = "这个电脑真的很好。", "This computer is really good."
QUIET = CaptionLook(
    quiet=True, reading_lines=("zh",), quiet_words=frozenset({ChosenWords.CURRICULUM})
)


# -- the button: quiet on turns word links off, and the reverse ------------------


def test_the_quiet_view_turns_word_links_off_and_word_links_turn_it_off() -> None:
    view = LookView(CaptionLook())
    view.set_links_shown(True, ("zh",))
    assert view.value.word_links is not WordLinks.OFF
    view.set_quiet(True, ("zh",))
    assert view.value.quiet and view.value.word_links is WordLinks.OFF
    view.set_links_shown(True)
    assert not view.value.quiet and view.value.word_links is not WordLinks.OFF
    view.set_word_links(WordLinks.OFF)
    view.set_quiet(True)
    view.set_word_links(WordLinks.COLOURS)  # Settings' own choice
    assert not view.value.quiet


def test_the_quiet_view_off_puts_word_links_back_as_they_were() -> None:
    """Off again, word links show as the learner had them (polyglotic-hq
    555: on every word by default; 523's settings sweep found them left
    off) - with their colours - and off stays off."""
    view = LookView(CaptionLook())
    view.set_links_shown(True, ("zh",))
    shown = view.value
    view.set_quiet(True, ("zh", "ja"))
    assert view.value.word_links is WordLinks.OFF
    view.set_quiet(False)
    assert view.value == shown
    off = LookView(CaptionLook(word_links=WordLinks.OFF))
    off.set_quiet(True)
    off.set_quiet(False)
    assert off.value.word_links is WordLinks.OFF
    # turned on before a restart: links as the links button shows them
    restarted = LookView(CaptionLook(quiet=True, word_links=WordLinks.OFF))
    restarted.set_quiet(False)
    assert restarted.value.word_links is LINKS_WHEN_ON


def test_settings_quiet_view_switch_puts_word_links_back(qapp: QApplication) -> None:
    """The way 523's sweep found it: Settings > Links' Quiet view, on and
    off."""
    view = LookView(CaptionLook(word_links=WordLinks.ARROWS))
    panel = QuietViewPanel(view, notes=True)
    panel.quiet.setChecked(True)
    assert view.value.quiet and view.value.word_links is WordLinks.OFF
    panel.quiet.setChecked(False)
    assert not view.value.quiet and view.value.word_links is WordLinks.ARROWS
    panel.deleteLater()


def test_the_quiet_view_puts_a_reading_over_a_chinese_window_and_back_off() -> None:
    view = LookView(CaptionLook())
    view.set_quiet(True, ("zh",))
    assert view.value.reading_lines == ("zh",)
    view.set_quiet(False)
    assert view.value.reading_lines == ()


def test_the_chosen_words_are_ticked_one_by_one() -> None:
    view = LookView(CaptionLook())
    assert view.value.quiet_words == {  # the default (496: words at your edge too)
        ChosenWords.CURRICULUM,
        ChosenWords.EDGE,
    }
    view.set_quiet_word(ChosenWords.SAVED, True)
    view.set_quiet_word(ChosenWords.CURRICULUM, False)
    view.set_quiet_word(ChosenWords.EDGE, False)
    assert view.value.quiet_words == {ChosenWords.SAVED}


# -- how it's drawn --------------------------------------------------------------


def test_every_line_is_italic_a_size_step_bigger_with_no_room_for_underlines() -> None:
    plain = caption_style(CaptionLook(reading_past=True))
    quiet = caption_style(replace(QUIET, reading_past=True))
    assert quiet.italic_all and not plain.italic_all
    assert quiet.text_px == pytest.approx(CaptionStyle().text_px * QUIET_SCALE)
    assert quiet.translation_factor == pytest.approx(QUIET_TRANSLATION)  # the larger
    assert not quiet.link_room and not quiet.arrows
    assert not quiet.reading_past  # a reading over every word
    assert shown_links(QUIET) is WordLinks.HOVER  # links kept, for the hover


def test_its_ink_is_quick_previews_grey_and_gold_with_no_link_colours() -> None:
    ink = look_ink(Ink(), QUIET)
    assert ink.quiet and ink.reading_colour is ReadingColour.SAME
    assert not ink.said_in_link_colours and not ink.translation_in_link_colours
    assert Ink().provisional_alpha == QUIET_ALPHA  # Quick preview's


@pytest.fixture
def shown(qapp: QApplication) -> Iterator[CaptionWindows]:
    tools = chinese_tools()
    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=tools)
    tools.changed.connect(windows.learning_changed)
    windows.set_look(QUIET)
    windows.set_captioned([("app", APP)])
    windows.apply(
        finished("c1", clause(SAID, MEANT, (("电脑", "computer"), ("真的", "really"))))
    )
    window = windows.windows["app"]
    window.setGeometry(100, 150, 900, 420)
    window.show()
    qapp.processEvents()
    yield windows
    windows.close()


def _marks(window: CaptionWindow) -> list[tuple[str, QTextCharFormat]]:
    found = []
    for line in window.canvas.lines_in_view():
        for index, row in enumerate(line.rows):
            for start, end, format_ in window.marks(line, index):
                found.append((row.text[start:end], format_))
    return found


def test_only_the_chosen_words_are_marked_and_in_blue(
    shown: CaptionWindows, qapp: QApplication
) -> None:
    tools = shown.learner
    assert tools is not None
    window = shown.windows["app"]
    assert _marks(window) == []  # nothing chosen yet: all grey and gold
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.save(
        computer, "电脑", "電腦", "diànnǎo", "computer", "saved", LookupContext(SAID)
    )
    shown.set_look(replace(QUIET, quiet_words=frozenset({ChosenWords.SAVED})))
    qapp.processEvents()
    marks = _marks(window)
    assert [text for text, _ in marks] == ["电脑"]
    (_, blue) = marks[0]
    assert not blue.hasProperty(LINK_MARK)  # no word link drawn
    assert blue.underlineStyle() is QTextCharFormat.UnderlineStyle.NoUnderline
    assert blue.foreground().color().name() == QUIET_BLUE  # readable on the panel


def test_a_live_lines_chosen_word_is_blue_too(
    shown: CaptionWindows, qapp: QApplication
) -> None:
    tools = shown.learner
    assert tools is not None
    computer = tools.lookup("电脑")[0].entry_id
    tools.vocabulary.save(
        computer, "电脑", "電腦", "diànnǎo", "computer", "saved", LookupContext(SAID)
    )
    shown.set_look(replace(QUIET, quiet_words=frozenset({ChosenWords.SAVED})))
    shown.apply(live("c2", clause("我的电脑又", "My computer")))
    qapp.processEvents()
    assert [text for text, _ in _marks(shown.windows["app"])] == ["电脑", "电脑"]


def test_hovering_a_word_lights_its_partner_quietly(
    shown: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = shown.windows["app"]
    filled: list[tuple[Marked, str]] = []
    real = window_module.Canvas._fill

    def recorded(painter, laid, at, marked, color):
        filled.append((marked, color.name(QColor.NameFormat.HexArgb)))
        real(painter, laid, at, marked, color)

    monkeypatch.setattr(window_module.Canvas, "_fill", staticmethod(recorded))
    line = window.canvas.lines_in_view()[0]
    said = line.rows[0]
    start = said.text.index("真的")
    window.canvas.hovered = Marked(line.key, 0, start, start + 2)
    window.canvas.repaint()
    soft = shade(window.bar, QUIET_HOVERED).name(QColor.NameFormat.HexArgb)
    partners = [m for m, c in filled if m.row == 1]
    assert partners and line.rows[1].text[partners[0].start : partners[0].end] == (
        "really"
    )
    assert {c for _, c in filled} == {soft}  # as soft as the word pointed at
    assert not window.canvas.engine.style.link_room


def test_the_strip_and_the_popover_offer_it(
    shown: CaptionWindows, qapp: QApplication
) -> None:
    window = shown.windows["app"]
    assert "quiet" not in window_module.STRIP  # the presets' dropdown has it (556)
    assert window.controls["quiet"].isChecked()
    assert window.controls["quiet_curriculum"].isChecked()
    assert not window.controls["quiet_saved"].isChecked()
    assert not window.controls["quiet_edge"].isChecked()  # QUIET's own choice
    asked: list[tuple[str, bool]] = []
    shown.quiet_word_wanted.connect(lambda which, on: asked.append((which, on)))
    window.controls["quiet_saved"].trigger()
    assert asked == [("saved", True)]
    wanted: list[tuple[bool, tuple[str, ...]]] = []
    shown.quiet_wanted.connect(lambda on, readings: wanted.append((on, readings)))
    window.controls["quiet"].trigger()
    assert wanted and wanted[0][0] is False


def test_a_blue_words_reading_is_blue_and_the_rest_gold(qapp: QApplication) -> None:
    from polyglotic_desktop.ui_next.caption_layout import _coloured_readings
    from polyglotic_desktop.ui_next.reading_lines import Placed

    blue = QTextCharFormat()
    blue.setForeground(QColor(QUIET_BLUE))
    from PySide6.QtGui import QTextLayout

    over = QTextLayout.FormatRange()
    over.start, over.length, over.format = 2, 2, blue
    readings = [Placed(0, 0, "zhè", 0), Placed(30, 0, "diàn", 2)]
    found = _coloured_readings(readings, [over])
    assert found[0] is None  # its row's: the gold
    assert found[1] is not None and found[1].name() == QColor(QUIET_BLUE).name()


def test_its_readings_are_grey_not_the_translations_gold(qapp: QApplication) -> None:
    """Polyglotic-hq 532 (the user, 2026-11-19: "the default pinyin/
    alternate reading font colour on quiet mode ... should be greyish"):
    pinyin over the quiet view's Chinese was drawn in its gold."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter
    from tests.ui_next.test_reading_lines import lines_of, made_up

    from polyglotic_desktop.ui_next.caption_layout import CaptionLayout

    lines = lines_of(finished("zh-1", clause("我们去看电影", "We go to the cinema")))
    line = lines.lines[0]
    style = replace(caption_style(QUIET), reading_lines=frozenset({"zh"}))
    engine = CaptionLayout(style, readings=made_up)
    laid = engine.laid(line, 900, 1.0)
    image = QImage(920, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor(QUIET.background))
    painter = QPainter(image)
    ink = look_ink(Ink(), QUIET)
    engine.paint(painter, line, laid, QPointF(10, 10), ink)
    painter.end()
    said = next(row for row in laid.rows if row.above)
    band = int(10 + said.top), int(10 + said.top + said.band)
    gold = grey = 0
    for y in range(*band):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if c.lightness() < 70:
                continue  # the panel
            if c.red() - c.blue() > 50:
                gold += 1
            elif abs(c.red() - c.blue()) < 12:
                grey += 1
    assert grey > 40 and gold == 0, (grey, gold)


# -- kept with the settings ------------------------------------------------------


def test_the_quiet_view_is_kept_with_the_settings_and_read_leniently() -> None:
    from polyglotic_desktop.main import caption_look, look_settings
    from polyglotic_desktop.ui.settings import AppSettings

    look = replace(
        CaptionLook(),
        quiet=True,
        quiet_words=frozenset({ChosenWords.LOAD, ChosenWords.SAVED}),
        curriculum_size=20,
    )
    stored = AppSettings().to_stored() | look_settings(look)
    stored["quiet_words"] = sorted(look.quiet_words)  # a list, as JSON keeps it
    stored["changed"] = ["quiet_view", "quiet_words", "curriculum_size"]  # as saved
    again = caption_look(AppSettings.from_stored(stored))
    assert (again.quiet, again.quiet_words, again.curriculum_size) == (
        True,
        {ChosenWords.LOAD, ChosenWords.SAVED},
        20,
    )
    newer = AppSettings.from_stored({"quiet_words": ["saved", "a newer kind"]})
    assert caption_look(newer).quiet_words == {ChosenWords.SAVED}
    assert AppSettings.from_stored({"curriculum_size": 0}).curriculum_size == 50


def test_the_load_is_kept_up_while_the_quiet_view_shows_its_words() -> None:
    from polyglotic_desktop.ui.settings import AppSettings

    assert AppSettings().load_rules_for("zh") is None  # the Lab's mode off
    chosen = AppSettings(quiet_words=("curriculum", "load"))
    assert chosen.load_rules_for("zh") is not None


def test_words_at_your_edge_are_on_for_a_new_learner_and_a_choice_is_kept() -> None:
    """496: ticked by default for a new learner; a file that holds the
    learner's choice keeps it."""
    from polyglotic_desktop.main import caption_look
    from polyglotic_desktop.ui.settings import AppSettings

    assert caption_look(AppSettings()).quiet_words == {
        ChosenWords.CURRICULUM,
        ChosenWords.EDGE,
    }
    kept = AppSettings.from_stored({"quiet_words": ["curriculum"]})
    assert caption_look(kept).quiet_words == {ChosenWords.CURRICULUM}


def test_untouched_blue_words_follow_the_default_and_chosen_ones_are_kept() -> None:
    """503 (496's note): which words the quiet view shows in blue follows
    the app's default until the learner changes it on this PC (decision
    0220's record) - another change to the look doesn't count as choosing
    them - and once chosen it's kept."""
    from tests.ui.fakes import MemorySettingsStore

    from polyglotic_desktop.main import caption_look, look_settings
    from polyglotic_desktop.ui.settings import FOLLOW_DEFAULT, AppSettings, Settings

    assert "quiet_words" in FOLLOW_DEFAULT
    store = MemorySettingsStore({})
    settings = Settings(store)
    look = caption_look(settings.value)
    settings.update(**look_settings(replace(look, quiet=True, curriculum_size=20)))
    assert "quiet_words" not in settings.value.changed
    # saved with an older default (0.1.8's previews: our curriculum alone)
    older = AppSettings.from_stored({**store.values, "quiet_words": ["curriculum"]})
    assert older.quiet_words == AppSettings().quiet_words
    assert older.quiet_view and older.curriculum_size == 20
    settings.update(quiet_words=("curriculum",))
    kept = AppSettings.from_stored(store.values)
    assert kept.quiet_words == ("curriculum",)


def test_a_word_capitalised_inside_its_sentence_is_not_lit_at_the_edge(
    qapp: QApplication,
) -> None:
    """496: "Agency" of the Central Intelligence Agency is part of a name;
    the same word in small letters, or a sentence's first, is at the edge."""
    from tests.lexicon.sample import english_sample
    from tests.ui.fakes import tools_for

    from polyglotic_desktop.core.learning.highlights import WordIntroductions
    from polyglotic_desktop.core.lexicon.english import EnglishDictionary
    from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
    from polyglotic_desktop.core.listening.captions import Language
    from polyglotic_desktop.ui_next.caption_marks import CaptionMarks, Panel
    from polyglotic_desktop.ui_next.views.captions import CaptionLines

    tools = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    tools.vocabulary.set_known_words(2000)  # awkward, the 2,500th: at the edge
    edge = frozenset({ChosenWords.EDGE})
    tools.vocabulary.set_chosen(edge, 50)
    view = CaptionLines((APP,), Language("zh"), keep=10)
    for n, said in enumerate(
        ("They keep Awkward running.", "Awkward. They keep awkward")
    ):
        view.apply(finished(f"c{n}", clause(said, "他们"), language=Language("en")))
    marks = CaptionMarks(tools)
    marks.set_look(
        WordLinks.OFF, WordIntroductions.OFF, Panel(quiet=True, quiet_words=edge)
    )
    lit = []
    for line in view.lines:
        text = line.rows[0].text
        lit.append([(s, text[s:e]) for s, e, _ in marks(line, 0)])
    assert lit == [[], [(0, "Awkward"), (19, "awkward")]]
