"""A wrapped label's lines keep to a readable length (polyglotic-hq 376):
in the main window's 720 px column a 12 px note ran to 120 characters a
line. The label is no wider than the measure, at the left of the room its
layout gives it. Offscreen."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from polyglotic_desktop.ui_next import controls, copying

LONG = (
    "How long words on screen may still be corrected as more is heard."
    " Shorter: fewer words change while you read, and more mistakes stay as"
    " first heard - most of all when Live updates come faster than every second."
)


@pytest.fixture
def column(qapp: QApplication) -> Iterator[QWidget]:
    found = QWidget()
    QVBoxLayout(found).setContentsMargins(0, 0, 0, 0)
    yield found
    found.close()
    shiboken6.delete(found)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def shown(column: QWidget, label: QLabel, width: int) -> None:
    layout = column.layout()
    assert isinstance(layout, QVBoxLayout)
    layout.addWidget(label)
    layout.addStretch(1)
    column.resize(width, 400)
    column.show()
    QApplication.processEvents()


def lines(label: QLabel) -> int:
    return round(label.height() / QFontMetricsF(label.font()).lineSpacing())


def test_a_wide_note_is_as_wide_as_the_measure_at_the_left(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True)
    shown(column, note, 700)
    assert isinstance(note, copying.Measured)
    assert note.width() == note.measure() < 700
    assert note.x() == 0  # at the left, not centred as a maximum width would be
    one_line = QFontMetricsF(note.font()).horizontalAdvance(LONG)
    assert lines(note) >= one_line / note.measure()  # as tall as its lines


@pytest.mark.windows_only  # Segoe UI's widths: Linux's fallback font is wider per character (train 2's Linux run)
def test_the_longest_line_is_about_seventy_characters(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True)
    shown(column, note, 700)
    average = QFontMetricsF(note.font()).horizontalAdvance(LONG) / len(LONG)
    assert 60 <= note.measure() / average <= 80


def test_a_narrow_note_is_as_before(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True)
    shown(column, note, 150)  # a caption window's settings, the rail
    assert note.width() == 150


def test_the_note_narrows_and_widens_with_its_column(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True)
    shown(column, note, 700)
    tall = note.height()
    column.resize(120, 400)
    QApplication.processEvents()
    assert note.width() == 120
    assert note.height() > tall
    column.resize(700, 400)
    QApplication.processEvents()
    assert note.width() == note.measure()
    assert note.height() == tall


def test_a_short_note_is_as_wide_as_its_words(column: QWidget) -> None:
    note = controls.label("Every caption window.", "Dim", wrap=True)
    shown(column, note, 700)
    words = QFontMetricsF(note.font()).horizontalAdvance(note.text())
    assert words <= note.width() <= words + 4
    assert lines(note) == 1


def test_a_word_longer_than_the_measure_isnt_cut(column: QWidget) -> None:
    path = "C:/" + "/".join(["a-folder-with-a-long-name"] * 8)  # can't be broken
    note = controls.label(f"The old file is kept as {path} for now.", wrap=True)
    shown(column, note, 2000)
    needs = QFontMetricsF(note.font()).horizontalAdvance(path)
    assert needs > note.measure()
    assert note.width() >= needs  # wider than the measure: all of the word shows


def test_one_line_labels_and_centred_ones_are_left_alone(column: QWidget) -> None:
    title = controls.label(LONG)  # not wrapped
    centred = controls.label(LONG, wrap=True)
    centred.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout = column.layout()
    assert layout is not None
    layout.addWidget(centred)
    shown(column, title, 700)
    assert not title.measured()
    assert not centred.measured()
    assert centred.width() == column.width()  # all of its room


def test_a_note_its_layout_puts_at_the_right_stays_there(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True)
    layout = column.layout()
    assert isinstance(layout, QVBoxLayout)
    layout.addWidget(note, 0, Qt.AlignmentFlag.AlignRight)
    column.resize(700, 400)
    column.show()
    QApplication.processEvents()
    assert not note.measured()
    assert note.geometry().right() == 699


def test_a_note_in_no_layout_is_left_alone(qapp: QApplication) -> None:
    holder = QWidget()
    note = controls.label(LONG, "Faint", wrap=True)
    note.setParent(holder)
    note.setGeometry(0, 0, 700, 40)
    assert not note.measured()
    assert note.heightForWidth(700) == QLabel.heightForWidth(note, 700)
    holder.deleteLater()


def test_a_note_moved_to_another_layout_is_measured_there(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True)
    shown(column, note, 700)
    other = QWidget()
    QVBoxLayout(other).addWidget(note)
    other.resize(700, 400)
    other.show()
    QApplication.processEvents()
    assert note.width() == note.measure()
    other.close()
    shiboken6.delete(other)


def test_a_label_a_click_goes_through_is_measured_too(column: QWidget) -> None:
    note = controls.label(LONG, "Faint", wrap=True, copyable=False)
    shown(column, note, 700)
    assert not isinstance(note, copying.Text)
    assert note.width() == note.measure()


def test_a_larger_font_has_a_wider_measure(column: QWidget) -> None:
    note = controls.label(LONG, wrap=True)
    shown(column, note, 1600)
    before = note.width()
    font = note.font()
    font.setPixelSize(24)
    note.setFont(font)
    QApplication.processEvents()
    assert note.width() == note.measure() > before


def test_a_links_address_isnt_a_word(column: QWidget) -> None:
    address = "https://example.com/" + "a-long-address/" * 12
    note = controls.label(f'{LONG} <a href="{address}">Read more</a>', wrap=True)
    shown(column, note, 2000)
    assert note.width() == note.measure()


@pytest.mark.windows_only  # Segoe UI's widths: Linux's fallback font is wider per character (train 2's Linux run)
def test_a_word_over_the_measure_stays_on_the_line(column: QWidget) -> None:
    note = controls.label("word", wrap=True)
    shown(column, note, 2000)
    for count in range(5, 60):
        said = " ".join(["word"] * count)
        note.setText(said)
        QApplication.processEvents()
        wide = QFontMetricsF(note.font()).horizontalAdvance(said)
        if note.measure() < wide <= note.measure() * copying.ONE_LINE:
            assert len(said) <= copying.ONE_LINE_CHARACTERS
            assert lines(note) == 1
            break
    else:
        raise AssertionError("no text between the measure and its allowance")


def test_new_words_are_measured_again(column: QWidget) -> None:
    note = controls.label("Short.", "Faint", wrap=True)
    shown(column, note, 700)
    assert note.width() < note.measure()
    note.setText(LONG)
    QApplication.processEvents()
    assert note.width() == note.measure()


def test_a_notices_band_is_as_wide_as_its_room(column: QWidget) -> None:
    band = controls.label("Busy time - captions continue", "Banner", wrap=True)
    own = controls.label(LONG, wrap=True)
    own.setStyleSheet("background: #223344; padding: 6px;")
    layout = column.layout()
    assert layout is not None
    layout.addWidget(own)
    shown(column, band, 700)
    assert band.width() == own.width() == 700


def test_many_narrow_characters_still_wrap(column: QWidget) -> None:
    said = " ".join(["ill"] * 30)  # 119 characters, narrow ones
    note = controls.label(said, wrap=True)
    shown(column, note, 2000)
    assert note.width() <= note.measure()


def test_a_chinese_sentence_keeps_to_the_measure_too(column: QWidget) -> None:
    said = "你查过、收藏和标记的词" * 12  # no spaces
    note = controls.label(said, "Faint", wrap=True)
    shown(column, note, 2000)
    assert note.width() == note.measure()
    assert lines(note) > 1
