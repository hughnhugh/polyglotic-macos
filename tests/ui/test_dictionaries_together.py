"""Chinese and English learned together: the card for a word comes from
that word's language's dictionary, every time (polyglotic-hq 337,
decision 0129) - whichever is main, whatever its row's language says.

A caption has one language, and each of its rows was looked up in that
language's dictionary alone. A mixed line - an English word in a Chinese
line, a Chinese name in an English one, or a line the speech model named
wrongly - then gave "Chinese for it" for an English word with English
learned, and nothing at all for a Chinese word: not even found to hover.

Through the real lookup path: `main.learner_tools` and `main.tools_beside`
on dictionary files written from the samples, the real `Lookup`.
Made-up text; offscreen."""

import random
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import FakeDictionaryFile, english_sample
from tests.test_sqlite_dictionary import write_sample

from polyglotic_desktop import main
from polyglotic_desktop.adapters.background_learning import BackgroundLearningStore
from polyglotic_desktop.adapters.sqlite_dictionary import (
    SqliteDictionary,
    write_dictionary,
)
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.scripts import word_script
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import LongLines, RowKind
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause, finished
from polyglotic_desktop.ui_next.caption_layout import cursor_x
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill
from polyglotic_desktop.ui_next.views.lookup import Lookup, Shows

ROWS: list[tuple[str | None, str]] = [
    ("zh", "这个电脑"),
    ("zh", "这个English游戏"),  # an English word in a Chinese line
    ("zh-hant", "這個電腦還錢"),
    ("en", "I run to 北京"),  # a Chinese word in an English line
    ("en", "研究生"),  # a Chinese line the speech model named English
    ("en", "they keep running left"),
    (None, "足球 awkward"),  # a line whose language has no code
    ("en", "I keep руку"),  # a Russian word in an English line
    ("zh", "这个руку"),  # and in a Chinese one
    ("ru", "дай руку left 北京"),  # English and Chinese in a Russian line
]

RUSSIAN = FakeDictionaryFile(
    [
        EntryRecord("wiktru:1", "рука", "", "рука́", ("(noun) hand",), 300),
        EntryRecord("wiktru:2", "дать", "", "да́ть", ("(verb) to give",), 90),
    ],
    {"рука": ["wiktru:1"], "дать": ["wiktru:2"]},
    lemmas={"руку": "рука", "дай": "дать"},
    form_readings={"руку": "ру́ку"},
)
"""A Russian pack's entries, Wiktionary-style (327's packs)."""


def dictionaries(folder: Path) -> Path:
    folder.mkdir()
    write_sample(folder / "cedict.sqlite")
    english = english_sample()
    write_dictionary(
        folder / "ecdict.sqlite",
        {"dictionary": "ecdict"},
        list(english.by_id.values()),
        english.forms,
        lemmas=english.lemmas,
    )
    return folder


def opened(
    tmp_path: Path, main_language: str, also: tuple[str, ...]
) -> tuple[LearningTools, list[BackgroundLearningStore | SqliteDictionary]]:
    """The tools as `main` opens them: the main language's, then every
    other full language learned beside it, with Russian's pack opened as
    `main.open_pack` opens a downloaded one (327), and every language
    learned told to the tools (`set_choices`, as the app does). With them,
    what to close."""
    folder = dictionaries(tmp_path / "dictionaries")
    path = folder / "wiktru-en.sqlite"
    write_dictionary(
        path,
        {"dictionary": "wiktru"},
        list(RUSSIAN.by_id.values()),
        RUSSIAN.forms,
        lemmas=RUSSIAN.lemmas,
        form_readings=RUSSIAN.form_readings,
    )
    pack, file = main.open_pack(path, "ru")
    data = tmp_path / "data"
    tools, store = main.learner_tools(folder, main_language == "en", data, {"ru": pack})
    languages = LearningLanguages.of(main_language, also)
    beside = main.tools_beside(tools, folder, data, languages)
    tools.set_choices(LanguageChoices(), {c: LanguageChoices() for c in languages.all})
    return tools, [store, *(s for _, s in beside), file]


@pytest.fixture(params=["zh", "en"])
def both(
    qapp: QApplication, tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[LearningTools]:
    """Chinese and English learned, either main - and Russian, with its
    pack: its learning data opens beside theirs (decision 0175)."""
    main_language = request.param
    other = "en" if main_language == "zh" else "zh"
    tools, stores = opened(tmp_path, main_language, (other, "ru"))
    assert [t.language for t in tools.every] == [main_language, other, "ru"]
    yield tools
    for store in stores:
        store.close()


def words(tools: LearningTools) -> list[tuple[str, str, tuple[int, int], str | None]]:
    """Every word a hover finds in `ROWS`, with its row: (word, row, span,
    row's language)."""
    found = []
    for language, text in ROWS:
        index = 0
        while index < len(text):
            span = tools.word_at(text, index, language)
            if span is None or span[0] >= span[1]:
                index += 1
                continue
            found.append((text[span[0] : span[1]], text, span, language))
            index = span[1]
    return found


OWN = {"han": "zh", "cyrillic": "ru", "latin": "en"}
"""The dictionary each script's words come from here."""


def from_own_dictionary(lookup: Lookup, word: str) -> None:
    """The card shown is `word`'s entry in its own language's dictionary:
    CC-CEDICT, ECDICT, or Russian's pack (a basic card, said in Russian)."""
    own = OWN[word_script(word) or ""]
    card = lookup.card()
    assert card.shows is Shows.ENTRY, word
    if own == "ru":
        assert card.basic and card.language == "ru" and card.readings, word
        return
    assert not card.basic and lookup.is_chinese == (own == "zh"), word
    entry = lookup.entry()
    assert entry is not None
    assert entry.entry_id.startswith("cedict:" if own == "zh" else "ecdict:"), word


def test_every_word_of_a_mixed_or_misnamed_line_is_found(both: LearningTools) -> None:
    found = [(word, text) for word, text, *_ in words(both)]
    for word, text in (
        ("北京", "I run to 北京"),
        ("研究生", "研究生"),
        ("English", "这个English游戏"),
        ("游戏", "这个English游戏"),
        ("足球", "足球 awkward"),
        ("awkward", "足球 awkward"),
        ("руку", "I keep руку"),
        ("руку", "这个руку"),
        ("left", "дай руку left 北京"),
        ("北京", "дай руку left 北京"),
    ):
        assert (word, text) in found


@pytest.mark.parametrize(
    ("word", "row", "language"),
    [
        ("English", "这个English游戏", "zh"),
        ("北京", "I run to 北京", "en"),
        ("研究生", "研究生", "en"),
        ("足球", "足球 awkward", None),
        ("awkward", "足球 awkward", None),
        ("电脑", "这个电脑", "zh"),
        ("run", "I run to 北京", "en"),
        ("руку", "I keep руку", "en"),
        ("руку", "这个руку", "zh"),
        ("руку", "дай руку left 北京", "ru"),
        ("left", "дай руку left 北京", "ru"),
        ("北京", "дай руку left 北京", "ru"),
    ],
)
def test_the_card_is_from_the_words_own_languages_dictionary(
    both: LearningTools, word: str, row: str, language: str | None
) -> None:
    lookup = Lookup(both)
    at = (row.index(word), row.index(word) + len(word))
    for pinned in (False, True):
        lookup.show(word, LookupContext(row), pinned, at, language)
        from_own_dictionary(lookup, word)


def test_a_word_is_saved_in_its_own_languages_learning_data(
    both: LearningTools,
) -> None:
    """A Chinese word pinned in an English row: saved in Chinese's words,
    not English's - and the reverse."""
    zh, en = both.of("zh"), both.of("en")
    lookup = Lookup(both)
    lookup.show("北京", LookupContext("I run to 北京"), True, (9, 11), "en")
    saved = lookup.add_to_deck()
    assert saved is not None
    lookup.show("English", LookupContext("这个English游戏"), True, (2, 9), "zh")
    english = lookup.add_to_deck()
    assert english is not None
    assert zh.vocabulary.status(zh.facts(saved)).status.value == "learning"
    assert en.vocabulary.status(en.facts(english)).status.value == "learning"
    assert zh.vocabulary.saved_word(english.entry_id) is None
    assert not any(e == saved.entry_id for e in en.vocabulary.met_entries())


def test_with_one_language_learned_a_row_keeps_its_own(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Only Chinese learned: an English word in a Chinese row is still
    "Chinese for it" (306), and nothing moves to a dictionary not open."""
    tools, stores = opened(tmp_path, "zh", ())
    try:
        assert tools.word_language("English", "zh") == "zh"
        lookup = Lookup(tools)
        lookup.show("English", LookupContext("这个English游戏"), True, (2, 9), "zh")
        assert lookup.card().shows is Shows.CHINESE_FOR
    finally:
        for store in stores:
            store.close()


def test_a_russian_word_stays_its_rows_where_russian_isnt_learned(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Russian's pack on this PC but Russian not learned (stopped, say):
    nothing moves to it - a Cyrillic word in an English row is English's
    to answer, as before."""
    tools, stores = opened(tmp_path, "en", ("zh",))
    try:
        assert "ru" in tools.basic
        assert tools.word_language("руку", "en") == "en"
        lookup = Lookup(tools)
        lookup.show("руку", LookupContext("I keep руку"), True, (7, 11), "en")
        assert not lookup.card().basic
    finally:
        for store in stores:
            store.close()


def test_a_few_hundred_lookups_in_mixed_order_while_both_read_ahead(
    both: LearningTools,
) -> None:
    """As at the start: both dictionaries read ahead on threads of their
    own (`prepare`) while the interface thread looks words up - Chinese,
    English and Russian, in mixed order - and another thread reads the same
    words through the same tools.
    Every card comes from its word's own language's dictionary; every
    read gives the answer it gives once all is settled."""
    found = words(both)
    random.seed(337)
    order = [random.choice(found) for _ in range(400)]
    expected = {
        (word, language): [
            e.entry_id for e in both.lookup(word, both.word_language(word, language))
        ]
        for word, _, _, language in found
    }
    elsewhere: list[tuple[tuple[str, str | None], list[str]]] = []

    def reads() -> None:
        for word, _, _, language in reversed(order):
            here = both.word_language(word, language)
            elsewhere.append(
                ((word, language), [e.entry_id for e in both.lookup(word, here)])
            )

    both.prepare()
    other = threading.Thread(target=reads)
    other.start()
    lookup = Lookup(both)
    for n, (word, row, span, language) in enumerate(order):
        lookup.show(word, LookupContext(row), n % 3 == 0, span, language)
        from_own_dictionary(lookup, word)
        entry = lookup.entry()  # None for a basic card: nothing kept
        settled = expected[(word, language)][0]
        assert entry is None or entry.entry_id == settled, (word, language)
        if n % 50 == 0:
            QApplication.processEvents()
    other.join(10)
    assert not other.is_alive()
    assert len(elsewhere) == len(order)
    assert all(ids == expected[key] for key, ids in elsewhere)


def test_a_chinese_word_in_an_english_caption_is_clicked_in_a_caption_window(
    both: LearningTools, qapp: QApplication
) -> None:
    """The user's way: a caption window, a click on the word - the card
    pinned from Chinese's dictionary; and an English word in a Chinese
    line from English's."""
    from tests.ui_next.test_lookup_card import AREA, click, find

    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=both)
    try:
        windows.set_captioned([("app", APP)])
        en, zh = Language("en"), Language("zh")
        windows.apply(
            finished("c1", clause("I run to 北京", "我跑到北京", into=zh), language=en)
        )
        windows.apply(
            finished("c2", clause("这个English游戏", "This English game"), language=zh)
        )
        shown = windows.windows["app"]
        shown.setGeometry(480, 600, 960, 360)
        qapp.processEvents()
        shown.canvas.repaint()
        card = windows.card
        assert card is not None
        for word, chinese in (("北京", True), ("English", False)):
            _, point = find(shown, word)
            click(shown, point)
            assert card.request is not None and card.request.word == word
            assert card.model.card().shows is Shows.ENTRY
            assert card.model.is_chinese is chinese
            card.close_card()
    finally:
        windows.close()


LAYOUTS = {
    "today's": CaptionLab(),
    "display new lines": CaptionLab(),
    "new": CaptionLab(flow=True, fill=Fill.PAIRED),
    "new, run on": CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True),
    "new, lined up": CaptionLab(flow=True, fill=Fill.PAIRED, aligned=True),
    "new, both": CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True, aligned=True),
}
"""Today's layout and the Lab's New layout with each of its two choices
(polyglotic-hq 340, decision 0132)."""


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_every_word_of_a_mixed_caption_opens_its_own_languages_card_in_every_layout(
    both: LearningTools, qapp: QApplication, layout: str
) -> None:
    """The user, 2026-11-15, on a preview with the New layout: "The multiple
    dictionaries is not working in caption window" (polyglotic-hq 353).
    Every word of the original rows of mixed and misnamed captions - found
    where it's drawn, as a hover or a click finds it (`_marked_at`), and
    looked up as a click pins it - opens its own script's language's
    entry, in every layout: the New layout hit-tests and looks up through
    the same word split as today's."""
    from tests.ui_next.test_card_stack import Clock
    from tests.ui_next.test_lookup_card import AREA

    windows = CaptionWindows(None, MIC, lambda: [AREA], learner=both)
    try:
        windows.set_captioned([("app", APP)])
        windows.set_look(CaptionLook(lab=LAYOUTS[layout]))
        shown = windows.windows["app"]
        clock = Clock()
        shown.clock = clock
        wrapped = layout in ("today's", "display new lines")
        if layout == "display new lines":
            shown.set_presets(
                replace(shown.preset_menu, long_lines=LongLines.DISPLAY_NEW_LINES)
            )
        said_last = "they keep running left"
        if wrapped:
            said_last = " ".join([said_last] * 4 + ["北京"])
        en, zh = Language("en"), Language("zh")
        for key, said, meant, into, language in (
            ("c1", "I run to 北京", "我跑到北京", zh, en),
            ("c2", "这个English游戏", "This English game", en, zh),
            ("c3", "研究生", "graduate student", zh, en),  # Chinese, named English
            ("c4", said_last, "他们一直往左跑", zh, en),
        ):
            windows.apply(
                finished(key, clause(said, meant, into=into), language=language)
            )
        shown.setGeometry(480, 100, 650 if wrapped else 1200, 740)
        qapp.processEvents()
        shown.grab()
        clock.now += 3  # let newly wrapped rows reach their painted positions
        shown.grab()
        flow = shown.canvas.engine.style.flow
        assert flow is not None
        assert flow.share == (layout != "today's")
        card = windows.card
        assert card is not None
        opened: dict[str, bool] = {}
        continuation = False
        for caption, laid, rect in shown.canvas.placed:
            for row in laid.rows:
                if row.row.kind is not RowKind.ORIGINAL:
                    continue
                text = row.row.text
                continuation |= row.start > 0
                for at, char in enumerate(text):
                    if char == " ":
                        continue
                    line = row.layout.lineForTextPosition(at)
                    point = QPointF(
                        rect.x() + cursor_x(line, at) + 2,
                        rect.y() + row.top + line.y() + line.height() / 2,
                    )
                    marked = shown._marked_at(point)
                    assert marked is not None, (layout, text, at)  # found to hover
                    found = shown.word_at(marked)
                    assert found is not None
                    source = caption.rows[row.index].text
                    assert marked.key == caption.key and marked.row == row.index
                    assert marked.start <= row.start + at < marked.end, (
                        source,
                        row.start,
                        at,
                        point,
                        marked,
                    )
                    assert found.word == source[marked.start : marked.end]
                    if found.word in opened:
                        continue
                    card.pin(found, shown)
                    assert card.model.card().shows is Shows.ENTRY, (layout, found.word)
                    opened[found.word] = card.model.is_chinese
                    card.close_card()
        if wrapped:
            assert continuation
        assert opened == {
            "I": False, "run": False, "to": False, "北京": True,
            "这个": True, "English": False, "游戏": True,
            "研究生": True,
            "they": False, "keep": False, "running": False, "left": False,
        }  # fmt: skip
    finally:
        windows.close()


def test_a_language_added_while_the_other_is_open_takes_its_words_at_once(
    qapp: QApplication, tmp_path: Path
) -> None:
    """English alone, then Chinese added during the run (`open_added`'s
    `tools_beside`): a Chinese word in an English line is found and looked
    up in Chinese's from then on - no restart."""
    tools, stores = opened(tmp_path, "en", ())
    try:
        assert tools.word_at("I run to 北京", 9, "en") is None
        folder, data = tmp_path / "dictionaries", tmp_path / "data"
        added = LearningLanguages.of("en", ("zh",))
        stores += [s for _, s in main.tools_beside(tools, folder, data, added)]
        assert tools.word_at("I run to 北京", 9, "en") == (9, 11)
        lookup = Lookup(tools)
        lookup.show("北京", LookupContext("I run to 北京"), True, (9, 11), "en")
        assert lookup.card().shows is Shows.ENTRY and lookup.is_chinese
    finally:
        for store in stores:
            store.close()
