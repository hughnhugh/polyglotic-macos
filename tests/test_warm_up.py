"""When a warm-up notice's wait is over (core.listening.warm_up): a caption
for the speech model, a translation for the translator."""

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.core.listening.warm_up import (
    MODELS_WARMING_UP,
    TRANSLATOR_WARMING_UP,
    warm_up_over,
)


def update(kind: CaptionKind, *clauses: Clause) -> CaptionUpdate:
    return CaptionUpdate(CaptionId("c1"), SourceId("s1"), kind, clauses)


WORDS = Clause("你好")
TRANSLATED = Clause("你好", {Language("en"): "Hello"})


def test_the_speech_models_warm_up_is_over_at_the_first_caption_with_words() -> None:
    assert warm_up_over(MODELS_WARMING_UP, update(CaptionKind.LIVE, WORDS))
    assert warm_up_over(MODELS_WARMING_UP, update(CaptionKind.FINISHED, WORDS))
    assert not warm_up_over(MODELS_WARMING_UP, update(CaptionKind.LIVE))
    assert not warm_up_over(MODELS_WARMING_UP, update(CaptionKind.WITHDRAWN))


def test_the_translators_warm_up_is_over_at_the_first_translation() -> None:
    assert not warm_up_over(TRANSLATOR_WARMING_UP, update(CaptionKind.FINISHED, WORDS))
    assert warm_up_over(TRANSLATOR_WARMING_UP, update(CaptionKind.LIVE, TRANSLATED))


def test_other_notices_are_never_over_this_way() -> None:
    assert not warm_up_over("server_restarting", update(CaptionKind.FINISHED, WORDS))
