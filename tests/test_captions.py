"""Caption updates as plain values (core.listening.captions).

Made-up captions; the protocol examples are turned into these in
`connection` (tests/test_protocol.py).
"""

import dataclasses

import pytest

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, WithdrawalReason

EN, ZH = Language("en"), Language("zh")


def test_a_finished_caption_with_a_translation_and_word_links() -> None:
    clause = Clause(
        "你好",
        translations={EN: "Hello"},
        links={EN: (WordLink((0, 2), (0, 5), key=True, confidence=0.9),)},
    )
    update = CaptionUpdate(
        CaptionId("c1"),
        SourceId("source-1"),
        CaptionKind.FINISHED,
        clauses=(clause,),
        language=ZH,
        languages_heard=(ZH,),
        replaces=(CaptionId("c2"),),
        processing_ms=412,
    )
    assert update.clauses[0].translations[EN] == "Hello"
    link = update.clauses[0].links[EN][0]
    assert clause.original[slice(*link.original)] == "你好"
    assert "Hello"[slice(*link.translation)] == "Hello"


def test_a_withdrawn_caption_has_only_its_reason() -> None:
    update = CaptionUpdate(
        CaptionId("c1"),
        SourceId("mic"),
        CaptionKind.WITHDRAWN,
        reason=WithdrawalReason.NEAR_SILENCE_PHRASE,
    )
    assert update.clauses == () and update.language is None
    assert update.replaces == ()


def test_caption_updates_cannot_be_changed() -> None:
    update = CaptionUpdate(CaptionId("c1"), SourceId("app"), CaptionKind.LIVE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        update.kind = CaptionKind.FINISHED  # type: ignore[misc]
