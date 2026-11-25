"""Words' "What you've heard" (polyglotic-hq project 163): coverage of the
last 7 days with its reference lines in 155's words - never
"comprehension" - and no number under 200 words heard; the tiles side by
side only when there's room. Made-up learning, in memory; offscreen."""

from collections.abc import Iterator, Mapping

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import tools_for

from polyglotic_desktop.core.learning.bands import MetWord
from polyglotic_desktop.core.learning.coverage import Coverage
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.heard_card import (
    Tile,
    Tiles,
    coverage_lines,
    duration,
    listening_lines,
    percent,
    summary_line,
)
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.word_bands import BY_FREQUENCY, BY_LEVEL, WordBands
from polyglotic_desktop.ui_next.words_page import WordsPage


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settle() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def test_a_share_is_rounded_down_never_up_to_a_reference_line() -> None:
    assert percent(0.9499) == "94%"
    assert percent(0.95) == "95%"
    assert percent(0.98) == "98%"
    assert percent(0.29) == "29%"  # not 28: 0.29 * 100 is 28.999...


def test_the_coverage_tile_in_words_with_its_reference_lines() -> None:
    number, meaning, note = coverage_lines(Coverage(known=910, deck=30, new=60))
    assert number == "91%"
    assert meaning == "of the words you heard, you knew"
    assert note == (
        '1 word in 11 was new to you. 95% is "can follow, with effort"; '
        '98% "comfortable, guess the rest".'
    )
    for line in (number, meaning, note):
        assert "comprehen" not in line.lower() and "understand" not in line.lower()


def test_every_word_known_and_too_few_words() -> None:
    _, _, note = coverage_lines(Coverage(known=500))
    assert note.startswith("Every word you heard, you knew.")
    _, _, note = coverage_lines(Coverage(new=500))
    assert note.startswith("Every word you heard was new to you.")
    _, _, note = coverage_lines(Coverage(known=100, new=300))  # not "1 in 1"
    assert note.startswith("Most words you heard were new to you.")
    _, _, note = coverage_lines(Coverage(known=200, new=200))
    assert note.startswith("1 word in 2 was new to you.")
    number, meaning, note = coverage_lines(Coverage(known=150, new=49))
    assert number == "" and meaning == "Not enough heard yet"
    assert "200 words in 7 days" in note


@pytest.fixture
def tools() -> LearningTools:
    zh = ChineseDictionary(chinese_sample())
    tools = tools_for(zh, "hsk-2025")
    tools.vocabulary.set_level(Level("hsk-2025", 6))
    return tools


def test_words_shows_the_last_7_days_coverage_as_captions_finish(
    qapp: QApplication, tools: LearningTools
) -> None:
    page = WordsPage(tools, None)
    tools.changed.connect(page.learning_changed)
    page.resize(900, 700)
    page.show()
    settle()
    tile = page.first.heard.coverage
    assert tile.number.isHidden() and tile.meaning.text() == "Not enough heard yet"
    vocabulary = tools.vocabulary
    vocabulary.set_status(tools.lookup("电脑")[0].entry_id, WordStatus.LEARNING)
    for word in ("研究", "生命"):
        vocabulary.set_status(tools.lookup(word)[0].entry_id, WordStatus.KNOWN)
    for n in range(100):  # 研究 生命 known, 电脑 in the deck: 2 of 3
        vocabulary.caption_finished(f"c{n}", tools.words_in("研究生命电脑"), False)
    page.refresh()
    assert vocabulary.coverage() == Coverage(known=200, deck=100)
    assert tile.number.text() == "66%" and not tile.number.isHidden()
    assert tile.note.text().startswith("1 word in 3 was new to you.")
    assert tile.accessibleName() == "66% of the words you heard, you knew"
    page.close()


def test_the_tiles_stack_when_narrow(qapp: QApplication) -> None:
    tiles = Tiles([Tile(f"t{n}", "Tile") for n in range(3)])
    tiles.resize(1000, 300)
    tiles.show()
    settle()
    assert tiles.side_by_side
    tiles.resize(420, 300)
    settle()
    assert not tiles.side_by_side
    tiles.close()


def test_listening_in_hours_and_minutes() -> None:
    assert duration(0) == "0 min"
    assert duration(59) == "0 min"
    assert duration(52 * 60 + 30) == "52 min"
    assert duration(3 * 3600) == "3 h"
    assert duration(12 * 3600 + 40 * 60 + 59) == "12 h 40 min"
    assert duration(1234 * 3600) == "1,234 h"
    number, meaning, note = listening_lines(45600, 11400)
    assert (number, meaning) == ("12 h 40 min", "3 h 10 min in the last 7 days")
    assert note == pc_or_mac(
        "Time captions were on, counted on this PC.",
        "Time captions were on, counted on this Mac.",
    )


def test_words_shows_listening_as_captions_come(
    qapp: QApplication, tools: LearningTools
) -> None:
    page = WordsPage(tools, None)
    page.show()
    settle()
    vocabulary = tools.vocabulary
    for _ in range(31):  # 30 gaps of 2 s: one minute
        vocabulary.listened("video")
        vocabulary._clock.advance(seconds=2)  # type: ignore[attr-defined]
    page.refresh()
    assert page.first.heard.listening.number.text() == "1 min"
    assert page.first.heard.listening.meaning.text() == "1 min in the last 7 days"
    page.close()


def test_the_summary_line_says_what_there_is() -> None:
    assert summary_line(0, Coverage(), 0) == ""
    assert summary_line(1243, Coverage(), 30) == "1,243 met"
    assert (
        summary_line(1243, Coverage(known=910, new=90), 45600)
        == "1,243 met · coverage 91% · 12 h 40 min"
    )


def _met(rank: int, level: int | None, status: WordStatus) -> MetWord:
    return (EntryFacts(EntryId(f"t:{rank}"), level, rank, False), status)


def test_the_bands_by_frequency_and_by_hsk_level(qapp: QApplication) -> None:
    bands = WordBands()
    met = [
        _met(5, 1, WordStatus.KNOWN),
        _met(800, 2, WordStatus.LEARNING),
        _met(1200, 3, WordStatus.NEW),
        _met(20000, None, WordStatus.NEW),
    ]
    sizes = ([1000, 1000, 3000, 5000], {1: 300, 2: 200, 3: 500})
    bands.set_words(met, sizes, ("1", "2", "3", "4", "5", "6", "7-9"))
    bands.show()
    settle()
    shown = [r for r in bands.rows if not r.isHidden()]
    assert [r.name.text() for r in shown] == [
        "Top 1,000",
        "1,001-2,000",
        "2,001-5,000",
        "5,001-10,000",
        "Rarer",
    ]
    assert shown[0].accessibleName() == (
        "Top 1,000: 1 known · 1 in deck · 0 new · 998 not heard"
    )
    assert shown[-1].counts.text() == "0 known · 0 in deck · 1 new"
    assert shown[-1].bar.isHidden()  # the rarer words: no length to fill
    assert not bands.view.isHidden()
    bands.view.choose(BY_LEVEL)
    shown = [r for r in bands.rows if not r.isHidden()]
    assert [r.name.text() for r in shown] == ["HSK 1", "HSK 2", "HSK 3"]
    assert shown[2].counts.text() == "0 known · 0 in deck · 1 new · 499 not heard"
    assert not shown[2].bar.isHidden()
    bands.set_words(met, (sizes[0], {}), ())  # an English learner: no levels
    assert bands.view.isHidden() and bands.view.value() == BY_FREQUENCY
    assert len([r for r in bands.rows if not r.isHidden()]) == 5
    bands.close()


def test_the_bands_sizes_are_read_once_per_scheme(tools: LearningTools) -> None:
    asked: list[str] = []
    dictionary = tools.dictionary
    original = dictionary.words_at_levels

    def counting(scheme_id: str) -> Mapping[int, int]:
        asked.append(scheme_id)
        return original(scheme_id)

    dictionary.words_at_levels = counting  # type: ignore[method-assign]
    tools.band_sizes()
    tools.band_sizes()
    assert asked == ["hsk-2025"]
    tools.vocabulary.set_level(Level("hsk-2021", 3))
    tools.band_sizes()
    assert asked == ["hsk-2025", "hsk-2021"]


def test_words_shows_the_summary_line_and_words_met(
    qapp: QApplication, tools: LearningTools
) -> None:
    page = WordsPage(tools, None)
    page.show()
    settle()
    assert page.first.summary.isHidden()  # nothing heard yet
    tools.vocabulary.caption_finished("c1", tools.words_in("研究生命电脑"), False)
    page.refresh()
    assert page.first.heard.met.number.text() == "3"
    assert page.first.heard.met.meaning.text() == "+3 new in the last 7 days"
    assert page.first.summary.text() == "3 met" and not page.first.summary.isHidden()
    page.close()
