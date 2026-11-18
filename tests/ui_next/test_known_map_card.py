"""Learning's map of the language (polyglotic-hq 489): every common word
one square, in the colour of how well the learner knows it; the counts of
red, between and green, the share of what's heard that's green, how they
moved this week; and what pointing at a square says. Made-up words, and
the app's own wiring over a made-up ranked dictionary."""

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from tests.learning.fakes import Clock, MemoryLearningStore, facts
from tests.tools.test_learner_start import ranked_dictionary
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.known_chance import Band
from polyglotic_desktop.core.learning.known_map import MAP_WORDS
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine, WordStatus
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.known_map_card import (
    SQUARE,
    KnownMapCard,
    WordsReader,
)
from polyglotic_desktop.ui_next.views.known_colours import known_colour
from polyglotic_desktop.ui_next.views.known_map import (
    ROW,
    KnownMapView,
    known_map_view,
)
from polyglotic_desktop.ui_next.views.lab import Palette

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
WORDS = [(rank, facts(f"w{rank}", level=None, rank=rank)) for rank in range(1, 1001)]
BY_ID = {f.entry_id: f for _, f in WORDS}


def learner(line: int, clock: Clock | None = None) -> Vocabulary:
    """A learner who set their line a fortnight ago; it's now a day ago."""
    clock = clock or Clock(NOW - timedelta(days=14))
    vocab = Vocabulary(
        MemoryLearningStore(),
        lambda entry_id, scheme: BY_ID.get(entry_id),
        "hsk-2025",
        clock,
    )
    vocab.set_known_words(line)
    clock.advance(days=13)
    return vocab


def view_of(vocab: Vocabulary, palette: Palette = Palette.RED_GREEN) -> KnownMapView:
    return known_map_view(
        "Mandarin", WORDS, vocab.chances, vocab.chances_as_of, NOW, palette
    )


def shown_wide(card: KnownMapCard, qapp: QApplication) -> None:
    """The card shown (offscreen) wide enough for 3 px squares."""
    card.resize(ROW * SQUARE + 60, 500)
    card.show()
    qapp.processEvents()
    assert card.picture.square == SQUARE


def test_the_view_counts_each_band_and_keeps_the_order(qapp: QApplication) -> None:
    view = view_of(learner(100))
    assert view.places == list(range(1, 1001))
    assert view.rows == 5  # 1,000 words in rows of 200
    bands = [c.band for c in view.chances if c is not None]
    assert view.now.mastered == bands.count(Band.MASTERED) > 0
    assert view.now.unknown == bands.count(Band.UNKNOWN) > 0
    # the commonest are green, the rarest red: the map reads left to right
    first, last = view.chances[0], view.chances[-1]
    assert first is not None and first.band is Band.MASTERED
    assert last is not None and last.band is Band.UNKNOWN
    assert view.now == view.week_ago  # nothing happened this week


def test_the_card_says_the_counts_the_share_and_the_week(qapp: QApplication) -> None:
    vocab = learner(100)
    vocab.set_status(WORDS[499][1].entry_id, WordStatus.KNOWN)  # this week
    card = KnownMapCard()
    try:
        card.show_map(view_of(vocab), lambda _: "")
        assert card.title is not None
        assert card.title.text() == "How well you know Mandarin"
        counts = card.counts.text()
        view = card.picture.view
        assert view is not None
        assert f"{view.now.mastered:,} words green" in counts
        assert f"{view.now.unknown:,} words red" in counts
        assert "of what you hear is green" in card.heard.text()
        assert card.week.text() == "In the last 7 days: +1 green, −1 red."
        assert "20,000 most common words" in card.about.text()
        card.picture.resize(ROW * SQUARE + 40, 10)  # room for 3 px squares
        card.picture.fit()
        assert card.picture.square == SQUARE
        assert card.picture.height() == view.rows * SQUARE
        card.picture.resize(ROW * 2 + 1, 10)  # narrower: 2 px, never wider
        card.picture.fit()
        assert card.picture.square == 2
        assert card.picture.height() == view.rows * 2
    finally:
        card.deleteLater()


def test_each_square_is_its_words_colour(qapp: QApplication) -> None:
    card = KnownMapCard()
    try:
        view = view_of(learner(300), Palette.ORANGE_BLUE)
        card.show_map(view, lambda _: "")
        shown_wide(card, qapp)
        picture = card.picture.grab().toImage()
        panel = style.current()["SURFACE"]
        for index in (0, 299, 999):
            chance = view.chances[index]
            assert chance is not None
            x = (index % ROW) * SQUARE + 1
            y = (index // ROW) * SQUARE + 1
            wanted = QColor(
                known_colour(round(chance.chance * 20) / 20, Palette.ORANGE_BLUE, panel)
            )
            assert picture.pixelColor(x, y).name() == wanted.name(), index
    finally:
        card.deleteLater()


def test_pointing_at_a_square_says_its_word_and_why(qapp: QApplication) -> None:
    clock = Clock(NOW - timedelta(days=14))
    vocab = learner(300, clock)
    rare = WORDS[899][1]
    vocab.caption_finished("c1", [_in_line(rare)], by_you=False)
    clock.advance(days=1)  # today's hearing counts from tomorrow
    card = KnownMapCard()
    try:
        card.show_map(view_of(vocab), lambda e: f"word-{e}")
        shown_wide(card, qapp)
        picture = card.picture
        index = picture.index_at(QPoint(899 % ROW * SQUARE + 1, 899 // ROW * SQUARE))
        assert index == 899
        said = picture.text_at(899)
        assert said is not None
        lines = said.split("\n")
        assert lines[0] == f"word-{rare.entry_id} · No. 900"
        assert lines[1].startswith("About ") and "likely you know it" in lines[1]
        assert "Past the about 300 words you know." in lines
        assert "Heard on 1 day." in lines
        assert picture.text_at(5) is not None
        assert "Within the about 300 words you know." in (picture.text_at(5) or "")
        assert picture.index_at(QPoint(ROW * SQUARE + 2, 0)) is None
    finally:
        card.deleteLater()


def test_a_language_without_ranks_says_so(qapp: QApplication) -> None:
    card = KnownMapCard()
    try:
        card.show_map(None, lambda _: "")
        assert "doesn't say how common" in card.about.text()
        assert card.picture.height() == 0
    finally:
        card.deleteLater()


def test_the_words_are_read_off_the_interface_thread(qapp: QApplication) -> None:
    reader = WordsReader()
    threads: list[str] = []
    got: list[tuple[str, list[tuple[int, EntryFacts]]]] = []
    reader.read.connect(got.append)

    def read() -> list[tuple[int, EntryFacts]]:
        threads.append(threading.current_thread().name)
        return [(n, facts(f"x{n}", level=None, rank=n)) for n in range(MAP_WORDS + 5)]

    reader.start("key", read)
    reader.start("again", read)  # one read at a time
    reader.wait()
    qapp.processEvents()
    assert threads == ["known-map"]
    assert len(got) == 1
    key, words = got[0]
    assert key == "key" and len(words) == MAP_WORDS  # at most the map's
    reader.deleteLater()


def test_learning_shows_the_map_of_the_language_in_use(
    qapp: QApplication, tmp_path: Path
) -> None:
    """The app's own wiring: a ranked dictionary's words read once, off
    the interface thread, then the map - and a status changed shows on it
    a second later, or when the page shows again."""
    folder = tmp_path / "dictionaries"
    folder.mkdir()
    ranked_dictionary(folder / "cedict.sqlite", 600)
    tools, store = main.learner_tools(folder, False, tmp_path / "data")
    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    try:
        built.desktop.tools = tools
        hub = built.hub
        hub.window.show()
        hub.window.go_to("learning")
        qapp.processEvents()
        tools.vocabulary.set_known_words(100)
        card = hub.learning.known_map
        hub.show_known_map()
        assert "Reading" in card.about.text()
        hub._map_reader.wait()
        qapp.processEvents()
        view = card.picture.view
        assert view is not None and len(view.places) == 600
        green = view.now.mastered
        tools.vocabulary.set_status(
            EntryId(view.entries[300]), WordStatus.KNOWN
        )  # far past the line
        hub.show_known_map()  # as the page shows again
        again = card.picture.view
        assert again is not None and again.now.mastered == green + 1
    finally:
        built.close()
        store.close()


def _in_line(word: EntryFacts) -> WordInLine:
    return WordInLine(0, 1, word)
