"""A caption window names the language spoken when it changes, not over
every caption (polyglotic-hq 526, DECISIONS #230 item 3: "Mandarin" was
above each caption)."""

from datetime import UTC, datetime, timedelta

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui.recorded_captions import APP
from polyglotic_desktop.ui_next.views.captions import (
    NAMED_AGAIN_SEC,
    CaptionLines,
    Labels,
)

EN, ZH = Language("en"), Language("zh")


def said(n: int, language: Language) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(f"c{n}"), APP, CaptionKind.FINISHED, (Clause(f"caption {n}"),),
        language, (language,),
    )  # fmt: skip


def lines(once: bool) -> tuple[CaptionLines, list[datetime]]:
    now = [datetime(2026, 11, 20, 9, 0, tzinfo=UTC)]
    labels = Labels(
        show_language=True, spoken=lambda heard: "+".join(heard), language_once=once
    )
    return CaptionLines([APP], None, keep=10, labels=labels, clock=lambda: now[0]), now


def test_the_language_is_named_when_it_changes() -> None:
    view, now = lines(once=True)
    for n, language in enumerate([ZH, ZH, ZH, EN, EN, ZH]):
        now[0] += timedelta(seconds=3)
        view.apply(said(n, language))
    assert [line.label for line in view.lines] == ["zh", "", "", "en", "", "zh"]


def test_and_again_after_a_long_quiet() -> None:
    view, now = lines(once=True)
    view.apply(said(1, ZH))
    now[0] += timedelta(seconds=NAMED_AGAIN_SEC + 1)
    view.apply(said(2, ZH))
    now[0] += timedelta(seconds=2)
    view.apply(said(3, ZH))
    assert [line.label for line in view.lines] == ["zh", "zh", ""]


def test_the_first_caption_kept_is_named_when_older_ones_go() -> None:
    view, now = lines(once=True)
    for n in range(12):  # keeps 10
        now[0] += timedelta(seconds=3)
        view.apply(said(n, ZH))
    assert [line.label for line in view.lines] == ["zh", *[""] * 9]


def test_elsewhere_every_caption_is_named_as_before() -> None:
    view, _now = lines(once=False)
    for n in range(3):
        view.apply(said(n, ZH))
    assert [line.label for line in view.lines] == ["zh", "zh", "zh"]
