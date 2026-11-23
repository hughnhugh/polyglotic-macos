"""Two independently recorded stretches can be one reversible display line."""

from dataclasses import replace

import pytest

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.continuations import CaptionGroups
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

A, B, C = map(CaptionId, ("fragment", "continuation", "replaced"))
APP = SourceId("app")
EN = Language("en")
ZH = Language("zh")
FIRST = CaptionUpdate(
    A,
    APP,
    CaptionKind.FINISHED,
    (Clause("目前在。", {EN: "Currently at."}),),
    ZH,
    (ZH,),
)
LINK = WordLink((3, 5), (3, 11), True, 1.0)
WHOLE = replace(
    FIRST,
    caption_id=B,
    continues=A,
    clauses=(Clause("目前在上海。", {EN: "In Shanghai."}, {EN: (LINK,)}),),
)


class Display:
    def __init__(self) -> None:
        self.history = CaptionHistory()
        self.refresh: list[CaptionId] = []
        self.groups = CaptionGroups(self.history, self.refresh.append)

    def receive(self, update: CaptionUpdate) -> None:
        for shown in self.groups.project(update):
            self.history.apply(shown)

    @property
    def originals(self) -> list[str]:
        return [c.original for c in self.history.captions]


def test_continuation_is_one_reversible_revision_with_the_combined_links() -> None:
    d = Display()
    d.receive(FIRST)
    key = d.history.captions[0].key
    d.receive(
        replace(WHOLE, continues=None, kind=CaptionKind.LIVE, clauses=(Clause("上海"),))
    )
    d.receive(WHOLE)
    d.receive(WHOLE)
    d.receive(FIRST)  # duplicate first answer
    d.receive(replace(WHOLE, continues=None, kind=CaptionKind.LIVE))  # late draft
    assert d.originals == ["目前在上海。"]
    (grouped,) = d.history.captions
    assert grouped.key == key
    assert grouped.clauses == WHOLE.clauses
    assert d.refresh == []

    d.receive(
        replace(WHOLE, continues=None, clauses=(Clause("上海。", {EN: "Shanghai."}),))
    )
    assert d.originals == ["目前在。", "上海。"]
    assert d.history.captions[0].key == key
    assert d.history.captions[0].clauses == FIRST.clauses


def test_withdrawn_child_restores_the_first_and_a_late_retry_stays_gone() -> None:
    d = Display()
    d.receive(FIRST)
    d.receive(WHOLE)
    d.receive(CaptionUpdate(B, APP, CaptionKind.WITHDRAWN))
    d.receive(WHOLE)
    assert d.originals == ["目前在。"]
    assert d.refresh == []


@pytest.mark.parametrize("withdraw", [True, False])
def test_changing_the_first_releases_the_group_and_refreshes_only_the_second(
    withdraw: bool,
) -> None:
    d = Display()
    d.receive(FIRST)
    d.receive(WHOLE)
    changed = (
        CaptionUpdate(A, APP, CaptionKind.WITHDRAWN)
        if withdraw
        else replace(FIRST, clauses=(Clause("现在。"),))
    )
    d.receive(changed)
    assert d.originals == ([] if withdraw else ["现在。"])
    assert d.refresh == [B]
    d.receive(WHOLE)  # a stale combined answer cannot undo the correction
    assert d.originals == ([] if withdraw else ["现在。"])
    independent = replace(WHOLE, continues=None, clauses=(Clause("上海。"),))
    d.receive(independent)
    assert d.originals[-1] == "上海。"


def test_true_audio_replacements_remain_permanent_alongside_a_display_join() -> None:
    d = Display()
    d.receive(FIRST)
    extra = replace(FIRST, caption_id=C)
    d.receive(extra)
    d.receive(replace(WHOLE, replaces=(C,)))
    d.receive(extra)
    d.receive(CaptionUpdate(B, APP, CaptionKind.WITHDRAWN))
    assert d.originals == ["目前在。"]
    assert d.history.dismissed(C)
    assert not d.history.dismissed(A)


def test_unmarked_captions_and_other_sources_keep_their_own_lines() -> None:
    d = Display()
    d.receive(FIRST)
    d.receive(replace(WHOLE, source_id=SourceId("other")))
    assert [c.caption_id for c in d.history.captions] == [A, B]
    d.receive(
        replace(
            WHOLE,
            continues=None,
            source_id=SourceId("other"),
            clauses=(Clause("上海。"),),
        )
    )
    assert d.originals == ["目前在。", "上海。"]
