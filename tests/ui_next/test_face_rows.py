"""Settings > Look's Fonts card: a row per captioned language, its list
grouped Sans / Serif / Handwritten / This PC's own / Any font on this PC
(polyglotic-hq 482, decision 0223) - and what a row's choice does."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem, Step
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, CaptionStyle
from polyglotic_desktop.ui_next.caption_window import caption_style
from polyglotic_desktop.ui_next.face_rows import FaceBox, FacesPanel
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.caption_window import (
    ORIGINAL_ONLY,
    CaptionLook,
    face_chosen,
)
from polyglotic_desktop.ui_next.views.panels import (
    DownloadsView,
    FaceDownloads,
    LanguagesView,
    LookView,
    SessionLanguages,
    captioned,
)


def row(text: str, language: str) -> CaptionRow:
    return CaptionRow(text, RowKind.ORIGINAL, Language(language), 0, True)


# -- which rows, and what a row's choice is (plain Python) -------------------------


def test_the_rows_are_the_languages_the_captions_are_in() -> None:
    languages = SessionLanguages(
        spoken="zh",
        in_use=("en", ORIGINAL_ONLY, "ja"),
        second_languages={"en": "zh"},
        recent_spoken=("th", "zh"),
    )
    assert captioned(languages) == ("zh", "th", "en", "ja")
    assert captioned(SessionLanguages()) == ()


def test_mandarin_shown_in_traditional_has_traditional_chineses_row() -> None:
    languages = SessionLanguages(
        spoken="zh", in_use=("en",), mandarin_script="traditional"
    )
    assert captioned(languages) == ("zh-hant", "en")


def test_a_rows_choice_then_the_one_font_chosen_before_then_the_default() -> None:
    look = CaptionLook(font="Georgia", faces=(("zh", "KaiTi"), ("th", "")))
    assert face_chosen(look, "zh") == "KaiTi"
    assert face_chosen(look, "th") is None  # its default, over Georgia
    assert face_chosen(look, "en") == "Georgia"  # no row's choice yet
    assert face_chosen(CaptionLook(), "en") is None


def test_a_rows_choice_is_kept_by_language() -> None:
    view = LookView(CaptionLook())
    view.set_face("zh", "KaiTi")
    view.set_face("en", "Georgia")
    view.set_face("zh", None)
    assert view.value.faces == (("en", "Georgia"), ("zh", ""))


def test_the_choices_are_saved_and_read_back() -> None:
    look = caption_look(AppSettings(caption_faces={"zh": "KaiTi", "th": ""}))
    assert look.faces == (("th", ""), ("zh", "KaiTi"))
    back = replace(AppSettings(), **look_settings(look))  # type: ignore[arg-type]
    assert back.caption_faces == {"th": "", "zh": "KaiTi"}


def test_a_settings_file_with_bad_choices_keeps_none_of_them() -> None:
    assert AppSettings.from_stored({"caption_faces": {"zh": 3}}).caption_faces == {}
    good = AppSettings.from_stored({"caption_faces": {"zh": "KaiTi", "en": ""}})
    assert good.caption_faces == {"zh": "KaiTi", "en": ""}


# -- in Qt -------------------------------------------------------------------------


def test_a_rows_face_draws_that_languages_captions(qapp: QApplication) -> None:
    style = caption_style(
        CaptionLook(font="Georgia", faces=(("zh", "KaiTi"), ("th", "")))
    )
    engine = CaptionLayout(style)
    assert engine._font(row("我们", "zh"), 1.0, False).families()[:3] == [
        "KaiTi",
        "Ma Shan Zheng Captions",
        "Noto Sans SC Captions",
    ]
    assert (
        engine._font(row("สวัสดี", "th"), 1.0, False).families()[0]
        == "Noto Sans Thai Looped"
    )
    assert engine._font(row("Hello", "en"), 1.0, False).families()[0] == "Georgia"
    assert CaptionLayout(CaptionStyle())._font(
        row("Hello", "en"), 1.0, False
    ).families()[0] == ("IBM Plex Sans")


@pytest.fixture
def panel(qapp: QApplication) -> Iterator[tuple[FacesPanel, LookView, LanguagesView]]:
    look = LookView(CaptionLook())
    languages = LanguagesView(SessionLanguages(spoken="zh", in_use=("en",)))
    made = FacesPanel(look, languages, notes=True)
    yield made, look, languages
    made.deleteLater()
    qapp.processEvents()


def test_a_row_for_each_language_captioned(
    panel: tuple[FacesPanel, LookView, LanguagesView],
) -> None:
    faces, _, languages = panel
    assert list(faces.boxes) == ["zh", "en"]
    assert faces.boxes["zh"].accessibleName() == "Chinese captions in"
    languages.change(replace(languages.value, spoken="th"))
    assert list(faces.boxes) == ["th", "en"]
    languages.change(SessionLanguages())
    assert list(faces.boxes) == ["en"]  # English's until one is chosen


def test_a_rows_list_is_grouped_and_its_default_marked(
    panel: tuple[FacesPanel, LookView, LanguagesView],
) -> None:
    box = panel[0].boxes["zh"]
    items = [(box.itemText(n), box.itemData(n)) for n in range(box.count())]
    assert items[:2] == [("Sans", None), ("Noto Sans SC", "Noto Sans SC Captions")]
    headings = [
        box.itemText(n)
        for n in range(box.count())
        if not box.model().flags(box.model().index(n, 0)) & Qt.ItemFlag.ItemIsEnabled
    ]
    assert headings[0] == "Sans"
    assert headings[-1] == pc_or_mac("Any font on this PC", "Any font on this Mac")
    # the calligraphy under a heading of its own, the default (532)
    at = headings.index("Calligraphy")
    assert headings[at + 1] == pc_or_mac("This PC's own", "This Mac's own")
    calligraphy = box.findText("Calligraphy")
    assert box.itemText(calligraphy + 1) == "Ma Shan Zheng (Default)"
    assert box.currentText() == "Ma Shan Zheng (Default)"


def test_picking_a_face_sets_that_language_only(
    panel: tuple[FacesPanel, LookView, LanguagesView],
) -> None:
    faces, look, _ = panel
    box = faces.boxes["en"]
    box.addItem("Georgia", "Georgia")  # under Any font, as if listed
    box.setCurrentIndex(box.findData("Georgia"))
    assert look.value.faces == (("en", "Georgia"),)
    box.setCurrentIndex(box.findData(""))
    assert look.value.faces == (("en", ""),)
    assert faces.boxes["zh"].currentData() == ""


def test_every_font_on_the_pc_is_listed_only_when_opened(qapp: QApplication) -> None:
    box = FaceBox("en")
    try:
        before = box.count()
        box.showPopup()
        box.hidePopup()
        assert box.count() > before  # this PC's fonts, under Any font
        assert box.currentData() == ""  # still the default
    finally:
        box.deleteLater()


def test_the_one_font_chosen_before_shows_in_every_row(qapp: QApplication) -> None:
    look = LookView(CaptionLook(font="Not On This PC"))
    languages = LanguagesView(SessionLanguages(spoken="ru", in_use=("en",)))
    faces = FacesPanel(look, languages)
    try:
        assert faces.boxes["ru"].currentData() == "Not On This PC"
        assert faces.boxes["en"].currentData() == "Not On This PC"
    finally:
        faces.deleteLater()


# -- faces downloaded when they're chosen (polyglotic-hq 482's packs) -------------


def test_a_face_not_here_says_its_size_and_is_asked_for_when_picked(
    qapp: QApplication,
) -> None:
    asked: list[tuple[str, bool]] = []
    downloads = DownloadsView(
        FaceDownloads(sizes={"notoserifsc": 2_420_000}),
        want=lambda pack, anyway: asked.append((pack, anyway)),
    )
    look = LookView(CaptionLook())
    faces = FacesPanel(look, LanguagesView(SessionLanguages(spoken="zh")), downloads)
    try:
        box = faces.boxes["zh"]
        index = box.findData("Noto Serif SC Captions")
        assert box.itemText(index) == "Noto Serif SC · 2.4 MB"
        box.setCurrentIndex(index)
        assert look.value.faces == (("zh", "Noto Serif SC Captions"),)
        assert asked == [("notoserifsc", False)]
        downloads.follow(replace(downloads.value, here=frozenset({"notoserifsc"})))
        assert box.itemText(index) == "Noto Serif SC"  # here: no size
    finally:
        faces.deleteLater()


def test_a_download_under_way_shows_under_its_row(qapp: QApplication) -> None:
    going = PackProgress("font:lxgwwenkaitc", Step.DOWNLOADING, 1_000_000, 3_120_000)
    downloads = DownloadsView(FaceDownloads(progress={"lxgwwenkaitc": going}))
    languages = LanguagesView(
        SessionLanguages(spoken="zh", in_use=("en",), mandarin_script="traditional")
    )
    faces = FacesPanel(LookView(CaptionLook()), languages, downloads)
    try:
        row = faces.face_rows[
            "zh-hant"
        ]  # its default comes as a download (532: LXGW WenKai TC)
        assert not row.status.isHidden()
        assert row.words.text() == "Downloading LXGW WenKai TC: 1.0 of 3.1 MB"
        assert row.bar.share == pytest.approx(1_000_000 / 3_120_000)
        assert row.again.isHidden()
        assert faces.face_rows["en"].status.isHidden()  # carried by the app
        stopped = replace(going, problem=Problem.OFFLINE, retry_in=None)
        downloads.follow(FaceDownloads(progress={"lxgwwenkaitc": stopped}))
        assert not row.again.isHidden() and row.again.text() == "Retry"
        downloads.follow(FaceDownloads(here=frozenset({"lxgwwenkaitc"})))
        assert row.status.isHidden()
    finally:
        faces.deleteLater()


def test_retry_asks_the_downloads_main_hands_over_after_the_card_is_made(
    qapp: QApplication,
) -> None:
    """`main` gives the view its `want` once the font downloads exist,
    after Settings and its card are made: Retry must reach that one."""
    stopped = PackProgress(
        "font:notosansjp", Step.DOWNLOADING, problem=Problem.OFFLINE, retry_in=None
    )
    downloads = DownloadsView(FaceDownloads(progress={"notosansjp": stopped}))
    faces = FacesPanel(
        LookView(CaptionLook()), LanguagesView(SessionLanguages(spoken="ja")), downloads
    )
    try:
        asked: list[tuple[str, bool]] = []
        downloads.want = lambda pack, anyway: asked.append((pack, anyway))
        faces.face_rows["ja"].again.click()
        assert asked == [("notosansjp", False)]
    finally:
        faces.deleteLater()
