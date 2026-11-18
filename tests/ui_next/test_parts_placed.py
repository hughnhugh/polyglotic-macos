"""A line pair's parts placed for the shortest word links, or evenly
(polyglotic-hq 458; the user, 2026-11-17: "placing characters in such a
way to reducing distance between all arrow length sums ... a 3rd alternate
lab mode could be clean even space everything"). The fixed-pitch fonts of
`test_flow`."""

import itertools
import random
from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_flow import ALL, CROSSED, MEANT, SAID, Pitch, models, where

from polyglotic_desktop.core.listening.caption_model import CaptionModel
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.ui.recorded_captions import (
    COMPUTER,
    CONTROLS,
    GAME,
    clause,
    finished,
    live,
)
from polyglotic_desktop.ui_next.caption_window import one_layout
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.flow import (
    Cut,
    Flow,
    Flowed,
    FlowOptions,
    Open,
    flow_options,
)
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill, Placing
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.placing import evenly, nearest

NOT = clause(
    "我们昨天没有去那个地方，",
    "We did not go to that place yesterday,",
    (("我们", "We"), ("没有", "not"), ("去", "go"), ("地方", "place"),
     ("昨天", "yesterday")),
)  # fmt: skip
"""Its first part's 昨天 is said early and translated last: packed, it
starts under "We"."""
WIDE = FlowOptions(share=True, split=True)
WIDE_RUN_ON = FlowOptions(share=True, split=True, run_on=True)
BOTH = FlowOptions(share=True, split=True, aligned=True)
BOTH_RUN_ON = FlowOptions(share=True, split=True, aligned=True, run_on=True)
ROWS = FlowOptions()
ROWS_LINED = FlowOptions(aligned=True)
BELOW_LINED = FlowOptions(Cut.CAPTION, aligned=True)
WAYS = {
    "wide": WIDE,
    "both": BOTH,
    "rows": ROWS,
    "rows lined": ROWS_LINED,
    "below lined": BELOW_LINED,
}
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each panel deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def talk() -> list[CaptionModel]:
    return models(
        finished("a", GAME, CONTROLS),
        finished("b", CROSSED, COMPUTER),
        finished("c", NOT, *ALL[4:]),
    )


def placed(options: FlowOptions, placing: Placing) -> FlowOptions:
    return replace(options, placing=placing)


def centres(
    captions: list[CaptionModel], flowed: Flowed
) -> dict[tuple[int, RowKind, int, int], tuple[int, float]]:
    """Each character's line pair and the x of its middle."""
    pitch = Pitch()
    found = {}
    for line in flowed.lines:
        for run in line.runs:
            text = captions[run.caption].clauses[run.words.clause].text(run.words.side)
            for char in range(run.words.start, run.words.end):
                x = run.x + pitch.width(text[run.words.start : char])
                key = (run.caption, run.words.side, run.words.clause, char)
                found[key] = (line.pair, x + pitch.width(text[char]) / 2)
    return found


def links_drawn(captions: list[CaptionModel], flowed: Flowed) -> list[float]:
    """How far across each word link goes, where both its ends are on one
    line pair: from the middle of the words said to the middle of their
    counterpart."""

    def middle(
        caption: int, side: RowKind, n: int, a: int, b: int
    ) -> tuple[int, float]:
        first, last = at[(caption, side, n, a)], at[(caption, side, n, b - 1)]
        return first[0] if first[0] == last[0] else -1, (first[1] + last[1]) / 2

    at = centres(captions, flowed)
    found = []
    for index, caption in enumerate(captions):
        for n, part in enumerate(caption.clauses):
            for pairs in part.pairs:
                under = middle(index, MEANT, n, *pairs.translation)
                for span in pairs.original:
                    over = middle(index, SAID, n, *span)
                    if over[0] == under[0] >= 0:
                        found.append(abs(over[1] - under[1]))
    return found


def in_turn(
    captions: list[CaptionModel], width: float, options: FlowOptions
) -> list[Flowed]:
    """The captions composed one by one, each carrying on where the one
    before ended - as a surface lays them out."""
    flow = Flow(Pitch())
    entry: Open | None = None
    found = []
    for caption in captions:
        flowed = flow.compose([caption], width, options, entry=entry)
        entry = flowed.open
        found.append(flowed)
    return found


# -- the arithmetic (`views.placing`) ------------------------------------------------


def total(shifts: list[float], wants: list[list[float]]) -> float:
    return sum(
        abs(y - want)
        for y, wanted in zip(shifts, wants, strict=True)
        for want in wanted
    )


def test_a_part_goes_to_the_middle_of_what_it_wants() -> None:
    assert nearest([[30.0]], 100.0) == [30.0]
    assert nearest([[10.0, 20.0, 90.0]], 100.0) == [20.0]  # the median
    assert nearest([[10.0, 30.0]], 100.0) == [20.0]  # two links: between them
    assert nearest([[250.0]], 100.0) == [100.0]  # no further than the room
    assert nearest([[-40.0]], 100.0) == [0.0]  # never left of packed


def test_parts_that_would_cross_move_as_one() -> None:
    # the first wants to be past the second: they stay in order, together,
    # at the median of what both want
    assert nearest([[80.0], [20.0]], 100.0) == [50.0, 50.0]
    assert nearest([[80.0, 90.0], [20.0]], 100.0) == [80.0, 80.0]
    assert nearest([[10.0], [60.0]], 100.0) == [10.0, 60.0]


def test_a_part_with_no_links_goes_between_its_neighbours() -> None:
    assert nearest([[], [60.0]], 100.0) == [30.0, 60.0]
    assert nearest([[20.0], [], [], [80.0]], 100.0) == [20.0, 40.0, 60.0, 80.0]
    assert nearest([[40.0], []], 100.0) == [40.0, 40.0]  # the last stays with it
    assert nearest([[], []], 100.0) == [0.0, 0.0]


def test_no_placing_has_shorter_links() -> None:
    """Against every placing on a 10-pixel grid, parts in order: the least
    total there is (isotonic regression in the L1 norm)."""
    rng = random.Random(458)
    grid = [float(x) for x in range(0, 101, 10)]
    for _ in range(60):
        count = rng.randint(1, 4)
        wants = [
            [float(rng.randrange(-30, 140, 10)) for _ in range(rng.randint(0, 3))]
            for _ in range(count)
        ]
        found = nearest(wants, 100.0)
        assert all(0.0 <= y <= 100.0 for y in found)
        assert all(a <= b for a, b in itertools.pairwise(found))
        least = min(
            total(list(ys), wants)
            for ys in itertools.combinations_with_replacement(grid, count)
        )
        assert total(found, wants) <= least + 1e-6


def test_evenly_spreads_the_room_between_the_parts() -> None:
    assert evenly(3, 90.0) == [0.0, 45.0, 90.0]
    assert evenly(1, 90.0) == [0.0]  # one part: nothing to spread
    assert evenly(2, 90.0, after_text=True) == [45.0, 90.0]
    assert evenly(3, 0.0) == [0.0, 0.0, 0.0]


# -- on the lines (`views.flow`) -----------------------------------------------------


@pytest.mark.parametrize("way", list(WAYS))
@pytest.mark.parametrize("placing", [Placing.NEAREST, Placing.EVENLY])
@pytest.mark.parametrize("width", [420, 600, 900, 1400])
def test_every_line_keeps_its_words_in_order_inside_the_width(
    way: str, placing: Placing, width: int
) -> None:
    captions = talk()
    packed = Flow(Pitch()).compose(captions, width, WAYS[way])
    flowed = Flow(Pitch()).compose(captions, width, placed(WAYS[way], placing))
    # the same characters on the same lines: only where they are across
    assert {k: v[0] for k, v in where(flowed).items()} == {
        k: v[0] for k, v in where(packed).items()
    }
    assert [(line.side, line.pair, line.top) for line in flowed.lines] == [
        (line.side, line.pair, line.top) for line in packed.lines
    ]
    for line in flowed.lines:
        assert line.end <= width + 0.5
        for before, after in itertools.pairwise(line.runs):
            assert before.x + before.width <= after.x + 0.5
        marks = [(x, "join") for x in line.joins] + [(r.x, "run") for r in line.runs]
        for x, _ in marks:
            assert -0.5 <= x <= width + 0.5
    if placing is Placing.EVENLY:
        return  # lined up, a part may go left of its counterpart's place
    # nothing is left of where the packed line has it
    was = centres(captions, packed)
    assert all(
        x >= was[key][1] - 0.5 for key, (_, x) in centres(captions, flowed).items()
    )


@pytest.mark.parametrize("way", ["wide", "both", "rows", "rows lined", "below lined"])
@pytest.mark.parametrize("width", [420, 600, 900, 1400])
def test_nearest_never_makes_the_links_longer(way: str, width: int) -> None:
    captions = talk()
    packed = Flow(Pitch()).compose(captions, width, WAYS[way])
    near = Flow(Pitch()).compose(captions, width, placed(WAYS[way], Placing.NEAREST))
    assert sum(links_drawn(captions, near)) <= sum(links_drawn(captions, packed)) + 0.5
    assert len(links_drawn(captions, near)) == len(links_drawn(captions, packed))


@pytest.mark.parametrize(
    "options",
    [BOTH, ROWS_LINED, WIDE, ROWS],
    ids=["both", "rows lined", "wide", "rows"],
)
def test_nearest_shortens_the_links_of_recorded_captions(options: FlowOptions) -> None:
    captions = talk()
    packed = Flow(Pitch()).compose(captions, 900, options)
    near = Flow(Pitch()).compose(captions, 900, placed(options, Placing.NEAREST))
    assert sum(links_drawn(captions, near)) < 0.9 * sum(links_drawn(captions, packed))


def test_lined_up_the_narrower_piece_moves_inside_its_slot() -> None:
    """The user's 不 far left of "not": a part's shorter piece goes over
    the words it is linked to, and no further than its counterpart's end."""
    captions = models(finished("a", NOT))
    packed = Flow(Pitch()).compose(captions, 900, ROWS_LINED)
    near = Flow(Pitch()).compose(captions, 900, placed(ROWS_LINED, Placing.NEAREST))
    was, now = centres(captions, packed), centres(captions, near)
    text = NOT.original
    moved = [
        n for n in range(len(text)) if now[(0, SAID, 0, n)][1] > was[(0, SAID, 0, n)][1]
    ]
    assert moved, "nothing of what was said moved over its translation"
    meant_end = max(run.x + run.width for run in near.lines[1].runs)
    assert max(run.x + run.width for run in near.lines[0].runs) <= meant_end + 0.5
    assert max(links_drawn(captions, near)) < max(links_drawn(captions, packed))


def test_not_lined_up_the_fuller_line_stays_as_text() -> None:
    captions = talk()
    packed = Flow(Pitch()).compose(captions, 900, WIDE)
    near = Flow(Pitch()).compose(captions, 900, placed(WIDE, Placing.NEAREST))
    for pair in {line.pair for line in packed.lines}:
        lines = [n for n, line in enumerate(packed.lines) if line.pair == pair]
        if len(lines) != 2:
            continue
        fuller = max(lines, key=lambda n: packed.lines[n].end)
        assert near.lines[fuller].runs == packed.lines[fuller].runs


def test_text_still_being_spoken_is_not_placed() -> None:
    """A live caption has no links yet, and must not move as words come."""
    captions = models(finished("a", GAME, CONTROLS), live("b", CROSSED))
    for options in (WIDE, BOTH, ROWS_LINED):
        packed = Flow(Pitch()).compose(captions, 420, options)
        for placing in (Placing.NEAREST, Placing.EVENLY):
            flowed = Flow(Pitch()).compose(captions, 420, placed(options, placing))
            assert flowed == packed


def test_evenly_fills_a_full_pair_to_the_edge_and_leaves_the_last() -> None:
    captions = talk()
    packed = Flow(Pitch()).compose(captions, 600, WIDE)
    even = Flow(Pitch()).compose(captions, 600, placed(WIDE, Placing.EVENLY))
    last = packed.lines[-1].pair
    was_at, now_at = centres(captions, packed), centres(captions, even)
    spread = 0
    for was, now in zip(packed.lines, even.lines, strict=True):
        if was.pair == last:
            assert now.end == was.end  # the last pair: as packed
            continue
        firsts = [
            (run.caption, run.words.side, run.words.clause, run.words.start)
            for run in now.runs
        ]
        shifts = [now_at[key][1] - was_at[key][1] for key in firsts]
        if len(shifts) > 1 and shifts[-1] > 0.5:
            spread += 1
            assert shifts[0] == 0.0  # the first stays at the edge
            assert now.end == pytest.approx(600.0, abs=0.6)
            steps = [b - a for a, b in itertools.pairwise(shifts)]
            assert max(steps) - min(steps) < 0.01  # every gap grew alike
    assert spread >= 2


def test_evenly_lined_up_the_parts_of_a_line_are_the_same_distance_apart() -> None:
    """A clause too long for a line, lined up: its first pair is full, and
    each of its lines has the same room between every two parts - not the
    rooms lining up left."""
    captions = models(finished("a", CONTROLS))
    width = next(
        w
        for w in range(300, 100, -10)
        if len(
            {line.pair for line in Flow(Pitch()).compose(captions, w, ROWS_LINED).lines}
        )
        == 2
    )
    packed = Flow(Pitch()).compose(captions, width, ROWS_LINED)
    even = Flow(Pitch()).compose(captions, width, placed(ROWS_LINED, Placing.EVENLY))
    checked = 0
    for was, now in zip(packed.lines, even.lines, strict=True):
        if now.pair != 0:
            assert now.end == was.end
            continue
        if len(now.runs) < 2:
            continue  # one part: it stays
        assert now.end == pytest.approx(width, abs=0.6)
        ends = [
            run.x + Pitch().width(captions[0].text(run.words).rstrip())
            for run in now.runs
        ]
        gaps = [b.x - end for end, b in zip(ends, now.runs[1:], strict=False)]
        if len(gaps) > 1:
            checked += 1
            assert max(gaps) - min(gaps) < 0.01
    assert checked == 2  # both lines of the full pair


@pytest.mark.parametrize("placing", [Placing.NEAREST, Placing.EVENLY])
def test_lined_up_a_caption_that_runs_on_starts_where_it_does_packed(
    placing: Placing,
) -> None:
    """Captions laid out one by one, each in the pair the one before left
    open: with parts placed, every caption's text is on the lines it is
    on packed."""
    captions = talk()
    packed = in_turn(captions, 900, BOTH_RUN_ON)
    flowed = in_turn(captions, 900, placed(BOTH_RUN_ON, placing))
    for n, (was, now) in enumerate(zip(packed, flowed, strict=True)):
        assert len(now.lines) == len(was.lines), n
        assert {k: v[0] for k, v in where(now).items()} == {
            k: v[0] for k, v in where(was).items()
        }
        assert (now.open is None) == (was.open is None)


def test_not_lined_up_the_line_that_moves_ends_no_later_than_the_fuller_one() -> None:
    captions = talk()
    packed = in_turn(captions, 900, WIDE_RUN_ON)
    flowed = in_turn(captions, 900, placed(WIDE_RUN_ON, Placing.NEAREST))
    for was, now in zip(packed, flowed, strict=True):
        if was.open is None or was.open.upper is None or was.open.lower is None:
            continue
        assert now.open is not None and now.open.upper and now.open.lower
        fuller = max(was.open.upper.end, was.open.lower.end)
        assert max(now.open.upper.end, now.open.lower.end) <= fuller + 0.5


# -- the choice ----------------------------------------------------------------------


def test_the_lab_passes_the_choice_to_the_layout() -> None:
    for fill in Fill:
        assert flow_options(fill).placing is Placing.PACKED
        assert flow_options(fill, placing=Placing.EVENLY).placing is Placing.EVENLY
    look = CaptionLook(lab=CaptionLab(flow=True, placing=Placing.NEAREST))
    found = one_layout(look)
    assert found is not None and found.placing is Placing.NEAREST


def test_choosing_a_placing_turns_new_layout_on() -> None:
    lab = CaptionLab()
    assert lab.placing is Placing.PACKED and lab.to_stored() == {}
    near = lab.choose(placing=Placing.NEAREST)
    assert near == CaptionLab(flow=True, placing=Placing.NEAREST)
    assert near.choose(placing=Placing.PACKED) == CaptionLab(flow=True)
    assert lab.choose(placing=Placing.PACKED) == lab  # nothing to turn on


def test_the_choice_is_kept() -> None:
    lab = CaptionLab(flow=True, placing=Placing.EVENLY)
    assert lab.to_stored() == {"flow": True, "placing": "evenly"}
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    assert CaptionLab.from_stored({"placing": "sideways"}) == CaptionLab()


def test_the_labs_row_shows_and_sets_it(qapp: QApplication) -> None:
    changed: list[CaptionLook] = []
    look = LookView(CaptionLook(), on_change=changed.append)
    panel = LabPanel(look)
    MADE.append(panel)
    panel.refresh()
    assert panel.placing.value() is Placing.PACKED
    panel.placing.changed.emit(Placing.NEAREST)
    assert look.value.lab == CaptionLab(flow=True, placing=Placing.NEAREST)
    panel.refresh()
    assert panel.placing.value() is Placing.NEAREST
    assert panel.flow.switch.isChecked()
    # without New layout it does nothing: shown as Packed, its value kept
    look.set_lab(replace(look.value.lab, flow=False))
    panel.refresh()
    assert panel.placing.value() is Placing.PACKED
    assert look.value.lab.placing is Placing.NEAREST
