"""Checking a line with the best model: "Looks wrong?" (project 101).

A learner who thinks a finished caption is wrong asks for it to be checked.
The app sends the speech it still holds for the line (recent speech,
decision 0027) to the server, which runs it on its best models and answers
with their version (polyglotic-server decision 0031). The app shows the two
side by side with what differs boxed; the learner may answer, and with
"The best model is right" the transcript keeps the best model's line.

The rules here, with no I/O and no Qt:
- what a recheck sends (`RecheckRequest`) and how it can end
  (`RecheckOutcome`: the server's four, and the app's own three - the
  audio isn't held any more, no listening session to send it on, no
  answer in time);
- what differs between two versions of a line (`differences`): word by
  word, or character by character in Chinese and Japanese;
- the content-free count sent when the comparison closes (`LineFlagged`,
  the tracking plan's `line_flagged`): the line's language, its source's
  category, how the check came out and the learner's answer - never its
  words or audio.

Nothing here keeps the line: the audio is the recent-speech store's, the
text the caption history's, and the server keeps nothing either.
"""

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.sources import Source
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ports.capture import SourceCategory

ANSWER_WITHIN_SEC = 30.0
"""How long the comparison waits for the server's answer (a check takes a
few seconds on the best models)."""

Span = tuple[int, int]
"""`[start, end)` in a line's text, in code points."""


class RecheckOutcome(StrEnum):
    """How a recheck ended: the server's `recheck_result` outcomes, then the app's own."""

    CHECKED = "checked"
    BEST_UNAVAILABLE = "best_unavailable"
    TRY_LATER = "try_later"
    FAILED = "failed"
    NOT_HELD = "not_held"  # the line's audio isn't held any more
    NOT_LISTENING = "not_listening"  # no listening session to send it on
    NO_ANSWER = "no_answer"  # nothing came back within ANSWER_WITHIN_SEC


@dataclass(frozen=True, slots=True)
class RecheckRequest:
    """One finished line's speech, to check on the best models. `audio` is
    the Ogg Opus as it was first sent: never logged."""

    caption_id: CaptionId
    source: Source
    speech_start: float
    speech_end: float
    audio: bytes = field(repr=False)
    spoken_language: Language | None  # None: detect
    targets: tuple[Language, ...]
    second_languages: Mapping[Language, Language] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecheckResult:
    """The best models' version of a line, or why there's none. `clauses`
    is empty for a check that heard no words (and for every other outcome).
    `retry_after`: seconds, with TRY_LATER."""

    caption_id: CaptionId
    outcome: RecheckOutcome
    clauses: tuple[Clause, ...] = ()
    language: Language | None = None
    languages_heard: tuple[Language, ...] = ()
    retry_after: int | None = None
    processing_ms: int | None = None


class Answer(StrEnum):
    """The learner's answer on the comparison - optional."""

    BEST_RIGHT = "best_right"  # "The best model is right": the transcript keeps it
    BOTH_FINE = "both_fine"
    BOTH_WRONG = "both_wrong"


class FlagOutcome(StrEnum):
    """How a flagged line's check came out, as the tracking plan counts it."""

    DIFFERS = "differs"
    SAME = "same"
    NO_WORDS = "no_words"
    BEST_UNAVAILABLE = "best_unavailable"
    TRY_LATER = "try_later"
    NOT_HELD = "not_held"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LineFlagged:
    """The count sent when a comparison closes (`line_flagged`, usage
    statistics, only with consent). `source_category` is None when the
    line's audio wasn't held (the store knew its source); `answer` None:
    closed without one."""

    language: Language
    source_category: SourceCategory | None
    outcome: FlagOutcome
    answer: Answer | None


def same_line(seen: Sequence[Clause], checked: Sequence[Clause]) -> bool:
    """Whether the best model's version says exactly what was shown: the
    same words, and the same translations into the languages both have."""
    if _joined(c.original for c in seen) != _joined(c.original for c in checked):
        return False
    shared = {t for c in seen for t in c.translations} & {
        t for c in checked for t in c.translations
    }
    return all(
        _joined(c.translations.get(t, "") for c in seen)
        == _joined(c.translations.get(t, "") for c in checked)
        for t in shared
    )


def flag_outcome(seen: Sequence[Clause], result: RecheckResult) -> FlagOutcome:
    """How a check came out, for the count: differs, the same, no words, or why it wasn't checked."""
    match result.outcome:
        case RecheckOutcome.CHECKED if not result.clauses:
            return FlagOutcome.NO_WORDS
        case RecheckOutcome.CHECKED:
            same = same_line(seen, result.clauses)
            return FlagOutcome.SAME if same else FlagOutcome.DIFFERS
        case RecheckOutcome.BEST_UNAVAILABLE:
            return FlagOutcome.BEST_UNAVAILABLE
        case RecheckOutcome.TRY_LATER:
            return FlagOutcome.TRY_LATER
        case RecheckOutcome.NOT_HELD:
            return FlagOutcome.NOT_HELD
        case _:
            return FlagOutcome.FAILED


# A unit of comparison: one Chinese or Japanese character (they aren't
# space-separated), or a run of letters and digits
_UNIT = re.compile(r"[⺀-鿿豈-﫿＀-￯]|[^\W_]+")


def differences(before: str, after: str) -> tuple[list[Span], list[Span]]:
    """The spans of `before` and of `after` to box: the words (or Chinese
    and Japanese characters) that one version has and the other doesn't,
    neighbours joined. Spaces and punctuation alone never count."""
    a = [(m.group().casefold(), m.span()) for m in _UNIT.finditer(before)]
    b = [(m.group().casefold(), m.span()) for m in _UNIT.finditer(after)]
    matcher = difflib.SequenceMatcher(
        None, [u for u, _ in a], [u for u, _ in b], autojunk=False
    )
    boxed_a: list[Span] = []
    boxed_b: list[Span] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            boxed_a.append((a[i1][1][0], a[i2 - 1][1][1]))
        if j2 > j1:
            boxed_b.append((b[j1][1][0], b[j2 - 1][1][1]))
    return boxed_a, boxed_b


def _joined(pieces: Iterable[str]) -> str:
    return " ".join(p.strip() for p in pieces if p.strip())
