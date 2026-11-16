"""Which strings a screen shows (tools/ui_lab/seen.py; polyglotic-hq 294):
a listening translator notes what's asked and translates nothing, and a
string counts where its own words are on screen, its `{names}` and count
standing for anything."""

import csv
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
from tools.i18n import __main__ as i18n
from tools.i18n import review
from tools.ui_lab import seen

from polyglotic_desktop.ui.interface_language import install


@pytest.fixture
def qapp() -> Iterator[QApplication]:
    """The app with English's counts, as it starts (decision 0034)."""
    app = QApplication.instance() or QApplication(["test"])
    assert isinstance(app, QApplication)
    if not app.property("interface_language"):
        app.setProperty("interface_language", "en")
        install(app, "en")
    yield app


def test_the_listening_translator_lets_the_files_answer(qapp: QApplication) -> None:
    asked = seen.Asked()
    qapp.installTranslator(asked)
    try:
        assert QCoreApplication.translate("Lab", "Nothing to see") == "Nothing to see"
        text = QCoreApplication.translate(
            "LookupCard", "Heard in %Ln caption(s)", None, 2
        )
        assert text == "Heard in 2 captions"  # English's file still answers
    finally:
        qapp.removeTranslator(asked)
    assert {
        ("Lab", "Nothing to see", ""),
        ("LookupCard", "Heard in %Ln caption(s)", ""),
    } <= asked.asked  # with Qt's own (its layout direction, as it's installed)


def test_a_string_shows_with_anything_for_its_names_and_count() -> None:
    parts = seen.pattern("Stop captioning {app}")
    assert parts is not None
    assert seen.shows(parts, "Settings\x00StopcaptioningDiscord")
    assert not seen.shows(parts, "Stop\x00captioning")  # not across two pieces
    count = seen.pattern("Heard in %Ln caption(s)")
    assert count is not None and seen.shows(count, "Heardin1,234captions")
    assert seen.pattern("{app}") is None  # nothing of its own to find
    assert seen.pattern("%n") is None


def test_a_screen_counts_what_its_widgets_show(qapp: QApplication) -> None:
    asked, found, shown = seen.recorder(qapp)
    window = QWidget()
    try:
        column = QVBoxLayout(window)
        column.addWidget(QLabel(QCoreApplication.translate("Home", "Start listening")))
        hidden = QPushButton(QCoreApplication.translate("Home", "Hidden button"))
        column.addWidget(hidden)
        hidden.hide()
        window.show()
        shown("lab.one", window)
        assert dict(found.states) == {("Home", "Start listening", ""): ["lab.one"]}
        assert asked.asked == set()  # emptied for the next screen
    finally:
        qapp.removeTranslator(asked)
        window.deleteLater()


def test_the_most_seen_sheet_is_in_their_order(tmp_path: Path) -> None:
    """A reviewer's sheet of the strings seen most: in `seen.tsv`'s order,
    each English once, with where it is in a reviewer's words."""
    ranking = tmp_path / "seen.tsv"
    seen.write(
        seen.Seen(
            {
                ("CaptionWindow", "Original only", ""): ["a", "b", "c"],
                ("Panels", "Original only", ""): ["a", "b"],
                ("TranscriptWindow", "Copy", ""): ["a"],
            }
        ),
        ranking,
    )
    sheet = tmp_path / "sheet.csv"
    rows = review.write_sheet(i18n.ts_path("zh_CN"), sheet, 60, seen=ranking)
    with sheet.open(encoding="utf-8-sig", newline="") as source:
        read = list(csv.DictReader(source))
    assert rows == 2
    assert [(r["context"], r["english"]) for r in read] == [
        ("CaptionWindow", "Original only"),
        ("TranscriptWindow", "Copy"),
    ]
    assert read[0]["where"] == "a caption window (on 3 of the UI lab's screens)"
