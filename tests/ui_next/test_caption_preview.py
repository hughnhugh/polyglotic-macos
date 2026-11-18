"""The live preview at the top of Settings > Captions > Look (polyglotic-hq
248's section 2.1; 261): two made-up captions over the app's own still,
drawn by the caption windows' engine in the look now, redrawn as it
changes - the thing the "Look..." window never had."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.adapters.traditional_table import read_table
from polyglotic_desktop.core.lexicon.traditional import TraditionalChinese
from polyglotic_desktop.core.listening.display import RowKind, WordLinks
from polyglotic_desktop.ui_next import caption_preview
from polyglotic_desktop.ui_next.caption_preview import CaptionPreview
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.panels import LookPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
)

MADE: list[QWidget] = []
"""What a test made, deleted at its end (`deleted`)."""


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each preview and panel deleted when its test ends, not at the
    interpreter's exit, where one still bound to its view can crash the run
    (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def shown(qapp: QApplication, view: LookView) -> CaptionPreview:
    preview = CaptionPreview(view)
    MADE.append(preview)
    preview.resize(640, 230)
    preview.show()
    qapp.processEvents()
    return preview


def test_it_follows_a_preset_a_colour_and_the_panel(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    preview = shown(qapp, view)
    view.set_preset("ember")
    ink = preview.surface.ink
    assert ink.original == QColor("#dcecff") and ink.translation == QColor("#ffa64d")
    view.set_colour("translation", "#7fe3ff")
    assert preview.surface.ink.translation == QColor("#7fe3ff")
    image = preview.grab().toImage()
    panel = preview.panel_rect()
    inside = image.pixelColor(int(panel.left()) + 4, int(panel.center().y()))
    outside = image.pixelColor(int(panel.left()) - 6, int(panel.center().y()))
    assert inside != outside  # the panel is drawn over the still
    preview.close()


def test_it_shows_what_the_look_shows(qapp: QApplication) -> None:
    view = LookView(CaptionLook(show_original=True))
    preview = shown(qapp, view)
    kinds = {row.kind for line in preview.lines.lines for row in line.rows}
    assert kinds == {RowKind.ORIGINAL, RowKind.TRANSLATION}
    tall = preview.panel_rect().height()
    view.set_show_original(False)
    kinds = {row.kind for line in preview.lines.lines for row in line.rows}
    assert kinds == {RowKind.TRANSLATION}
    assert preview.panel_rect().height() < tall  # the panel fits its captions
    view.set_face("zh", "Segoe UI")
    assert preview.surface.engine.style.faces == (("zh", "Segoe UI"),)
    view.set_word_links(WordLinks.ARROWS)
    view.set_show_original(True)
    assert preview.surface.engine.style.arrows  # room for the curves
    preview.close()


def test_it_is_at_the_top_of_settings_look_only(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    settings, rail = LookPanel(view, notes=True, preview=True), LookPanel(view)
    MADE.extend((settings, rail))
    assert settings.preview is not None and rail.preview is None
    preset_row = settings.presets.parentWidget()
    assert preset_row is not None
    column = settings.column
    assert column.indexOf(settings.preview) < column.indexOf(preset_row)


def test_a_preview_that_goes_is_no_longer_told(qapp: QApplication) -> None:
    view = LookView(CaptionLook())
    preview = CaptionPreview(view)
    preview.deleteLater()
    qapp.processEvents()
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    view.set_preset("paper")  # nothing left to tell: no error


def said(preview: CaptionPreview) -> list[str]:
    """What each made-up caption says, as laid out."""
    return [
        row.text
        for line in preview.lines.lines
        for row in line.rows
        if row.kind is RowKind.ORIGINAL
    ]


def test_its_captions_are_in_the_characters_mandarin_is_shown_in(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 400 (found by 375): with "Show Mandarin in: Traditional"
    the caption windows showed Traditional, and the preview of them still
    Simplified - what a learner looks at right after choosing it."""
    view = LookView(CaptionLook(show_original=True))
    languages = LanguagesView(SessionLanguages(mandarin_script="traditional"))
    preview = CaptionPreview(view, languages=languages, unfinished=True)
    MADE.append(preview)
    assert said(preview) == [
        "這個季度的數字看起來不錯。",
        "我們畢竟要完成這個項目。",
        "那我們下週再",
    ]
    clauses = caption_preview.sample_clauses(traditional=True)
    linked = [
        clause.original[a:b]
        for clause in clauses
        for link in clause.links[caption_preview.EN]
        for a, b in (link.original,)
    ]  # the words linked, found in Traditional too
    assert linked == ["季度", "數字", "不錯", "畢竟", "完成", "項目"]
    readings = caption_preview.sample_readings(said(preview)[0], "zh")
    assert [r.text for r in readings][:4] == ["zhè", "ge", "jì", "dù"]

    languages.set_traditional(False)  # Simplified again
    assert said(preview)[0] == "这个季度的数字看起来不错。"
    assert len(preview.lines.lines) == 3  # the same captions, not more


def test_this_pcs_script_when_none_is_chosen(qapp: QApplication) -> None:
    """None chosen: as this PC reads Chinese (`traditional_here`; 375)."""
    view = LookView(CaptionLook(show_original=True))
    here = LanguagesView(SessionLanguages(traditional_here=True))
    preview = CaptionPreview(view, languages=here)
    MADE.append(preview)
    assert said(preview)[0] == "這個季度的數字看起來不錯。"


def test_settings_look_and_the_lab_follow_speech_s_choice(qapp: QApplication) -> None:
    view = LookView(CaptionLook(show_original=True))
    languages = LanguagesView(SessionLanguages())
    look = LookPanel(view, notes=True, preview=True, languages=languages)
    lab = LabPanel(view, languages=languages)
    MADE.extend((look, lab))
    assert look.preview is not None
    languages.set_traditional(True)
    assert said(look.preview)[0] == "這個季度的數字看起來不錯。"
    assert said(lab.preview)[-1] == "那我們下週再"


def test_its_traditional_is_the_app_s_own_converter_s() -> None:
    """The preview writes its few characters itself, rather than read the
    converter's 1 MB table for a picture: here the two agree, sentence by
    sentence and word by word."""
    converter = TraditionalChinese(read_table())
    texts = [
        said for said, _, _ in (*caption_preview._SAMPLES, caption_preview._UNFINISHED)
    ]
    words = [
        w
        for _, _, pairs in (*caption_preview._SAMPLES, caption_preview._UNFINISHED)
        for w, _ in pairs
    ]
    words += [
        word.split()[0]
        for line in caption_preview._PINYIN.values()
        for word in line.split("|")
    ]
    for text in texts + words:
        assert caption_preview._written(text, True) == converter.convert(text), text
