"""Settings is one page with six sections at its top - Look · Timing ·
Speech · Dictation · App · Lab - each holding what a learner comes to
change, every setting one click from the top (polyglotic-hq 304, the
user's "Categorise the settings better"); every caption window's settings
are there, each with its line under its name; "Look..." is gone, and a
caption window's "All caption settings..." opens Settings > Look
(polyglotic-hq 248's sections 2.1-2.4, the user's F11 and F18; 261)."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QRect
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from tests.ui_next.test_caption_window import window_of
from tools.ui_lab import checks, lab

from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui_next import panels, settings_page, style
from polyglotic_desktop.ui_next.controls import Card
from polyglotic_desktop.ui_next.face_rows import FacesPanel
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.main_window import MainWindow, roomy_size
from polyglotic_desktop.ui_next.panels import (
    BehaviourPanel,
    LanguagesPanel,
    LookPanel,
    QuietViewPanel,
    ReadingLinesPanel,
    ResetCard,
    TimingPanel,
    WordLinksPanel,
)
from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from polyglotic_desktop.ui_next.settings_popover import ROWS, WINDOW_ROWS
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)

MADE: list[SettingsPage] = []
"""The pages a test made, deleted after it (`deleted`)."""


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each page deleted at the end of its test, its panels with it - not
    left to the interpreter's exit, where a page's panels, still bound to
    their views, crashed Linux's run now and then (exit code 134,
    "malloc_consolidate()": #416's first CI run)."""
    yield
    while MADE:
        page = MADE.pop()
        if shiboken6.isValid(page):
            page.close()
            shiboken6.delete(page)


def page_with(
    look: LookView | None = None,
    timing: TimingView | None = None,
    speech: LanguagesView | None = None,
) -> SettingsPage:
    actions = (QAction("Tell us"),)
    page = SettingsPage(
        [("margin", "Margin")],
        *actions,
        look=look or LookView(CaptionLook()),
        timing=timing or TimingView(Timing()),
        speech=speech or LanguagesView(SessionLanguages()),
    )
    page.keep = actions  # type: ignore[attr-defined]  # alive as long as it
    # wide enough for ten sections' tabs on one line in any of the test
    # machines' fonts (556; eight fitted at 900; Linux's faces are wider)
    page.resize(1300, 700)
    MADE.append(page)
    return page


def test_ten_sections_at_the_top_look_shown_first(qapp: QApplication) -> None:
    """Presets first among them (polyglotic-hq 556); Hotkeys after Dictation
    (567); Look still the one a page opens on."""
    page = page_with()
    page.show()
    qapp.processEvents()
    assert SECTIONS == (
        "presets", "look", "links", "readings", "timing", "speech", "dictation",
        "hotkeys", "app", "lab",
    )  # fmt: skip
    assert [b.text() for b in page.sections.buttons] == [
        "Presets",
        "Look",
        "Word links",
        "Readings",
        "Timing",
        "Speech",
        "Dictation",
        "Hotkeys",
        "App",
        "Lab",
    ]
    assert page.sections.value() == "look"
    shown = [key for key, box in page.section.items() if box.isVisible()]
    assert shown == ["look"]
    page.sections.choose("app")
    assert [key for key, box in page.section.items() if box.isVisible()] == ["app"]
    assert page.theme.isVisible() and not page.look.isVisible()
    page.show_section("look")
    assert page.sections.value() == "look" and page.look.isVisible()
    page.close()


CARDS = (
    LookPanel,
    FacesPanel,
    ResetCard,
    WordLinksPanel,
    QuietViewPanel,
    ReadingLinesPanel,
    TimingPanel,
    BehaviourPanel,
    LanguagesPanel,
    LabPanel,
)
"""The caption sections' cards (`settings_page.CAPTION_CARDS`)."""


def made(page: SettingsPage) -> set[str]:
    return {kind.__name__ for kind in CARDS if page.findChildren(kind)}


def test_a_caption_section_is_made_when_its_first_shown(qapp: QApplication) -> None:
    """The start makes the page unseen: its six caption sections were about
    39 ms of it, and took the start at 30,000 words met over its budget
    (polyglotic-hq 544). Each is made the first time it's shown - Look, the
    one the page opens on, when the page is - or a card of it asked for."""
    page = page_with()
    assert made(page) == set()
    page.show()
    qapp.processEvents()
    assert made(page) == {"LookPanel", "FacesPanel", "ResetCard"}
    assert page.look.isVisible() and page.reset.isVisible()
    page.show_section("timing")
    assert made(page) == {
        "LookPanel", "FacesPanel", "ResetCard", "TimingPanel", "BehaviourPanel",
    }  # fmt: skip
    assert page.timing.isVisible() and page.behaviour.isVisible()  # in this frame
    assert isinstance(page.lab, LabPanel)  # asked for: made, though not shown
    assert not page.lab.isVisible()
    page.close()


def test_the_former_sections_names_still_land(qapp: QApplication) -> None:
    """A way in written for 248's sections lands where its settings went:
    Captions on Look, its first; Learning on Word links, which points to
    the Learning page (470: Look before); App on App."""
    page = page_with()
    page.show()
    qapp.processEvents()
    for former, now in (("captions", "look"), ("learning", "links"), ("app", "app")):
        page.show_section("timing")
        page.show_section(former)
        assert page.sections.value() == now
        assert [k for k, box in page.section.items() if box.isVisible()] == [now]
    with pytest.raises(ValueError):
        page.show_section("nowhere")
    page.close()


def every_section_made(page: SettingsPage) -> None:
    """Each section shown once, ending on Look: a caption section's cards
    are made the first time it is (polyglotic-hq 544)."""
    for key in (*SECTIONS, "look"):
        page.show_section(key)


def cards_in(page: SettingsPage, key: str) -> list[QWidget]:
    column = page.section[key].layout()
    assert column is not None
    items = [column.itemAt(i) for i in range(column.count())]
    return [w for item in items if item is not None and (w := item.widget())]


def test_each_caption_group_is_in_the_section_it_is_come_to_for(
    qapp: QApplication,
) -> None:
    """In 248's order within each: Look holds the look, its Fonts (482)
    and Reset; Word links and Readings (369: pinyin; 450: Jyutping too) are
    sections of their own (470: Look was 2,557 px with no landmark), the
    quiet view (477) beside word links; Timing the timing and Behaviour
    (when captions come and go); Speech what's heard; the Lab,
    experimental, is last on its own."""
    page = page_with()
    every_section_made(page)
    groups: list[Card] = [page.look, page.word_links, page.quiet, page.reading]
    groups += [page.timing, page.behaviour, page.speech, page.reset]
    titles = [g.title.text() if g.title else "" for g in groups]
    assert titles == [
        "Look", "Word links", "Quiet view", "Readings", "Timing", "Behaviour",
        "Speech", "Reset",
    ]  # fmt: skip
    assert cards_in(page, "look") == [
        page.look, page.translation_size, page.faces, page.reset,
    ]  # fmt: skip
    assert cards_in(page, "links") == [page.word_links, page.quiet]
    assert cards_in(page, "readings") == [page.reading]
    assert cards_in(page, "timing") == [page.timing, page.behaviour]
    assert cards_in(page, "speech") == [page.speech]
    assert cards_in(page, "lab") == [page.lab]
    others, own = cards_in(page, "dictation")
    assert others is page.dictation_for_others
    assert own.isAncestorOf(page.dictation_on)


SETTINGS = {
    "look": (
        "look.preset.classic", "look.original_colour", "look.translation_colour",
        "look.background_colour", "look.background", "look.face_en",
        "look.show_original", "look.show_language", "look.show_source",
        "look.reset", "look.caption_text",
    ),
    "links": (
        "look.word_links", "look.link_line", "look.link_gap", "look.link_detail",
        "look.to_learning", "look.quiet", "look.quiet_curriculum", "look.quiet_edge",
        "look.quiet_load", "look.quiet_saved", "look.curriculum_size",
    ),
    "readings": ("look.reading_zh", "look.reading_yue", "look.reading_size"),
    "timing": (
        "timing.mode", "timing.live_interval",
        "timing.max_wait", "timing.settle_after", "look.arrival", "look.fade_after",
    ),
    "speech": ("languages.spoken", "languages.spelling_hints"),
    "dictation": (
        "settings.dictation", "settings.dictation_key", "settings.dictation_key_reset",
        "settings.dictation_language", "settings.dictation_australian",
    ),
    "app": (
        "settings.text_size", "settings.theme", "settings.window_theme",
        "settings.check_updates",
        "settings.restart_update", "settings.notices",
    ),
    "lab": (
        "lab.new_for", "lab.new_fade", "lab.older", "lab.unfinished", "lab.loading",
        "lab.link_px", "lab.row_gap", "lab.caption_gap", "lab.arrival_gap",
        "lab.reset", "lab.load_colours",
    ),
}  # fmt: skip
"""Every setting on the page (304's list), by the object name its control
has had since before 304, in the section it's in now."""


def test_every_setting_is_in_exactly_one_section_one_click_from_the_top(
    qapp: QApplication,
) -> None:
    """None left behind or shown twice by the regrouping - the app's
    language under the title is the one setting in every section, as it
    was (284)."""
    page = page_with()
    every_section_made(page)
    for key, names in SETTINGS.items():
        for name in names:
            found = [
                each
                for each in SECTIONS
                if page.section[each].findChild(QWidget, name) is not None
            ]
            assert found == [key], name
    assert not any(
        page.section[each].isAncestorOf(page.language_picker) for each in SECTIONS
    )


def test_a_change_in_settings_is_the_views_and_every_panel_shows_it(
    qapp: QApplication,
) -> None:
    look = LookView(CaptionLook())
    page, other = page_with(look=look), page_with(look=look)
    page.look.original.click()  # Show the original above the translation
    assert look.value.show_original is False
    assert not other.look.original.isChecked()
    page.word_links.link_detail.choose(page.word_links.link_detail._values[0])
    assert other.word_links.link_detail.value() == look.value.link_detail


def test_translate_live_captions_switch_is_gone(
    qapp: QApplication,
) -> None:
    timing = TimingView(Timing(CaptionMode.WHOLE))
    speech = LanguagesView(SessionLanguages())
    page = page_with(timing=timing, speech=speech)
    page.show()
    page.show_section("timing")
    qapp.processEvents()
    assert page.findChild(QWidget, "timing.translate_live") is None
    assert page.findChild(QWidget, "languages.translate_live") is None
    page.close()


def test_settings_points_to_the_learning_page_and_holds_nothing_of_it(
    qapp: QApplication,
) -> None:
    """What's learned, the level and word introductions are the Learning
    page's (248's section 3.6; polyglotic-hq 262): Settings only points
    there, from Look's Word links - the Learning section, which held only
    a button there, is gone (304); the sidebar has Learning too."""
    page = page_with()
    wanted: list[bool] = []
    page.learning_wanted.connect(lambda: wanted.append(True))
    link = page.word_links.findChild(QLabel, "look.to_learning")
    assert link is not None and "Learning" in link.text()
    link.linkActivated.emit("learning")
    assert wanted == [True]
    assert "learning" not in page.section
    # nor anywhere else in Settings: both live on Learning now (262)
    assert page.findChild(QWidget, "languages.learning") is None
    assert page.findChild(QWidget, "look.common_words_only") is None


def test_every_caption_setting_has_its_line_and_its_tooltip(qapp: QApplication) -> None:
    """F18: a line under every setting that isn't obvious, and the same on
    hover - 248's section 2.4's copy."""
    page = page_with()
    look = page.look
    assert look.background.toolTip().startswith("0 % is no box at all")
    assert look.colours["translation"].toolTip().startswith("The colour of the trans")
    assert page.behaviour.fade.toolTip().startswith("Captions disappear after")
    assert page.word_links.word_links.toolTip().startswith("Which words of what was")


def test_the_hub_opens_at_960_by_680_at_least(qapp: QApplication) -> None:
    """248's section 2.1: a bigger Settings (F11) - a section fits without
    scrolling at the common sizes - where it opens; its minimum is the
    floor, so the learner can make it smaller (polyglotic-hq 586, decision
    0276)."""
    window = MainWindow(QAction("Quit"))
    assert roomy_size() == (960, 680)
    window.fit_to(QRect(0, 0, 2560, 1392))
    assert (window.width(), window.height()) == (1000, 740)  # SIZE, above it
    assert (window.minimumWidth(), window.minimumHeight()) == (760, 520)
    window.keep_in_tray = False
    window.close()


def test_all_caption_settings_ends_every_windows_popover(qapp: QApplication) -> None:
    """ "Look..." is gone (F11); "All caption settings..." takes its place,
    last, in a window's popover and a joined window's own."""
    assert "look" not in ROWS and ROWS[-1] == "all_settings"
    assert "look" not in WINDOW_ROWS and WINDOW_ROWS[-1] == "all_settings"
    window = window_of(qapp)
    asked: list[bool] = []
    window.all_settings_wanted.connect(lambda: asked.append(True))
    window.hovered = True
    window._show_band(True)
    window.buttons["settings"].click()
    popover = window.popover
    assert popover is not None
    row = popover.rows["all_settings"]
    assert isinstance(row, QPushButton) and row.text() == "All caption settings…"
    row.click()
    assert asked == [True]
    assert "look" not in window.controls
    window.close()


def test_the_apps_language_is_under_the_title_in_every_section(
    qapp: QApplication,
) -> None:
    """The user's live testing (polyglotic-hq 270): "App language should
    also be more obvious rather than hid in 2 layers" - so it's under the
    page's title whichever section shows, each language by its own name
    (284) - and only there: App's own Language card said it a second time
    (polyglotic-hq 449's finding 9, 470)."""
    actions = (QAction("Tell us"),)
    page = SettingsPage(
        [("margin", "Margin")],
        *actions,
        [("en", "English"), ("zh_CN", "简体中文")],
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
    )
    page.keep = actions  # type: ignore[attr-defined]
    MADE.append(page)
    page.resize(1300, 700)
    page.show()
    qapp.processEvents()
    picker = page.language_picker
    chosen: list[str] = []
    page.interface_language_chosen.connect(chosen.append)
    for section in SECTIONS:
        page.show_section(section)
        assert picker.isVisible()
    assert [picker.itemText(i) for i in range(picker.count())][1:] == [
        "English",
        "简体中文",
    ]
    assert not page.language_later.isVisible()
    picker.setCurrentIndex(2)
    assert chosen == ["zh_CN"]
    assert page.language_later.isVisible()  # from the next start
    picker.setCurrentIndex(picker.findData("en"))
    assert chosen[-1] == "en"
    page.show_interface_language("")
    assert picker.currentIndex() == 0
    assert chosen[-1] == "en"  # showing the setting isn't choosing it


def test_a_machine_drafted_language_says_so_and_asks(qapp: QApplication) -> None:
    """polyglotic-hq 294 (decision 0087): the app's text in a language no
    native speaker has checked says it's a machine draft, under the title
    in every section, with "Tell us what reads wrong" - the feedback form."""
    actions = (QAction("Tell us"),)
    page = SettingsPage(
        [("margin", "Margin")],
        *actions,
        [("de", "Deutsch"), ("en", "English")],
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
    )
    page.keep = actions  # type: ignore[attr-defined]
    MADE.append(page)
    page.resize(1300, 700)
    page.show()
    qapp.processEvents()
    assert not page.language_draft.isVisible()  # English: not a draft
    page.show_draft(True)
    asked: list[bool] = []
    page.translation_feedback_wanted.connect(lambda: asked.append(True))
    for section in SECTIONS:
        page.show_section(section)
        assert page.language_draft.isVisible() and page.language_wrong.isVisible()
    assert page.language_draft.text() == "Machine draft"
    # on a line of its own under the picker: beside it, a long language's
    # words ran past the page at the Largest text size (294's walk)
    picker = page.language_picker.mapTo(page, page.language_picker.rect().bottomLeft())
    note = page.language_wrong.mapTo(page, page.language_wrong.rect().topLeft())
    assert note.y() >= picker.y()
    page.language_wrong.click()
    assert asked == [True]


# -- settings you can scan (polyglotic-hq 470; 449's design 4A) -------------------------


def test_each_section_and_card_has_its_mark_beside_its_name(
    qapp: QApplication,
) -> None:
    """The user, 2026-11-17: "More icons in settings for visibility ...
    make each setting category very obvious as you scroll the page": each
    tab its mark beside its name, each card's title a size up with its mark
    in a soft square - never a mark alone (NN/g's icon usability)."""
    page = page_with()
    page.show()
    qapp.processEvents()
    every_section_made(page)
    for key, button in zip(SECTIONS, page.sections.buttons, strict=True):
        assert not button.icon().isNull(), key
        assert button.text(), key  # beside its name
    for key in SECTIONS:
        cards = [c for c in cards_in(page, key) if isinstance(c, Card)]
        assert cards, key
        for card in cards:
            assert card.title is not None
            marks = card.findChildren(QWidget, "CardMark")  # its soft square
            assert len(marks) == 1, card.title.text()
            assert card.title.property("heading") is True
            assert card.title.wordWrap()  # a long title wraps at Largest
    app_titles = [
        c.title.text() for c in cards_in(page, "app") if isinstance(c, Card) and c.title
    ]
    assert "Language" not in app_titles  # the line under the title is the one place
    page.close()


def test_a_card_title_is_a_size_up_from_a_rows(qapp: QApplication) -> None:
    sheet = style.stylesheet(style.current())
    page = page_with()
    page.use_sheet(sheet)
    page.show()
    qapp.processEvents()
    title = page.look.title
    assert title is not None
    row_title = page.word_links.findChild(QLabel, "RowTitle")
    assert row_title is not None
    assert title.font().pixelSize() == style.px(16)
    assert title.font().pixelSize() > row_title.font().pixelSize()
    mark = page.look.findChild(QWidget, "CardMark")
    assert mark is not None and mark.width() == style.px(30)
    style.use_app_text_size("largest")  # its square grows with the text
    try:
        page.use_sheet(style.stylesheet(style.current()))
        qapp.processEvents()
        assert title.font().pixelSize() == style.px(16) > 16
        assert mark.width() == style.px(30) > 30
    finally:
        style.use_app_text_size("normal")
    page.close()


def test_the_title_and_sections_stay_put_as_the_page_scrolls(
    qapp: QApplication,
) -> None:
    """Pinned at the top (449's finding 7: Look was 2,557 px, and the tabs
    and card titles scrolled away)."""
    page = page_with()
    page.resize(1300, 500)
    page.show()
    qapp.processEvents()
    page.show_section("app")
    qapp.processEvents()
    bar = page.verticalScrollBar()
    assert bar.maximum() > 0
    # the tabs, or their dropdown in fonts too wide for ten on a line (556, 567)
    head = page.sections if page.sections.isVisible() else page.section_picker
    before = head.mapTo(page, head.rect().topLeft())
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert head.mapTo(page, head.rect().topLeft()) == before
    assert head.isVisible() and not page.viewport().isAncestorOf(head)
    # what scrolls stays under them
    assert page.viewport().geometry().top() >= page.head.geometry().bottom()
    page.close()


def test_the_card_scrolled_into_is_named_under_the_sections(
    qapp: QApplication,
) -> None:
    """Its title scrolled away, the card the learner is in is named, with
    its mark, under the pinned sections; at a card's top it isn't."""
    page = page_with()
    page.resize(1300, 500)
    page.show()
    qapp.processEvents()
    page.show_section("app")
    qapp.processEvents()
    assert not page.pinned.isVisible()
    # Appearance: App's cards end soon after Transcripts since its hotkeys
    # moved to their own section (567) - too near the end to scroll into
    appearance = next(
        c for c in cards_in(page, "app") if isinstance(c, Card) and c.title
        and c.title.text() == "Appearance"
    )  # fmt: skip
    inner = page.widget()
    assert inner is not None
    top = appearance.mapTo(inner, appearance.rect().topLeft()).y()
    page.verticalScrollBar().setValue(top + 40)
    qapp.processEvents()
    assert page.pinned.isVisible()
    assert page.pinned.title.text() == "Appearance"
    assert page.pinned.geometry().top() == page.viewport().geometry().top()
    page.verticalScrollBar().setValue(top - 2)  # its own title in view
    qapp.processEvents()
    assert not page.pinned.isVisible() or page.pinned.title.text() != "Appearance"
    page.show_section("look")  # another section starts at its top
    qapp.processEvents()
    assert not page.pinned.isVisible()
    page.close()


def test_where_the_tabs_dont_fit_on_one_line_they_are_a_dropdown(
    qapp: QApplication,
) -> None:
    """449's finding 8: at 390 px the eight tabs wrapped to four rows."""
    page = page_with()
    page.show()
    qapp.processEvents()
    assert fitted(page)
    page.resize(420, 600)
    qapp.processEvents()
    assert not page.sections.isVisible() and page.section_picker.isVisible()
    picker = page.section_picker
    assert [picker.itemText(i) for i in range(picker.count())][:3] == [
        "Presets", "Look", "Word links",
    ]  # fmt: skip
    assert all(not picker.itemIcon(i).isNull() for i in range(picker.count()))
    picker.setCurrentIndex(SECTIONS.index("readings"))
    assert page.sections.value() == "readings"
    assert [k for k, box in page.section.items() if box.isVisible()] == ["readings"]
    page.show_section("app")
    assert picker.currentData() == "app"
    page.resize(1300, 600)
    qapp.processEvents()
    assert fitted(page)
    page.close()


def fitted(page: SettingsPage) -> bool:
    """The tabs where they fit the column on one line, else the dropdown:
    one of them, never both. Nine fit in Windows' fonts at every text size
    (the UI lab's Settings states); Linux's wider faces take the dropdown
    (polyglotic-hq 556)."""
    column = page.content.parentWidget()
    assert column is not None
    fits = page.sections.sizeHint().width() <= column.width()
    return page.sections.isVisible() == fits and page.section_picker.isVisible() != fits


def test_the_dropdown_holds_every_section_at_the_largest_text_size(
    qapp: QApplication,
) -> None:
    """Each section's name fits the dropdown as it's drawn - at the largest
    text size, Traditional Chinese's "應用程式" (App) ran 2 px past its
    right (the UI lab on Train A, 2026-11-18; polyglotic-hq 500). In the
    lab's fonts, Windows' (`lab.application`): its Chinese face's ink is
    narrower than its advance, where offscreen's own face's isn't."""
    lab.application()
    style.use_interface_language("zh_TW")
    style.use_app_text_size("largest")
    page = page_with()
    try:
        page.use_sheet(style.stylesheet(style.current()))
        picker = page.section_picker
        names = (
            "預設集",
            "字幕外觀",
            "詞語對應",
            "讀音",
            "時機",
            "語音",
            "聽寫",
            "快速鍵",
            "應用程式",
            "實驗室",
        )
        for index, name in enumerate(names):  # zh_TW's, as its .ts file has them
            picker.setItemText(index, name)
        page.resize(420, 600)
        page.show()
        qapp.processEvents()
        assert picker.isVisible()
        for index in range(picker.count()):
            picker.setCurrentIndex(index)
            qapp.processEvents()
            found = checks.inspect(
                "ui_next.test", page, lambda w: lab.photograph(w, False), windows=[page]
            ).findings
            cut = [f.detail for f in found if f.check == "clipped_text"]
            assert [d for d in cut if names[index] in d] == []
    finally:
        page.close()
        style.use_app_text_size("normal")
        style.use_interface_language("en")


def test_the_tabs_are_judged_by_the_column_s_settled_width(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 567: judged by the column's width as it passed through
    others - the head's height moving the viewport, the scroll bar coming
    and going - the tabs and the dropdown took turns 128 times in one
    switch to Speech at the window's narrowest, 160 ms (the UI lab's
    `w4_settings_minimum`, its budget 8). The room they're judged by is the
    column's width once settled, with the bar or without it."""
    page = page_with()
    try:
        page.show()
        column = page.content.parentWidget()
        assert column is not None
        for width, section in ((700, "speech"), (900, "dictation"), (1300, "speech")):
            page.resize(width, 600)
            page.show_section(section)
            for _ in range(3):
                qapp.processEvents()
            # never wider than the column: a few pixels narrower at most (the
            # stretches either side round), the same with the bar or without
            room = page.head_room()
            assert column.width() - 12 <= room <= column.width(), (width, section)
    finally:
        page.close()


def test_transcript_settings_show_both_limits(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_page, "TRANSCRIPT_HOURS", 1)
    monkeypatch.setattr(settings_page, "ASK_FROM_LINES", 1)
    monkeypatch.setattr(settings_page, "TRANSCRIPT_LINES", 62)
    page = page_with()
    assert [button.text() for button in page.transcript_length.buttons][:2] == [
        "Newest 62 lines",
        "Last 1 hour",
    ]
    assert page.transcript_ask.detail.text() == (
        "With Last 1 hour or Whole session: Quit asks about a transcript "
        "of more than 1 line that isn't saved."
    )


def test_the_respelling_description_says_how_many_words_are_covered(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(panels, "RESPELLED_WORD_LIMIT", 42)
    page = page_with()
    page.show_section("readings")
    switch = page.findChild(QWidget, "look.reading_en")
    assert switch is not None
    assert "42 commonest words" in switch.toolTip()
