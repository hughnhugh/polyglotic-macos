from dataclasses import dataclass

from polyglotic_desktop.adapters.caption_word_breaks import (
    RECENT_CLAUSES,
    CaptionWordSplit,
    PackWordBreaks,
)
from polyglotic_desktop.ports.word_split import SplitWord


@dataclass
class Splitter:
    calls: int = 0

    def words(self, text: str) -> tuple[SplitWord, ...]:
        self.calls += 1
        return (SplitWord(0, len(text)),)


def test_selects_by_language_caches_per_clause_and_reports_a_missing_pack() -> None:
    chinese = Splitter()
    breaks = PackWordBreaks({"zh": chinese})
    expected = (SplitWord(0, 2),)
    assert breaks.words("很好", "zh") == expected
    assert breaks.words("很好", "zh") == expected
    assert chinese.calls == 1
    assert breaks.words("ภาษา", "th") is None


def test_only_recent_clause_splits_are_retained() -> None:
    chinese = Splitter()
    breaks = PackWordBreaks({"zh": chinese})
    for i in range(RECENT_CLAUSES):
        breaks.words(str(i), "zh")
    breaks.words("0", "zh")  # still in use on another surface
    breaks.words("next", "zh")
    breaks.words("0", "zh")
    assert chinese.calls == RECENT_CLAUSES + 1
    assert breaks.words("1", "zh") == (SplitWord(0, 1),)
    assert chinese.calls == RECENT_CLAUSES + 2


def test_dictionary_spans_are_adapted_to_word_break_values() -> None:
    split = CaptionWordSplit(lambda _text: [(0, 2), (2, 4)])
    assert [(word.start, word.end) for word in split.words("很好天气")] == [
        (0, 2),
        (2, 4),
    ]


def test_main_wiring_splits_and_composes_a_live_caption_through_the_pack() -> None:
    """The production composition root's adapter reaches the live flow path."""
    from tests.ui.fakes import chinese_tools
    from tests.ui_next.test_flow import Pitch

    from polyglotic_desktop.core.listening.caption_model import caption_model
    from polyglotic_desktop.core.listening.captions import Language
    from polyglotic_desktop.core.listening.history import CaptionHistory
    from polyglotic_desktop.main import caption_word_breaks
    from polyglotic_desktop.ui.recorded_captions import clause, live
    from polyglotic_desktop.ui_next.views.flow import Flow, FlowOptions

    tools = chinese_tools()
    breaks = caption_word_breaks(tools)
    history = CaptionHistory()
    history.apply(live("wired", clause("我很好，你呢", "I am well, and you?")))
    model = caption_model(history.captions[0], Language("en"), word_breaks=breaks)
    composed = Flow(Pitch()).compose([model], 100, FlowOptions(share=True, split=True))

    assert [
        model.clauses[0].original[a:b] for a, b, _ in model.clauses[0].original_units
    ] == [
        "我",
        "很",
        "好，",
        "你",
        "呢",
    ]
    assert composed.lines
    # Rebuilding the same clause is served by PackWordBreaks' per-clause cache.
    assert breaks.words("我很好，你呢", "zh") == breaks.words("我很好，你呢", "zh")
