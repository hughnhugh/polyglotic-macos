"""A selection in a caption window, as places in its captions (polyglotic-hq
340's design, 358): the words it holds and their text, across clauses,
sides and captions, and through the captions' updates. Made-up captions."""

from polyglotic_desktop.core.listening.caption_model import (
    CaptionModel,
    Words,
    caption_model,
)
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.selection import (
    Place,
    Selection,
    selected,
    selected_text,
)
from polyglotic_desktop.ui.recorded_captions import (
    COMPUTER,
    FRUIT,
    GAME,
    OKAY,
    RESTART,
    WEEKEND,
    finished,
    live,
)

EN = Language("en")
SAID, MEANT = RowKind.ORIGINAL, RowKind.TRANSLATION


def models(*updates: object) -> list[CaptionModel]:
    history = CaptionHistory()
    for update in updates:
        history.apply(update)  # type: ignore[arg-type]
    return [caption_model(caption, EN) for caption in history.captions]


def three() -> list[CaptionModel]:
    return models(
        finished("a", WEEKEND, OKAY), finished("b", COMPUTER, RESTART),
        finished("c", GAME),
    )  # fmt: skip


def test_within_a_clause_it_is_a_phrase_of_its_words() -> None:
    a, _, _ = three()
    chosen = Selection(Place(a.key, 0, 2, SAID), Place(a.key, 0, 4, SAID))
    assert chosen.one_clause and not chosen.both_sides
    assert selected(three(), chosen) == [(a.key, Words(SAID, 0, 2, 4))]
    assert selected_text(three(), chosen) == "周末"


def test_across_clauses_and_captions_on_one_side() -> None:
    """From part way through the first caption's second clause to part way
    through the third caption: a caption a line, its clauses joined."""
    captions = three()
    a, b, c = captions
    chosen = Selection(Place(a.key, 1, 0, SAID), Place(c.key, 0, 4, SAID))
    assert not chosen.one_clause
    assert selected_text(captions, chosen) == (
        "好不好？\n我的电脑又卡了，我得重新启动。\n这个游戏"
    )
    assert [key for key, _ in selected(captions, chosen)] == [
        a.key, b.key, b.key, c.key,
    ]  # fmt: skip


def test_dragged_backwards_it_holds_the_same_words() -> None:
    captions = three()
    a, _, c = captions
    forwards = Selection(Place(a.key, 1, 0, SAID), Place(c.key, 0, 4, SAID))
    backwards = Selection(forwards.focus, forwards.anchor)
    assert selected(captions, backwards) == selected(captions, forwards)


def test_translations_alone_are_spaced_as_they_read() -> None:
    captions = three()
    a, b, _ = captions
    start = WEEKEND.translations[EN].index("this")
    chosen = Selection(Place(a.key, 0, start, MEANT), Place(b.key, 0, 11, MEANT))
    assert selected_text(captions, chosen) == ("this weekend, okay?\nMy computer")


def test_from_one_side_to_the_other_takes_both_sides_of_each_clause_whole() -> None:
    """One end on what was said, the other on a translation: both sides of
    every clause between - what was said, then its translation."""
    captions = three()
    a, b, _ = captions
    chosen = Selection(Place(a.key, 1, 2, SAID), Place(b.key, 0, 3, MEANT))
    assert chosen.both_sides
    assert selected_text(captions, chosen).splitlines() == [
        "好不好？",
        "okay?",
        "我的电脑又卡了，",
        "My computer froze again,",
    ]


def test_a_caption_gone_from_the_window_drops_out() -> None:
    captions = three()
    a, _, c = captions
    chosen = Selection(Place(a.key, 0, 0, SAID), Place(c.key, 0, 2, SAID))
    without_b = [a, c]
    assert selected_text(without_b, chosen) == "我们周末一起去打游戏吧，好不好？\n这个"


def test_it_keeps_its_words_as_the_captions_grow() -> None:
    """It names places, not lines: a caption that grows, and another that
    arrives, leave the words held as they were."""
    history = CaptionHistory()
    history.apply(finished("a", WEEKEND))
    history.apply(live("b", COMPUTER))
    before = [caption_model(caption, EN) for caption in history.captions]
    a, b = before
    chosen = Selection(Place(a.key, 0, 2, SAID), Place(b.key, 0, 4, SAID))
    held = selected_text(before, chosen)
    history.apply(finished("b", COMPUTER, RESTART))
    history.apply(finished("c", FRUIT))
    after = [caption_model(caption, EN) for caption in history.captions]
    assert selected_text(after, chosen) == held == "周末一起去打游戏吧，\n我的电脑"


def test_a_clause_rewritten_shorter_ends_where_its_text_does() -> None:
    (a,) = models(finished("a", OKAY))
    chosen = Selection(Place(a.key, 0, 0, SAID), Place(a.key, 0, 99, SAID))
    assert selected(models(finished("a", OKAY)), chosen) == [
        (a.key, Words(SAID, 0, 0, len("好不好？")))
    ]


def test_an_empty_selection_holds_nothing() -> None:
    a, _, _ = three()
    at = Place(a.key, 0, 3, SAID)
    assert selected(three(), Selection(at, at)) == []
    assert selected_text(three(), Selection(at, at)) == ""
