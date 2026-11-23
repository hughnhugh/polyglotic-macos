"""Type what they said from caption lines or a held speaker clip."""

from collections.abc import Iterable
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import CaptionUpdate, Language
from polyglotic_desktop.core.listening.history import is_cjk, join_text
from polyglotic_desktop.core.listening.sources import TYPE_THEIRS, Source
from polyglotic_desktop.core.shared.tunables import tunable
from polyglotic_desktop.ports.capture import SourceCategory

THEIRS_SOURCE = Source(TYPE_THEIRS, SourceCategory.SYSTEM)

SILENCE_PEAK = tunable(
    "type_theirs.silence_peak",
    0.004,
    "fraction of full scale (peak)",
    (0.0005, 0.05),
    source="669: reject holds containing only digital silence or near-silence",
)
HOLD_REPEAT_SEC = tunable(
    "type_theirs.x11_repeat_wait",
    0.02,
    "seconds",
    (0.005, 0.1),
    source="669: wait briefly for the matching press in an X11 auto-repeat pair",
)
PORTAL_POLL_SEC = tunable(
    "type_theirs.portal_stop_poll",
    0.1,
    "seconds",
    (0.05, 0.5),
    source="669: let a pending portal dialog or hold be cancelled on rebinding",
)


class TypeWhat(StrEnum):
    ORIGINAL = "original"
    TRANSLATION = "translation"


def theirs_text(update: CaptionUpdate, target: Language | None) -> str:
    """Join the finished caption's clauses using the selected output language."""
    return _typing_text(
        (clause.translations.get(target) or clause.original)
        if target is not None and clause.written_in.get(target, target) == target
        else clause.original
        for clause in update.clauses
    )


def shown_text(updates: tuple[CaptionUpdate, ...], target: Language | None) -> str:
    """Type the window's original or its displayed translation for each clause."""
    return _typing_text(
        (clause.translations.get(target) or clause.original)
        if target is not None
        else clause.original
        for update in updates
        for clause in update.clauses
    )


def _typing_text(clauses: Iterable[str]) -> str:
    text = join_text(clauses)
    return text + " " if text and not is_cjk(text[-1]) else text
