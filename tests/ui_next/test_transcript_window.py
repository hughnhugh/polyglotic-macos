"""W2, the transcript window, offscreen (`ui_next.transcript_window`) and
the transcripts kept per app (`ui_next.transcripts`): the strip, the
list, search, Back to live (no "Looks wrong?": 339), copy and save, the rail and
its popover, and following the caption windows."""

import csv
import io
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QToolButton, QWidget
from tests.ui_next.made_up import EN, OTHER_APP, ZH, finished_updates

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.recheck import RecheckOutcome, RecheckResult
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.languages import show_mandarin_in_traditional
from polyglotic_desktop.ui_next.panels import LanguagesPanel, TimingPanel
from polyglotic_desktop.ui_next.transcript_window import (
    FOLD_BELOW,
    LINES_LAID_OUT,
    TranscriptWindow,
)
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, Notice
from polyglotic_desktop.ui_next.views.captions import TRANSCRIPT_LINES
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.transcript import (
    RAIL_WIDTH,
    STORED_KEY,
    Transcript,
    TranscriptChoices,
)

DISCORD = SourceLabel("Discord", "#4dd0e1")
YOU = SourceLabel("You", "#7c9cff")


def made_up(count: int = 10, **options: object) -> Transcript:
    found = Transcript(APP, EN, mic=MIC, **options)  # type: ignore[arg-type]
    for update in finished_updates(count):
        found.apply(update)
    return found


@pytest.fixture
def window(qapp: QApplication) -> Iterator[TranscriptWindow]:
    shown = TranscriptWindow("Discord.exe", made_up(), DISCORD, TranscriptChoices())
    shown.animate = False
    shown.resize(900, 600)
    shown.show()
    qapp.processEvents()
    yield shown
    shown.close()


def click(widget: object, at: QPointF) -> None:
    for kind in (
        QMouseEvent.Type.MouseButtonPress,
        QMouseEvent.Type.MouseButtonRelease,
    ):
        event = QMouseEvent(
            kind,
            at,
            at,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget, event)  # type: ignore[arg-type]


# -- the window --------------------------------------------------------------------------


def test_its_title_and_foot(window: TranscriptWindow) -> None:
    assert window.windowTitle() == "Discord - Transcript"
    assert (
        window.foot.text()
        == "10 lines · following · gone when you quit, unless you save it"
    )
    assert window.list.shown > 0


def test_the_foot_says_the_transcript_lasts_this_session_only(
    window: TranscriptWindow,
) -> None:
    """polyglotic-hq 228 (224's finding 6): nothing in the app said a
    transcript is gone when Polyglotic quits. The foot says so whenever
    there are lines - not while searching, which is about the matches."""
    assert window.foot.text().endswith(" · gone when you quit, unless you save it")
    window.search.setText("fruit")
    assert "quit" not in window.foot.text()
    window.search.clear()
    assert "unless you save it" in window.foot.text()


def test_empty_it_says_where_captions_collect(qapp: QApplication) -> None:
    shown = TranscriptWindow("Discord.exe", made_up(0), DISCORD, TranscriptChoices())
    shown.show()
    qapp.processEvents()
    assert shown.foot.text() == ""  # the list says it, once
    assert shown.list.shown == 0
    shown.close()


def test_a_new_caption_shows_while_following(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    window.transcript.apply(finished_updates(1, start=10)[0])
    window.refresh()
    window.list.repaint()
    assert (
        window.foot.text()
        == "11 lines · following · gone when you quit, unless you save it"
    )
    assert window.list.placed[-1][0].key == window.transcript.lines[-1].key


def test_scrolled_back_new_lines_are_counted_until_back_to_live(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    window.list.scroll_by(400)
    for update in finished_updates(2, start=10):
        window.transcript.apply(update)
    window.refresh()
    assert window.pill.isVisible()
    assert window.pill.text() == "Back to live · 2 new"
    assert (
        window.foot.text()
        == "12 lines · scrolled back · gone when you quit, unless you save it"
    )
    window.pill.click()
    assert not window.pill.isVisible()
    assert window.transcript.scroll.following


def test_search_counts_matches_and_says_when_there_are_none(
    window: TranscriptWindow,
) -> None:
    window.search.setText("fruit")
    assert window.foot.text() == "2 matches · following"
    marks = window.list.marks(window.transcript.lines[-1], 1)
    assert marks  # the match is marked where it shows
    window.search.setText("nothing like this")
    assert window.foot.text() == "0 matches"
    window.search.clear()
    assert (
        window.foot.text()
        == "10 lines · following · gone when you quit, unless you save it"
    )


def test_esc_in_the_search_clears_it(window: TranscriptWindow) -> None:
    """polyglotic-hq 133: Esc in a transcript's search left "abc" there.
    It clears it - every line again - and only from the search box."""
    from PySide6.QtTest import QTest

    window.search.setFocus()
    QTest.keyClicks(window.search, "fruit")
    assert window.foot.text().startswith("2 matches")
    QTest.keyClick(window.search, Qt.Key.Key_Escape)
    assert window.search.text() == ""
    assert (
        window.foot.text()
        == "10 lines · following · gone when you quit, unless you save it"
    )
    window.search.setText("fruit")
    window.list.setFocus()
    QTest.keyClick(window.list, Qt.Key.Key_Escape)  # not in the search: kept
    assert window.search.text() == "fruit"


def test_text_size_is_its_own_and_kept_in_range(window: TranscriptWindow) -> None:
    changed = []
    window.changed.connect(lambda: changed.append(True))
    window.buttons["bigger"].click()
    assert window.choices.text_size == 1.1 == window.transcript.text_size
    window.step_text(-20)
    assert window.choices.text_size == 0.7
    assert len(changed) == 2


def test_the_strip_folds_copy_and_save_when_narrow(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    assert window.buttons["copy"].isVisible() and not window.buttons["more"].isVisible()
    window.resize(FOLD_BELOW - 40, 400)
    qapp.processEvents()
    assert not window.buttons["copy"].isVisible() and window.buttons["more"].isVisible()


def test_the_strip_asks_for_its_caption_window_s_choices(
    window: TranscriptWindow,
) -> None:
    asked: list[object] = []
    window.language_wanted.connect(asked.append)
    window.timing_wanted.connect(asked.append)
    window.language_actions["ja"].trigger()
    window.language_actions[""].trigger()
    window.timing_actions[CaptionMode.INSTANT].trigger()
    assert asked == ["ja", "", "live"]


def test_it_shows_its_caption_window_s_choices(window: TranscriptWindow) -> None:
    window.follow(DISCORD, "", True, CaptionMode.CALM, YOU)
    assert window.buttons["language"].text() == "Original only ▾"
    assert window.buttons["timing"].text() == "Calm ▾"
    assert window.tag.mic


def test_the_rail_s_panels_are_made_a_turn_at_a_time_once_it_shows(
    qapp: QApplication,
) -> None:
    made: list[str] = []

    def panel(text: str) -> QWidget:
        made.append(text)
        return QLabel(text)

    makers = [partial(panel, "one"), partial(panel, "two")]
    shown = TranscriptWindow(
        "k", made_up(), DISCORD, TranscriptChoices(), panels=makers
    )
    shown.show()
    assert made == []  # not while it opens
    qapp.sendPostedEvents()
    qapp.processEvents()
    assert made == ["one", "two"]
    assert [p.text() for p in shown.rail.panels] == ["one", "two"]  # type: ignore[attr-defined]
    shown.close()


def test_the_rail_opening_first_makes_its_panels_at_once(
    window: TranscriptWindow,
) -> None:
    window._makers = [partial(QLabel, "one"), partial(QLabel, "two")]
    window.toggle_rail()
    assert len(window.rail.panels) == 2 and window._makers == []


def test_it_takes_the_window_theme(window: TranscriptWindow) -> None:
    light = style.Theme({"BG": "#f5f6f7", "TEXT": "#172033"}, dark=False)
    window.set_theme(light)
    assert window.colors.background == "#f5f6f7" and window.colors.light
    assert window.list.colors is window.colors
    assert "#f5f6f7" in window.styleSheet()


def test_the_rail_slides_in_beside_the_list_and_is_remembered(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    width = window.list.width()
    window.buttons["settings"].click()
    qapp.processEvents()
    assert window.choices.rail_open
    assert window.rail.isVisible() and window.rail.width() == RAIL_WIDTH
    assert window.list.width() == width - RAIL_WIDTH
    assert window.buttons["settings"].isChecked()
    window.buttons["settings"].click()
    qapp.processEvents()
    assert not window.choices.rail_open and not window.rail.isVisible()


def test_below_700_px_the_rail_is_a_popover(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    window.choices = TranscriptChoices(rail_open=True)
    window.resize(640, 480)
    qapp.processEvents()
    assert not window.rail.isVisible()  # no room beside the list
    window.toggle_rail()
    qapp.processEvents()
    assert window.popover_open and window.rail.isVisible()
    assert window.rail.geometry().right() == window.width() - 1  # over the list
    assert window.rail.parent() is window  # never another parent
    click(window.list, QPointF(20, 20))  # a press elsewhere closes it
    qapp.processEvents()
    assert not window.popover_open and not window.rail.isVisible()
    window.toggle_rail()
    QApplication.sendEvent(
        window,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        ),
    )
    assert not window.popover_open
    window.resize(900, 600)  # room again: the rail it remembered
    qapp.processEvents()
    assert window.rail.isVisible()


def test_no_looks_wrong_on_a_hovered_line(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    """ "Looks wrong?" left the interface (polyglotic-hq 339)."""
    _, rect = window.list.placed[-1]
    hover = QMouseEvent(
        QMouseEvent.Type.MouseMove, rect.center(), rect.center(),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    window.list.mouseMoveEvent(hover)
    window.list.repaint()
    assert not hasattr(window, "looks_wrong") and not hasattr(window.list, "flagged")
    assert window.list.toolTip() == ""


def test_a_checked_line_says_so(window: TranscriptWindow) -> None:
    line = window.transcript.lines[-1]
    other = finished_updates(1, start=3)[0]
    window.transcript.use_checked(
        line.caption_id, other.clauses, other.language, other.languages_heard
    )
    heading = window.list._heading(window.transcript.lines[-1]).layout.text()
    assert heading.endswith("Mandarin · checked by the best model")


def test_copy_all_copies_what_shows(window: TranscriptWindow) -> None:
    window.search.setText("fruit")
    window.copy_all()
    copied = QGuiApplication.clipboard().text()
    assert copied.count("\n\n") == 1  # two lines, a paragraph each
    assert "English: The fruit" in copied


def test_copy_all_and_save_keep_the_whole_session(
    qapp: QApplication, tmp_path: Path
) -> None:
    """polyglotic-hq 133: a transcript kept its last 1,000 lines, silently -
    Copy all and Save lost the start of a long film. The list still holds
    the newest 1,000 (its budgets); Copy all and Save have every line, and
    the foot says so."""
    lines = TRANSCRIPT_LINES + 25
    shown = TranscriptWindow(
        "Discord.exe", made_up(lines), DISCORD, TranscriptChoices()
    )
    shown.resize(900, 600)
    shown.show()
    qapp.processEvents()
    assert len(shown.transcript.lines) == TRANSCRIPT_LINES
    assert shown.text().count("\n\n") == lines - 1  # a paragraph a line
    shown.save_to(tmp_path / "t.csv")
    rows = (tmp_path / "t.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(rows) == 1 + lines
    assert shown.foot.text() == (
        "the newest 1,000 of 1,025 lines · all in Copy all and Save · following"
        " · gone when you quit, unless you save it"
    )
    shown.search.setText("fruit")  # searching: the list's lines only, said
    assert shown.foot.text().endswith("in the newest 1,000 lines · following")
    shown.close()


def test_copied_and_saved_times_are_the_ones_shown(
    window: TranscriptWindow, tmp_path: Path
) -> None:
    """Copy all, Save as text and the CSV give each line's time as the list
    shows it - this PC's time, not UTC (polyglotic-hq 133: they were 11
    hours off in Sydney). On a PC set to UTC this can't tell the two apart."""
    line = window.transcript.lines[0]
    shown = window.list._heading(line).layout.text()[:8]
    assert shown == f"{line.started_at.astimezone():%H:%M:%S}"
    assert window.text().startswith(f"[{shown}]")
    window.save_to(tmp_path / "t.txt")
    assert (tmp_path / "t.txt").read_text(encoding="utf-8").startswith(f"[{shown}]")
    window.save_to(tmp_path / "t.csv")
    assert shown in (tmp_path / "t.csv").read_text(encoding="utf-8-sig")


def test_saved_as_text_srt_or_csv(window: TranscriptWindow, tmp_path: Path) -> None:
    for name in ("t.txt", "t.srt", "t.csv"):
        window.save_to(tmp_path / name)
    assert (tmp_path / "t.txt").read_text(encoding="utf-8").count("English:") == 10
    assert (tmp_path / "t.srt").read_text(encoding="utf-8").startswith("1\n")
    assert (tmp_path / "t.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_a_second_language_line_is_saved_and_copied_under_its_language(
    qapp: QApplication, tmp_path: Path
) -> None:
    """English heard in a window into English, Chinese its second language:
    the server keeps the Chinese line under English, and Save and Copy put
    it in the English column, the Chinese one empty (polyglotic-hq 432)."""
    transcript = Transcript(APP, EN, second=ZH, mic=MIC)
    said = CaptionUpdate(
        CaptionId("c1"),
        APP,
        CaptionKind.FINISHED,
        clauses=(Clause("See you tomorrow.", translations={EN: "明天见。"}),),
        language=EN,
        languages_heard=(EN,),
    )
    transcript.apply(said)
    shown = TranscriptWindow("Discord.exe", transcript, DISCORD, TranscriptChoices())
    shown.show()
    qapp.processEvents()
    try:
        shown.save_to(tmp_path / "t.csv")
        text = (tmp_path / "t.csv").read_text(encoding="utf-8-sig")
        [row] = list(csv.DictReader(io.StringIO(text)))
        assert (row["en"], row["zh"]) == ("", "明天见。")
        assert "Chinese (Simplified): 明天见。" in shown.text()
        assert "English:" not in shown.text()
        # "Show Mandarin in: Traditional": its lines named by it (433)
        show_mandarin_in_traditional(True)
        try:
            assert "Chinese (Traditional): 明天见。" in shown.text()
            shown.save_to(tmp_path / "t.txt")
            saved = (tmp_path / "t.txt").read_text(encoding="utf-8-sig")
            assert "Chinese (Traditional):" in saved and "Simplified" not in saved
        finally:
            show_mandarin_in_traditional(False)
        shown.save_to(tmp_path / "t.srt")
        srt = (tmp_path / "t.srt").read_text(encoding="utf-8")
        assert "See you tomorrow.\n明天见。" in srt
        shown._copy_line(shown.transcript.lines[0].key, "translation")
        assert QGuiApplication.clipboard().text() == "明天见。"
    finally:
        shown.close()


def test_a_saved_csv_names_the_app_on_every_row(
    window: TranscriptWindow, tmp_path: Path
) -> None:
    """The CSV's "source" column was always empty: two apps' transcripts,
    saved side by side, were told apart only by their file names
    (polyglotic-hq 184's and 203's QA)."""
    window.save_to(tmp_path / "t.csv")
    text = (tmp_path / "t.csv").read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 10
    assert {row["source"] for row in rows} == {"Discord"}


def test_original_only_copies_no_translation(window: TranscriptWindow) -> None:
    window.transcript.set_language(None, None)
    assert "English:" not in window.text()


def test_its_controls_have_names_a_screen_reader_says(
    window: TranscriptWindow,
) -> None:
    assert window.search.accessibleName() == "Search the transcript"
    clear = window.search.findChild(QToolButton)
    assert clear is not None and clear.accessibleName() == "Clear the search"
    assert clear.focusPolicy() & Qt.FocusPolicy.TabFocus
    assert window.buttons["more"].accessibleName().startswith("More")
    assert window.buttons["settings"].accessibleName() == "Settings"


def test_the_search_placeholder_reads_on_its_field(window: TranscriptWindow) -> None:
    placeholder = window.search.palette().color(QPalette.ColorRole.PlaceholderText)
    assert placeholder.name() == window.colors.dim


def test_the_session_s_notice_shows_over_the_list(window: TranscriptWindow) -> None:
    window.set_notice(Notice.PAUSED)
    assert window.notice.isVisible() and window.notice.text() == "Paused"
    window.set_notice(None)
    assert not window.notice.isVisible()


# -- the transcripts, one per app ----------------------------------------------------------


class Store:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def both(qapp: QApplication) -> Iterator[tuple[CaptionWindows, Transcripts, Store]]:
    store = Store()
    areas = [Rect(0, 0, 1920, 1040)]
    windows = CaptionWindows(store, MIC, lambda: areas)
    windows.set_labels({APP: DISCORD, OTHER_APP: SourceLabel("Zoom", "#a5d66f")}, "You")
    transcripts = Transcripts(windows, store, areas=lambda: areas)
    windows.set_captioned([("Discord.exe", APP), ("Zoom.exe", OTHER_APP)])
    yield windows, transcripts, store
    transcripts.close()
    windows.close()


def test_a_transcript_per_app_collects_with_its_window_closed(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    _, transcripts, _ = both
    for update in finished_updates(3) + finished_updates(2, OTHER_APP):
        transcripts.apply(update)
    assert len(transcripts.transcripts["Discord.exe"].lines) == 3
    assert len(transcripts.transcripts["Zoom.exe"].lines) == 2
    assert transcripts.shown == {}
    assert [a.text() for a in transcripts.menu.actions()] == ["Discord", "Zoom"]


def test_it_opens_beside_its_caption_window(
    both: tuple[CaptionWindows, Transcripts, Store], qapp: QApplication
) -> None:
    windows, transcripts, _ = both
    windows.transcript_wanted.connect(transcripts.show)
    windows.windows["Discord.exe"].controls["transcript"].trigger()
    shown = transcripts.shown["Discord.exe"]
    assert shown.isVisible()
    # joined, as two windows start (554): beside the window it's a column of
    assert windows.joined_window is not None
    caption = windows.joined_window.geometry()
    assert shown.geometry().size().toTuple() == (720, 520)
    assert not shown.geometry().intersects(caption)


def test_on_a_small_screen_a_second_transcript_doesnt_hide_the_first(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 184: at 1280 x 720 (a laptop at 150 %) there's no room
    beside a caption window, and each transcript opened centred - exactly
    over the one before."""
    store = Store()
    areas = [Rect(0, 0, 1280, 672)]
    windows = CaptionWindows(store, MIC, lambda: areas)
    windows.set_labels({APP: DISCORD, OTHER_APP: SourceLabel("Zoom", "#a5d66f")}, "You")
    transcripts = Transcripts(windows, store, areas=lambda: areas)
    windows.set_captioned([("Discord.exe", APP), ("Zoom.exe", OTHER_APP)])
    try:
        transcripts.show("Discord.exe")
        transcripts.show("Zoom.exe")
        first = transcripts.shown["Discord.exe"].geometry()
        second = transcripts.shown["Zoom.exe"].geometry()
        assert second.topLeft() != first.topLeft()
        assert QRect(0, 0, 1280, 672).contains(second)
    finally:
        transcripts.close()
        windows.close()


def test_joined_it_opens_beside_the_joined_window(
    both: tuple[CaptionWindows, Transcripts, Store], qapp: QApplication
) -> None:
    windows, transcripts, _ = both
    windows.join()
    joined = windows.joined_window
    assert joined is not None
    qapp.processEvents()
    transcripts.show("Zoom.exe")
    shown = transcripts.shown["Zoom.exe"]
    assert not shown.geometry().intersects(joined.geometry())


class Views:
    """The session's panels' views, as `main.Panels` holds them."""

    def __init__(self) -> None:
        self.languages = LanguagesView(SessionLanguages())
        self.timing = TimingView(Timing(CaptionMode.WHOLE, 2.0))
        self.look = LookView(CaptionLook())


def rail_of(transcripts: Transcripts, key: str) -> LanguagesPanel:
    """App `key`'s transcript opened, with its rail: its Languages panel."""
    transcripts.show(key)
    shown = transcripts.shown[key]
    shown.animate = False
    shown.toggle_rail()
    panel = shown.rail.panels[0]
    assert isinstance(panel, LanguagesPanel)
    return panel


def test_its_language_and_my_speech_are_its_caption_window_s(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    windows, transcripts, _ = both
    transcripts.panels = Views()
    rail = rail_of(transcripts, "Discord.exe")
    shown = transcripts.shown["Discord.exe"]
    shown.language_wanted.emit("ja")  # the strip's chip
    assert windows.windows["Discord.exe"].choices.translate_into == "ja"
    assert str(transcripts.transcripts["Discord.exe"].target) == "ja"
    assert shown.buttons["language"].text() == "JA ▾"
    assert rail.this_window is not None
    assert rail.this_window.value.translate_into == "ja"
    assert rail.show_mic is not None
    rail.show_mic.click()  # the rail's "Show my speech here"
    assert windows.windows["Discord.exe"].choices.show_mic
    assert MIC in transcripts.transcripts["Discord.exe"].captions.sources
    windows.windows["Discord.exe"].set_language("")  # from the caption window
    assert transcripts.transcripts["Discord.exe"].target is None
    assert rail.this_window.value.translate_into == ""


def test_the_rail_s_panels_are_the_session_s(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    _, transcripts, _ = both
    views = Views()
    transcripts.panels = views
    one, other = rail_of(transcripts, "Discord.exe"), rail_of(transcripts, "Zoom.exe")
    timing = transcripts.shown["Zoom.exe"].rail.panels[1]
    assert isinstance(timing, TimingPanel)
    views.languages.set_spoken("zh")  # one change: every rail shows it
    assert one.spoken.value() == other.spoken.value() == "zh"
    assert one.this_window is not other.this_window  # each its own window's


def test_an_app_no_longer_captioned_keeps_its_lines_for_the_session(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    windows, transcripts, _ = both
    for update in finished_updates(3):
        transcripts.apply(update)
    transcripts.show("Discord.exe")
    windows.set_captioned([("Zoom.exe", OTHER_APP)])
    assert "Discord.exe" not in transcripts.shown
    transcripts.apply(finished_updates(1, start=5)[0])  # not captioned: not kept
    windows.set_captioned([("Zoom.exe", OTHER_APP), ("Discord.exe", APP)])
    assert len(transcripts.transcripts["Discord.exe"].lines) == 3


def test_the_best_model_s_version_reaches_its_transcript(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    _, transcripts, _ = both
    for update in finished_updates(2):
        transcripts.apply(update)
    line = transcripts.transcripts["Discord.exe"].lines[-1]
    other = finished_updates(1, start=3)[0]
    transcripts.use_checked(
        line.caption_id,
        RecheckResult(
            line.caption_id,
            RecheckOutcome.CHECKED,
            other.clauses,
            other.language,
            other.languages_heard,
        ),
    )
    assert transcripts.transcripts["Discord.exe"].lines[-1].checked


def test_its_text_size_and_rail_are_remembered_per_app(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    windows, transcripts, store = both
    transcripts.show("Zoom.exe")
    shown = transcripts.shown["Zoom.exe"]
    shown.animate = False
    shown.step_text(2)
    shown.toggle_rail()
    transcripts.save_now()
    saved = store.values[STORED_KEY]
    assert saved == {"Zoom.exe": {"text_size": 1.2, "rail_open": True}}
    again = Transcripts(windows, store)
    assert again.transcripts["Zoom.exe"].text_size == 1.2
    again.close()


def test_a_save_when_the_file_cant_be_read_keeps_todays_settings(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    """Nothing read - the file gone, or locked for a moment - isn't "every
    other key removed": today's settings, as last read, aren't lost (the
    rule `Settings.update` follows)."""
    _, transcripts, store = both
    store.values["targets"] = ["en"]
    transcripts.show("Zoom.exe")
    shown = transcripts.shown["Zoom.exe"]
    shown.animate = False
    shown.step_text(2)
    transcripts.save_now()
    store.values = {}  # can't be read at this moment
    shown.toggle_rail()
    transcripts.save_now()
    assert store.values["targets"] == ["en"]  # as last read
    saved = store.values[STORED_KEY]
    assert saved == {"Zoom.exe": {"text_size": 1.2, "rail_open": True}}


def test_pause_shows_on_open_transcripts(
    both: tuple[CaptionWindows, Transcripts, Store],
) -> None:
    _, transcripts, _ = both
    transcripts.show("Discord.exe")
    transcripts.set_connection(Notice.RECONNECTING)
    assert transcripts.shown["Discord.exe"].notice.text() == "Reconnecting"
    transcripts.set_paused(True)
    assert transcripts.shown["Discord.exe"].notice.text() == "Paused"


def test_it_keeps_layouts_for_a_few_screens_not_every_line(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    """An evening's captions, each shown as it comes while following: the
    transcript lists its 1,000 and keeps the layouts - what was said, and
    each heading - of only the last `LINES_LAID_OUT` shown (polyglotic-hq
    239: kept for 2,500 lines, they grew the app all evening). Scrolled
    back to the oldest, those are laid out again and drawn."""
    for update in finished_updates(TRANSCRIPT_LINES + 200, start=10):
        window.transcript.apply(update)
        window.refresh()
        window.list.repaint()
    assert len(window.transcript.lines) == TRANSCRIPT_LINES
    assert window.list.engine.held <= LINES_LAID_OUT
    assert len(window.list._headings) <= LINES_LAID_OUT
    window.list.go_to_oldest()
    window.list.repaint()
    assert window.list.placed[0][0].key == window.transcript.lines[0].key
    assert window.list.engine.held <= LINES_LAID_OUT


def test_its_notice_and_back_to_live_are_measured_again_at_a_new_text_size(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    """A text size change while it's open (Windows', or the app's own:
    polyglotic-hq 292): its notice and Back to live are restyled at the new
    size - and measured again, or the larger text was cut at their old
    width."""
    window.set_notice(Notice.PAUSED)
    window.list.scroll_by(400)
    for update in finished_updates(2, start=10):
        window.transcript.apply(update)
    window.refresh()
    try:
        style.use_text_scale(2.0)
        window.restyle()
        qapp.processEvents()
        for shown in (window.notice, window.pill):
            assert shown.isVisible()
            assert shown.width() >= shown.sizeHint().width(), shown.objectName()
    finally:
        style.use_text_scale(1.0)
