"""The one caption layout (polyglotic-hq 340, decision 0132): every way of
filling the window is `views.flow` with different options; every
character is on a line once, inside the width; text already shown never
moves when more comes; and a resize measures nothing again. A fixed-pitch
stand-in for the fonts (20 px a Chinese character, 10 px a Latin one), so
the lines are the same on every machine."""

import itertools

import pytest

from polyglotic_desktop.core.listening.caption_model import (
    CaptionModel,
    caption_model,
)
from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.ui.recorded_captions import (
    BOUGHT,
    COMPUTER,
    CONTROLS,
    FRUIT,
    GAME,
    MIC,
    OKAY,
    RESTART,
    WEEKEND,
    clause,
    finished,
    live,
)
from polyglotic_desktop.ui_next.views.flow import (
    Cut,
    Flow,
    Flowed,
    FlowOptions,
    flow_options,
)
from polyglotic_desktop.ui_next.views.lab import Fill, Join

EN = Language("en")
SAID, MEANT = RowKind.ORIGINAL, RowKind.TRANSLATION
ROWS = FlowOptions()
STACKED = FlowOptions(Cut.CAPTION)
PAIRED = FlowOptions(share=True, split=True)
ALIGNED = FlowOptions(share=True, split=True, aligned=True)
RUN_ON = FlowOptions(share=True, split=True, run_on=True)
ROWS_LINED = FlowOptions(aligned=True)
BELOW_LINED = FlowOptions(Cut.CAPTION, aligned=True)
EVERY = (ROWS, STACKED, PAIRED, ALIGNED, RUN_ON, ROWS_LINED, BELOW_LINED)
ALL = (GAME, CONTROLS, COMPUTER, RESTART, WEEKEND, OKAY, FRUIT, BOUGHT)
CROSSED = clause(
    "我昨天在图书馆借了三本关于历史的书，",
    "I borrowed three books about history from the library yesterday,",
    (("昨天", "yesterday"), ("图书馆", "library"), ("借", "borrowed"),
     ("三本", "three"), ("历史", "history"), ("书", "books")),
)  # fmt: skip


class Pitch:
    """Fonts of a fixed pitch."""

    ascent, below = 20.0, 8.0

    def font(self, side: RowKind, language: Language | None, text: str) -> "Pitch":
        return self

    def width(self, text: str) -> float:
        return sum(20.0 if ord(c) > 0x2E80 else 10.0 for c in text)


def models(*updates: object) -> list[CaptionModel]:
    history = CaptionHistory((MIC,))
    for update in updates:
        history.apply(update)  # type: ignore[arg-type]
    return [caption_model(caption, EN) for caption in history.captions]


def one(*clauses: Clause) -> list[CaptionModel]:
    return models(finished("a", *clauses))


def text_of(
    captions: list[CaptionModel], flowed: Flowed, pair: int, side: RowKind
) -> str:
    return " | ".join(
        captions[run.caption].text(run.words).strip()
        for line in flowed.lines
        if line.pair == pair and line.side is side
        for run in line.runs
    )


def where(flowed: Flowed) -> dict[tuple[int, RowKind, int, int], tuple[int, float]]:
    """Each character's line - counted among the lines of its side: with
    the translation below, a new line of what was said moves every
    translation line down, as it must - and the x its run starts at."""
    found = {}
    count = {SAID: 0, MEANT: 0}
    for line in flowed.lines:
        n = count[line.side]
        count[line.side] += 1
        for run in line.runs:
            for char in range(run.words.start, run.words.end):
                key = (run.caption, run.words.side, run.words.clause, char)
                assert key not in found, "a character on two lines"
                found[key] = (n, run.x)
    return found


# -- every way of filling the window, one composer ----------------------------------


def test_a_clause_a_row_is_a_line_pair_for_each_clause() -> None:
    captions = one(GAME, CONTROLS)
    flowed = Flow(Pitch()).compose(captions, 900, ROWS)
    assert [(line.pair, line.side) for line in flowed.lines] == [
        (0, SAID), (0, MEANT), (1, SAID), (1, MEANT),
    ]  # fmt: skip
    assert all(not line.joins for line in flowed.lines)


def test_translation_below_runs_the_clauses_on_in_each_half() -> None:
    captions = one(GAME, CONTROLS)
    flowed = Flow(Pitch()).compose(captions, 900, STACKED)
    assert [line.side for line in flowed.lines] == [SAID, MEANT]
    assert (
        text_of(captions, flowed, 0, SAID)
        == "这个游戏的画面很漂亮， | 但是操作有点难。"
    )
    assert len(flowed.lines[0].joins) == 1  # the ellipsis between the clauses


def test_line_by_line_cuts_a_clause_where_no_link_crosses() -> None:
    """但是 | 操作有点难 over but | the controls ...: the cut both sides can take."""
    captions = one(GAME, CONTROLS)
    flowed = Flow(Pitch()).compose(captions, 420, PAIRED)
    assert text_of(captions, flowed, 0, SAID).endswith("但是")
    assert text_of(captions, flowed, 0, MEANT).endswith("but the")
    assert text_of(captions, flowed, 1, SAID).startswith("操作有点难。")
    assert text_of(captions, flowed, 1, MEANT).startswith("controls are a bit hard.")


def test_where_the_languages_order_words_differently_the_pair_is_still_filled() -> None:
    """Today's line by line had nowhere to cut this clause and wrapped it
    as a clause row (340's picture 05): now a line pair, then the rest."""
    captions = one(CROSSED)
    flowed = Flow(Pitch()).compose(captions, 420, PAIRED)
    assert [(line.pair, line.side) for line in flowed.lines] == [
        (0, SAID), (0, MEANT), (1, SAID), (1, MEANT),
    ]  # fmt: skip
    assert flowed.lines[1].end > 0.8 * 420  # the wider language fills its line


def test_lined_up_each_part_starts_where_its_counterpart_does() -> None:
    captions = one(GAME, CONTROLS)
    flowed = Flow(Pitch()).compose(captions, 900, ALIGNED)
    said, meant = flowed.lines[0], flowed.lines[1]
    starts = {run.x for run in meant.runs}
    assert len(starts) >= 3
    covered = [(run.x, run.x + run.width) for run in said.runs]
    assert all(any(a <= x <= b for a, b in covered) for x in starts)


def test_captions_that_run_on_share_a_line_pair() -> None:
    """Short captions leave most of the window empty today - each starts a
    line of its own (340's picture 07)."""
    short = [
        finished(str(n), clause(said, meant))
        for n, (said, meant) in enumerate(
            (
                ("好的。", "Okay."),
                ("等一下。", "Wait."),
                ("你在哪儿？", "Where are you?"),
            )
        )
    ]
    captions = models(*short)
    apart = Flow(Pitch()).compose(captions, 900, PAIRED)
    together = Flow(Pitch()).compose(captions, 900, RUN_ON)
    assert len(apart.lines) == 6 and len(together.lines) == 2
    assert {run.caption for run in together.lines[0].runs} == {0, 1, 2}


def test_todays_lab_choices_are_options() -> None:
    assert flow_options(Fill.CLAUSES) == ROWS
    assert flow_options(Fill.STACKED) == STACKED
    assert flow_options(Fill.PAIRED) == PAIRED


# -- what holds in every one of them -------------------------------------------------


@pytest.mark.parametrize("options", EVERY)
@pytest.mark.parametrize("join", list(Join))
def test_every_character_is_on_a_line_once_inside_the_width(
    options: FlowOptions, join: Join
) -> None:
    captions = models(
        finished("a", *ALL[:4]), finished("b", CROSSED), live("c", *ALL[4:])
    )
    flow = Flow(Pitch())
    for width in range(160, 1300, 37):
        flowed = flow.compose(captions, width, FlowOptions(
            options.cut, options.share, options.split, options.aligned,
            options.run_on, join,
        ))  # fmt: skip
        placed = where(flowed)
        for n, caption in enumerate(captions):
            for c, part in enumerate(caption.clauses):
                for side in (SAID, MEANT):
                    for char in range(len(part.text(side))):
                        assert (n, side, c, char) in placed
        for line in flowed.lines:
            assert all(
                a.x + a.width <= b.x + 0.5 for a, b in itertools.pairwise(line.runs)
            )
            assert line.runs[-1].x + line.runs[-1].width <= width + 0.5
        tops = [line.top for line in flowed.lines]
        assert tops == sorted(tops) and flowed.height >= tops[-1]


@pytest.mark.parametrize("options", EVERY)
@pytest.mark.parametrize("join", list(Join))
def test_text_already_shown_never_moves_when_a_clause_or_caption_comes(
    options: FlowOptions, join: Join
) -> None:
    """Today's pour moved a word down a line in 2-3 % of growths with an
    ellipsis between clauses (340's stability340.py)."""
    flow = Flow(Pitch())
    chosen = FlowOptions(
        options.cut, options.share, options.split, options.aligned, options.run_on, join
    )
    for width in range(200, 1200, 23):
        for count in range(1, len(ALL)):
            # two captions, the second growing by a clause
            before = models(finished("a", *ALL[:2]), finished("b", *ALL[2 : 2 + count]))
            after = models(finished("a", *ALL[:2]), finished("b", *ALL[2 : 3 + count]))
            was = where(flow.compose(before, width, chosen))
            now = where(flow.compose(after, width, chosen))
            assert all(now[key] == at for key, at in was.items()), (width, count)
        alone = where(flow.compose(models(finished("a", *ALL[:3])), width, chosen))
        joined = where(
            flow.compose(
                models(finished("a", *ALL[:3]), finished("b", *ALL[3:5])), width, chosen
            )
        )
        assert all(joined[key] == at for key, at in alone.items()), width


def test_a_resize_measures_nothing_again() -> None:
    captions = one(*ALL)
    flow = Flow(Pitch())
    flow.compose(captions, 900, PAIRED)
    measured = flow.measured
    assert measured == 2 * len(ALL)
    for width in range(300, 900, 10):
        flow.compose(captions, width, PAIRED)
        flow.compose(captions, width, STACKED)
    assert flow.measured == measured


def test_your_own_speech_is_lined_up_on_the_right() -> None:
    captions = one(GAME)
    flowed = Flow(Pitch()).compose(captions, 900, ROWS, right=True)
    assert all(abs(line.end - 900) < 0.5 for line in flowed.lines)


def test_a_caption_still_being_spoken_trails_off() -> None:
    captions = models(live("a", GAME))
    flowed = Flow(Pitch()).compose(captions, 900, ROWS)
    assert len(flowed.lines[-1].joins) == 1
    assert not Flow(Pitch()).compose(captions, 900, ROWS, trail=False).lines[-1].joins


def test_originals_hidden_only_the_translations_are_laid() -> None:
    captions = one(GAME, CONTROLS)
    hidden = FlowOptions(share=True, split=True, show_original=False)
    flowed = Flow(Pitch()).compose(captions, 900, hidden)
    assert {line.side for line in flowed.lines} == {MEANT}


# -- run-on, a caption at a time (a surface lays each caption out by itself) ---------


@pytest.mark.parametrize("width", [200, 330, 480, 760, 1100, 1900])
@pytest.mark.parametrize("join", list(Join))
def test_a_caption_composed_from_what_the_one_before_left_open_lands_where_together(
    width: int, join: Join
) -> None:
    """Composed one by one - each from the line pair the one before left
    open - the captions' text is exactly where composing them together
    puts it: the window lays out one caption at a time, and nothing of the
    captions before is laid out again."""
    options = FlowOptions(share=True, split=True, run_on=True, join=join)
    captions = models(
        finished("a", GAME, CONTROLS),
        finished("b", OKAY),
        finished("c", COMPUTER, RESTART, WEEKEND),
        finished("d", FRUIT),
    )
    flow = Flow(Pitch())
    together = flow.compose(captions, float(width), options)
    wanted = {
        (run.caption, run.words, round(run.x, 3), round(line.top, 3))
        for line in together.lines
        for run in line.runs
    }
    found = set()
    top = 0.0
    entry = None
    for index, caption in enumerate(captions):
        alone = flow.compose([caption], float(width), options, entry=entry)
        if entry is not None:
            top -= entry.height  # it starts on the pair left open
        else:
            top += flow.gaps.pair if index else 0.0
        found |= {
            (index, run.words, round(run.x, 3), round(top + line.top, 3))
            for line in alone.lines
            for run in line.runs
        }
        top += alone.height
        entry = alone.open
        assert entry is not None
    assert found == wanted
    assert top == pytest.approx(together.height)


def test_nothing_is_left_open_unless_captions_run_on() -> None:
    """A caption still being spoken leaves nothing open either: its end
    still moves."""
    (caption,) = one(GAME, CONTROLS)
    flow = Flow(Pitch())
    for options in (ROWS, STACKED, PAIRED, ALIGNED):
        assert flow.compose([caption], 900.0, options).open is None
    left = flow.compose([caption], 900.0, RUN_ON).open
    assert left is not None and left.upper is not None and left.lower is not None
    assert left.height == pytest.approx(2 * 28.0 + flow.gaps.row)
    (spoken,) = models(live("a", GAME, CONTROLS))
    assert flow.compose([spoken], 900.0, RUN_ON).open is None
    assert flow.compose([caption], 900.0, RUN_ON, right=True).open is None


@pytest.mark.parametrize("width", [240, 300, 420])
def test_what_was_said_is_never_drawn_over_a_translation_s_last_line(
    width: int,
) -> None:
    """The caption before ends in a line of its translation alone - its
    translation ran on past what was said. The next caption's original has
    no line there: it starts on the pair under it, composed one by one as
    together (polyglotic-hq 366: it was drawn over that line, and composed
    together it pushed the line down)."""
    long = clause("好。", "Okay, that sounds really good to me, let us do it.")
    first, second = models(finished("a", long), finished("b", OKAY))
    flow = Flow(Pitch())
    entry = flow.compose([first], float(width), RUN_ON).open
    assert entry is not None and entry.upper is None and entry.lower is not None
    alone = flow.compose([second], float(width), RUN_ON, entry=entry)
    said = [line for line in alone.lines if line.side is SAID and line.runs]
    assert said and all(line.top >= entry.height for line in said)
    before = flow.compose([first], float(width), RUN_ON)
    together = flow.compose([first, second], float(width), RUN_ON)

    def placed(flowed: Flowed, caption: int, top: float = 0.0) -> set[object]:
        return {
            (run.words, round(top + line.top, 3), round(run.x, 3))
            for line in flowed.lines
            for run in line.runs
            if run.caption == caption
        }

    assert placed(together, 0) == placed(before, 0)  # nothing of it moved
    top = before.height - entry.height  # where the pair left open starts
    assert placed(alone, 0, top) == placed(together, 1)
    assert top + alone.height == pytest.approx(together.height)


def test_a_caption_that_fits_nothing_on_the_open_pair_starts_under_it() -> None:
    """Too little room left to be worth cutting a clause for: the pair
    ends there - with its ellipsis, in the room that is there - and the
    caption starts on the next."""
    first, second = models(finished("a", GAME), finished("b", CROSSED))
    flow = Flow(Pitch())
    width = flow.compose([first], 2000.0, RUN_ON).lines[1].end + 30.0
    entry = flow.compose([first], width, RUN_ON).open
    assert entry is not None
    alone = flow.compose([second], width, RUN_ON, entry=entry)
    carried = [line for line in alone.lines if not line.runs]
    assert [line.top for line in carried] == [0.0, 28.0 + flow.gaps.row]
    assert all(line.joins for line in carried)  # the ellipsis that closes each
    first_run = next(line for line in alone.lines if line.runs)
    assert first_run.top == pytest.approx(entry.height + flow.gaps.pair)
    assert first_run.runs[0].x == 0.0
