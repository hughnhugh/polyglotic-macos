"""Caption history: the session's captions in order, kept up to date as
caption updates arrive.

From the proof of concept's `captions.py` (`CaptionBoard`), typed, on
protocol.md's caption updates:
- a **live update** replaces its caption in place, or adds it at the end;
- a **finished caption** replaces it for good - and a **joined caption**
  (a finished update with `replaces`) also takes the place of the captions
  it replaces, in the earliest one's place;
- a **withdrawn caption** goes.

Every caption keeps a `key` for as long as it's shown - through its live
updates, its finishing and joins - so a view updates what it drew rather
than drawing it afresh. The last `MAX_HISTORY` captions are kept - or
as many as asked, and with `keep_for` only those that first appeared in
that many seconds (a transcript's "the last 3 hours", polyglotic-hq 334);
`set_limits` changes both while captions arrive. If asked
(`keep_earlier`), the finished captions that dropped off before them are
kept as text, for writing out the whole session (a transcript's Copy all
and Save, polyglotic-hq 137) - and a raised limit takes them back.

**Never blank:** a translation stays until a new one arrives. If a live
update comes without a clause's translation that the previous version had
(the translation still on its way, or live translation turned off
mid-caption), the clause keeps the previous one. A finished caption keeps
it only for a clause whose original didn't change (the translation failed
this time) - otherwise what was finished is what's shown.

**Settled text** (polyglotic-hq 296, decision 0088): what a caption has
shown for a few seconds doesn't change. An update - a live update, the
finished caption, a join - is the same speech heard again; `apply` keeps
the words the caption (and, for a join, the captions it replaces) has
shown unchanged for 3s (or the shorter time chosen: `set_settle_after`),
and its clauses above the last two, and takes
only what comes after them from the update (`core.listening.settling`).

An update that comes too late is ignored: a live update for a caption
already finished, or any update for one that was withdrawn or replaced.

**A caption whose finished caption won't come ends with what it shows**
(polyglotic-hq 557, 529's B3): its finished speech failed on the server,
was given up, or was never sent. It stayed live - provisional - for good,
and never reached the transcript or Copy all. `ended` gives the finished
update that ends it, its words and translations as shown; applied like
any other, it ends it everywhere the updates go.

**Established text** (polyglotic-hq 494, decision 0228;
`core.listening.established`): a live caption keeps how much of its start
the server says is established - the update's count, carried over to the
text as shown (its settled words kept) - and an update that changes words
shown as established says which words took their place (`corrected`), for
a quiet correction.

**Checked by the best model** ("Looks wrong?", project 101): when the
learner says the best model's version is right, `use_checked` puts it in
the finished caption's place, marked `checked`, keeping the version first
shown (`first_shown`). A later join of the caption replaces it as any
finished update does.

Holds caption text: never log it. Not thread-safe - one thread (the UI's).
"""

import itertools
from collections import OrderedDict, deque
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.established import (
    Span,
    corrected,
    kept_established,
)
from polyglotic_desktop.core.listening.settling import (
    SETTLE_AFTER_SEC,
    SETTLE_RANGE,
    Stable,
    joint,
    settle,
    settled_length,
    shown_text,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

MAX_HISTORY = 300
"""Captions kept; older ones drop off the front (the proof of concept's)."""

_GONE_REMEMBERED = 300
"""Withdrawn and replaced caption ids remembered, to ignore late updates."""


@dataclass(frozen=True, slots=True)
class Caption:
    """A caption as the history holds it: its latest version.

    `key` is stable for as long as the caption is shown, through its
    updates and any join; views use it to keep what they drew. `by_you`:
    from the user's own mic. `live`: still being spoken - a live update,
    replaced later. `started_at` is when it first appeared (a join keeps
    the earlier caption's); `updated_at` when this version arrived.
    `checked`: the best model's version, chosen by the learner over
    `first_shown`, the one the caption first finished with. `established`:
    how much of a live caption's start is established, in characters of
    its clauses' originals counted in order (0 for a finished one: all of
    it is final); `corrected`: the words this version put in place of
    words the version before showed as established, in the same count
    (`core.listening.established`). `respoken`: the learner re-spoke it
    for its source (polyglotic-hq 567): theirs, marked so."""

    key: int
    caption_id: CaptionId
    source_id: SourceId
    by_you: bool
    live: bool
    clauses: tuple[Clause, ...]
    language: Language | None
    languages_heard: tuple[Language, ...]
    started_at: datetime
    updated_at: datetime
    checked: bool = False
    first_shown: tuple[Clause, ...] = ()
    established: int = 0
    corrected: tuple[Span, ...] = ()
    respoken: bool = False

    @property
    def original(self) -> str:
        """What was said: the clauses' originals joined."""
        return join_text(c.original for c in self.clauses)

    def translation(self, language: Language) -> str:
        """The caption translated into `language`, clause by clause - a
        clause with no translation into it shows its original."""
        return join_text(c.translations.get(language, c.original) for c in self.clauses)


def join_text(pieces: Iterable[str]) -> str:
    """Joins text with a space - or without one next to a Chinese or
    Japanese character, which aren't space-separated (the proof of
    concept's `join_text`)."""
    out = ""
    for raw in pieces:
        piece = raw.strip()
        if not piece:
            continue
        if out and not (is_cjk(out[-1]) or is_cjk(piece[0])):
            out += " "
        out += piece
    return out


def is_cjk(char: str) -> bool:
    """A Chinese or Japanese character or punctuation mark, full-width
    forms included: no space goes beside it (`join_text`, and dictation's
    text)."""
    return (
        "\u2e80" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        or "\uff00" <= char <= "\uffef"
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def newest_finished(captions: Sequence[Caption]) -> Caption | None:
    """The newest finished caption - the one the "Copy the newest caption"
    hotkey copies (polyglotic-hq 567) - or None."""
    return next((c for c in reversed(captions) if not c.live), None)


def copied_text(caption: Caption) -> str:
    """A caption as it's copied: what was said, then its translation into
    each language it has one in, a line each."""
    languages = dict.fromkeys(lang for c in caption.clauses for lang in c.translations)
    lines = [caption.original, *(caption.translation(x) for x in languages)]
    return "\n".join(lines)


class CaptionHistory:
    """The session's captions in order, oldest first. `apply` takes each
    caption update; views read `captions` and `version` (bumped on every
    change, so they know when to redraw)."""

    def __init__(
        self,
        your_sources: Collection[SourceId] = (),
        clock: Callable[[], datetime] = _utc_now,
        max_captions: int = MAX_HISTORY,
        keep_earlier: int = 0,
        keep_for: float | None = None,
    ) -> None:
        """`your_sources`: the sources that are the user's own mic - their
        captions are "by you". `max_captions`: at most this many kept;
        `keep_for`: and only those that first appeared in the last this
        many seconds (None: however long ago). `keep_earlier`: how many
        finished captions that drop off the front are kept in `earlier`
        (the oldest of those go first)."""
        self._yours = frozenset(your_sources)
        self._clock = clock
        self._max = max_captions
        self._keep_for = keep_for
        self.earlier: deque[Caption] = deque(maxlen=keep_earlier)
        """Finished captions dropped off the front, oldest first, as text:
        no word links, no first version - what writing them out needs.
        Never updated again: a join, withdrawal or check this far back
        doesn't reach them - unless a raised limit takes them back
        (`set_limits`), still as text."""
        self._captions: list[Caption] = []
        self._keys = itertools.count(1)
        self._gone: OrderedDict[CaptionId, None] = OrderedDict()
        # how long each shown caption's words have stood, and how much
        # speech its latest version heard (seconds; None: not known)
        self._stable: dict[CaptionId, Stable] = {}
        self._heard: dict[CaptionId, float | None] = {}
        self._settle_after = SETTLE_AFTER_SEC
        self.started_at = clock()
        self.version = 0

    @property
    def captions(self) -> tuple[Caption, ...]:
        return tuple(self._captions)

    def caption(self, caption_id: CaptionId) -> Caption | None:
        return next((c for c in self._captions if c.caption_id == caption_id), None)

    def dismissed(self, caption_id: CaptionId) -> bool:
        """Whether a withdrawal or permanent audio join already retired this ID."""
        return caption_id in self._gone

    def ended(self, caption_id: CaptionId) -> CaptionUpdate | None:
        """The update that ends `caption_id` when its finished caption won't
        come (dropped): finished, with what it shows - its words, their
        translations, its language. None if it isn't shown live: finished
        already, gone, or never shown (nothing provisional to end)."""
        caption = self.caption(caption_id)
        if caption is None or not caption.live:
            return None
        return CaptionUpdate(
            caption_id=caption.caption_id,
            source_id=caption.source_id,
            kind=CaptionKind.FINISHED,
            clauses=caption.clauses,
            language=caption.language,
            languages_heard=caption.languages_heard,
        )

    @property
    def settle_after(self) -> float:
        """How long shown words may still change, in seconds
        (`SETTLE_RANGE`; 0: settled as soon as shown)."""
        return self._settle_after

    def set_settle_after(self, seconds: float) -> None:
        """The learner's choice, kept within `SETTLE_RANGE`. It applies
        from the next update on: what an earlier update changed stays."""
        low, high = SETTLE_RANGE
        self._settle_after = min(high, max(low, seconds))

    @property
    def limits(self) -> tuple[int, float | None]:
        """At most how many captions are kept, and for how many seconds
        (None: however long ago they appeared)."""
        return self._max, self._keep_for

    def set_limits(self, max_captions: int, keep_for: float | None = None) -> None:
        """Keeps at most `max_captions`, and with `keep_for` only those that
        first appeared in the last that many seconds - from now: what's
        past the new limits drops off the front at once (finished captions
        into `earlier`, if it keeps any); under a raised limit the captions
        that dropped off before come back from `earlier`, newest first,
        while they're within it - as text (no word links)."""
        if (max_captions, keep_for) == self.limits:
            return
        self._max, self._keep_for = max_captions, keep_for
        before = len(self._captions)
        oldest = self._oldest_kept()
        taken: list[Caption] = []
        while (
            self.earlier
            and before + len(taken) < self._max
            and (oldest is None or self.earlier[-1].started_at >= oldest)
        ):
            taken.append(self.earlier.pop())
        if taken:
            self._captions[:0] = reversed(taken)
            self.version += 1
        if self._drop_off_the_front():
            self.version += 1

    def is_yours(self, source_id: SourceId) -> bool:
        return source_id in self._yours

    def apply(
        self, update: CaptionUpdate, *, hold_live_translation: bool = False
    ) -> Caption | None:
        """Applies a caption update. Returns the caption as it now stands,
        or None if it went (withdrawn) or the update came too late."""
        if update.caption_id in self._gone:
            return None
        if update.kind is CaptionKind.WITHDRAWN:
            self._remove([update.caption_id])
            return None
        current = self.caption(update.caption_id)
        if update.kind is CaptionKind.LIVE and current is not None and not current.live:
            return None  # a late live update never undoes a finished caption
        live = update.kind is CaptionKind.LIVE
        now = self._clock()
        replaced = () if live else update.replaces
        clauses, stable = self._settled(update, replaced, now.timestamp())
        if current is not None:
            # Video can finish the original before its translated packet arrives.
            # Keep the last accepted words through a correction of that original.
            pending_translation = (
                hold_live_translation
                and current.live
                and not any(clause.translations for clause in update.clauses)
            )
            clauses = keep_translations(
                current.clauses, clauses, live or pending_translation
            )
        established = (
            kept_established(update.clauses, update.established, clauses) if live else 0
        )
        fixed = (
            corrected(current.clauses, current.established, clauses)
            if current is not None and current.live
            else ()
        )
        caption = Caption(
            key=0,  # set by _place
            caption_id=update.caption_id,
            source_id=update.source_id,
            by_you=update.source_id in self._yours,
            live=live,
            clauses=clauses,
            language=update.language,
            languages_heard=update.languages_heard,
            started_at=now,
            updated_at=now,
            established=established,
            corrected=fixed,
            respoken=update.respoken or (current is not None and current.respoken),
        )
        placed = self._place(caption, (update.caption_id, *replaced))
        for caption_id in replaced:
            if caption_id != update.caption_id:
                self._forget(caption_id, permanent=caption_id != update.display_member)
        self._stable[update.caption_id] = stable
        self._heard[update.caption_id] = _speech_heard(update)
        self._drop_off_the_front()
        self.version += 1
        return placed

    def _settled(
        self, update: CaptionUpdate, replaced: tuple[CaptionId, ...], at: float
    ) -> tuple[tuple[Clause, ...], Stable]:
        """`update`'s clauses with what's settled of the captions it takes
        the place of kept as shown (its own, and for a join the ones it
        replaces, in the order shown), and how long the result's words
        have stood."""
        ids = (update.caption_id, *replaced)
        shown = [c for c in self._captions if c.caption_id in ids]
        if not shown or update.display_member is not None:
            return update.clauses, Stable().after("", shown_text(update.clauses), at)
        before: tuple[Clause, ...] = ()
        stable = Stable()
        for caption in shown:  # one caption's text after another's
            own = self._stable.get(caption.caption_id, Stable())
            text = shown_text(before)
            starts = len(text) + len(joint(text, shown_text(caption.clauses)))
            stable = stable.then(len(text), starts, own)
            before += caption.clauses
        settled = settled_length(
            before, stable.stood(at, self._settle_after), shown[-1].live
        )
        heard, hears = self._heard.get(update.caption_id), _speech_heard(update)
        grew = None
        if len(shown) == 1 and heard and hears and hears >= heard:
            grew = hears / heard
        clauses = settle(before, update.clauses, settled, grew)
        return clauses, stable.after(shown_text(before), shown_text(clauses), at)

    def use_checked(
        self,
        caption_id: CaptionId,
        clauses: tuple[Clause, ...],
        language: Language | None,
        languages_heard: tuple[Language, ...],
    ) -> Caption | None:
        """The best model's version of a finished caption, which the learner
        said is right, in its place; None if the caption isn't shown any
        more, is live, or the version has no words."""
        current = self.caption(caption_id)
        if current is None or current.live or not clauses:
            return None
        checked = replace(
            current,
            clauses=clauses,
            language=language or current.language,
            languages_heard=languages_heard or current.languages_heard,
            updated_at=self._clock(),
            checked=True,
            first_shown=current.first_shown or current.clauses,
            corrected=(),
        )
        self._captions[self._captions.index(current)] = checked
        self._stable[caption_id] = self._stable.get(caption_id, Stable()).after(
            shown_text(current.clauses),
            shown_text(clauses),
            checked.updated_at.timestamp(),
        )
        self.version += 1
        return checked

    def _place(self, caption: Caption, ids: tuple[CaptionId, ...]) -> Caption:
        """Puts `caption` in the place of the captions with `ids` - in the
        earliest one's place, keeping its key and when it first appeared -
        or at the end if none are shown."""
        positions = [i for i, c in enumerate(self._captions) if c.caption_id in ids]
        if not positions:
            placed = replace(caption, key=next(self._keys))
            self._captions.append(placed)
            return placed
        first = self._captions[positions[0]]
        placed = replace(caption, key=first.key, started_at=first.started_at)
        for i in reversed(positions[1:]):
            del self._captions[i]
        self._captions[positions[0]] = placed
        return placed

    def _oldest_kept(self) -> datetime | None:
        """The earliest a kept caption may have first appeared, now
        (`keep_for`); None: any time."""
        if self._keep_for is None:
            return None
        return self._clock() - timedelta(seconds=self._keep_for)

    def _drop_off_the_front(self) -> bool:
        """The oldest captions past `max_captions`, or that first appeared
        longer than `keep_for` ago, go - the finished ones into `earlier`,
        if it keeps any. True if any went."""
        cut = max(0, len(self._captions) - self._max)
        oldest = self._oldest_kept()
        if oldest is not None:
            while cut < len(self._captions) and self._captions[cut].started_at < oldest:
                cut += 1
        if not cut:
            return False
        dropped = self._captions[:cut]
        del self._captions[:cut]
        for caption in dropped:
            self._stable.pop(caption.caption_id, None)
            self._heard.pop(caption.caption_id, None)
        if self.earlier.maxlen:
            self.earlier.extend(_as_text(c) for c in dropped if not c.live)
        return True

    def _remove(self, ids: list[CaptionId]) -> None:
        kept = [c for c in self._captions if c.caption_id not in ids]
        for caption_id in ids:
            self._forget(caption_id)
        if len(kept) != len(self._captions):
            self._captions = kept
            self.version += 1

    def _forget(self, caption_id: CaptionId, *, permanent: bool = True) -> None:
        """Remembers that a caption went, so a late update can't bring it back."""
        if permanent:
            self._gone[caption_id] = None
        self._stable.pop(caption_id, None)
        self._heard.pop(caption_id, None)
        while len(self._gone) > _GONE_REMEMBERED:
            self._gone.popitem(last=False)


def _speech_heard(update: CaptionUpdate) -> float | None:
    """How many seconds of speech `update` heard, if its times are known."""
    times = update.times
    return None if times is None else times.speech_end - times.speech_start


def _as_text(caption: Caption) -> Caption:
    """The caption without what only showing it needs (word links, the
    version first shown): its text, translations, times and source."""
    clauses = tuple(replace(c, links={}) for c in caption.clauses)
    return replace(caption, clauses=clauses, first_shown=())


def keep_translations(
    before: tuple[Clause, ...], after: tuple[Clause, ...], live: bool
) -> tuple[Clause, ...]:
    """`after`'s clauses, each keeping the translations the clause at the
    same place had in `before` and hasn't now (never blank): always for a
    live update; for a finished one only where the clause's original is
    unchanged. A kept translation keeps its word links only if the
    original is unchanged (their spans would be wrong otherwise)."""
    kept = []
    for n, clause in enumerate(after):
        old = before[n] if n < len(before) else None
        if old is None:
            kept.append(clause)
            continue
        same = old.original == clause.original
        missing = [
            lang for lang in old.translations if not clause.translations.get(lang)
        ]
        if not missing or not (live or same):
            kept.append(clause)
            continue
        translations: dict[Language, str] = dict(clause.translations)
        links: dict[Language, tuple[WordLink, ...]] = dict(clause.links)
        written: dict[Language, Language] = dict(clause.written_in)
        for lang in missing:
            translations[lang] = old.translations[lang]
            if same and lang in old.links:
                links[lang] = old.links[lang]
            else:
                links.pop(lang, None)
            if lang in old.written_in:  # the kept line's own language
                written[lang] = old.written_in[lang]
            else:
                written.pop(lang, None)
        kept.append(
            replace(clause, translations=translations, links=links, written_in=written)
        )
    return tuple(kept)
