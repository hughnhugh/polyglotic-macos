"""One model of a caption (polyglotic-hq 340, decision 0132): its links
numbered across the whole caption, and its clauses kept through updates.
Made-up captions."""

from polyglotic_desktop.core.listening.caption_model import (
    CaptionModel,
    Words,
    caption_model,
    units,
)
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import LinkDetail, RowKind
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.ui.recorded_captions import (
    COMPUTER,
    OKAY,
    RESTART,
    WEEKEND,
    finished,
    live,
)

EN = Language("en")
SAID, MEANT = RowKind.ORIGINAL, RowKind.TRANSLATION


def models(*updates: object, before: list[CaptionModel] | None = None) -> list:
    history = CaptionHistory()
    for update in updates:
        history.apply(update)  # type: ignore[arg-type]
    return [caption_model(caption, EN) for caption in history.captions]


def test_no_two_links_of_a_caption_share_a_number() -> None:
    """Numbered from 0 in each clause, two clauses on one line shared a
    colour (340's picture 02): 我们 and 好不好 both orange."""
    (model,) = models(finished("a", WEEKEND, OKAY))
    numbers = [link.number for link in model.links]
    assert numbers == list(range(5))  # four in the first clause, one in the next
    assert model.links[4].original == (Words(SAID, 1, 0, 3),)
    assert model.text(model.links[4].translation[0]) == "okay"


def test_a_clause_that_comes_later_renumbers_none_before_it() -> None:
    (short,) = models(finished("a", WEEKEND))
    (longer,) = models(finished("a", WEEKEND, OKAY))
    assert longer.links[: len(short.links)] == short.links


def test_a_live_captions_last_clause_has_no_links_yet() -> None:
    (model,) = models(live("a", COMPUTER, RESTART))
    assert model.clauses[0].settled and not model.clauses[1].settled
    assert {link.translation[0].clause for link in model.links} == {0}
    assert model.clauses[1].cuts == ()


def test_a_clause_that_did_not_change_keeps_its_model() -> None:
    """What a layout measured for it is kept through the caption's updates."""
    history = CaptionHistory()
    history.apply(live("a", COMPUTER, RESTART))
    first = caption_model(history.captions[0], EN)
    history.apply(finished("a", COMPUTER, RESTART))
    second = caption_model(history.captions[0], EN, previous=first)
    assert second.clauses[0] is first.clauses[0]
    assert second.clauses[1] is not first.clauses[1]  # it settled: links came


def test_key_words_and_the_cap_choose_among_the_links() -> None:
    (model,) = models(finished("a", WEEKEND, OKAY))
    key = list(model.shown_links(LinkDetail.KEY))
    assert [model.text(link.original[0]) for link in key] == [
        "周末", "一起", "打游戏", "好不好",
    ]  # fmt: skip
    capped = list(model.shown_links(cap=2))
    assert [link.translation[0].clause for link in capped] == [0, 0, 1]


def test_the_links_at_a_word() -> None:
    (model,) = models(finished("a", WEEKEND, OKAY))
    at = WEEKEND.translations[EN].index("weekend")
    (link,) = model.links_at(Words(MEANT, 0, at, at + 1))
    assert model.text(link.original[0]) == "周末"
    assert model.links_at(Words(MEANT, 0, 6, 8)) == ()  # "go": no link


def test_units_are_words_and_wide_characters() -> None:
    assert [(a, b) for a, b, _ in units("so I bought")] == [(0, 2), (3, 4), (5, 11)]
    assert len(units("我买了很多。")) == 5  # the full stop stays with 多


def test_wide_script_uses_word_edges_from_the_language_pack() -> None:
    from polyglotic_desktop.ports.word_split import SplitWord

    text = "我很好，你呢"
    found = units(
        text,
        (SplitWord(0, 1), SplitWord(1, 3), SplitWord(3, 4), SplitWord(4, 6)),
    )
    assert [text[start:end] for start, end, _ in found] == ["我", "很好，", "你呢"]


def test_a_second_language_line_kept_under_the_target_is_in_the_second() -> None:
    """The one layout reads the translation's language for its font and
    pinyin: a caption already in the target, its line in the second
    language kept under the target, is in the second - its links still the
    target's (polyglotic-hq 427)."""
    from polyglotic_desktop.ui.recorded_captions import clause

    zh = Language("zh")
    history = CaptionHistory()
    already = clause("I like it", "我喜欢", (("like", "喜欢"),))  # under English
    history.apply(finished("a", already, language=EN))
    model = caption_model(history.captions[0], EN, zh)
    assert model.clauses[0].language == zh
    assert [model.text(link.translation[0]) for link in model.links] == ["喜欢"]
    assert caption_model(history.captions[0], EN).clauses[0].language == EN
