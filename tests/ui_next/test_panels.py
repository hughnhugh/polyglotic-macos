"""The three shared panels as widgets, offscreen (project 109's section 4):
one widget class bound to one view, in any container; a change made in
one shows in every other within the click budget, and reaches the
caption windows."""

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from tests.budget_judge import sampled, within
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.playout import Ahead
from polyglotic_desktop.core.listening.sources import MIC, SourceId
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui_next.caption_window import timing_tip
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import (
    BehaviourPanel,
    LanguagesPanel,
    LookPanel,
    ResetCard,
    TimingPanel,
    WordLinksPanel,
)
from polyglotic_desktop.ui_next.views.caption_window import ORIGINAL_ONLY, CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
    WindowLanguage,
    WindowLanguageView,
)
from polyglotic_desktop.ui_next.views.placement import Rect


def test_a_change_in_one_panel_shows_in_the_other(qapp: QApplication) -> None:
    view = LanguagesView(SessionLanguages(in_use=("en",)))
    home, rail = LanguagesPanel(view), LanguagesPanel(view)
    home.spoken.choose("yue")
    assert rail.spoken.value() == "yue" and view.value.spoken == "yue"
    home.second["en"].setCurrentIndex(home.second["en"].findData("ja"))
    assert rail.second["en"].currentData() == "ja"
    rail.hints.setText("Caleb, HSK")
    rail.hints.editingFinished.emit()
    assert home.hints.text() == "Caleb, HSK"
    home.deleteLater()
    rail.deleteLater()


def test_second_language_rows_follow_the_languages_in_use(qapp: QApplication) -> None:
    view = LanguagesView(SessionLanguages())
    panel = LanguagesPanel(view)
    assert panel.second == {}
    view.follow(SessionLanguages(in_use=("en", "ja")))
    assert list(panel.second) == ["en", "ja"]
    kept = panel.second["en"]
    view.follow(SessionLanguages(in_use=("en", "ja"), translate_live=False))
    assert panel.second["en"] is kept  # not rebuilt for another change
    assert panel.translate_live is not None
    assert not panel.translate_live.isChecked()


def test_second_language_boxes_are_reached_under_spoken_language(
    qapp: QApplication,
) -> None:
    """The boxes are made after the panel; Tab still reaches them where
    they are, before Translate live captions - not last (131)."""
    from tests.ui_next.made_up import tab_stops

    view = LanguagesView(SessionLanguages(in_use=("en", "ja")))
    panel = LanguagesPanel(view)
    panel.show()
    qapp.processEvents()
    stops = tab_stops(panel)
    spoken = stops.index(panel.spoken.chip)
    # then Show Mandarin in's two choices (375)
    assert stops[spoken + 1 : spoken + 3] == panel.mandarin_script.buttons
    assert stops[spoken + 3 : spoken + 5] == [panel.second["en"], panel.second["ja"]]
    assert stops[spoken + 5] is panel.translate_live
    panel.close()


def test_this_window_only_in_a_transcripts_rail(qapp: QApplication) -> None:
    session = LanguagesView(SessionLanguages())
    assert LanguagesPanel(session).translate_into is None  # Home: the line instead
    own = WindowLanguageView(WindowLanguage("Discord", "en"))
    panel = LanguagesPanel(session, own)
    assert panel.translate_into is not None and panel.show_mic is not None
    # the window's two rows under their heading; the session's rows under
    # theirs, so they don't read as this window's (131)
    sections = [
        s.text() for s in panel.findChildren(QLabel) if s.objectName() == "SectionLabel"
    ]
    assert sections == ["THIS WINDOW - DISCORD", "EVERY WINDOW"]
    assert not [
        s
        for s in LanguagesPanel(session).findChildren(QLabel)
        if s.objectName() == "SectionLabel"
    ]
    panel.translate_into.setCurrentIndex(panel.translate_into.findData(ORIGINAL_ONLY))
    panel.show_mic.click()
    assert own.value == WindowLanguage("Discord", ORIGINAL_ONLY, True)
    own.follow(WindowLanguage("Discord", "ja", False))
    assert panel.translate_into.currentData() == "ja"
    assert not panel.show_mic.isChecked()


def test_a_panel_that_goes_is_no_longer_told(qapp: QApplication) -> None:
    view = TimingView(Timing())
    panel = TimingPanel(view)
    assert len(view._listeners) == 1
    panel.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert view._listeners == []
    view.set_mode(CaptionMode.INSTANT)  # nothing left to refresh


def test_the_card_stack_has_a_switch_in_the_paced_modes(qapp: QApplication) -> None:
    view = TimingView(Timing(CaptionMode.STEADY))
    panel = TimingPanel(view)
    panel.show()
    assert panel.cards_row.isVisible() and panel.cards_row.switch.isChecked()
    assert not panel.zones_row.isVisible()  # the cards take the two zones' place
    panel.cards_row.switch.setChecked(False)
    assert not view.value.cards
    assert panel.zones_row.isVisible()  # off: the two zones, and their switch
    panel.mode.choose(CaptionMode.INSTANT)
    assert not panel.cards_row.isVisible()
    panel.close()


def test_the_interval_only_with_live_updates(qapp: QApplication) -> None:
    view = TimingView(Timing(CaptionMode.WHOLE, 10.0))
    panel = TimingPanel(view)
    panel.show()
    assert not panel.live.isVisible()
    panel.mode.choose(CaptionMode.INSTANT)
    assert panel.live.isVisible() and view.value.mode is CaptionMode.INSTANT
    assert panel.interval.currentData() == 10.0  # set by hand: shown as itself
    panel.interval.setCurrentIndex(0)
    assert view.value.live_interval == 0.5
    panel.close()


def test_each_modes_sentence_promises_what_was_measured(qapp: QApplication) -> None:
    """polyglotic-hq 145 measured the real models (2026-11-07, p50): Quick
    preview's line at 1.9 s, and every finished caption 0.4-0.6 s after
    the speech ends. Project 176: the sentences say so. Steady's first
    words came at 4.5-5.5 s; since 277 a dim line comes at the longest
    wait for text if the speaker talks on, and Steady's sentence says
    that wait."""
    view = TimingView(Timing(CaptionMode.WHOLE))
    panel = TimingPanel(view)
    steady = panel.sentence.text()
    assert "half a second after it ends" in steady
    assert "A dim line comes first if the speaker talks on for 3 seconds" in steady
    view.set_max_wait(5.0)
    assert "talks on for 5 seconds" in panel.sentence.text()
    panel.mode.choose(CaptionMode.STEADY)
    assert panel.sentence.text() == timing_tip(CaptionMode.STEADY)


def test_the_longest_wait_for_text_in_every_mode(qapp: QApplication) -> None:
    """polyglotic-hq 277: one choice for every timing, 2 to 6 s; one set
    by hand shows as itself. A drop-down, so a change is one click: the
    settings are saved and sent once."""
    handed: list[Timing] = []
    view = TimingView(Timing(CaptionMode.WHOLE, 1.5, 3.5), handed.append)
    panel = TimingPanel(view)
    panel.show()
    for mode in OFFERED_MODES:
        panel.mode.choose(mode)
        assert panel.wait.isVisible()
    assert panel.wait.currentData() == 3.5  # set by hand: shown as itself
    assert [panel.wait.itemData(i) for i in range(panel.wait.count())] == [
        2.0,
        2.5,
        3.0,
        3.5,
        4.0,
        5.0,
        6.0,
    ]
    handed.clear()  # the modes chosen above
    panel.wait.setCurrentIndex(0)
    assert view.value.max_wait == 2.0 and handed == [view.value]
    view.follow(Timing(CaptionMode.INSTANT, 1.5, 6.0))  # changed elsewhere
    assert panel.wait.currentData() == 6.0 and len(handed) == 1  # not handed back
    panel.close()


def _gone(*panels: QWidget) -> None:
    for panel in panels:
        panel.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_each_timing_shows_only_its_own_settings(qapp: QApplication) -> None:
    """polyglotic-hq 295 (the user, 2026-11-11: "caption timing setting
    should give their respective options"): under the choice, the chosen
    timing's own settings - Whole captions the longest wait; Instant how
    often, translating live and the longest wait; Steady its newest word
    and the words ahead; Calm the words ahead - and nothing else (526:
    Quick preview, retired, is not offered)."""
    speech = LanguagesView(SessionLanguages(in_use=("en",)))
    panel = TimingPanel(TimingView(Timing()), languages=speech)
    panel.show()
    rows = {
        "newest": panel.newest_row,
        "ahead": panel.ahead_row,
        "live": panel.live,
        "translate": panel.translate_row,
        "wait": panel.wait_row,
    }
    own = {
        CaptionMode.INSTANT: {"live", "translate", "wait"},
        CaptionMode.WHOLE: {"wait"},
        CaptionMode.STEADY: {"newest", "ahead", "wait"},
        CaptionMode.CALM: {"ahead", "wait"},
    }
    assert tuple(own) == OFFERED_MODES
    try:
        for mode, shown in own.items():
            panel.mode.choose(mode)
            visible = {name for name, row in rows.items() if row and row.isVisible()}
            assert visible == shown, mode
        panel.mode.choose(CaptionMode.STEADY)
        panel.newest_row.switch.click()
        panel.ahead.choose(Ahead.WAITING)
        assert (panel.view.value.newest_word, panel.view.value.words_ahead) == (
            True,
            Ahead.WAITING,
        )
        # each says what it trades; the one longest wait, for every timing
        assert "show text sooner" in panel.live.detail.text()
        assert "the same in every timing" in panel.wait_row.detail.text()
        # Live updates every offers 0.5 to 6 s and says nothing of 20 (before
        # 295: "from 0.5 to 20 seconds", with 6 s the most offered)
        assert "20" not in panel.live.detail.text()
    finally:
        _gone(panel)


def test_live_updates_say_when_the_longest_wait_comes_first(
    qapp: QApplication,
) -> None:
    """Live updates every 6 s with the longest wait at 3 s updates every 3 s
    (core.listening.timing: the longest wait comes first): the panel says
    so under the interval, and says nothing when the interval is followed
    (polyglotic-hq 295)."""
    view = TimingView(Timing(CaptionMode.INSTANT, 6.0, 3.0))
    panel = TimingPanel(view)
    panel.show()
    try:
        assert panel.live_note.isVisible()
        assert panel.live_note.text().startswith("Text still updates every 3s")
        view.set_max_wait(2.0)
        assert "every 2s" in panel.live_note.text()
        view.set_max_wait(6.0)
        assert not panel.live_note.isVisible()
        view.set_live_interval(1.5)
        view.set_max_wait(2.0)
        assert not panel.live_note.isVisible()
        view.set_mode(CaptionMode.WHOLE)
        assert not panel.live.isVisible()
    finally:
        _gone(panel)


def test_reset_from_its_card(qapp: QApplication) -> None:
    view = LookView(CaptionLook(opacity=0.2))
    panel, reset = LookPanel(view), ResetCard(view)
    reset.reset.click()
    assert view.value.opacity == CaptionLook().opacity
    assert panel.background.value() == round(CaptionLook().opacity * 100)
    assert "Reset positions" in reset.reset.toolTip()  # the places: Home's
    panel.deleteLater()
    reset.deleteLater()


def test_a_change_reaches_every_panel_and_window_within_a_click(
    qapp: QApplication,
) -> None:
    windows = CaptionWindows(None, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    sources = [SourceId(f"app-{n}") for n in (1, 2, 3)]
    windows.set_captioned([(f"app{n}", s) for n, s in enumerate(sources)])
    for source in sources:
        for update in finished_updates(150, source=source):
            windows.apply(update)
    view = LookView(windows.look, on_change=windows.set_look)
    home, rail = WordLinksPanel(view), WordLinksPanel(view)
    home.show()
    rail.show()
    qapp.processEvents()
    links = [WordLinks.OFF, WordLinks.HOVER]

    def change() -> None:
        home.word_links.choose(links[view.value.word_links is WordLinks.OFF])

    # Warmed up (the lab records the first, cold one), and the garbage
    # collector held off: late in the whole suite this process holds
    # thousands of Qt objects, and a full collection landing in one run took
    # 91-99 ms in CI (2026-11-07; the change itself: 5-20 ms) - the test
    # process's, not the click's (tests/budget_judge.py).
    within(budgets.CLICK, lambda: sampled(qapp, [change] * 7))
    assert rail.word_links.value() == view.value.word_links
    assert all(w.look == view.value for w in windows.windows.values())
    home.close()
    rail.close()
    windows.close()


def test_every_choice_is_a_tab_stop_one_at_a_time(qapp: QApplication) -> None:
    from PySide6.QtCore import Qt

    from polyglotic_desktop.ui_next.controls import Segmented

    choices = Segmented([("a", "A"), ("b", "B"), ("c", "C")], "a")
    choices.show()
    qapp.processEvents()
    tab = Qt.FocusPolicy.TabFocus
    assert all(b.focusPolicy() & tab == tab for b in choices.buttons)
    choices.buttons[2].click()
    choices.buttons[2].click()  # the chosen one stays chosen
    assert choices.value() == "c"
    assert [b.isChecked() for b in choices.buttons] == [False, False, True]
    choices.close()


def test_no_window_flashes_while_a_panel_is_built(qapp: QApplication) -> None:
    """A label shown before it has a parent is a top-level window for a
    moment: on Windows' platform a flash on the screen, which may take the
    focus (116 saw it, 2026-11-07). Building a panel shows no window."""
    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QWidget

    from polyglotic_desktop.ui_next.controls import Row, SwitchRow

    class Windows(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.shown: list[str] = []

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if (
                event.type() == QEvent.Type.Show
                and isinstance(watched, QWidget)
                and watched.isWindow()
            ):
                self.shown.append(type(watched).__name__)
            return False

    seen = Windows()
    qapp.installEventFilter(seen)
    try:
        built = [
            LanguagesPanel(LanguagesView(SessionLanguages(in_use=("en",)))),
            LanguagesPanel(
                LanguagesView(SessionLanguages()),
                WindowLanguageView(WindowLanguage("Discord")),
            ),
            TimingPanel(TimingView(Timing(CaptionMode.INSTANT))),
            TimingPanel(
                TimingView(Timing(CaptionMode.INSTANT)),
                languages=LanguagesView(SessionLanguages()),
            ),
            LanguagesPanel(LanguagesView(SessionLanguages()), speech=True),
            LookPanel(LookView(CaptionLook())),
            LookPanel(LookView(CaptionLook()), notes=True),
            WordLinksPanel(LookView(CaptionLook()), notes=True, learning=True),
            BehaviourPanel(LookView(CaptionLook()), notes=True),
            ResetCard(LookView(CaptionLook())),
            Row("A setting", "What it does", QWidget()),
            SwitchRow("On or off", "What it does", "a.switch"),
        ]
        qapp.processEvents()
    finally:
        qapp.removeEventFilter(seen)
    assert seen.shown == []
    for each in built:
        each.deleteLater()


def test_arrows_is_offered_again_and_a_saved_arrows_shows_as_arrows(
    qapp: QApplication,
) -> None:
    """Arrows draws its curves again (249, F7; 151 had retired it while a
    window underlined it as Colours)."""
    view = LookView(CaptionLook(word_links=WordLinks.ARROWS), on_change=lambda _: None)
    panel = WordLinksPanel(view)
    assert [b.text() for b in panel.word_links.buttons] == [
        "Off",
        "On hover",
        "Underline",  # 248's name for 249's Colours
        "Arrows",
    ]
    assert panel.word_links.value() is WordLinks.ARROWS
    assert panel.link_detail.isEnabled()
    view.set_word_links(WordLinks.COLOURS)
    assert panel.word_links.value() is WordLinks.COLOURS


def test_one_sentence_at_most_under_a_control_in_a_rail_the_rest_on_hover(
    qapp: QApplication,
) -> None:
    """151's P2 (176): the Look window had nine paragraphs under its
    controls. In a transcript's narrow rail every line is said on hover
    and to a screen reader; Common words only kept its line until it
    moved to Learning as word introductions (polyglotic-hq 262)."""
    from polyglotic_desktop.ui_next.controls import Row, SwitchRow

    view = LookView(CaptionLook())
    look = LookPanel(view)
    panels = [look, WordLinksPanel(view), BehaviourPanel(view)]
    rows: list[Row | SwitchRow] = []
    for panel in panels:
        panel.show()
        rows += [*panel.findChildren(Row), *panel.findChildren(SwitchRow)]
    shown = [row.detail.text() for row in rows if row.detail.isVisible()]
    assert shown == []
    assert all(row.toolTip() for row in rows)
    assert look.background.accessibleDescription().startswith("0 % is no box")
    assert look.source.accessibleDescription().startswith("The app's name")
    for panel in panels:
        panel.close()


def test_in_settings_every_setting_has_its_line_under_its_name(
    qapp: QApplication,
) -> None:
    """248's section 2.1 and 2.4 (F18): in Settings > Captions each
    setting's line is under its name - tooltips need a mouse and a wait -
    and its control says it on hover too."""
    from polyglotic_desktop.ui_next.controls import Row, SwitchRow

    view = LookView(CaptionLook())
    panels = [
        LookPanel(view, notes=True),
        WordLinksPanel(view, notes=True),
        BehaviourPanel(view, notes=True),
    ]
    for panel in panels:
        panel.show()
        rows: list[Row | SwitchRow] = [
            *panel.findChildren(Row),
            *panel.findChildren(SwitchRow),
        ]
        assert rows
        for row in rows:
            assert row.detail.isVisible() and row.detail.text(), row
            assert row.toolTip() == row.detail.text()
        panel.close()


def test_live_updates_every_says_the_first_waits_for_a_second(
    qapp: QApplication,
) -> None:
    """At 0.5 or 0.75 s the first live update still comes at 1.0 s of
    speech (LIVE_MIN_AUDIO_SEC; polyglotic-hq 270's triage, 284): the
    control says so rather than promise 0.5 s."""
    from polyglotic_desktop.ui_next.panels import TimingPanel
    from polyglotic_desktop.ui_next.views.panels import Timing, TimingView

    panel = TimingPanel(TimingView(Timing()))
    try:
        assert "first update waits for a second of speech" in panel.live.toolTip()
        assert panel.interval.accessibleDescription() == panel.live.toolTip()
    finally:
        panel.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_how_long_text_may_still_change_is_chosen_beside_the_timing(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 309 (the user: "make this a configurable setting.
    After 0s - 3seconds"): one choice for every timing, 3s as it was -
    Steady too, whose dim line and joined captions it settles. Its line
    says what a shorter time costs in words, with no figure: 309's were
    measured on read speech only, and no accuracy figure is said that
    polyglotic-hq hasn't cleared (329's QA; 330)."""
    handed: list[Timing] = []
    view = TimingView(Timing(), handed.append)
    panel = TimingPanel(view)
    panel.show()
    for mode in OFFERED_MODES:
        panel.mode.choose(mode)
        assert panel.settle.isVisible()
    assert panel.settle.currentData() == 3.0
    items = range(panel.settle.count())
    assert [panel.settle.itemData(i) for i in items] == [0.0, 1.0, 2.0, 3.0]
    assert panel.settle.itemText(0) == "0s"
    said = " ".join(found.text() for found in panel.settle_row.findChildren(QLabel))
    assert "fewer words change while you read" in said
    assert "more mistakes stay as first heard" in said
    assert not any(char.isdigit() for char in said), said
    handed.clear()
    panel.settle.setCurrentIndex(1)
    assert view.value.settle_after == 1.0 and handed == [view.value]
    view.follow(Timing(CaptionMode.INSTANT, 1.5, 3.0, 0.5))  # set by hand, elsewhere
    assert panel.settle.currentData() == 0.5 and len(handed) == 1
    panel.close()
    _gone(panel)
