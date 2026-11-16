"""Unfamiliar words under the "common words only" cap (project 019,
section 6): new words up to about the next band, about 5% of a caption's
words and 2 per line, the most heard and commonest first, never names."""

from tests.learning.fakes import facts

from polyglotic_desktop.core.learning.highlights import (
    WordIntroductions,
    caption_cap,
    unfamiliar_words,
)
from polyglotic_desktop.core.learning.levels import UNLIMITED, KnownLine, WindowSize
from polyglotic_desktop.core.learning.statuses import estimated_status
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level, WordInLine

LINE = KnownLine.picked(Level("hsk-2025", 2))
WINDOW = LINE.window()


def line_of(*entries: EntryFacts) -> list[WordInLine]:
    return [WordInLine(i * 2, i * 2 + 2, e) for i, e in enumerate(entries)]


def shown(
    lines: list[list[WordInLine]],
    heard: dict[str, int] | None = None,
    common_only: bool = True,
) -> list[list[str]]:
    counts = heard or {}
    result = unfamiliar_words(
        lines,
        lambda f: estimated_status(f, LINE),
        WINDOW,
        lambda entry_id: counts.get(entry_id.removeprefix("test:"), 0),
        common_only,
    )
    return [[w.entry.entry_id.removeprefix("test:") for w in line] for line in result]


def known(n: int) -> list[EntryFacts]:
    return [facts(f"known{i}", level=1) for i in range(n)]


def test_the_cap_is_about_five_percent_and_at_least_one() -> None:
    assert [caption_cap(n) for n in (1, 10, 29, 30, 50, 100)] == [1, 1, 1, 2, 3, 5]


def test_only_new_words_within_reach_are_shown_and_never_names() -> None:
    line = line_of(
        *known(30),
        facts("next-band", level=3),
        facts("too-rare", level=5),
        facts("off-list", level=None),
        facts("Zhang", level=3, is_name=True),
    )
    assert shown([line]) == [["next-band"]]
    # without the cap: every new word, but still no names
    assert shown([line], common_only=False) == [["next-band", "too-rare", "off-list"]]


def test_the_most_heard_then_the_commonest_words_win_the_places() -> None:
    line = line_of(
        *known(20),
        facts("rarer", level=3, rank=4000),
        facts("commoner", level=3, rank=900),
        facts("heard-often", level=3, rank=8000),
    )
    assert shown([line]) == [["commoner"]]  # 23 words: room for 1
    assert shown([line], heard={"heard-often": 7}) == [["heard-often"]]


def test_at_most_two_per_line_and_each_word_once() -> None:
    a, b, c = (facts(n, level=3, rank=r) for n, r in (("a", 1), ("b", 2), ("c", 3)))
    first = line_of(*known(40), a, b, c)
    second = line_of(*known(40), a, c)
    assert shown([first, second]) == [["a", "b"], ["c"]]


def test_a_word_set_new_by_the_learner_shows_even_if_easy() -> None:
    easy = facts("easy-but-new", level=1)
    result = unfamiliar_words(
        [line_of(*known(5), easy)],
        lambda f: estimated_status(f, None if f == easy else LINE),
        WINDOW,
        lambda entry_id: 0,
        True,
    )
    assert [w.entry.entry_id for w in result[0]] == [EntryId("test:easy-but-new")]


def in_words(
    line: list[WordInLine], known: int, size: WindowSize | None, common_only: bool
) -> list[str]:
    """What a learner who knows `known` words is shown of `line`."""
    said = KnownLine.words(known)
    result = unfamiliar_words(
        [line],
        lambda f: estimated_status(f, said),
        said.window(size),
        lambda entry_id: 0,
        common_only,
    )
    return [w.entry.entry_id.removeprefix("test:") for w in result[0]]


def test_a_line_in_words_points_out_the_learning_window_and_never_rarer_words() -> None:
    """polyglotic-hq 323: known up to the line, learning in the window past
    it, rarer beyond - "every new word" too never marks a rarer one."""
    line = line_of(
        *(facts(f"common{i}", level=None, rank=i + 1) for i in range(20)),
        facts("just-past", level=None, rank=1001),
        facts("window-end", level=None, rank=2000),
        facts("rarer", level=None, rank=2001),
        facts("no-rank", level=None, rank=None),
        facts("Zhang", level=None, rank=1500, is_name=True),
    )
    assert in_words(line, 1000, None, common_only=False) == ["just-past", "window-end"]
    assert in_words(line, 1000, None, common_only=True) == ["just-past"]  # the cap
    # the window's size is the learner's: 500 ends before 2,000, 2,000 takes 2,001
    assert in_words(line, 1000, 500, common_only=False) == ["just-past"]
    assert in_words(line, 1000, 2000, common_only=False) == [
        "just-past", "window-end", "rarer",
    ]  # fmt: skip
    # the line moved: what was the window is known
    assert in_words(line, 2000, None, common_only=False) == ["rarer"]
    # a size of the learner's own, and unlimited: every new word past the
    # line, the unranked too - and the cap still holds a few (decision 0144)
    assert in_words(line, 1000, 1001, common_only=False) == [
        "just-past", "window-end", "rarer",
    ]  # fmt: skip
    assert in_words(line, 1000, UNLIMITED, common_only=False) == [
        "just-past", "window-end", "rarer", "no-rank",
    ]  # fmt: skip
    assert in_words(line, 1000, UNLIMITED, common_only=True) == ["just-past"]


def test_a_syllabus_word_is_placed_by_its_level_when_its_rank_is_rarer() -> None:
    """A word in HSK 1 (300 words) that the frequency list puts 6,361st: a
    learner of 1,000 words knows it; one of 200 is learning it."""
    thanks = facts("thanks", level=1, rank=6361, level_words=300)
    news = facts("news-word", level=None, rank=250)
    line = line_of(thanks, news)
    assert in_words(line, 1000, None, common_only=False) == []
    assert in_words(line, 200, None, common_only=False) == ["thanks", "news-word"]
    assert in_words(line, 260, 100, common_only=False) == ["thanks"]


def test_word_introductions_are_kept_as_off_and_common_words_only() -> None:
    """Learning's three choices (polyglotic-hq 262) and the two settings
    that keep them: off wins, and keeps the cap for coming back."""
    of = WordIntroductions.of
    assert of(False, True) is WordIntroductions.A_FEW
    assert of(False, False) is WordIntroductions.EVERY
    assert of(True, True) is of(True, False) is WordIntroductions.OFF
    for choice in WordIntroductions:
        assert of(choice.off, choice.common_only) is choice
    assert WordIntroductions.OFF.common_only  # back on: a few


def test_a_number_in_numerals_is_never_pointed_out() -> None:
    """二十 and 十五 were dotted as new at a big window and at Unlimited
    (polyglotic-hq 351): the frequency list ranks them as rare written
    forms (5,165th and 3,172nd), numbers being mostly written in digits."""
    twenty = EntryFacts(EntryId("test:二十"), None, 5165, False, is_number=True)
    fifteen = EntryFacts(EntryId("test:十五"), None, 3172, False, is_number=True)
    rare = facts("rare", level=None, rank=3500)
    line = line_of(twenty, fifteen, rare)
    for size in (5000, UNLIMITED):
        for common_only in (True, False):
            assert in_words(line, 3000, size, common_only) == ["rare"]
    # a line kept as a level shows every new word - but a number isn't new
    assert shown([line], common_only=False) == [["rare"]]
