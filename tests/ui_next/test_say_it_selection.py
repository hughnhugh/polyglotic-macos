"""Say it on a selection (polyglotic-hq 495, 488's design): the sentence
card's second row - a button a language, the side used last first - reads
the side in its spoken form through the `Reader` port, turns into Stop,
lights the word being said in the window, hands each sentence's sound to
the captions' hush, and stops on a click, Esc, a new selection, the card
going, another reading or dictation; never starts while dictation's key is
held; with no voice says how to add one. The transcript's selection menu
has it too. A stand-in reader: nothing is played. Real windows, offscreen;
made-up captions."""

from collections.abc import Iterator, Sequence
from typing import cast

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QPushButton
from tests.ui_next import test_lookup_card as cards
from tests.ui_next.test_copy_from_the_transcript import drag as transcript_drag
from tests.ui_next.test_lookup_card import window
from tests.ui_next.test_select_captions import SAID, drag, last_two, point
from tests.ui_next.test_transcript_lookup import both, find, listed

from polyglotic_desktop.core.listening.caption_model import Words
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.ports.speaker import Ended, Quality, Sounding, Spoken, Voice
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.selection_reading import SelectionReading
from polyglotic_desktop.ui_next.sentence_card import SentenceCard
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.speech import (
    MAC_SPEECH_SETTINGS,
    SPEECH_SETTINGS,
    BetterVoice,
)

windows = cards.windows  # a window of 40 made-up captions, Chinese into English
keys = cards.keys
problem = cards.problem
__all__ = ["both", "keys", "problem", "windows"]  # the fixtures, shared

HUIHUI = Voice("zh-cn-1", "Microsoft Huihui", "zh-CN")
DAVID = Voice("en-us-1", "Microsoft David", "en-US")


class Reader:
    """The `Reader` port, made up: it remembers what it was asked."""

    def __init__(self, voices: tuple[Voice, ...] = (HUIHUI, DAVID)) -> None:
        self.installed = voices
        self.read_: list[tuple[tuple[str, ...], str]] = []
        self.stops = 0
        self.sounding: Sounding | None = None
        self.ended: Ended | None = None
        self.spoken: Spoken | None = None

    def voices(self) -> tuple[Voice, ...]:
        return self.installed

    def read(
        self,
        chunks: Sequence[str],
        voice: Voice,
        rate: float,
        sounding: Sounding,
        ended: Ended,
        spoken: Spoken,
    ) -> None:
        if self.ended is not None:
            self.ended(False)  # one at a time: the last wins
        self.read_.append((tuple(chunks), voice.id))
        self.sounding, self.ended, self.spoken = sounding, ended, spoken

    def stop(self) -> None:
        self.stops += 1
        if self.ended is not None:
            ended, self.ended = self.ended, None
            ended(False)


class Settings:
    def __init__(self) -> None:
        self.first = RowKind.ORIGINAL
        self.held = False
        self.hushed: list[tuple[float, float]] = []
        self.opened: list[str] = []

    def remember(self, kind: RowKind) -> None:
        self.first = kind


@pytest.fixture
def reader() -> Reader:
    return Reader()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def say_it(
    qapp: QApplication, reader: Reader, settings: Settings
) -> Iterator[SelectionReading]:
    made = SelectionReading(
        reader,
        hush=lambda s, n: settings.hushed.append((s, n)),
        blocked=lambda: settings.held,
        first=lambda: settings.first,
        remember=settings.remember,
        open_url=settings.opened.append,
    )
    yield made
    made.deleteLater()
    qapp.processEvents()


def offered(windows: CaptionWindows, say_it: SelectionReading) -> SentenceCard:
    """The two newest captions selected, said side only: the card."""
    windows.use_say_it(say_it)
    shown = window(windows)
    first, second = last_two(shown)
    drag(shown, point(shown, first.key, SAID, 0), point(shown, second.key, SAID, 2))
    card = shown.sentence_card
    assert card is not None and card.isVisible()
    return card


def buttons(card: SentenceCard) -> list[QPushButton]:
    return [button for button, _ in card.sides]


def settle(qapp: QApplication) -> None:
    qapp.processEvents()


def test_the_card_offers_each_side_by_its_languages_own_name(
    windows: CaptionWindows, say_it: SelectionReading
) -> None:
    card = offered(windows, say_it)
    assert card.say_label.isVisible() and card.say_label.text() == "Say it"
    assert [b.text() for b in buttons(card)] == ["▶ 中文", "▶ English"]
    assert [b.toolTip() for b in buttons(card)] == [
        "Say it in Chinese",
        "Say it in English",
    ]
    assert not card.isActiveWindow()  # never takes the keyboard
    card.hide()


def test_a_click_reads_its_spoken_form_turns_to_stop_and_lights_each_word(
    qapp: QApplication,
    windows: CaptionWindows,
    say_it: SelectionReading,
    reader: Reader,
    settings: Settings,
) -> None:
    card = offered(windows, say_it)
    shown = window(windows)
    first, _ = last_two(shown)
    said, _ = card.sides[0]
    said.click()
    ((chunks, voice),) = reader.read_
    assert voice == HUIHUI.id
    joined = "".join(chunks)
    assert joined.startswith(first.rows[0].text[:2])
    assert said.text() == "■ Stop"
    assert shown.held.selection is not None  # its click kept the selection
    # each sentence's sound to the captions' hush, as it starts
    assert reader.sounding is not None and reader.spoken is not None
    reader.sounding(10.0, 1.5)
    assert settings.hushed == [(10.0, 1.5)]
    reader.spoken(0, 0, 2)  # the first two characters of the first sentence
    settle(qapp)
    assert shown.canvas.said_now == {first.key: [Words(SAID, 0, 0, 2)]}
    # the reading ends: the button is ready again, nothing lit
    assert reader.ended is not None
    reader.ended(True)
    settle(qapp)
    assert said.text() == "▶ 中文" and shown.canvas.said_now == {}
    card.hide()


def test_a_second_click_stops_it_and_the_side_used_last_comes_first(
    qapp: QApplication,
    windows: CaptionWindows,
    say_it: SelectionReading,
    reader: Reader,
    settings: Settings,
) -> None:
    card = offered(windows, say_it)
    translation, side = card.sides[1]
    assert side.kind is RowKind.TRANSLATION
    translation.click()
    assert reader.read_[-1][1] == DAVID.id
    assert settings.first is RowKind.TRANSLATION  # remembered
    translation.click()
    settle(qapp)
    assert reader.stops == 1 and translation.text() == "▶ English"
    card.hide()
    shown = window(windows)
    first, second = last_two(shown)
    drag(shown, point(shown, first.key, SAID, 1), point(shown, second.key, SAID, 3))
    again = shown.sentence_card
    assert again is not None
    assert [b.text() for b in buttons(again)] == ["▶ English", "▶ 中文"]
    again.hide()


@pytest.mark.parametrize("how", ["esc", "card", "selection"])
def test_esc_the_card_going_or_a_new_selection_stops_it(
    qapp: QApplication,
    windows: CaptionWindows,
    say_it: SelectionReading,
    reader: Reader,
    how: str,
) -> None:
    card = offered(windows, say_it)
    shown = window(windows)
    buttons(card)[0].click()
    assert say_it.reading is not None
    if how == "esc":
        shown.held.clear()  # what Esc and a click elsewhere do
    elif how == "card":
        card.hide()
    else:
        first, second = last_two(shown)
        drag(shown, point(shown, first.key, SAID, 1), point(shown, second.key, SAID, 1))
    settle(qapp)
    assert say_it.reading is None and reader.stops >= 1
    assert shown.canvas.said_now == {}
    card.hide()


def test_another_reading_or_the_word_speaker_ends_it_and_dictation_stops_it(
    qapp: QApplication,
    windows: CaptionWindows,
    say_it: SelectionReading,
    reader: Reader,
) -> None:
    card = offered(windows, say_it)
    said, translation = buttons(card)
    said.click()
    translation.click()  # the reader ends the first one, told False
    settle(qapp)
    assert said.text() == "▶ 中文" and translation.text() == "■ Stop"
    say_it.stop()  # what `main` does as dictation takes the mic
    settle(qapp)
    assert translation.text() == "▶ English" and say_it.reading is None
    card.hide()


def test_never_while_dictations_key_is_held(
    windows: CaptionWindows,
    say_it: SelectionReading,
    reader: Reader,
    settings: Settings,
) -> None:
    card = offered(windows, say_it)
    settings.held = True
    buttons(card)[0].click()
    assert reader.read_ == [] and say_it.reading is None
    card.hide()


def test_with_no_voice_the_button_says_how_to_add_one(
    qapp: QApplication,
    windows: CaptionWindows,
    say_it: SelectionReading,
    reader: Reader,
    settings: Settings,
) -> None:
    reader.installed = (DAVID,)
    card = offered(windows, say_it)
    said = buttons(card)[0]
    assert said.text() == "+ Add a Chinese voice"
    assert pc_or_mac("Add voices", "Manage Voices") in said.toolTip()
    said.click()
    opened = pc_or_mac(SPEECH_SETTINGS, MAC_SPEECH_SETTINGS)
    assert settings.opened == [opened] and reader.read_ == []
    reader.installed = (HUIHUI, DAVID)  # added in Windows' settings
    QApplication.sendEvent(say_it._recheck, QEvent(QEvent.Type.Timer))
    say_it._look_again()
    settle(qapp)
    assert said.text() == "▶ 中文"
    card.hide()


def test_saved_waits_for_the_reading_before_the_card_goes(
    qapp: QApplication, windows: CaptionWindows, say_it: SelectionReading
) -> None:
    card = offered(windows, say_it)
    buttons(card)[0].click()
    card.buttons[0].click()  # saved: "Saved to ..."
    card._go()  # the moment's up, but it reads
    assert card.isVisible() and say_it.reading is not None
    say_it.stop()
    card._go()
    assert not card.isVisible()


# -- in a transcript ----------------------------------------------------------------


def test_the_transcripts_menu_says_it_and_esc_stops_it(
    qapp: QApplication,
    both: tuple[CaptionWindows, Transcripts],
    say_it: SelectionReading,
    reader: Reader,
) -> None:
    both[1].use_say_it(say_it)
    shown = listed(both[1])
    _, start = find(shown, "电脑")
    _, end = find(shown, "游戏")
    transcript_drag(shown, start, end)
    menu = shown.menu_at(start.y())
    assert menu is not None
    into = cast(QMenu, menu.actions()[-1].menu())
    assert menu.actions()[-1].text() == "Say it"
    assert [a.text() for a in into.actions()] == ["▶ 中文", "▶ English"]
    into.actions()[0].trigger()
    ((chunks, _),) = reader.read_
    assert "电脑" in "".join(chunks)
    assert reader.spoken is not None
    reader.spoken(0, 0, 1)
    settle(qapp)
    assert shown.said_now  # lit in the transcript
    menu.deleteLater()
    again = shown.menu_at(start.y())
    assert again is not None
    stop = cast(QMenu, again.actions()[-1].menu()).actions()[0]
    assert stop.text() == "■ Stop"
    again.deleteLater()
    QApplication.sendEvent(
        shown,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        ),
    )
    settle(qapp)
    assert say_it.reading is None and shown.said_now == {}


def test_the_window_is_the_owner(
    windows: CaptionWindows, say_it: SelectionReading
) -> None:
    card = offered(windows, say_it)
    buttons(card)[0].click()
    reading = say_it.reading
    assert reading is not None and isinstance(reading[0], CaptionWindow)
    card.hide()


# -- a basic voice (polyglotic-hq 518) ------------------------------------------------

TINGTING = Voice("compact.zh-CN.Tingting", "Tingting", "zh-CN", Quality.BASIC)
"""A Mac's compact Chinese voice."""


@pytest.fixture
def basic(
    qapp: QApplication, reader: Reader
) -> Iterator[tuple[SelectionReading, list[str]]]:
    """Say it with a Mac's compact Chinese voice, and the languages silenced."""
    reader.installed = (TINGTING, DAVID)
    quiet: list[str] = []
    made = SelectionReading(reader, better=BetterVoice(lambda: quiet, quiet.append))
    yield made, quiet
    made.deleteLater()
    qapp.processEvents()


def test_the_card_says_a_better_voice_can_be_added_until_silenced(
    qapp: QApplication,
    windows: CaptionWindows,
    basic: tuple[SelectionReading, list[str]],
    reader: Reader,
) -> None:
    say_it, quiet = basic
    card = offered(windows, say_it)
    assert not card.better.isVisible()
    buttons(card)[1].click()  # English: Microsoft David, a good voice
    settle(qapp)
    assert not card.better.isVisible()
    buttons(card)[0].click()  # Chinese: Tingting, a basic one
    settle(qapp)
    assert card.better.isVisible() and "Manage Voices" in card.better.text()
    assert card.never_again.text() == "Don't show again for Chinese"
    assert card.dismiss.isVisible()
    card.dismiss.click()  # not ticked: only for now
    settle(qapp)
    assert not card.better.isVisible() and quiet == []
    say_it.stop()
    buttons(card)[0].click()  # every time it plays
    settle(qapp)
    assert card.better.isVisible()
    card.never_again.setChecked(True)
    card.dismiss.click()
    settle(qapp)
    assert quiet == ["zh"] and not card.better.isVisible()
    say_it.stop()
    buttons(card)[0].click()
    settle(qapp)
    assert len(reader.read_) == 4 and not card.better.isVisible()
    card.hide()


def test_the_transcript_says_it_in_a_box(
    qapp: QApplication,
    both: tuple[CaptionWindows, Transcripts],
    basic: tuple[SelectionReading, list[str]],
) -> None:
    say_it, quiet = basic
    both[1].use_say_it(say_it)
    shown = listed(both[1])
    _, start = find(shown, "电脑")
    _, end = find(shown, "游戏")
    transcript_drag(shown, start, end)
    menu = shown.menu_at(start.y())
    assert menu is not None
    cast(QMenu, menu.actions()[-1].menu()).actions()[0].trigger()
    menu.deleteLater()
    box = shown.findChild(QMessageBox)
    assert box is not None and box.isVisible() and "Manage Voices" in box.text()
    check = box.checkBox()
    assert check is not None and check.text() == "Don't show again for Chinese"
    check.setChecked(True)
    box.buttons()[0].click()
    settle(qapp)
    assert quiet == ["zh"] and say_it.notice is None
    say_it.stop()
