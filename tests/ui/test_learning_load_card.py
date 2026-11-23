"""Learning's card for the learning load (polyglotic-hq 324): the load in
numbers and a bar, its words in four lists with what each has been heard
and needs, the one-click check, feeding it by hand, and its rules - shown
only while the Lab's mode is on. The sample dictionary with made-up
ranks, made-up captions. Offscreen."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import Built, MemorySettingsStore, tools_for

from polyglotic_desktop.core.learning.load import Counting, LoadRules, Stage
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next import load_card
from polyglotic_desktop.ui_next.load_card import LoadCard, progress_text
from polyglotic_desktop.ui_next.views.load import Listed, LoadRow, LoadView, load_view

NOW = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)  # an hour on the fake clock
RANKS = {"人": 5, "这个": 20, "电脑": 1200, "游戏": 1300, "研究": 1400, "足球": 1500}


def learner(size: int = 3, step: int = 3, limit: int = 0) -> LearningTools:
    """A learner of 1,000 words with a load of the next `size`: 电脑, 游戏
    and 研究; 足球 is next to enter."""
    tools = tools_for(
        ChineseDictionary(chinese_sample(frequency_ranks=RANKS)), "hsk-2025"
    )
    tools.vocabulary.set_known_words(1000)
    tools.vocabulary.set_load_rules(LoadRules(size=size, step=step, stage_limit=limit))
    return tools


def entry(tools: LearningTools, word: str) -> EntryId:
    return tools.lookup(word)[0].entry_id


def hear(tools: LearningTools, text: str) -> None:
    hear.count = getattr(hear, "count", 0) + 1  # type: ignore[attr-defined]
    tools.vocabulary.caption_finished(
        f"heard-{hear.count}",  # type: ignore[attr-defined]
        tools.words_in(text),
        by_you=False,
    )


def seen(tools: LearningTools, listed: Listed, rows: int = 20) -> LoadView:
    view = load_view(tools.vocabulary.load, tools.describe, NOW, listed, rows)
    assert view is not None
    return view


def words(view: LoadView) -> list[str]:
    return [row.word for row in view.rows]


# -- what the card is given --------------------------------------------------------------


def test_no_card_while_the_mode_is_off() -> None:
    tools = learner()
    tools.vocabulary.set_load_rules(None)
    assert load_view(tools.vocabulary.load, tools.describe, NOW, Listed.READY) is None


def test_the_lists_hold_the_loads_words_with_what_each_was_heard_and_needs() -> None:
    tools = learner()
    hear(tools, "电脑 " * 4 + "游戏")  # 电脑: orange, heard once more; 游戏: red, once
    view = seen(tools, Listed.IN_LOAD)
    assert view.available and view.progress.stages == (2, 1, 0, 0)
    assert words(view) == ["电脑", "游戏", "研究"]  # furthest on first
    computer, game, study = view.rows
    assert (computer.stage, computer.heard, computer.step) == (Stage.ORANGE, 1, 3)
    assert (game.stage, game.heard) == (Stage.RED, 1)
    assert (study.stage, study.heard) == (Stage.RED, 0)
    assert computer.reading and computer.meaning
    assert words(seen(tools, Listed.NEXT)) == ["足球"]
    assert words(seen(tools, Listed.READY)) == []
    assert words(seen(tools, Listed.GRADUATED)) == []


def test_a_word_past_green_is_ready_to_check_and_graduates_to_its_own_list() -> None:
    tools = learner()
    hear(tools, "电脑 " * 12)
    ready = seen(tools, Listed.READY)
    assert words(ready) == ["电脑"] and ready.progress.ready == 1
    assert words(seen(tools, Listed.IN_LOAD)) == ["游戏", "研究"]
    tools.vocabulary.check_word(entry(tools, "电脑"), True)
    after = seen(tools, Listed.GRADUATED)
    assert words(after) == ["电脑"]
    assert (after.progress.graduated_week, after.progress.ready) == (1, 0)
    assert words(seen(tools, Listed.IN_LOAD)) == ["游戏", "研究", "足球"]  # refilled


def test_a_list_longer_than_its_rows_says_there_are_more() -> None:
    tools = learner()
    view = seen(tools, Listed.IN_LOAD, rows=2)
    assert len(view.rows) == 2 and view.more == 1
    assert seen(tools, Listed.IN_LOAD, rows=3).more == 0
    assert seen(learner(size=2), Listed.NEXT, rows=1).more == 1  # 研究, then 足球


def test_a_dictionary_without_frequencies_has_no_load_to_show() -> None:
    tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    tools.vocabulary.set_load_rules(LoadRules())
    view = seen(tools, Listed.IN_LOAD)
    assert not view.available and not view.rows


def test_what_a_word_needs_in_words(qapp: QApplication) -> None:
    row = LoadRow(EntryId("x"), "电脑", "diàn nǎo", "computer", Stage.ORANGE, 2, 3)
    assert progress_text(row) == "Orange: heard 2 of 3"
    held = LoadRow(EntryId("x"), "电脑", "", "", Stage.RED, 4, 3)
    assert held.held and "waiting for room" in progress_text(held)
    ready = LoadRow(EntryId("x"), "电脑", "", "", Stage.READY, 0, 3)
    assert progress_text(ready) == "Ready to check"
    assert progress_text(LoadRow(EntryId("x"), "电脑", "", "")) == ""


# -- the card ------------------------------------------------------------------------------


@pytest.fixture
def card(qapp: QApplication) -> Iterator[LoadCard]:
    made = LoadCard()
    yield made
    made.deleteLater()


def show(card: LoadCard, tools: LearningTools) -> None:
    card.show_load(seen(tools, card.listed, card.rows))


def test_the_card_says_the_load_in_numbers_with_a_bar(
    card: LoadCard, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load_card, "WEEK", timedelta(days=2))
    tools = learner()
    hear(tools, "电脑 " * 12 + "游戏 " * 3)
    show(card, tools)
    assert not card.isHidden()
    assert "3 of 3" in card.summary.text()  # one of them ready to check
    assert "Ready to check: 1" in card.summary.text()
    assert "Graduated in the last 2 days:" in card.summary.text()
    assert card.by_stage.text().split("  ·  ") == [
        "Red 1",
        "Orange 1",
        "Yellow 0",
        "Green 0",
    ]
    parts = card.bar.parts()
    assert [round(share, 2) for _, share, _ in parts] == [0.33, 0.33, 0.33]
    assert len({colour for _, _, colour in parts}) == 3  # red, orange, ready
    card.show_load(None)
    assert card.isHidden()  # the mode off: no card


def test_the_check_is_one_click_on_the_ready_list(card: LoadCard) -> None:
    tools = learner()
    hear(tools, "电脑 " * 12)
    show(card, tools)  # opens on Ready to check
    computer = entry(tools, "电脑")
    asked: list[tuple[str, bool]] = []
    card.checked.connect(lambda e, knows: asked.append((e, knows)))
    card.buttons[("not_yet", computer)].click()
    card.buttons[("know", computer)].click()
    assert asked == [(computer, False), (computer, True)]
    assert card.buttons[("know", computer)].accessibleName() == "I know this: 电脑"


def test_a_word_in_the_load_can_be_known_or_put_off_and_the_next_added(
    card: LoadCard,
) -> None:
    tools = learner()
    game, football = entry(tools, "游戏"), entry(tools, "足球")
    asked: list[tuple[str, object]] = []
    card.known.connect(lambda e: asked.append(("known", e)))
    card.not_now.connect(lambda e: asked.append(("not now", e)))
    card.add_wanted.connect(lambda e: asked.append(("add", e)))
    card.add_next_wanted.connect(lambda n: asked.append(("next", n)))
    card.listed_chosen.connect(lambda: show(card, tools))
    card.lists.choose(Listed.IN_LOAD)
    card.buttons[("know", game)].click()
    card.buttons[("not_now", game)].click()
    card.lists.choose(Listed.NEXT)
    card.buttons[("add", football)].click()
    card.add_next[1].click()
    assert asked == [
        ("known", game),
        ("not now", game),
        ("add", football),
        ("next", 25),
    ]


def test_show_more_asks_for_more_rows_and_another_list_starts_short(
    card: LoadCard,
) -> None:
    tools = learner()
    card.rows = 2
    card.lists.set_value(Listed.IN_LOAD)
    show(card, tools)
    assert not card.more.isHidden() and len(card.buttons) == 4
    again: list[int] = []
    card.listed_chosen.connect(lambda: again.append(card.rows))
    card.more.click()
    assert again[-1] > 2
    card.lists.choose(Listed.NEXT)
    assert again[-1] == 20


def test_an_empty_list_says_why_and_a_language_without_frequencies_says_so(
    card: LoadCard,
) -> None:
    show(card, learner())
    assert not card.none.isHidden() and "passed green" in card.none.text()
    plain = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    plain.vocabulary.set_load_rules(LoadRules())
    show(card, plain)
    assert "no word frequencies" in card.summary.text()
    assert card.lists.isHidden() and card.bar.isHidden() and card.none.isHidden()


def test_the_rules_are_shown_and_a_choice_asks_for_them_changed(card: LoadCard) -> None:
    tools = learner(size=510, step=2, limit=50)
    show(card, tools)
    assert card.size_box.currentData() == 510  # raised by hand: offered as it is
    assert card.step.value() == 2 and card.limit.currentData() == 50
    assert card.counting.currentData() == Counting.EVERY
    chosen: list[LoadRules] = []
    card.rules_chosen.connect(chosen.append)
    card.step.choose(5)
    card.counting.setCurrentIndex(card.counting.findData(Counting.DAY))
    card.counting.activated.emit(card.counting.currentIndex())
    assert chosen[0] == LoadRules(size=510, step=5, stage_limit=50)
    assert chosen[1].counting is Counting.DAY
    card.size_box.setCurrentIndex(card.size_box.findData(1000))
    card.size_box.activated.emit(card.size_box.currentIndex())
    assert chosen[-1].size == 1000


# -- in the app -----------------------------------------------------------------------------


def test_learning_shows_the_card_while_the_mode_is_on_and_keeps_its_rules(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({"learning": "zh"})
    built = Built(store, tools=True)
    try:
        tools = built.desktop.tools
        assert tools is not None
        page = built.hub.learning
        built.hub.window.go_to("learning")
        built.hub.window.show()
        qapp.processEvents()
        assert page.load.isHidden()  # the mode off: Learning as it was
        built.desktop.settings.update(caption_lab={"load": True})
        built.hub.show_load()
        assert not page.load.isHidden()
        page.load.step.choose(5)
        assert built.desktop.settings.value.load_rules_for("zh") == LoadRules(step=5)
        assert tools.vocabulary.load.rules == LoadRules(step=5)
        page.load.add_next[0].click()  # +10: the size goes up, and is kept
        assert built.desktop.settings.value.load_rules_for("zh") == LoadRules(510, 5)
        tools.vocabulary.set_status(tools.lookup("电脑")[0].entry_id, WordStatus.KNOWN)
        built.desktop.settings.update(caption_lab={"load": False})
        built.hub.show_load()
        assert page.load.isHidden()
    finally:
        built.close()
