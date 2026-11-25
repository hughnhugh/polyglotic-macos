"""A listening session's summary: how it went, without anything that was said.

ENGINEERING.md, "Measuring the experience": per-caption detail stays in
the app and is summarised once per listening session. `SessionSummary`
watches the session - finished speech sent, caption updates back, errors,
reconnects - and `ended` gives polyglotic-server's tracking plan event
`listening_session_ended` (v1) as plain values:
- `speech_minutes`: finished speech, each caption once (a joined caption
  by its latest speech); withdrawn captions don't count;
- `captions`: finished captions kept (not withdrawn, not taken in by a
  join);
- `source_category`: the category most of that speech came from - None
  when nothing was captioned (the tracking plan's `none`);
- `known_app`: of the sources that are apps on the known-apps list, the
  one most of that speech came from, as the tracking plan names it
  (`discord`) - None when none of them is (an app not on the list is
  never named; polyglotic-hq DECISIONS.md #30);
- `caption_mode`: the learner's caption mode as the session started -
  `steady`, `preview` (Quick preview) or `live` (polyglotic-hq project
  064; `preview` is in the tracking plan from polyglotic-server #116);
- `delay_p50_ms`, `delay_p95_ms` - **caption delay as seen**: from the end
  of speech, detected on the PC, to its finished caption arriving (the
  0.8s pause, the network and the server included; drawing it adds a few
  milliseconds on the interface's thread); None when nothing was
  captioned;
- `rewrite_ratio` - words shown in live updates that didn't survive into
  the finished caption, divided by the finished captions' words;
  `erasure_ratio` the same for the first target language's translation.
  Chinese and Japanese count by character, other languages by word;
- `dropped`: finished speech with no finished caption back within 10s,
  or an error;
- `reconnects`; `live_interval_seconds`: the live-update interval the
  mode followed (None for Steady);
- **what the app recovered from by itself** (polyglotic-hq 566, from 557;
  decision 0266), so a tester's "it hangs" can be told apart from a
  failure without their log: `session_failures`, the times the session
  failed inside the app and tried again (`session_failed`; the server
  closing it is a reconnect); `capture_restarts`, the times a capture
  failed and started again, or tried to; `unreadable_dropped`, waiting
  rows this version couldn't read, dropped since the last summary - the
  last two counted by the capture and the outbox and handed to `ended`;
- `lookups`, `saves`: lookups shown and words saved during the session -
  counts only, the only usage statistics about them (polyglotic-hq
  DECISIONS.md #20: no event per lookup or save);
- **per app vs whole system** (polyglotic-hq project 134; DECISIONS.md
  #58): what was captured over the session (`captured`, a `Capture` - the
  mode, how many apps on their own, the learner's own speech) - how long
  in each mode (`apps_seconds`, `apps_plus_rest_seconds` - an app and
  everything else the PC plays, DECISIONS.md #59 - and
  `whole_system_seconds`), the mode most of
  the time was in (`capture_mode`; `none` if nothing was chosen all
  along), changes between modes (`mode_switches`), how long at each
  number of apps (`apps_0_seconds` to `apps_3_seconds`; everything the PC
  plays and nothing chosen are 0 apps), the most at once (`apps_max`) and
  how long "Show my speech here" was on (`my_speech_seconds`) - left out
  when the summary was never told what was captured; and what the
  learner did (`SessionAction`): transcripts opened, lines flagged
  ("Looks wrong?"), whether a source was shown in the original only, and
  whether the joined window was on. Numbers and yes/no only - never an
  app's name;
- **songs mode** (polyglotic-hq 595, decision 0287): how long a music
  player was heard in songs mode (`lyrics_seconds`, `songs`) and how often
  the learner turned the Lyrics switch on or off (`lyrics_switches`,
  `SessionAction.LYRICS_SWITCHED`) - both left out of a session that had
  neither, so a server without them in its plan drops only the sessions
  that used it.

A session with no finished caption is summarised too (the tracking plan,
since S2b): its dropped captions and reconnects are what it has to say.

The text of live updates is held only until its caption finishes, in
memory, as word counts; nothing of it is in the summary. Times are on the
app's monotonic clock (the speech times'), passed in by the caller: no
clock is read here. One thread at a time (the session's).
"""

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.pace import (
    PaceMeter,
    PaceReading,
    WordCount,
    caption_pace,
    spaced_word_count,
)
from polyglotic_desktop.core.listening.sources import Capture, CaptureMode
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    CaptionMode,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.ports.capture import SourceCategory

log = logging.getLogger(__name__)

DROPPED_AFTER_SEC = 10.0
"""Finished speech with no finished caption back after this is dropped
(the tracking plan's `dropped_captions`)."""

_CHARACTER = "぀-ヿ㐀-䶿一-鿿豈-﫿"
_WORDS = re.compile(rf"[{_CHARACTER}]|[^\W{_CHARACTER}]+")


def words(text: str) -> Counter[str]:
    """The words of a line, as rewrite rates count them: each Chinese or
    Japanese character, or each run of letters and digits elsewhere."""
    return Counter(w.lower() for w in _WORDS.findall(text))


@dataclass(frozen=True)
class ListeningSessionEnded:
    """The tracking plan's `listening_session_ended`, version 1."""

    speech_minutes: float
    captions: int
    source_category: SourceCategory | None
    """None: nothing was captioned (`none`)."""
    caption_mode: str
    delay_p50_ms: int | None
    delay_p95_ms: int | None
    rewrite_ratio: float
    erasure_ratio: float
    dropped: int
    reconnects: int
    live_interval_seconds: float | None
    capture_restarts: int = 0
    session_failures: int = 0
    unreadable_dropped: int = 0
    lookups: int = 0
    saves: int = 0
    known_app: str | None = None
    """A known app's id in the tracking plan; None: none was captioned."""
    transcripts_opened: int = 0
    lines_flagged: int = 0
    original_only: bool = False
    joined_window: bool = False
    capture_mode: str | None = None
    """Per app vs whole system (project 134); None, and the rest below too,
    when the summary was never told what was captured."""
    apps_seconds: float | None = None
    whole_system_seconds: float | None = None
    apps_plus_rest_seconds: float | None = None
    mode_switches: int | None = None
    apps_max: int | None = None
    apps_0_seconds: float | None = None
    apps_1_seconds: float | None = None
    apps_2_seconds: float | None = None
    apps_3_seconds: float | None = None
    my_speech_seconds: float | None = None
    preset_saves: int | None = None
    """Preset steps (587), each how many there were and how many changed
    settings they carried in all - None, and so not sent, in a session with
    none: a server from before 587 drops a summary with them."""
    preset_saves_as: int | None = None
    preset_discards: int | None = None
    preset_changes_saved: int | None = None
    preset_changes_saved_as: int | None = None
    preset_changes_discarded: int | None = None
    lyrics_seconds: float | None = None
    """How long a music player was heard in songs mode (595); None, and
    `lyrics_switches` too, for a session that neither had it on nor
    switched it."""
    lyrics_switches: int | None = None
    pace_them_mean: int = 0
    pace_them_peak: int = 0
    pace_you_mean: int = 0
    pace_you_peak: int = 0
    pace_them_seconds_1_60: int = 0
    pace_them_seconds_61_120: int = 0
    pace_them_seconds_121_180: int = 0
    pace_them_seconds_181_240: int = 0
    pace_them_seconds_241_plus: int = 0
    pace_you_seconds_1_60: int = 0
    pace_you_seconds_61_120: int = 0
    pace_you_seconds_121_180: int = 0
    pace_you_seconds_181_240: int = 0
    pace_you_seconds_241_plus: int = 0


class SessionAction(StrEnum):
    """What the learner did during a session that its summary counts."""

    TRANSCRIPT_OPENED = "transcript_opened"
    LINE_FLAGGED = "line_flagged"
    """"Looks wrong?" asked about a line."""
    ORIGINAL_ONLY = "original_only"
    """A source was shown in the original only (no translation)."""
    JOINED_WINDOW = "joined_window"
    """The joined window was on."""
    LYRICS_SWITCHED = "lyrics_switched"
    """The Lyrics switch turned on or off (595)."""


class PresetStep(StrEnum):
    """A step on the chosen preset the summary counts, with how many of its
    settings it carried (polyglotic-hq 587): never which, nor a name."""

    SAVED = "saved"
    """Save to the preset in use."""
    SAVED_AS = "saved_as"
    """Save as new preset…"""
    DISCARDED = "discarded"
    """Discard changes."""


APP_COUNTS = 4
"""`apps_0_seconds` to `apps_3_seconds`: the plan's app counts (3 at most)."""


@dataclass
class _Sent:
    speech_start: float
    speech_end: float
    category: SourceCategory
    sent_at: float
    known_app: str | None = None
    voiced_seconds: float | None = None
    source_id: str = ""


@dataclass
class _Finished:
    seconds: float
    category: SourceCategory
    words: int
    translated_words: int
    known_app: str | None
    pace_seconds: float
    pace_words: int
    pace_wpm: int | None


@dataclass
class _Live:
    """What live updates of a caption showed, as word counts."""

    originals: list[Counter[str]] = field(default_factory=list)
    translations: list[Counter[str]] = field(default_factory=list)


def _percentile(values: list[float], share: float) -> int:
    """The nearest-rank percentile, in whole milliseconds."""
    ranked = sorted(values)
    index = max(0, min(len(ranked) - 1, math.ceil(share * len(ranked)) - 1))
    return round(ranked[index] * 1000)


def _not_kept(shown: list[Counter[str]], finished: Counter[str]) -> int:
    return sum((update - finished).total() for update in shown)


class SessionSummary:
    def __init__(
        self,
        live_interval: float | None,
        target: Language | None = None,
        mode: CaptionMode | None = None,
        capture: Capture | None = None,
        started: float | None = None,
        *,
        count_words: WordCount = spaced_word_count,
    ) -> None:
        """`live_interval`: the live-update interval followed (None: none).
        `target`: the first target language, whose translation's rewrites
        are counted. `mode`: the caption mode; if not given, Live updates,
        or Steady when there are none. `capture`: what is captured as the
        session starts, at `started` (None: not known yet - `captured`
        tells it)."""
        self._count_words = count_words
        self._live_interval = live_interval
        if mode is None:
            mode = CaptionMode.WHOLE if live_interval is None else CaptionMode.INSTANT
        self._mode = mode
        self._target = target
        self._sent: dict[CaptionId, _Sent] = {}
        self._finished: dict[CaptionId, _Finished] = {}
        self._live: dict[CaptionId, _Live] = {}
        self._delays: list[float] = []
        self._rewritten = 0
        self._erased = 0
        self._dropped = 0
        self._reconnects = 0
        self._session_failures = 0
        self._lookups = 0
        self._saves = 0
        self._did: Counter[SessionAction] = Counter()
        self._preset_steps: Counter[PresetStep] = Counter()
        self._preset_changes: Counter[PresetStep] = Counter()
        self._capture = capture
        self._since = started
        self._mode_time: dict[CaptureMode, float] = {}
        self._apps_time = [0.0] * APP_COUNTS
        self._my_speech = 0.0
        self._songs_since: float | None = None
        """When songs mode came on, while it's on (`songs`)."""
        self._songs_seconds: float | None = None
        """How long songs mode was on before; None: never on."""
        self._switches = 0
        self._apps_max = capture.apps if capture is not None else 0
        self._pace_them = PaceMeter()
        self._pace_you = PaceMeter()
        self._pace_them_by_source: dict[str, PaceMeter] = {}
        self._pace_you_by_source: dict[str, PaceMeter] = {}
        self._paced: dict[CaptionId, int] = {}
        self._pace_logged_at = started
        self._drawn_original = 0
        self._drawn_translation = 0

    def captured(self, capture: Capture, at: float) -> None:
        """What is captured changed at `at` (or is first known). A change
        between modes - apps, an app and everything else, everything the PC
        plays - is a mode switch; choosing for the first time isn't."""
        self._count_time(at)
        before = self._capture
        if (
            before is not None
            and capture.mode != before.mode
            and CaptureMode.NONE not in (capture.mode, before.mode)
        ):
            self._switches += 1
        self._capture = capture
        self._apps_max = max(self._apps_max, capture.apps)

    def did(self, action: SessionAction) -> None:
        """The learner did something the summary counts."""
        self._did[action] += 1

    def preset_step(self, step: PresetStep, changes: int) -> None:
        """A step on the chosen preset that carried `changes` settings (587)."""
        self._preset_steps[step] += 1
        self._preset_changes[step] += max(0, changes)

    def songs(self, on: bool, at: float) -> None:
        """Whether a music player is heard in songs mode, from `at` (595)."""
        if on and self._songs_since is None:
            self._songs_since = at
        elif not on and self._songs_since is not None:
            self._songs_seconds = (self._songs_seconds or 0.0) + max(
                0.0, at - self._songs_since
            )
            self._songs_since = None

    def _count_time(self, at: float) -> None:
        """Adds the time since the last change to what was captured then."""
        capture, since = self._capture, self._since
        self._since = at
        if capture is None or since is None:
            return
        seconds = max(0.0, at - since)
        mode = capture.mode
        self._mode_time[mode] = self._mode_time.get(mode, 0.0) + seconds
        self._apps_time[min(capture.apps, APP_COUNTS - 1)] += seconds
        if capture.my_speech:
            self._my_speech += seconds

    def _with_learner(
        self, summary: ListeningSessionEnded, at: float
    ) -> ListeningSessionEnded:
        """`summary` with per app vs whole system, and what the learner did."""
        self._count_time(at)
        did = self._did
        summary = replace(
            summary,
            transcripts_opened=did[SessionAction.TRANSCRIPT_OPENED],
            lines_flagged=did[SessionAction.LINE_FLAGGED],
            original_only=did[SessionAction.ORIGINAL_ONLY] > 0,
            joined_window=did[SessionAction.JOINED_WINDOW] > 0,
        )
        steps, changes = self._preset_steps, self._preset_changes
        if steps:
            summary = replace(
                summary,
                preset_saves=steps[PresetStep.SAVED],
                preset_saves_as=steps[PresetStep.SAVED_AS],
                preset_discards=steps[PresetStep.DISCARDED],
                preset_changes_saved=changes[PresetStep.SAVED],
                preset_changes_saved_as=changes[PresetStep.SAVED_AS],
                preset_changes_discarded=changes[PresetStep.DISCARDED],
            )
        if self._songs_since is not None:
            self.songs(False, at)
        switched = did[SessionAction.LYRICS_SWITCHED]
        if self._songs_seconds is not None or switched:
            summary = replace(
                summary,
                lyrics_seconds=round(self._songs_seconds or 0.0, 1),
                lyrics_switches=switched,
            )
        if self._capture is None:
            return summary
        chosen: dict[CaptureMode, float] = {
            m: t for m, t in self._mode_time.items() if m is not CaptureMode.NONE
        }
        main = max(chosen, key=lambda m: chosen[m]) if chosen else CaptureMode.NONE
        apps = [round(t, 1) for t in self._apps_time]
        return replace(
            summary,
            capture_mode=main.value,
            apps_seconds=round(self._mode_time.get(CaptureMode.APPS, 0.0), 1),
            whole_system_seconds=round(
                self._mode_time.get(CaptureMode.WHOLE_SYSTEM, 0.0), 1
            ),
            apps_plus_rest_seconds=round(
                self._mode_time.get(CaptureMode.APPS_PLUS_REST, 0.0), 1
            ),
            mode_switches=self._switches,
            apps_max=min(self._apps_max, APP_COUNTS - 1),
            apps_0_seconds=apps[0],
            apps_1_seconds=apps[1],
            apps_2_seconds=apps[2],
            apps_3_seconds=apps[3],
            my_speech_seconds=round(self._my_speech, 1),
        )

    def speech_sent(self, request: TranscriptionRequest, at: float) -> None:
        """Speech went to the server at `at`; only finished speech counts."""
        if request.kind is not SpeechKind.FINISHED:
            return
        source = request.source
        self._sent[request.caption_id] = _Sent(
            request.speech_start,
            request.speech_end,
            source.category,
            at,
            source.known_app,
            request.voiced_seconds,
            str(source.id),
        )
        for replaced in request.replaces:
            self._sent.pop(replaced, None)

    def caption_updated(self, update: CaptionUpdate, at: float) -> int | None:
        """Record an update that arrived at `at` and return its caption pace."""
        if update.kind is CaptionKind.LIVE:
            live = self._live.setdefault(update.caption_id, _Live())
            live.originals.append(self._original(update))
            live.translations.append(self._translation(update))
            return None
        sent = self._sent.pop(update.caption_id, None)
        taken_in = [update.caption_id, *update.replaces]
        for caption_id in update.replaces:
            self._sent.pop(caption_id, None)
            self._finished.pop(caption_id, None)
        if update.kind is CaptionKind.WITHDRAWN:
            self._finished.pop(update.caption_id, None)
            for caption_id in taken_in:
                if caption_id in self._live:
                    del self._live[caption_id]
            return None
        previous = self._finished.get(update.caption_id)
        original, translation = self._original(update), self._translation(update)
        for caption_id in taken_in:
            shown = self._live.pop(caption_id, None)
            if shown is not None:
                self._rewritten += _not_kept(shown.originals, original)
                self._erased += _not_kept(shown.translations, translation)
        if sent is None:
            return previous.pace_wpm if previous is not None else None
        self._drawn_original += original.total()
        self._drawn_translation += translation.total()
        replaced = sum(self._paced.pop(caption_id, 0) for caption_id in update.replaces)
        # Count dictionary words in the finished original, never server tokens.
        word_count = sum(
            self._count_words(clause.original, update.language)
            for clause in update.clauses
        )
        span = max(0.0, sent.speech_end - sent.speech_start)
        spoken_seconds = (
            span
            if span > 0.0
            else max(0.0, sent.voiced_seconds)
            if sent.voiced_seconds is not None
            else 0.0
        )
        continuation = (
            self._finished.get(update.continues) if update.continues else None
        )
        learner = sent.category is SourceCategory.MIC or update.respoken
        pace = self._pace_you if learner else self._pace_them
        by_source = self._pace_you_by_source if learner else self._pace_them_by_source
        source_pace = by_source.get(sent.source_id)
        if source_pace is None:
            source_pace = by_source[sent.source_id] = PaceMeter()
        if update.caption_id not in self._paced:
            count = max(0, word_count - replaced)
            # A continuation repeats the anchor's words over the new request's audio.
            extra_words = (
                max(0, count - continuation.pace_words) if continuation else None
            )
            pace.add(count, spoken_seconds, sent.speech_end, new_words=extra_words)
            source_pace.add(
                count, spoken_seconds, sent.speech_end, new_words=extra_words
            )
            self._paced[update.caption_id] = word_count
        elif previous is not None and spoken_seconds > previous.pace_seconds:
            # A join can finish the same caption again with more speech.
            count = max(0, word_count - previous.pace_words)
            extra = spoken_seconds - previous.pace_seconds
            pace.extend(count, extra, sent.speech_end)
            source_pace.extend(count, extra, sent.speech_end)
            self._paced[update.caption_id] = word_count
        caption_seconds = spoken_seconds
        if update.continues is not None:
            # These clauses include the earlier audio, but the request does not.
            caption_seconds = (
                spoken_seconds + continuation.pace_seconds if continuation else 0.0
            )
        wpm = caption_pace(word_count, caption_seconds)
        if self._pace_logged_at is None:
            self._pace_logged_at = at
        elif at - self._pace_logged_at >= 60.0:
            them_now, them_mean, you_now, you_mean = self.pace(at)
            log.info(
                "pace: them %d now %d avg, you %d now %d avg, "
                "drawn original %d, drawn translation %d, peaks %d/%d",
                them_now,
                them_mean,
                you_now,
                you_mean,
                self._drawn_original,
                self._drawn_translation,
                self._pace_them.peak,
                self._pace_you.peak,
            )
            self._pace_logged_at = at
        delay = at - sent.speech_end
        self._delays.append(delay)
        if at - sent.sent_at > DROPPED_AFTER_SEC:
            self._dropped += 1
        self._finished[update.caption_id] = _Finished(
            span,
            sent.category,
            original.total(),
            translation.total(),
            sent.known_app,
            spoken_seconds,
            word_count,
            wpm,
        )
        return wpm

    def failed(self, caption_id: CaptionId) -> None:
        """The server answered a caption's speech with an error."""
        if self._sent.pop(caption_id, None) is not None:
            self._dropped += 1

    def reconnected(self) -> None:
        self._reconnects += 1

    def session_failed(self) -> None:
        """The session failed inside the app and is trying again (decision
        0266) - not the server closing it, which is a reconnect."""
        self._session_failures += 1

    def looked_up(self) -> None:
        """A lookup was shown during the session (hover or pinned)."""
        self._lookups += 1

    def saved(self) -> None:
        """A word was saved during the session."""
        self._saves += 1

    def ended(
        self, at: float, *, capture_restarts: int = 0, unreadable_dropped: int = 0
    ) -> ListeningSessionEnded:
        """The summary, as the session ends at `at` - with no source
        category or delays if nothing was captioned. `capture_restarts` and
        `unreadable_dropped`: counted by the captures and the outbox over
        the session."""
        them = self._pace_them.seconds
        you = self._pace_you.seconds
        return replace(
            self._ended(at),
            capture_restarts=capture_restarts,
            session_failures=self._session_failures,
            unreadable_dropped=unreadable_dropped,
            pace_them_mean=self._pace_them.mean,
            pace_them_peak=self._pace_them.peak,
            pace_you_mean=self._pace_you.mean,
            pace_you_peak=self._pace_you.peak,
            pace_them_seconds_1_60=them["1_60"],
            pace_them_seconds_61_120=them["61_120"],
            pace_them_seconds_121_180=them["121_180"],
            pace_them_seconds_181_240=them["181_240"],
            pace_them_seconds_241_plus=them["241_plus"],
            pace_you_seconds_1_60=you["1_60"],
            pace_you_seconds_61_120=you["61_120"],
            pace_you_seconds_121_180=you["121_180"],
            pace_you_seconds_181_240=you["181_240"],
            pace_you_seconds_241_plus=you["241_plus"],
        )

    def pace(self, at: float) -> tuple[int, int, int, int]:
        """Them/you current and average pace for the listening interface."""
        return (
            self._pace_them.now(at),
            self._pace_them.mean,
            self._pace_you.now(at),
            self._pace_you.mean,
        )

    def pace_by_source(
        self, at: float
    ) -> tuple[dict[str, PaceReading], dict[str, PaceReading]]:
        """Current/average pace for each source, split into them and you.

        Session-wide meters remain the source of telemetry; these meters are
        only the independently routed caption-window readouts.
        """
        return (
            {
                source_id: meter.reading(at)
                for source_id, meter in self._pace_them_by_source.items()
            },
            {
                source_id: meter.reading(at)
                for source_id, meter in self._pace_you_by_source.items()
            },
        )

    def _ended(self, at: float) -> ListeningSessionEnded:
        self._dropped += sum(
            1 for sent in self._sent.values() if at - sent.sent_at > DROPPED_AFTER_SEC
        )
        self._sent.clear()
        if not self._finished:
            nothing = ListeningSessionEnded(
                speech_minutes=0.0,
                captions=0,
                source_category=None,
                caption_mode=self._mode.usage_value,
                delay_p50_ms=None,
                delay_p95_ms=None,
                rewrite_ratio=0.0,
                erasure_ratio=0.0,
                dropped=self._dropped,
                reconnects=self._reconnects,
                live_interval_seconds=self._live_interval,
                lookups=self._lookups,
                saves=self._saves,
            )
            return self._with_learner(nothing, at)
        seconds: dict[SourceCategory, float] = {}
        for caption in self._finished.values():
            seconds[caption.category] = (
                seconds.get(caption.category, 0.0) + caption.seconds
            )
        known: dict[str, float] = {}
        for caption in self._finished.values():
            if caption.known_app is not None:
                known[caption.known_app] = (
                    known.get(caption.known_app, 0.0) + caption.seconds
                )
        words_ = sum(c.words for c in self._finished.values())
        translated = sum(c.translated_words for c in self._finished.values())
        summary = ListeningSessionEnded(
            speech_minutes=round(sum(seconds.values()) / 60, 2),
            captions=len(self._finished),
            source_category=max(seconds, key=lambda c: seconds[c]),
            caption_mode=self._mode.usage_value,
            delay_p50_ms=_percentile(self._delays, 0.5),
            delay_p95_ms=_percentile(self._delays, 0.95),
            rewrite_ratio=round(self._rewritten / words_, 3) if words_ else 0.0,
            erasure_ratio=round(self._erased / translated, 3) if translated else 0.0,
            dropped=self._dropped,
            reconnects=self._reconnects,
            live_interval_seconds=self._live_interval,
            lookups=self._lookups,
            saves=self._saves,
            known_app=max(known, key=lambda a: known[a]) if known else None,
        )
        return self._with_learner(summary, at)

    def _original(self, update: CaptionUpdate) -> Counter[str]:
        return words(" ".join(c.original for c in update.clauses))

    def _translation(self, update: CaptionUpdate) -> Counter[str]:
        if self._target is None:
            return Counter()
        return words(
            " ".join(c.translations.get(self._target, "") for c in update.clauses)
        )
