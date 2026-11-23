"""Lookup context: the line a word was looked up in, and its translation.

From the proof of concept's `ui/lookup.py` (`context_for`), out of Qt and
by language code rather than by script. A saved word keeps it as its
source sentence and that sentence's translation - the user's own data,
kept on this PC (never sent: the server gets entry IDs and times only).

The word's counterpart in the line's translation ("Here: ngân hàng";
polyglotic-hq 328) is shown on the card and nowhere else: a saved word
doesn't keep it, nor Anki, nor the learning events - whether a saved word
should is the user's decision (326's stage 2).

**Lookups kept** (`LookupCount`, polyglotic-hq 373; the user, DECISIONS
#176 (c): "yes, keep everything"): how often each word was looked up on
this PC - pinned (a click) and on hover - and when last, kept with the
learning data and never sent beyond the lookup events the server already
gets (entry IDs and times). A word the learner said they know and then
looked up again, pinned, `CHECK_AFTER` times is offered in a check; the
app never changes its status by itself (#176 (d)).
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

CHECK_AFTER = 2
"""Pinned lookups of a word the learner said they know, after they said
so, that offer it in a check (the user, DECISIONS #176 (d): "looked up
twice afterwards")."""

TURNS_NEW_AFTER = 2
"""Pinned lookups of a word only assumed known that turn it new
(`Vocabulary.looked_up`): one click alone doesn't - it selects a word,
opens its card to hear it, or misses (polyglotic-hq 397: "the", "that"
and "you", clicked once each, were dotted as new). Twice, as a word said
known is offered in a check (`CHECK_AFTER`)."""

DEEP_WITHIN = 0.5
"""The share of the learner's line, from its most common word, whose
words no number of clicks makes new (`Vocabulary.looked_up`): "the" (the
1st) for someone who knows about 2,000 words - the harness clicked it on
three rows, and it was dotted again (polyglotic-hq 397). Past it, up to
the line, two clicks do: the line is "about" N words."""


@dataclass(frozen=True)
class LookupCount:
    """How often a word was looked up on this PC: `pinned` (a click) and
    `hovered`, `last` when last; `pinned_since_known`: pinned lookups since
    the learner last said they know it (0 when they haven't, or said
    anything about it since)."""

    pinned: int = 0
    hovered: int = 0
    last: datetime | None = None
    pinned_since_known: int = 0

    def looked_up(self, pinned: bool, at: datetime, said_known: bool) -> "LookupCount":
        """One more lookup at `at`; `said_known`: the learner said they know
        the word (a pinned lookup then counts towards a check)."""
        return LookupCount(
            self.pinned + pinned,
            self.hovered + (not pinned),
            at if self.last is None else max(self.last, at),
            self.pinned_since_known + (pinned and said_known),
        )

    def said(self) -> "LookupCount":
        """The learner said something about the word: the check's count
        starts again."""
        return replace(self, pinned_since_known=0)

    def joined(self, other: "LookupCount") -> "LookupCount":
        """Two entries' counts as one (an entry merged into another)."""
        lasts = [t for t in (self.last, other.last) if t is not None]
        return LookupCount(
            self.pinned + other.pinned,
            self.hovered + other.hovered,
            max(lasts) if lasts else None,
            self.pinned_since_known + other.pinned_since_known,
        )

    @property
    def to_check(self) -> bool:
        """Looked up, pinned, `CHECK_AFTER` times since the learner said
        they know it: offered in a check, never changed by the app."""
        return self.pinned_since_known >= CHECK_AFTER


_CONTINUED = " …"  # how a cut-off overlay row ends


@dataclass(frozen=True)
class LookupContext:
    sentence: str  # the line the word was in
    translation: str = ""  # that line in another language, if any
    counterpart: str = ""
    """What the word is in the translation shown with its line: the words
    the caption's word links join it to ("" for none). For the card only."""
    counterpart_language: str = ""
    """The counterpart's language code, for its font ("" if unknown)."""
    word_class: str | None = None
    """Display class of the word in this caption, if available."""


def is_chinese(language: str) -> bool:
    """Mandarin in any script, or Cantonese (protocol.md's codes)."""
    return language == "zh" or language.startswith("zh-") or language == "yue"


def lookup_context(line: str, versions: Mapping[str, str]) -> LookupContext:
    """The lookup context of a word in `line`, one of `versions` - the
    caption's (or the clause row's) text by language code, what was said
    first, then its translations. The translation paired with it: for a
    Chinese line, the English version if there is one, else the first
    that isn't Chinese; for any other line, a Chinese version if there is
    one, else the first other version."""
    sentence = line.removesuffix(_CONTINUED)
    own = next((lang for lang, text in versions.items() if text == sentence), None)
    others = [
        (lang, text)
        for lang, text in versions.items()
        if text and text != sentence and lang != own
    ]
    if own is not None and is_chinese(own):
        preferred = [text for lang, text in others if lang == "en"] + [
            text for lang, text in others if not is_chinese(lang)
        ]
    else:
        preferred = [text for lang, text in others if is_chinese(lang)]
    preferred += [text for _, text in others]
    return LookupContext(sentence, preferred[0] if preferred else "")
