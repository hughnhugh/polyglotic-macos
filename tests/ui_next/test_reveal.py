"""A new caption's lines shown one at a time: the rules, without Qt (the
Lab's Gap between new lines, polyglotic-hq 309). Keys and counts only."""

from polyglotic_desktop.ui_next.views.reveal import Reveal

GAP, LONGEST = 0.25, 3.0


def run(reveal: Reveal, totals: dict[int, int], start: float, until: float) -> list:
    """What shows at each change from `start` to `until`, stepping when
    the reveal says something is due: (time, {key: lines shown})."""
    seen, now = [], start
    while now <= until:
        if reveal.step(now, GAP, LONGEST, totals.get):
            shown = {key: reveal.shown(key) for key in totals}
            seen.append(
                (
                    round(now, 3),
                    {k: totals[k] if v is None else v for k, v in shown.items()},
                )
            )
        wait = reveal.wait_for(now, GAP, LONGEST)
        if wait is None:
            break
        now += max(wait, 0.001)
    return seen


def test_a_caption_on_its_own_shows_its_first_line_at_once_then_one_a_gap() -> None:
    """The user, 2026-11-14: a finished caption's lines "shown one after
    another a short moment apart ... never all together" - and its first
    is no later than today."""
    reveal = Reveal()
    reveal.add(7, 10.0)
    assert reveal.shown(7) == 0 and reveal.pending
    seen = run(reveal, {7: 4}, 10.0, 20.0)
    assert seen == [
        (10.0, {7: 1}),
        (10.25, {7: 2}),
        (10.5, {7: 3}),
        (10.75, {7: 4}),
    ]
    assert reveal.shown(7) is None and not reveal.pending


def test_a_one_line_caption_is_simply_there() -> None:
    reveal = Reveal()
    reveal.add(1, 5.0)
    assert reveal.step(5.0, GAP, LONGEST, {1: 1}.get)
    assert reveal.shown(1) is None and not reveal.pending
    assert reveal.wait_for(5.0, GAP, LONGEST) is None


def test_captions_arriving_together_show_oldest_first_line_by_line() -> None:
    reveal = Reveal()
    reveal.add(2, 0.0)
    reveal.add(1, 0.0)
    seen = run(reveal, {1: 2, 2: 2}, 0.0, 9.0)
    assert seen == [
        (0.0, {1: 1, 2: 0}),
        (0.25, {1: 2, 2: 0}),
        (0.5, {1: 2, 2: 1}),
        (0.75, {1: 2, 2: 2}),
    ]


def test_a_line_soon_after_the_last_waits_out_the_gap() -> None:
    reveal = Reveal()
    reveal.add(1, 0.0)
    assert reveal.step(0.0, GAP, LONGEST, {1: 1}.get)
    reveal.add(2, 0.1)
    assert not reveal.step(0.1, GAP, LONGEST, {2: 1}.get)
    assert reveal.shown(2) == 0
    assert abs((reveal.wait_for(0.1, GAP, LONGEST) or 0.0) - 0.15) < 1e-9
    assert reveal.step(0.25, GAP, LONGEST, {2: 1}.get)
    assert reveal.shown(2) is None


def test_no_caption_waits_longer_than_the_longest_wait_for_text() -> None:
    """Decision 0068's bound wins: a burst of long captions - past the
    longest wait, a caption's lines are all there at once."""
    reveal = Reveal()
    totals = {key: 20 for key in (1, 2, 3)}
    for key in totals:
        reveal.add(key, 0.0)
    seen = run(reveal, totals, 0.0, 30.0)
    assert seen[-1][0] <= LONGEST + 0.001
    assert seen[-1][1] == {1: 20, 2: 20, 3: 20}
    assert not reveal.pending
    late = Reveal()
    late.add(1, 0.0)
    assert late.step(0.0, GAP, 0.3, {1: 9}.get) and late.shown(1) == 1
    assert late.wait_for(0.26, GAP, 0.3) == 0.0  # the next line is due
    assert late.step(0.31, GAP, 0.3, {1: 9}.get) and late.shown(1) is None


def test_a_caption_that_went_or_shrank_is_forgotten() -> None:
    reveal = Reveal()
    reveal.add(1, 0.0)
    reveal.add(2, 0.0)
    assert reveal.step(0.0, GAP, LONGEST, {1: 3, 2: 3}.get)
    assert not reveal.step(0.1, GAP, LONGEST, {2: 3}.get)  # 1 withdrawn
    assert reveal.shown(1) is None and reveal.shown(2) == 0
    assert reveal.step(0.25, GAP, LONGEST, {2: 3}.get) and reveal.shown(2) == 1
    assert not reveal.step(0.3, GAP, LONGEST, {2: 1}.get)  # rewritten shorter
    assert not reveal.pending


def test_everything_at_once_when_asked() -> None:
    reveal = Reveal()
    reveal.add(1, 0.0)
    reveal.step(0.0, GAP, LONGEST, {1: 5}.get)
    assert reveal.settle() and reveal.shown(1) is None
    assert not reveal.settle()
    reveal.add(2, 1.0)
    reveal.step(1.0, GAP, LONGEST, {2: 5}.get)
    reveal.add(2, 1.1)  # told twice: what shows of it stays
    assert reveal.shown(2) == 1
