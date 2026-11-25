"""One app's captions as its caption window or transcript shows them: what
was said and its translation into one language - or no translation
("captions only").

Each app captioned (a source) gets a caption window and a transcript of
its own, each with the original and one translation (polyglotic-hq
DECISIONS.md #53); the user's own speech (the mic, "You") can show in it
too, so a view takes one or more sources (the user, 2026-11-07).
`CaptionLines` keeps those sources' captions in a caption history of its
own - so a transcript holds its 1,000 lines, not the session's last 300
across every app - and turns each into a `Line`: the rows core's display
rules give it (`core.listening.display`), in the language chosen. With
no language chosen a clause is its original row alone - no translation
row, not an empty one. A line is rebuilt only when its caption changes,
or the language or display options do; the text size changes no rows.

Above each caption a small line can say where it came from and the
language spoken ("Discord  Mandarin", "You"): `Labels`, in the source's
colour - the user's own always, the others' with "show the source" on.

`revision` goes up on anything that changes what shows; the widget
drawing the view repaints then. Where it's scrolled to is `scroll`.

Holds caption text: never log it. Not thread-safe - one thread (the
interface's).
"""

import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from polyglotic_desktop.core.listening.caption_model import (
    CaptionModel,
    caption_model,
)
from polyglotic_desktop.core.listening.captions import (
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.delays import CaptionDelay, delay
from polyglotic_desktop.core.listening.display import (
    CaptionRow,
    DisplayOptions,
    RowKind,
    caption_rows,
    with_link_classes,
)
from polyglotic_desktop.core.listening.history import Caption, CaptionHistory
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ports.word_breaks import WordBreaks
from polyglotic_desktop.ports.word_classes import ClassEvidenceFor
from polyglotic_desktop.ui_next.views.pour import matching_cuts
from polyglotic_desktop.ui_next.views.scroll import Scroll

DELAYS_KEPT = 512
"""Captions whose delay a view remembers (live ones never finished go too)."""

CAPTION_WINDOW_LINES = 150

"""Lines a caption window keeps to scroll back through (as today's overlay)."""

TRANSCRIPT_LINES = 1_000
"""Lines a transcript lists - laid out, searched and scrolled through; the
surfaces' budgets hold at this many."""

TRANSCRIPT_MOST_LINES = 10_000
"""The most lines a transcript lists when the learner keeps three hours or
the whole session in it (polyglotic-hq 334): about eight hours of a
lecture's constant speech, at 20 captions a minute. Each caption update
costs a transcript about 0.15 ms per 1,000 lines it lists (measured,
2026-11-14): 1.5 ms at this many, inside a new caption's budget; past it
the oldest lines are in Copy all and Save only (`SESSION_LINES`)."""

SESSION_LINES = 50_000
"""Lines a transcript keeps for Copy all and Save: the whole session (a
film, a long call) - about two days of constant speech - kept as text
beyond the `TRANSCRIPT_LINES` it lists (polyglotic-hq 137). The cap only
keeps an app left captioning for days from growing without end."""

TEXT_SIZES = (0.7, 2.0)
"""The smallest and largest text size, as a scale of the base size (as
today's setting): a transcript's."""
CAPTION_TEXT_SIZES = (0.6, 4.0)
"""A caption window's (the user, 2026-11-14: "maximal logical
customisation for caption and translation text sizes"; polyglotic-hq 305).
60 %: 12.6 px at the base 21 px - the 12 px the app's smallest text keeps
(the lookup card's floor), Windows' 9 pt. 400 %: the largest at which a
caption of two short lines (a 37-character English sentence and its
12 Chinese characters, label and all) still fits a full-width 1080p window
at its default height, 300 px - each line on one row (measured with real
fonts: 299 px tall at 400 %, one row each up to 530 %)."""


_NO_TRANSLATION = Language("")
"""A target no clause is translated into: core's rules then show each
clause's original alone (captions only)."""

_NO_ID = CaptionId("")
_YOU = SourceLabel("You", "#7c9cff")
"""The user's own mic's label unless named: blue, as "You" always was."""


NAMED_AGAIN_SEC = 60.0
"""With `Labels.language_once`: the language is named again on a caption
that starts this long after the one before."""


@dataclass(frozen=True, slots=True)
class Line:
    """A caption as a surface shows it. `key` stays the same through the
    caption's updates and joins (the caption history's), so a surface
    keeps what it laid out until `rows` change. `by_you`: from the user's
    own mic ("You"). `provisional`: Quick preview's line - drawn dim and
    italic until its finished caption. `label`: the small line above it
    (`Labels`), in `label_color` ("#rrggbb"); empty for none. `heard`: the
    languages spoken in it; `checked`: the best model's version, which the
    learner said is right ("Looks wrong?") - a transcript says both.
    `respoken`: the learner re-spoke it for its source (polyglotic-hq
    567): its label and heading say so."""

    key: int
    source: SourceId
    by_you: bool
    rows: tuple[CaptionRow, ...]
    live: bool
    provisional: bool
    started_at: datetime
    caption_id: CaptionId = _NO_ID
    respoken: bool = False
    label: str = ""
    label_color: str = ""
    heard: tuple[Language, ...] = ()
    checked: bool = False
    model: CaptionModel | None = None
    """The caption's model (polyglotic-hq 340, `CaptionLines.set_models`):
    what the one layout composes."""
    cuts: tuple[tuple[tuple[int, int], ...], ...] = ()
    """By clause: where its original and its translation can both be
    cut (`views.pour.matching_cuts`) - only when the surface pours
    line by line (`CaptionLines.set_cuts`); empty otherwise."""
    link_context: Caption | None = None
    """The caption with the same endpoint classes used for marks and lookup."""
    has_pace: bool = False
    """This caption has a pace reading in its heading."""


@dataclass(frozen=True)
class Labels:
    """What the small line above each caption says: its source's name, in
    its colour (`sources`; on this PC only) - always for the user's own
    ("You", `you`), for the others with `show_source` - and the language
    spoken, with `show_language` (`spoken` names it: "Mandarin",
    "Mandarin + English"); and, with `delay`, how long the caption took to
    show (`delay` says it: polyglotic-hq 271, off unless the learner asks).
    `language_once`: the language is named when it changes - on the first
    caption, when a caption's languages differ from the one before, and
    after `NAMED_AGAIN_SEC` of nothing - not over every caption
    (polyglotic-hq 526, DECISIONS #230 item 3). `respoken`: the word a
    re-spoken caption is marked with ("re-spoken", polyglotic-hq 567) - its
    source then named whatever `show_source` says, so whose it is shows."""

    sources: Mapping[SourceId, SourceLabel] = field(default_factory=dict)
    show_source: bool = False
    show_language: bool = False
    you: SourceLabel = _YOU
    spoken: Callable[[Sequence[Language]], str] | None = None
    delay: Callable[[CaptionDelay], str] | None = None
    language_once: bool = False
    source_once: bool = False
    """With `language_once`: the source too is named when it changes or
    after `NAMED_AGAIN_SEC`, not over every caption (Steady's cards, each a
    line: decision 0260)."""
    respoken: str = ""
    show_time: bool = False
    """Caption panels use a local time and announce a source only on change."""
    pace: Callable[[int], str] | None = None
    show_info: bool = True
    """When False, hides the entire header line above each caption."""
    own_source: SourceId | None = None
    """The window's own source: left out of caption headers (the title bar names it)."""

    def of(
        self,
        caption: Caption,
        took: CaptionDelay | None = None,
        before: Caption | None = None,
    ) -> tuple[str, str]:
        """The label's text and colour for `caption`; `took`: its delay, if
        known; `before`: the caption above it, if any."""
        if not self.show_info:
            return "", ""
        parts = []
        color = ""
        source = self.sources.get(caption.source_id)
        if source is None and caption.by_you:
            source = self.you
        again = True
        if before is not None:
            if self.show_time:
                again = before.source_id != caption.source_id
            elif self.language_once and self.source_once:
                gap = (caption.started_at - before.started_at).total_seconds()
                again = before.source_id != caption.source_id or gap > NAMED_AGAIN_SEC
        marked = caption.respoken and bool(self.respoken)
        own = (
            self.own_source is not None
            and caption.source_id == self.own_source
            and not caption.by_you
        )
        if source is not None and (self.show_source or caption.by_you or marked):
            if not own and (again or (marked and not self.show_time)):
                parts.append(source.name)
            if not own or marked:
                color = source.color
        if marked:
            parts.append(self.respoken)
        heard = caption.languages_heard or (
            (caption.language,) if caption.language else ()
        )
        named = self.show_language and heard and self.spoken is not None
        if named and self.language_once and not self.show_time and before is not None:
            was = before.languages_heard or (
                (before.language,) if before.language else ()
            )
            gap = (caption.started_at - before.started_at).total_seconds()
            named = heard != was or gap > NAMED_AGAIN_SEC
        if named and self.spoken is not None:
            parts.append(self.spoken(heard))
        pace = None if self.pace is None else caption.pace_wpm
        show_time = self.show_time or pace is not None
        if show_time:
            parts.append(caption.started_at.astimezone().strftime("%H:%M"))
        if self.pace is not None and pace is not None:
            parts.append(self.pace(pace))
        if self.delay is not None and took is not None:
            parts.append(self.delay(took))
        if show_time:
            return " · ".join(parts), "" if self.show_time else color
        return "  ".join(parts), color


@dataclass(frozen=True)
class LineDisplay:
    """The choices that determine the lines built from a caption history."""

    target: Language | None
    second: Language | None
    options: DisplayOptions
    labels: Labels
    cuts: bool
    models: bool


class CaptionLines:
    """Some sources' captions - an app's, and the user's own if shown - as
    lines in one translation language, or none."""

    def __init__(
        self,
        sources: Collection[SourceId],
        target: Language | None,
        *,
        keep: int,
        keep_earlier: int = 0,
        second: Language | None = None,
        options: DisplayOptions | None = None,
        yours: Collection[SourceId] = (),
        text_size: float = 1.0,
        labels: Labels | None = None,
        finished_only: bool = False,
        cuts: bool = False,
        clock: Callable[[], datetime] | None = None,
        sizes: tuple[float, float] = TEXT_SIZES,
    ) -> None:
        """`sources`: whose captions show. `target`: the one translation
        shown, None for captions only. `keep`: lines kept, oldest dropped
        first (`CAPTION_WINDOW_LINES`, `TRANSCRIPT_LINES`); `keep_earlier`:
        finished captions dropped from those kept as text in `earlier`
        (`SESSION_LINES`, a transcript's). `second`: the
        language shown for a clause already in `target`. `yours`: the
        sources that are the user's own mic. `finished_only`: no line for a
        caption still being spoken (a transcript's). `clock`: when captions
        arrive - by default now (the lab's made-up times are the same every
        run). `sizes`: the text size's range (a caption window's is
        CAPTION_TEXT_SIZES)."""
        self.sources = frozenset(sources)
        self.sizes = sizes
        self.keep = keep
        """Lines kept: no surface shows more of this view's than these."""
        self._finished_only = finished_only
        self._modelled: tuple[Language | None, Language | None] = (None, None)
        self.scroll = Scroll()
        self.revision = 0
        self._history = (
            CaptionHistory(yours, clock, max_captions=keep, keep_earlier=keep_earlier)
            if clock is not None
            else CaptionHistory(yours, max_captions=keep, keep_earlier=keep_earlier)
        )
        self._display = LineDisplay(
            target,
            second,
            options or DisplayOptions(),
            labels or Labels(),
            cuts,
            models=False,
        )
        self._text_size = _clamped(text_size, sizes)
        self._lines: tuple[Line, ...] = ()
        self._built: dict[int, tuple[Caption, Line, SourceId | None]] = {}
        """Caption, projected line and the source immediately above it."""
        self._delays: dict[CaptionId, CaptionDelay] = {}
        self.word_breaks: WordBreaks | None = None
        """How long each caption's latest update took to show - its own
        speech's only (`CaptionUpdate.times`); the newest `DELAYS_KEPT`."""
        self._history_version = self._history.version
        self.class_evidence: ClassEvidenceFor | None = None

    # -- what shows -----------------------------------------------------------------

    @property
    def lines(self) -> tuple[Line, ...]:
        """The lines, oldest first (in key order)."""
        return self._lines

    def caption(self, key: int) -> Caption | None:
        """The caption a line shows, by the line's key: its clauses in every
        language, for a lookup's context line."""
        found = self._built.get(key)
        return (found[1].link_context or found[0]) if found else None

    def refresh_link_classes(self) -> bool:
        """Refresh displayed endpoint evidence after a dictionary change."""
        return self.class_evidence is not None and self._rebuild(
            everything=False, reclassify=True
        )

    @property
    def target(self) -> Language | None:
        """The one translation shown; None: captions only."""
        return self._display.target

    @property
    def fallbacks(self) -> tuple[Language, ...]:
        """The translation target and the second language - in that order,
        those set: the dictionaries a lookup tries after its row's
        (polyglotic-hq 337)."""
        return tuple(
            x for x in (self._display.target, self._display.second) if x is not None
        )

    @property
    def text_size(self) -> float:
        return self._text_size

    @property
    def started_at(self) -> datetime:
        """When these lines began to be kept: the listening session's start,
        as far as they're concerned (an SRT's cues are timed from it)."""
        return self._history.started_at

    @property
    def earlier(self) -> Sequence[Caption]:
        """The finished captions kept from before the lines, oldest first
        (with `keep_earlier`): in Copy all and Save, not in the list."""
        return self._history.earlier

    def captions_of(self, lines: Sequence[Line]) -> list[Caption]:
        """The captions `lines` show, in their order (for copying and saving
        them: every language they hold)."""
        return [self._built[line.key][0] for line in lines if line.key in self._built]

    # -- from the session ----------------------------------------------------------

    def apply(
        self, update: CaptionUpdate, *, hold_live_translation: bool = False
    ) -> bool:
        """A caption update; True if what shows changed. Other sources'
        updates are ignored."""
        if update.source_id not in self.sources:
            return False
        took = delay(update, time.perf_counter())
        if took is not None:  # before the line is built: its label says it
            self._delays[update.caption_id] = took
            while len(self._delays) > DELAYS_KEPT:
                del self._delays[next(iter(self._delays))]
        self._history.apply(update, hold_live_translation=hold_live_translation)
        return self._history_changed()

    def use_checked(
        self,
        caption_id: CaptionId,
        clauses: tuple[Clause, ...],
        language: Language | None,
        languages_heard: tuple[Language, ...],
    ) -> bool:
        """The best model's version of a finished caption, which the
        learner said is right ("Looks wrong?"), in its place."""
        self._history.use_checked(caption_id, clauses, language, languages_heard)
        return self._history_changed()

    # -- the learner's choices -----------------------------------------------------

    @property
    def settle_after(self) -> float:
        """How long shown text may still change, in seconds."""
        return self._history.settle_after

    def set_settle_after(self, seconds: float) -> None:
        """How long shown text may still change (the caption history's;
        polyglotic-hq 309). Nothing shown changes for it."""
        self._history.set_settle_after(seconds)

    def set_display(self, display: LineDisplay) -> None:
        """Project the history once with all the window's current choices."""
        if display != self._display:
            self._display = display
            self._rebuild(everything=True)

    def set_language(
        self, target: Language | None, second: Language | None = None
    ) -> None:
        """The one translation shown (None: captions only), and the second
        language."""
        self.set_display(replace(self._display, target=target, second=second))

    def set_options(self, options: DisplayOptions) -> None:
        self.set_display(replace(self._display, options=options))

    def set_cuts(self, on: bool) -> None:
        """Whether each line says where its clauses and their translations
        can both be cut (`Line.cuts`): for a surface that pours them line
        by line (the Lab's, polyglotic-hq 309)."""
        self.set_display(replace(self._display, cuts=on))

    def set_models(self, on: bool) -> None:
        """Whether each line carries its caption's model, for a surface
        laid out by the one layout (polyglotic-hq 340)."""
        self.set_display(replace(self._display, models=on))

    def set_labels(self, labels: Labels) -> None:
        """What the line above each caption says."""
        self.set_display(replace(self._display, labels=labels))

    def set_limits(self, keep: int, keep_for: float | None = None) -> None:
        """Lines kept from now on: at most `keep`, and with `keep_for` only
        those whose caption first appeared in that many seconds - what's
        past them goes at once (into `earlier`, if it keeps any), and lines
        dropped before come back from it under a raised limit (a
        transcript's length, polyglotic-hq 334)."""
        self.keep = keep
        self._history.set_limits(keep, keep_for)
        self._history_changed()

    def show_sources(self, sources: Collection[SourceId]) -> None:
        """Whose captions show from now on (the user's own mic shown or
        not). Lines already kept stay."""
        self.sources = frozenset(sources)

    def set_text_size(self, size: float) -> None:
        """The text size, as a scale of the base size, kept in `sizes`.
        No line changes; the widget lays out what shows again."""
        size = _clamped(size, self.sizes)
        if size != self._text_size:
            self._text_size = size
            self.revision += 1

    # -- keeping the lines in step ---------------------------------------------------

    def _history_changed(self) -> bool:
        if self._history.version == self._history_version:
            return False
        return self._rebuild(everything=False)

    def _rebuild(self, everything: bool, *, reclassify: bool = False) -> bool:
        """The lines from the history's captions: a caption's line is
        reused while the caption is the same version (and, unless
        `everything`, the language and options are unchanged). False if no
        line changed (a live update, where only finished captions show)."""
        built: dict[int, tuple[Caption, Line, SourceId | None]] = {}
        lines = []
        above: Caption | None = None
        labels = self._display.labels
        for caption in self._history.captions:
            if self._finished_only and caption.live:
                continue
            found = None if everything else self._built.get(caption.key)
            above_source = above.source_id if above is not None else None
            line = (
                found[1]
                if found is not None and found[0] is caption and not reclassify
                else None
            )
            if (
                line is not None
                and found is not None
                and labels.show_time
                and labels.delay is None
                and found[2] == above_source
            ):
                built[caption.key] = found
                lines.append(line)
                above = caption
                continue
            if line is None or labels.language_once or labels.show_time:
                if (
                    found is not None
                    and labels.language_once
                    and labels.source_once
                    and not labels.show_time
                ):
                    # A card keeps its label when the line above leaves (552).
                    label = (found[1].label, found[1].label_color)
                else:
                    label = labels.of(
                        caption, self._delays.get(caption.caption_id), above
                    )
                if line is None:
                    line = self._line(caption, *label)
                elif (line.label, line.label_color) != label:
                    line = replace(line, label=label[0], label_color=label[1])
            if reclassify and found is not None and line == found[1]:
                line = found[1]
            above = caption
            built[caption.key] = (caption, line, above_source)
            lines.append(line)
        self._modelled = (self._display.target, self._display.second)
        self._history_version = self._history.version
        kept = tuple(lines)
        if not everything and _same(kept, self._lines):
            return False
        self._built = built
        self._lines = kept
        self.revision += 1
        return True

    def _line(self, caption: Caption, label: str, color: str) -> Line:
        display = self._display
        contextual = (
            with_link_classes(
                caption, display.target, display.second, self.class_evidence
            )
            if display.target is not None and self.class_evidence is not None
            else caption
        )
        if display.target is None:  # captions only: each clause's original
            options = replace(display.options, show_original=True)
            rows = caption_rows(caption, _NO_TRANSLATION, None, options)
        else:
            rows = caption_rows(
                contextual, display.target, display.second, display.options
            )
        model = None
        if display.models:
            before = self._built.get(caption.key)
            same_languages = self._modelled == (display.target, display.second)
            old = before[1].model if before is not None and same_languages else None
            if (
                before is not None
                and (before[1].link_context or before[0]) == contextual
                and old is not None
            ):
                model = old  # the same caption: a label or an option changed
            else:
                model = caption_model(
                    contextual,
                    display.target,
                    display.second,
                    old,
                    self.word_breaks,
                )
        return Line(
            key=caption.key,
            source=caption.source_id,
            by_you=caption.by_you,
            respoken=caption.respoken,
            rows=tuple(rows),
            live=caption.live,
            provisional=caption.live and display.options.preview,
            started_at=caption.started_at,
            caption_id=caption.caption_id,
            label=label,
            label_color=color,
            heard=caption.languages_heard
            or ((caption.language,) if caption.language else ()),
            checked=caption.checked,
            model=model,
            cuts=_cuts(caption, rows, model) if display.cuts else (),
            link_context=contextual if contextual is not caption else None,
            has_pace=(
                display.labels.show_info
                and display.labels.pace is not None
                and caption.pace_wpm is not None
            ),
        )


def _cuts(
    caption: Caption, rows: Sequence[CaptionRow], model: CaptionModel | None = None
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """By clause, where a settled clause shown with its translation can be
    cut in both (`matching_cuts`, from its word links - whether or not
    they're drawn)."""
    originals = {row.clause for row in rows if row.kind is RowKind.ORIGINAL}
    found: list[tuple[tuple[int, int], ...]] = [()] * len(caption.clauses)
    last = len(caption.clauses) - 1
    for row in rows:
        n = row.clause
        if (
            row.kind is not RowKind.TRANSLATION
            or n not in originals
            or row.language is None
            or (caption.live and n == last)
        ):
            continue
        if (
            model is not None
            and row.language == row.target
            and row.text == model.clauses[n].translation
        ):
            # The one layout already matched these same texts and word links.
            found[n] = model.clauses[n].cuts
            continue
        clause = caption.clauses[n]
        links = [
            (link.original, link.translation)
            for link in clause.links.get(row.language, ())
        ]
        found[n] = matching_cuts(clause.original, row.text, links)
    return tuple(found)


def _same(a: tuple[Line, ...], b: tuple[Line, ...]) -> bool:
    """The same lines, each the very same object (none rebuilt)."""
    return len(a) == len(b) and all(x is y for x, y in zip(a, b, strict=True))


def _clamped(size: float, sizes: tuple[float, float]) -> float:
    low, high = sizes
    return round(min(high, max(low, size)), 2)
