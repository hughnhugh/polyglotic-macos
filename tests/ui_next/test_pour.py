"""Poured captions' rules, without Qt (the Lab's Captions fill the width,
polyglotic-hq 309): a caption's clauses run on in lines as wide as the
window - a line ends where the next word wouldn't fit, not where a clause
ends. Made-up text; a made-up measure (10 px a character, 20 a Chinese
one)."""

import itertools

import pytest

from polyglotic_desktop.ui_next.views.lab import Join
from polyglotic_desktop.ui_next.views.pour import (
    ELLIPSIS,
    Gap,
    Pair,
    Poured,
    matching_cuts,
    pour,
    pour_paired,
    pour_stacked,
    tokens,
    wide,
)


def measure(row: int, text: str) -> float:
    return float(sum(20 if wide(char) else 10 for char in text))


def said(lines: list[Poured], texts: dict[int, str]) -> list[str]:
    """Each poured line as it reads, an ellipsis where one is drawn."""
    out = []
    for line in lines:
        parts = [(p.x, texts[p.row][p.start : p.end]) for p in line.pieces]
        parts += [(x, ELLIPSIS) for _, x in line.marks]
        text, end = "", 0.0
        for x, part in sorted(parts):
            if text and x - end > 5.0:
                text += " "  # room between them: it reads as a space
            text, end = text + part.rstrip(), x + measure(0, part.rstrip())
        out.append(text)
    return out


ONE = "I went to the shop,"
TWO = "and bought milk."


def test_words_are_never_split_and_spaces_go_with_the_word_before() -> None:
    assert tokens("I went  home.") == [(0, 1, 2), (2, 6, 8), (8, 13, 13)]
    text = "we go"
    assert [text[s:e] for s, e, _ in tokens(text)] == ["we", "go"]
    assert tokens("") == [(0, 0, 0)]
    assert tokens("  hi") == [(0, 4, 4)]  # leading spaces stay with the word


def test_chinese_breaks_at_any_character_but_not_before_its_punctuation() -> None:
    text = "我买了，很多。"
    assert [text[s:e] for s, e, _ in tokens(text)] == ["我", "买", "了，", "很", "多。"]
    quoted = "他说「好」"
    assert [quoted[s:e] for s, e, _ in tokens(quoted)] == ["他", "说", "「好」"]
    mixed = "用 Python 写"
    assert [mixed[s:e] for s, e, _ in tokens(mixed)] == ["用", "Python", "写"]


def test_a_live_captions_trailing_ellipsis_stays_with_its_last_word() -> None:
    text = "and then …"
    assert [text[s:e] for s, e, _ in tokens(text)] == ["and", "then …"]


def test_clauses_run_on_with_an_ellipsis_at_the_join() -> None:
    """The user, 2026-11-14: "text will fill the complete caption window
    line by line seperating by ellipsis" - a clause no longer takes a row
    of its own."""
    rows = [(0, ONE), (1, TWO)]
    lines = pour(rows, 600.0, measure, Join.ELLIPSIS)
    assert said(lines, dict(rows)) == ["I went to the shop,… and bought milk."]
    assert [p.row for p in lines[0].pieces] == [0, 1]
    assert lines[0].pieces[1].x > lines[0].marks[0][1]  # after the ellipsis


def test_a_line_ends_where_the_next_word_would_not_fit() -> None:
    rows = [(0, ONE), (1, TWO)]
    lines = pour(rows, 300.0, measure, Join.ELLIPSIS)
    assert said(lines, dict(rows)) == ["I went to the shop,… and", "bought milk."]
    assert all(line.end <= 300.0 for line in lines)
    narrow = pour(rows, 120.0, measure, Join.ELLIPSIS)
    assert said(narrow, dict(rows)) == [
        "I went to",
        "the shop,…",  # the join's ellipsis stays on its clause's line
        "and bought",
        "milk.",
    ]


def test_an_ellipsis_at_each_lines_end_too_or_only_a_space() -> None:
    rows = [(0, ONE), (1, TWO)]
    ends = pour(rows, 300.0, measure, Join.LINE_ENDS)
    assert said(ends, dict(rows)) == ["I went to the shop,… and…", "bought milk."]
    assert all(line.end <= 300.0 for line in ends)
    space = pour(rows, 300.0, measure, Join.SPACE)
    assert said(space, dict(rows)) == ["I went to the shop, and bought", "milk."]
    assert not any(line.marks for line in space)


def test_chinese_is_poured_by_the_character_with_no_space_at_the_join() -> None:
    rows = [(0, "超市的水果打折了，"), (1, "我买了很多。")]
    lines = pour(rows, 240.0, measure, Join.SPACE)
    assert said(lines, dict(rows)) == ["超市的水果打折了，我买了", "很多。"]
    marked = pour(rows, 240.0, measure, Join.ELLIPSIS)
    assert said(marked, dict(rows))[0] == "超市的水果打折了，…我买"
    assert marked[0].marks[0][1] == 180.0  # right after the comma: no space


def test_a_word_wider_than_a_whole_line_is_cut_to_fit() -> None:
    rows = [(0, "a Rechtsschutzversicherung b")]
    lines = pour(rows, 100.0, measure, Join.ELLIPSIS)
    assert said(lines, dict(rows)) == ["a", "Rechtsschu", "tzversiche", "rung b"]
    assert all(line.end <= 100.0 for line in lines)


@pytest.mark.parametrize("join", list(Join))
@pytest.mark.parametrize("width", [60.0, 150.0, 333.0, 2000.0])
def test_every_character_is_poured_once_in_order(join: Join, width: float) -> None:
    rows = [(0, ONE), (2, "超市的水果打折了，"), (4, TWO), (6, "x")]
    lines = pour(rows, width, measure, join)
    for row, text in rows:
        pieces = [p for line in lines for p in line.pieces if p.row == row]
        assert pieces[0].start == 0 and pieces[-1].end == len(text)
        for before, after in itertools.pairwise(pieces):
            assert before.end == after.start
            assert not text[after.start].isspace()  # a line starts with a word


def test_stacked_what_was_said_above_and_its_translation_below() -> None:
    """Placement (a): each pours on its own - the translation's lines
    start below what was said's, a row's gap between."""
    originals = [(0, "超市的水果打折了，"), (2, "我买了很多。")]
    translations = [(1, "The fruit was on sale,"), (3, "so I bought a lot.")]
    lines = pour_stacked(originals, translations, 320.0, measure, Join.ELLIPSIS)
    texts = dict(originals + translations)
    assert said(lines, texts) == [
        "超市的水果打折了，…我买了很多。",
        "The fruit was on sale,… so I",
        "bought a lot.",
    ]
    assert [line.gap for line in lines] == [Gap.NONE, Gap.ROW, Gap.NONE]
    only = pour_stacked(originals, [], 320.0, measure, Join.ELLIPSIS)
    assert len(only) == 1  # captions only: one stream
    assert pour_stacked([], translations, 320.0, measure, Join.SPACE)[0].gap is Gap.NONE


# -- line by line: a line of what was said, the line of its translation ----------------

Link = tuple[tuple[int, int], tuple[int, int]]
Cuts = tuple[tuple[int, int], ...]
WENT = "我买了很多然后回家了"
WENT_EN = "I bought a lot and then went home"
SALE = "超市的水果打折了"
SALE_EN = "The fruit at the supermarket was on sale"


def links(original: str, translation: str, *pairs: tuple[str, str]) -> list[Link]:
    found = []
    for said, meant in pairs:
        a, c = original.index(said), translation.index(meant)
        found.append(((a, a + len(said)), (c, c + len(meant))))
    return found


WENT_LINKS = links(
    WENT,
    WENT_EN,
    ("买", "bought"),
    ("很多", "a lot"),
    ("然后", "then"),
    ("回家", "home"),
)
SALE_LINKS = links(
    SALE, SALE_EN, ("超市", "supermarket"), ("水果", "fruit"), ("打折", "on sale")
)
WENT_CUTS = matching_cuts(WENT, WENT_EN, WENT_LINKS)
SALE_CUTS = matching_cuts(SALE, SALE_EN, SALE_LINKS)


def parts(original: str, translation: str, cuts: Cuts) -> tuple[list[str], list[str]]:
    ps = [0, *(p for p, _ in cuts), len(original)]
    qs = [0, *(q for _, q in cuts), len(translation)]
    return (
        [original[a:b].strip() for a, b in itertools.pairwise(ps)],
        [translation[a:b].strip() for a, b in itertools.pairwise(qs)],
    )


def test_a_clause_and_its_translation_are_cut_where_their_words_match() -> None:
    """The user, 2026-11-14: "wrapping the appropriate amount of words
    above or below" - each part of one says what the same part of the
    other says. A word with no link goes with the words after it (and),
    or in Chinese with those before (了)."""
    assert parts(WENT, WENT_EN, WENT_CUTS) == (
        ["我买了", "很多", "然后", "回家了"],
        ["I bought", "a lot", "and then", "went home"],
    )
    back = matching_cuts(WENT_EN, WENT, [(t, o) for o, t in WENT_LINKS])
    assert parts(WENT_EN, WENT, back) == (
        ["I bought", "a lot", "and then", "went home"],
        ["我买了", "很多", "然后", "回家了"],
    )


def test_no_cut_where_the_languages_order_the_words_differently() -> None:
    """超市的水果 is "the fruit at the supermarket": the links cross, so
    neither can be cut inside it - only before 打折了 / "was on sale"."""
    assert parts(SALE, SALE_EN, SALE_CUTS) == (
        ["超市的水果", "打折了"],
        ["The fruit at the supermarket", "was on sale"],
    )


def test_no_cut_without_links_to_go_by_or_inside_a_linked_phrase() -> None:
    assert matching_cuts(WENT, WENT_EN, []) == ()
    assert matching_cuts(WENT, WENT_EN, WENT_LINKS[:1]) == ()
    assert matching_cuts(WENT, WENT_EN, [((0, 99), (0, 3)), ((-1, 2), (0, 3))]) == ()
    phrase = links(
        "we play games now", "我们现在打游戏", ("play games", "打游戏"), ("now", "现在")
    )
    assert matching_cuts("we play games now", "我们现在打游戏", phrase) == ()


def paired(
    width: float, join: Join = Join.ELLIPSIS
) -> tuple[list[Poured], dict[int, str]]:
    pairs = [
        Pair((0, WENT), (1, WENT_EN), WENT_CUTS),
        Pair((2, SALE), (3, SALE_EN), SALE_CUTS),
        Pair((4, "好的。")),  # not translated yet
    ]
    texts = {0: WENT, 1: WENT_EN, 2: SALE, 3: SALE_EN, 4: "好的。"}
    return pour_paired(pairs, width, measure, join), texts


def test_lines_alternate_what_was_said_then_its_translation() -> None:
    """Placement (b): a pair of lines takes as many matching parts as fit
    both; the next pair starts a clause's gap below."""
    lines, texts = paired(300.0)
    assert said(lines, texts) == [
        "我买了很多然后",
        "I bought a lot and then",
        "回家了…",
        "went home…",
        "超市的水果",
        "The fruit at the supermarket",
        "打折了…好的。",
        "was on sale…",
    ]
    assert [line.gap for line in lines] == [
        Gap.NONE,
        Gap.ROW,
        *[Gap.CLAUSE, Gap.ROW] * 3,
    ]
    assert not any(line.fallback for line in lines)
    assert all(line.end <= 300.0 for line in lines)


def test_clauses_that_fit_share_a_pair_of_lines() -> None:
    lines, texts = paired(800.0, Join.SPACE)
    assert said(lines, texts) == [
        "我买了很多然后回家了 超市的水果打折了 好的。".replace(" ", ""),
        "I bought a lot and then went home The fruit at the supermarket was on sale",
    ]
    marked, _ = paired(300.0, Join.LINE_ENDS)
    assert said(marked, texts)[:2] == ["我买了很多然后…", "I bought a lot and then…"]


def test_a_part_too_wide_with_nowhere_to_cut_wraps_as_a_clause_does() -> None:
    """The fallback: 超市的水果 / "The fruit at the supermarket" can't be
    cut in step, and the translation is wider than the line - so it
    wraps, its original first, as a clause row does today."""
    lines, texts = paired(200.0)
    assert said(lines, texts) == [
        "我买了很多",
        "I bought a lot",
        "然后回家了…",
        "and then went home…",
        "超市的水果",
        "The fruit at the",
        "supermarket",
        "打折了…好的。",
        "was on sale…",
    ]
    assert [line.fallback for line in lines] == [False] * 4 + [True] * 3 + [False] * 2
    assert lines[6].gap is Gap.NONE and lines[7].gap is Gap.CLAUSE


@pytest.mark.parametrize("join", list(Join))
@pytest.mark.parametrize("width", [60.0, 120.0, 200.0, 333.0, 2000.0])
def test_paired_every_character_once_and_each_pair_of_lines_ends_at_a_match(
    join: Join, width: float
) -> None:
    lines, texts = paired(width, join)
    for row, text in texts.items():
        pieces = [p for line in lines for p in line.pieces if p.row == row]
        assert pieces[0].start == 0 and pieces[-1].end == len(text)
        assert all(a.end == b.start for a, b in itertools.pairwise(pieces))
    assert all(line.end <= width + 0.5 for line in lines if not line.fallback)
    matches = {0: {*WENT_CUTS, (len(WENT), len(WENT_EN))},
               2: {*SALE_CUTS, (len(SALE), len(SALE_EN))}}  # fmt: skip
    for top, bottom in itertools.pairwise(lines):
        if top.fallback or bottom.fallback or bottom.gap is not Gap.ROW:
            continue
        for row, ends in matches.items():
            above = [p.end for p in top.pieces if p.row == row]
            below = [p.end for p in bottom.pieces if p.row == row + 1]
            if above and below:
                assert (above[-1], below[-1]) in ends
