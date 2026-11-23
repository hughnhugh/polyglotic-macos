"""The live-update timing rules, as a pure state machine (protocol version 1).

Fed each source's speech-detection results frame by frame, `CaptionTiming`
decides when to send which stretch of which source's audio: a live update
of a caption while the speech goes on, a finished caption at the pause, a
long-speech split after 20s of nonstop speech, and a joined caption when
the same source speaks again within 2s. It holds no audio and does no I/O:
it says "transcribe this source from `speech_start` to `speech_end`", and
whoever holds the audio cuts it (with `SLICE_PAD_SEC` either side, but
not at a cut: below).

Speech detection marks the start of speech late when the first sound is
soft, so a caption that starts after silence starts `ONSET_LEAD_IN_SEC`
before its first speech frame - never reaching into audio already sent
for the source's caption before (`TimingRules.lead_in`, project 038).

The rules and constants come from the proof of concept
(`overlay_core._capture_loop_inner`, `_plan_final`, `_commit_run` on its
`master-polyglotic` branch) and keep its names. Moving them to the server
in protocol version 2 is a move, not a rewrite (polyglotic-server decision
0003).

`TimingRules` (polyglotic-hq project 033) adds the options the proof of
concept didn't have, all off by default so the defaults are the proof of
concept's: the live-update schedule (every N seconds, growing, one
glimpse), a shorter silence hangover, breath cuts (finishing a long
stretch at the next short pause), and turn cuts (finishing a caption
sooner when another source starts speaking).

The app doesn't use those defaults: it follows the learner's
`CaptionMode` - Instant (the default, project 626), Whole captions,
Steady or Calm - each a
set of these rules that projects 021, 037 and 046 measured, and each
joining only onto fragments - and the learner's longest wait for text
(`max_wait`, 3s unless they choose 2-6s; polyglotic-hq 277): in every
mode, speech never runs longer than that without a live update asked
for.

A caption finished while the speech goes on - a breath cut's limit, a
long-speech split - is cut at the quietest moment of the last
`CUT_LOOKBACK_SEC`, by each frame's loudness, not at the frame the limit
fell on, and the requests say so (`cut_after`, `cut_before`): no margin at
the cut, so the two captions' audio meets without overlapping, and the
server leaves the first caption's text open at its end (desktop decision
0083, polyglotic-hq 291: a tester's fast video was cut every 6.02s
mid-word, each piece ending in a full stop and half of them repeating the
last one's last words).

Not thread-safe: one caller at a time (capture threads take a lock).
"""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import NewType

from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.ports.mic_bleed import MicBleedCheck

CaptionId = NewType("CaptionId", str)
"""A caption's identity across its updates (made by the app; protocol.md)."""

# Speech detection gives one result per frame: 512 samples at 16kHz (32ms).
VAD_SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
FRAME_SEC = FRAME_SAMPLES / VAD_SAMPLE_RATE
# The audio sent for a stretch of speech runs from this long before
# `speech_start` to this long after `speech_end` (protocol.md, "Speech
# audio": the server doesn't count it as minutes).
SLICE_PAD_SEC = 0.2
# Speech detection (Silero) marks speech late on a soft first sound: a
# caption that starts after silence is taken to start this much before its
# first speech frame - with SLICE_PAD_SEC, 0.5s of audio before it. Project
# 038 (FLEURS, the desktop's own detection and timing, a CPU speech model):
# the first word of a clip's first caption came back in 68 of 75 English
# clips with 0.5s before it, against 60 with 0.2s; 0.8s gave 70.
ONSET_LEAD_IN_SEC = 0.3
# A speech segment ends after this much silence ...
SILENCE_HANGOVER_SEC = 0.8
# ... and one with less speech than this (and no live update yet) is ignored.
MIN_SPEECH_SEC = 0.4
# The first live update waits for this much audio: a shorter clip is too
# little for the speech model to place the language.
LIVE_MIN_AUDIO_SEC = 1.0
# Seconds between live updates, by default (the user can choose 0.5 to 20,
# or off). 1.0 since polyglotic-hq 494 (DECISIONS.md #211, the user,
# 2026-11-18: "two agree" every 1.0 s): the server says what two live updates
# in a row agree on is established (its decision 0095), and 1.0 s apart
# establishes about half the words 2.6 s before the finished caption - 37 %
# at the old 1.5 s (polyglotic-hq 487, live's speech model). About 3.2 times
# Steady's audio on the speech model, against 2.4 times at 1.5 s.
LIVE_UPDATE_INTERVAL_SEC = 1.0
# A live caption grows in sections: once the current one passes this long,
# its text is kept as it stands and live updates carry on in a new section
# from there, so each live update is at most ~1s of the model's work. (The
# finished caption still redoes the whole stretch.)
LIVE_SECTION_SEC = 6.0
# The `growing` schedule: live updates this far into each live section
# (the user's idea, 2026-11-04: 1.5s, 3s, 6s rather than every 1.5s).
GROWING_OFFSETS_SEC = (1.5, 3.0, 6.0)
# Speech running longer than this without a pause is finished as its own
# caption and continues in a new one (a long-speech split).
FINAL_MAX_SEC = 20.0
# The same source speaking again within this long, with nothing else
# captioned in between and FINAL_MAX_SEC at most in all, is transcribed
# again as one caption that replaces the earlier one (a joined caption).
JOIN_GAP_SEC = 2.0
# Joins repair fragments only: speech is joined onto the caption before it
# only if that one ran less than this - a sentence cut short by a pause,
# not a whole sentence (project 033; project 021 measured whole-run joins
# as the biggest waste: each re-heard the whole run, up to 20s).
FRAGMENT_SEC = 2.0
# Steady and Quick preview: a caption finishes after this much silence
# (project 033's Y; the proof of concept's 0.8s stays for Live updates).
STEADY_HANGOVER_SEC = 0.6
# Quick preview: its first provisional live update is taken this far into a
# caption (project 033's Z); then the growing schedule's, at GROWING_OFFSETS_SEC
# into each live section (polyglotic-hq 260).
PREVIEW_AFTER_SEC = 1.5
# The longest wait for text: in every caption mode, speech never runs longer
# than this without text asked for - a live update when nothing else is due
# (polyglotic-hq 277; the user, 2026-11-11: "max 3s or something before
# displaying current text"). The learner chooses it, within MAX_WAIT_RANGE.
MAX_WAIT_FOR_TEXT_SEC = 3.0
MAX_WAIT_RANGE = (2.0, 6.0)
# A caption finished while the speech goes on (a breath cut's limit, a
# long-speech split) is cut at the quietest moment of this many seconds
# before the limit - between words, not where the limit fell (decision
# 0083). polyglotic-hq 291, a tester's fast video: speech detection said
# speech all through, but the quietest 32ms of the 1.5s before each 6s
# limit was near silence in all 13 cuts; at the limit itself it was
# mid-word.
CUT_LOOKBACK_SEC = 1.5
# The quietest moment is the quietest run of this many frames (~100ms):
# longer than the closure of a "p" or "t" inside a word.
_QUIET_RUN_FRAMES = 3
# The server's speech ceiling: seconds of audio a minute per account, live
# updates and finished speech together (protocol.md, Limits; `welcome`'s
# `limits.speech_seconds_per_minute`). Over it the server refuses live
# updates - all of them, until enough of the minute has aged out: with
# three apps talking at 0.75s, every live update for about 20s of each
# minute (polyglotic-hq 307). So the app keeps to it itself, evenly
# (decision 0097): live updates wait their turn for a share of it.
SPEECH_SECONDS_PER_MINUTE = 600.0
# The app's own share of the ceiling: under it by more than the difference
# between its count and the server's (which counts a frame by its bytes
# too).
LIVE_BUDGET_SHARE = 0.9
# How much of the ceiling the app can send at once before live updates are
# spread: three apps' live updates at 0.75s for about 8s.
LIVE_BURST_SHARE = 0.1

_MIN_SPEECH_FRAMES = int(MIN_SPEECH_SEC / FRAME_SEC)  # 12 frames


def _frames(seconds: float) -> int:
    """How many whole frames make up `seconds` (0.8s -> 25 frames)."""
    return max(1, int(seconds / FRAME_SEC + 1e-9))


class SpeechKind(StrEnum):
    LIVE = "live"
    FINISHED = "finished"


class LiveSchedule(StrEnum):
    """When live updates are sent while someone talks (finished captions
    only: a `live_update_interval` of None, whatever the schedule)."""

    EVERY = "every"
    """Every `live_update_interval` seconds (the proof of concept's rule)."""
    GROWING = "growing"
    """At GROWING_OFFSETS_SEC into each live section: fewer updates, the
    text rewritten less often, the first words as soon as with `every`."""
    GLIMPSE = "glimpse"
    """One live update per caption, `live_update_interval` seconds in (at
    least LIVE_MIN_AUDIO_SEC), then nothing until the finished caption."""


@dataclass(frozen=True, slots=True)
class BreathCut:
    """Finish a long stretch early, at a breath: once a speech segment has
    run `after` seconds, the first pause of `pause` seconds finishes it
    (the finished caption covers the speech so far), and the speech after
    the pause starts a new caption. At `limit` seconds without such a
    pause it is split anyway, like the long-speech split. A breath cut is
    deliberate, so what follows it is never joined onto it. Gives finished
    captions in pieces of a few seconds instead of nothing until a long
    stretch ends (project 021's item 2). The defaults are 021's; the
    caption modes' own are `BREATH_CUTS`."""

    after: float = 4.0
    pause: float = 0.3
    limit: float = 8.0


@dataclass(frozen=True, slots=True)
class TimingRules:
    """The timing rules' options. The defaults are the proof of concept's,
    except the lead-in (the proof of concept had none: project 038)."""

    schedule: LiveSchedule = LiveSchedule.EVERY
    silence_hangover: float = SILENCE_HANGOVER_SEC
    """Seconds of silence that end a speech segment."""
    breath_cut: BreathCut | None = None
    turn_cut: float | None = None
    """On calls: when another source starts speaking while this one has
    been silent for this many seconds, finish this one's caption now
    rather than at the full hangover (turn-taking as an end-of-speech
    cue). None: off."""
    join_gap: float = JOIN_GAP_SEC
    """Speech again within this long of the same source's last finished
    caption is joined onto it (re-transcribed as one). 0: never join."""
    join_only_under: float | None = None
    """Join only to repair a fragment: when the earlier caption ran less
    than this many seconds. None: join whatever its length (the proof of
    concept's rule - every join re-hears the whole run)."""
    lead_in: float = ONSET_LEAD_IN_SEC
    """Seconds a caption that starts after silence starts before its first
    speech frame, so a soft first word isn't clipped - less where the
    source's previous caption ended closer than that (with the slices'
    margins), so no audio is sent twice that wasn't before. Not after a
    long-speech split or a breath cut's limit: the speech goes on there.
    0: the first speech frame, as the proof of concept."""


class CaptionMode(StrEnum):
    """How captions are timed and shown: the learner's choice on the
    Captions page (polyglotic-hq DECISIONS.md #4, #107 and #230; until they
    choose, `default_caption_mode`). Each mode is a set of `TimingRules`
    and a live-update interval (`rules`, `live_update_interval`); in all of
    them, joins only repair fragments (FRAGMENT_SEC). Steady and Calm show
    their live updates through the playout (`paced`; `playout`, decision
    0245).

    The values are what the settings keep, so two are older than their
    names (decision 0246): Whole captions was called Steady until
    2026-11-20 and keeps "steady"; Instant was Live updates and keeps
    "live"."""

    STEADY = "words"
    """Word by word, in the speaker's rhythm, a constant delay behind: live
    updates every `LIVE_UPDATE_INTERVAL_SEC`, their words shown through
    the playout - each at the moment it was said plus the delay, the
    newest held back until it is confirmed (polyglotic-hq 526)."""
    WHOLE = "steady"
    """Whole captions: each caption once, finished - at a 0.6s pause, or
    at a breath once it has run a while (`BREATH_CUTS`: 3s, cut at 6s).
    Project 033's Y: the least GPU work, the first words a median ~3.6s
    after the speaker starts. No live updates of its own - only the
    longest wait for text's (polyglotic-hq 277): a provisional line once a
    caption has run that long, and again each time it runs that long more,
    replaced by the finished caption. Nothing sooner."""
    PREVIEW = "preview"
    """Quick preview, retired 2026-11-20 (decision 0246): not offered, and
    a learner who chose it is on Steady (`ui.settings`). Its rules stay
    until polyglotic-hq DECISIONS #230 is answered: Whole captions, plus
    provisional live updates on the growing schedule - 1.5 and 3s into
    each piece of a caption - all replaced by the finished caption."""
    INSTANT = "live"
    """Every live update shown as it comes, every few seconds (the
    learner's interval) while someone talks, finished at a 0.8s pause: the
    proof of concept's timing, kept as an option - except that joins only
    repair fragments, and that long speech is finished in pieces
    (`BREATH_CUTS`: at a breath once it has run 3s, cut at 6s), so a
    finished caption never rewrites more than its own line or two
    (decision 0088; the proof of concept redid up to 20s at once)."""
    SCROLLING = "scrolling"
    """Video uses live originals and translations in scrolling rows."""
    CALM = "calm"
    """Steady, showing only the words the server calls established: later
    (about as late as Whole captions), and the fewest shown words ever
    changed."""

    @property
    def rules(self) -> TimingRules:
        return _MODE_RULES[self]

    @property
    def usage_value(self) -> str:
        """The original speech timing in the existing version-1 tracking plan."""
        return (
            CaptionMode.INSTANT.value if self is CaptionMode.SCROLLING else self.value
        )

    @property
    def paced(self) -> bool:
        """Whether the mode's live updates are shown through the playout."""
        return self in (CaptionMode.STEADY, CaptionMode.CALM)

    @property
    def provisional_lines(self) -> bool:
        """Whether the mode's live updates are provisional lines - dim,
        translated, replaced by the finished caption: Whole captions' (the
        longest wait for text's only) and Quick preview's. The other
        modes' are the caption itself."""
        return self in (CaptionMode.WHOLE, CaptionMode.PREVIEW)

    @property
    def live_translated(self) -> bool:
        """Whether the mode's live updates are always translated: the
        provisional lines (polyglotic-hq 268, 277), and the paced modes',
        whose clauses show their translation as they end. Instant's are
        as the learner's "Translate live captions" says."""
        return self.provisional_lines or self.paced

    def live_update_interval(self, chosen: float) -> float | None:
        """The live-update interval the mode follows, given the learner's
        `chosen` one (which only Instant uses): None for Whole captions,
        PREVIEW_AFTER_SEC for Quick preview, `LIVE_UPDATE_INTERVAL_SEC`
        for the paced modes (what the playout's delay was measured at)."""
        if self is CaptionMode.WHOLE:
            return None
        if self is CaptionMode.PREVIEW:
            return PREVIEW_AFTER_SEC
        if self.paced:
            return LIVE_UPDATE_INTERVAL_SEC
        return chosen


OFFERED_MODES = (
    CaptionMode.INSTANT,
    CaptionMode.WHOLE,
    CaptionMode.STEADY,
    CaptionMode.CALM,
)
"""The modes a learner can choose, in the order shown: Quick preview is
retired (decision 0246)."""


def default_caption_mode() -> CaptionMode:
    """Instant for a learner who follows the app's default (project 626)."""
    return CaptionMode.INSTANT


_INSTANT_BREATH = BreathCut(after=3.0, pause=0.3, limit=6.0)
BREATH_CUTS: Mapping[CaptionMode, BreathCut] = {
    CaptionMode.WHOLE: BreathCut(after=3.0, pause=0.3, limit=6.0),
    CaptionMode.PREVIEW: BreathCut(after=3.0, pause=0.3, limit=6.0),
    CaptionMode.INSTANT: _INSTANT_BREATH,
    CaptionMode.SCROLLING: _INSTANT_BREATH,
    CaptionMode.STEADY: BreathCut(after=3.0, pause=0.3, limit=6.0),
    CaptionMode.CALM: BreathCut(after=3.0, pause=0.3, limit=6.0),
}
"""Each mode's breath cut - where it's tuned, `after` and `limit` above all
(polyglotic-hq 260): the mode's rules take it from here. 3s, a 0.3s pause,
cut at 6s (polyglotic-hq 268, from 243's phase 2 on the real models,
2026-11-09): in continuous speech 021's 4/0.3/8 almost never found its
pause, so the 8s limit fired and Steady showed nothing for 8.2s at a time
(the user's F34); at 3/6 it's 6.2s, and the card's p95 drops a third
(shorter requests batch better). 021's accuracy check at the shorter cut
is still to run. Live updates has the same since polyglotic-hq 296
(decision 0088; the user, 2026-11-13: "We don't need to rewrite words
spoken 3 seconds ago right?"): without one its finished caption redid the
whole stretch, up to the long-speech split's 20s - 14 to 22 clauses
rewritten at once. In pieces, text more than a line or two up never
changes."""

_WHOLE_RULES = TimingRules(
    silence_hangover=STEADY_HANGOVER_SEC,
    breath_cut=BREATH_CUTS[CaptionMode.WHOLE],
    join_only_under=FRAGMENT_SEC,
)
_INSTANT_RULES = TimingRules(
    breath_cut=BREATH_CUTS[CaptionMode.INSTANT], join_only_under=FRAGMENT_SEC
)
_MODE_RULES = {
    CaptionMode.WHOLE: _WHOLE_RULES,
    CaptionMode.PREVIEW: replace(
        _WHOLE_RULES,
        schedule=LiveSchedule.GROWING,
        breath_cut=BREATH_CUTS[CaptionMode.PREVIEW],
    ),
    CaptionMode.INSTANT: _INSTANT_RULES,
    CaptionMode.SCROLLING: _INSTANT_RULES,
    # the paced modes are fed as Instant is: the playout was measured on its updates
    CaptionMode.STEADY: replace(
        _INSTANT_RULES, breath_cut=BREATH_CUTS[CaptionMode.STEADY]
    ),
    CaptionMode.CALM: replace(_INSTANT_RULES, breath_cut=BREATH_CUTS[CaptionMode.CALM]),
}


class WithdrawalReason(StrEnum):
    """Why a caption was withdrawn (protocol.md). The app withdraws only
    for mic bleed; the server can also withdraw a caption that was only
    filler words, a phrase speech models invent in near-silence, or empty."""

    MIC_BLEED = "mic_bleed"
    FILLER_WORDS = "filler_words"
    NEAR_SILENCE_PHRASE = "near_silence_phrase"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    """Transcribe `source`'s audio from `speech_start` to `speech_end` (the
    app's clock, seconds) as a live update or the finished caption of
    `caption_id`. `section` is the live section (live updates only);
    `replaces` lists the captions a joined caption replaces.

    `cut_after`: the speech goes on after `speech_end` - the caption was
    cut there (a breath cut's limit, a long-speech split): its audio ends
    at `speech_end` exactly, and its text isn't finished there.
    `cut_before`: `speech_start` is such a cut, so the audio starts there
    exactly. Neither end carries the slice's margin (`SLICE_PAD_SEC`), so
    no stretch of audio is sent for both captions (protocol.md, "Speech
    cut while it goes on")."""

    caption_id: CaptionId
    kind: SpeechKind
    source: Source
    speech_start: float
    speech_end: float
    section: int | None = None
    replaces: tuple[CaptionId, ...] = ()
    cut_before: bool = False
    cut_after: bool = False
    held: bool = False
    """A live update that waited its turn under the speech ceiling before
    it was asked for (`CaptionTiming._live_budget`): nothing the server
    is told - the session counts them, to tell the learner once that live
    updates have slowed (`core.listening.held_back`)."""

    @property
    def audio_seconds(self) -> float:
        """How long the audio sent for it is: the speech and its margins -
        what the server's speech ceiling counts."""
        return self.speech_end - self.speech_start + sum(self.pads)

    @property
    def pads(self) -> tuple[float, float]:
        """The audio's margins before `speech_start` and after `speech_end`:
        `SLICE_PAD_SEC`, but none at a cut."""
        return (
            0.0 if self.cut_before else SLICE_PAD_SEC,
            0.0 if self.cut_after else SLICE_PAD_SEC,
        )


@dataclass(frozen=True, slots=True)
class WithdrawCaption:
    """Take back a caption already shown as a live update - its speech
    turned out to be the PC's own audio in the mic (mic bleed)."""

    caption_id: CaptionId
    source: Source
    reason: WithdrawalReason


Decision = TranscriptionRequest | WithdrawCaption


@dataclass(slots=True)
class _SpeechSegment:
    """A source's current speech segment, from its start to the pause."""

    start: float
    last_update: float
    section_start: float
    caption_id: CaptionId | None = None  # set by the first live update
    lead_in: float = 0.0  # the caption starts this long before `start`
    section: int = 0
    section_updates: int = 0  # live updates sent in the current section
    live_updates: int = 0  # live updates sent for this segment in all
    speech_frames: int = 0
    cut_before: bool = False  # it began where the caption before was cut
    levels: tuple[float, ...] = ()  # the last frames' loudness, newest last
    quiet_at: float | None = None  # where to cut it, if it runs to the limit
    quiet_level: float = float("inf")


@dataclass(slots=True)
class _SourceState:
    source: Source
    bleed: MicBleedCheck | None
    segment: _SpeechSegment | None = None
    silence_frames: int = 0
    sent_until: float | None = None  # the end of the last finished caption sent
    heard_until: float | None = None  # end of its last speech-detection frame


@dataclass(frozen=True, slots=True)
class _Run:
    """The last finished caption: the only one that can still be joined."""

    source_id: SourceId
    caption_id: CaptionId
    start: float
    end: float
    cut_before: bool = False


def _new_caption_id() -> CaptionId:
    return CaptionId(str(uuid.uuid4()))


def _next_section_if_long(segment: _SpeechSegment, end: float) -> None:
    """A live caption whose current section has passed LIVE_SECTION_SEC by
    `end` carries on in a new section from its last live update."""
    if end - segment.section_start > LIVE_SECTION_SEC:
        segment.section += 1
        segment.section_start = segment.last_update
        segment.section_updates = 0


class CaptionTiming:
    """Decides live updates, finished captions, long-speech splits and joins
    for every source in a listening session.

    Call `frame` for each speech-detection result of each source, in time
    order per source, with the time the frame ends on the app's clock (one
    clock for every source). It returns what to send, in order.
    """

    def __init__(
        self,
        live_update_interval: float | None = LIVE_UPDATE_INTERVAL_SEC,
        new_caption_id: Callable[[], CaptionId] = _new_caption_id,
        rules: TimingRules | None = None,
        max_wait: float | None = None,
    ) -> None:
        self.live_update_interval = live_update_interval
        """Seconds between live updates (`every`), or when the glimpse is
        taken (`glimpse`), as the user chose; None for finished captions
        only."""
        self.max_wait = max_wait
        """The longest wait for text (seconds): speech never runs longer
        than this since its caption's start or its last live update
        without a live update, whatever the schedule - in Steady, the only
        live updates (polyglotic-hq 277). The learner's choice, in
        MAX_WAIT_RANGE; None: no such rule (the proof of concept's)."""
        self.rules = rules = rules or TimingRules()
        self.pace_hint: float | None = None
        """The server's pace hint (protocol.md, `pace`): when it's busy, live
        updates at most this often, however often the user chose. None: no
        hint. Finished captions are never held back."""
        self.paused = False
        """Nothing is sent while paused; speech is still followed, so
        captions pick up mid-sentence when resumed."""
        self.paused_sources: frozenset[SourceId] = frozenset()
        """Sources paused on their own - a caption window hidden past the
        learner's limit (polyglotic-hq 335): nothing is sent for them, as
        while paused, and their speech is still followed."""
        self.speech_ceiling: float | None = SPEECH_SECONDS_PER_MINUTE
        """The server's speech ceiling, seconds of audio a minute: live
        updates wait rather than pass it (`_live_budget`). None: no such
        rule (the proof of concept's)."""
        self.live_updates_held = 0
        """How many live updates that were due have waited for the speech
        ceiling, so far - each once, however long it waited."""
        self._budget: float | None = None  # seconds of audio; None: full
        self._budget_at = 0.0
        self._waiting: set[SourceId] = set()  # sources with a live update held
        self._served: dict[SourceId, float] = {}  # each source's last live update
        self._new_caption_id = new_caption_id
        self._sources: dict[SourceId, _SourceState] = {}
        self._run: _Run | None = None
        self.change(rules, live_update_interval)

    def change(self, rules: TimingRules, live_update_interval: float | None) -> None:
        """Follows other rules and another live-update interval from the
        next frame on - the learner chose another caption mode while
        listening. Speech under way carries on under the new rules."""
        self.rules = rules
        self.live_update_interval = live_update_interval
        self._silence_frames_needed = _frames(rules.silence_hangover)
        self._turn_cut_frames = (
            _frames(rules.turn_cut) if rules.turn_cut is not None else None
        )

    @property
    def paced_interval(self) -> float | None:
        """Seconds between live updates as followed: the user's choice,
        stretched to the pace hint if that's longer."""
        chosen = self.live_update_interval
        if chosen is None or self.pace_hint is None:
            return chosen
        return max(chosen, self.pace_hint)

    @property
    def paced_max_wait(self) -> float | None:
        """The longest wait for text as followed: the learner's, stretched
        to the server's pace hint if that's longer - a busy server's hint
        holds back every live update (finished captions never wait)."""
        chosen = self.max_wait
        if chosen is None or self.pace_hint is None:
            return chosen
        return max(chosen, self.pace_hint)

    def hearing(self) -> frozenset[SourceId]:
        """The sources whose speech is under way - enough of it to be sent
        when it finishes - while not paused: what the listening mark shows
        is being heard."""
        if self.paused:
            return frozenset()
        return frozenset(
            source_id
            for source_id, state in self._sources.items()
            if source_id not in self.paused_sources
            and state.segment is not None
            and state.segment.speech_frames >= _MIN_SPEECH_FRAMES
        )

    def _silent(self, source_id: SourceId) -> bool:
        """Nothing is sent for `source_id` now: paused, or paused on its own."""
        return self.paused or source_id in self.paused_sources

    def captioning(self, source_id: SourceId) -> bool:
        """Whether this source is following speech and may issue captions."""
        return source_id in self._sources and not self._silent(source_id)

    def finished_before(self, source_id: SourceId, end: float) -> bool:
        """Has the source decided all captions for speech starting before end?"""
        if not self.captioning(source_id):
            return True
        state = self._sources[source_id]
        return (
            state.heard_until is not None
            and state.heard_until >= end
            and (state.segment is None or state.segment.start >= end)
        )

    def add_source(self, source: Source, bleed: MicBleedCheck | None = None) -> None:
        """Starts following `source`. `bleed` is checked before anything is
        sent for it (the mic's check against what the PC played)."""
        self._sources[source.id] = _SourceState(source, bleed)

    def remove_source(self, source_id: SourceId) -> None:
        """Stops following a source. Speech in progress is dropped."""
        self._sources.pop(source_id, None)
        self._waiting.discard(source_id)
        self._served.pop(source_id, None)

    def frame(
        self, source_id: SourceId, end: float, speech: bool, level: float | None = None
    ) -> list[Decision]:
        """One speech-detection result: the frame ending at `end` was speech
        or not, and its `level` - how loud it was (any measure that's lower
        for quieter audio; None: not known, and a cut at a limit falls where
        the limit does). Returns the decisions it leads to (usually none)."""
        self._refill(end)
        state = self._sources[source_id]
        state.heard_until = end
        decisions = self._heard(source_id, end, speech, level)
        if state.segment is None:
            self._waiting.discard(source_id)  # no speech, no turn to wait for
        if self._budget is not None:
            for decision in decisions:
                if isinstance(decision, TranscriptionRequest):
                    self._budget -= decision.audio_seconds
        return decisions

    def _refill(self, now: float) -> None:
        """The live budget, a leaky bucket on the app's clock: it holds at
        most LIVE_BURST_SHARE of the ceiling, and fills at the rate that
        keeps any minute's audio - a burst and all - under
        LIVE_BUDGET_SHARE of it. Everything sent is taken from it; only live
        updates wait for it."""
        ceiling = self.speech_ceiling
        if ceiling is None:
            self._budget = None
            return
        full = LIVE_BURST_SHARE * ceiling
        if self._budget is None:
            self._budget = full
        else:
            rate = (LIVE_BUDGET_SHARE - LIVE_BURST_SHARE) * ceiling / 60.0
            gained = max(0.0, now - self._budget_at) * rate
            self._budget = min(full, self._budget + gained)
        self._budget_at = now

    def _live_budget(self, source_id: SourceId, now: float) -> bool:
        """Whether `source_id`'s live update, due now, can go: there's
        budget left, and no other source with one held had its last live
        update longer ago - so each source gets its turn, and none is
        starved by the others. Otherwise it waits: it's due again at the
        source's next frame."""
        if self._budget is None:
            return True
        last = self._served.get(source_id, 0.0)
        others = (self._served.get(s, 0.0) for s in self._waiting if s != source_id)
        if self._budget > 0 and last <= min(others, default=last):
            self._waiting.discard(source_id)
            self._served[source_id] = now
            return True
        if source_id not in self._waiting:
            self._waiting.add(source_id)
            self.live_updates_held += 1
        return False

    def _heard(
        self, source_id: SourceId, end: float, speech: bool, level: float | None
    ) -> list[Decision]:
        state = self._sources[source_id]
        segment = state.segment
        decisions: list[Decision] = []
        if speech:
            if segment is None:
                start = end - FRAME_SEC
                segment = state.segment = _SpeechSegment(
                    start, start, start, lead_in=self._lead_in(state, start)
                )
                decisions.extend(self._turn_cuts(state, end))
            segment.speech_frames += 1
            state.silence_frames = 0
        elif segment is not None:
            state.silence_frames += 1
        if segment is None:
            return decisions
        if level is not None:
            self._note_level(segment, end, level)

        if state.silence_frames >= self._silence_frames_needed:
            speech_end = end - state.silence_frames * FRAME_SEC
            state.segment, state.silence_frames = None, 0
            return decisions + self._finish(state, segment, speech_end)
        cut = self.rules.breath_cut
        if cut is not None and end - segment.start >= cut.after:
            if state.silence_frames >= _frames(cut.pause):
                speech_end = end - state.silence_frames * FRAME_SEC
                state.segment, state.silence_frames = None, 0
                return decisions + self._split(state, segment, speech_end, resume=False)
            if end - segment.start >= cut.limit:
                return decisions + self._cut(state, segment, end)
        if end - segment.start >= FINAL_MAX_SEC:
            return decisions + self._cut(state, segment, end)
        return decisions + self._live_update(state, segment, end)

    def _limit(self) -> float:
        """How long speech runs before it's cut while it goes on: the breath
        cut's limit, else the long-speech split's."""
        cut = self.rules.breath_cut
        return min(cut.limit, FINAL_MAX_SEC) if cut is not None else FINAL_MAX_SEC

    def _note_level(self, segment: _SpeechSegment, end: float, level: float) -> None:
        """Keeps track of the quietest moment in the last CUT_LOOKBACK_SEC
        before the segment's limit: the middle of its quietest run of
        _QUIET_RUN_FRAMES frames (the latest, of equals)."""
        segment.levels = (*segment.levels, level)[-_QUIET_RUN_FRAMES:]
        run_start = end - len(segment.levels) * FRAME_SEC
        if (
            len(segment.levels) < _QUIET_RUN_FRAMES
            or run_start < segment.start + self._limit() - CUT_LOOKBACK_SEC - 1e-9
        ):
            return
        quiet = sum(segment.levels) / len(segment.levels)
        if quiet <= segment.quiet_level:
            segment.quiet_level = quiet
            segment.quiet_at = end - len(segment.levels) * FRAME_SEC / 2

    def _cut(
        self, state: _SourceState, segment: _SpeechSegment, end: float
    ) -> list[Decision]:
        """The limit, with the speech going on: finish the caption at the
        quietest moment of the last CUT_LOOKBACK_SEC (at `end` if the
        frames' loudness isn't known) and carry on from there."""
        at = segment.quiet_at if segment.quiet_at is not None else end
        return self._split(state, segment, at, resume=True, now=end)

    def _lead_in(self, state: _SourceState, start: float) -> float:
        """How long before `start` a caption starting after silence starts:
        the rule's lead-in, less what would reach back into the audio sent
        for the source's previous caption (its margin and this one's)."""
        lead = self.rules.lead_in
        if state.sent_until is not None:
            lead = min(lead, start - state.sent_until - 2 * SLICE_PAD_SEC)
        return max(0.0, lead)

    def _turn_cuts(self, speaker: _SourceState, end: float) -> list[Decision]:
        """Another source has started speaking: the sources already in
        their hangover are finished now (turn-taking as the cue), if the
        turn-cut rule is on and they have been silent long enough."""
        frames_needed = self._turn_cut_frames
        if frames_needed is None:
            return []
        decisions: list[Decision] = []
        for other in self._sources.values():
            segment = other.segment
            if (
                other is speaker
                or segment is None
                or other.silence_frames < frames_needed
            ):
                continue
            speech_end = end - other.silence_frames * FRAME_SEC
            other.segment, other.silence_frames = None, 0
            decisions.extend(self._finish(other, segment, speech_end))
        return decisions

    def _finish(
        self, state: _SourceState, segment: _SpeechSegment, speech_end: float
    ) -> list[Decision]:
        """The pause: the whole speech segment (or the run it joins) once
        more, as a finished caption replacing its live updates."""
        source = state.source
        if self._silent(source.id):
            return []
        if state.bleed is not None and state.bleed(segment.start, speech_end):
            if segment.caption_id is None:
                return []
            return [
                WithdrawCaption(segment.caption_id, source, WithdrawalReason.MIC_BLEED)
            ]
        if segment.caption_id is None and segment.speech_frames < _MIN_SPEECH_FRAMES:
            return []
        start, caption_id, replaces, cut_before = self._plan_finished(
            source.id, segment, speech_end
        )
        self._run = _Run(source.id, caption_id, start, speech_end, cut_before)
        state.sent_until = speech_end
        return [
            TranscriptionRequest(
                caption_id,
                SpeechKind.FINISHED,
                source,
                start,
                speech_end,
                replaces=replaces,
                cut_before=cut_before,
            )
        ]

    def _plan_finished(
        self, source_id: SourceId, segment: _SpeechSegment, end: float
    ) -> tuple[float, CaptionId, tuple[CaptionId, ...], bool]:
        """Where a finished stretch should be transcribed from, which caption
        it is, which captions it replaces, and whether it starts at a cut.
        Joined onto the same source's
        last caption if that ended within JOIN_GAP_SEC, nothing else was
        captioned since, and the whole stays within FINAL_MAX_SEC."""
        run = self._run
        rules = self.rules
        live_caption = segment.caption_id
        if (
            run is not None
            and run.source_id == source_id
            and segment.start - run.end <= rules.join_gap
            and end - run.start <= FINAL_MAX_SEC
            and (
                rules.join_only_under is None
                or run.end - run.start < rules.join_only_under
            )
        ):
            # Redo the whole run as the earlier caption, replacing this
            # stretch's live caption if it had one.
            replaces = (live_caption,) if live_caption else ()
            return run.start, run.caption_id, replaces, run.cut_before
        start = segment.start - segment.lead_in
        return start, live_caption or self._new_caption_id(), (), segment.cut_before

    def _split(
        self,
        state: _SourceState,
        segment: _SpeechSegment,
        end: float,
        resume: bool,
        now: float | None = None,
    ) -> list[Decision]:
        """A deliberate cut - talking past FINAL_MAX_SEC (or a breath cut's
        limit), or a breath: finish what's there, up to `end`, and carry on
        in a new caption. With `resume` the speech goes on: the new segment
        starts at `end` - before `now`, the frame being heard, when the cut
        fell at a quieter moment - and both requests say they were cut
        there. Without it the next speech starts one. Nothing is joined
        onto a cut: the stretch was cut on purpose."""
        decisions: list[Decision] = []
        if not self._silent(state.source.id) and not (
            state.bleed is not None and state.bleed(segment.start, end)
        ):
            caption_id = segment.caption_id or self._new_caption_id()
            decisions.append(
                TranscriptionRequest(
                    caption_id,
                    SpeechKind.FINISHED,
                    state.source,
                    segment.start - segment.lead_in,
                    end,
                    cut_before=segment.cut_before,
                    cut_after=resume,
                )
            )
            state.sent_until = end
        self._run = None
        state.segment = None
        if resume:
            heard = round((now - end) / FRAME_SEC) if now is not None else 0
            state.segment = _SpeechSegment(
                end, end, end, speech_frames=max(0, heard), cut_before=True
            )
        return decisions

    def _live_update(
        self, state: _SourceState, segment: _SpeechSegment, end: float
    ) -> list[Decision]:
        """Still talking: update the growing live caption on the schedule -
        or, whatever the schedule (none, in Steady), once the longest wait
        for text has passed since the caption's start or its last live
        update."""
        interval = self.paced_interval
        wait = self.paced_max_wait
        source_id = state.source.id
        if (
            self._silent(source_id)
            or (interval is None and wait is None)
            or state.silence_frames
            or end - segment.start < LIVE_MIN_AUDIO_SEC
        ):
            self._waiting.discard(source_id)
            return []
        overdue = wait is not None and end - segment.last_update >= wait
        schedule = self.rules.schedule
        if interval is None:  # no schedule: the longest wait's live updates only
            if not overdue:
                return []
            _next_section_if_long(segment, end)
        elif schedule is LiveSchedule.GLIMPSE:
            glimpse = not segment.live_updates and end - segment.start >= interval
            if not (glimpse or overdue):
                return []
            if not glimpse:
                _next_section_if_long(segment, end)
        elif schedule is LiveSchedule.GROWING:
            # Paced (or a longer interval chosen): the earlier offsets go.
            offsets = tuple(o for o in GROWING_OFFSETS_SEC if o >= interval) or (
                GROWING_OFFSETS_SEC[-1],
            )
            if segment.section_updates >= len(offsets):
                segment.section += 1
                segment.section_start = segment.last_update
                segment.section_updates = 0
            due = end - segment.section_start >= offsets[segment.section_updates]
            if not (due or overdue):
                return []
        else:
            if end - segment.last_update < interval and not overdue:
                return []
            _next_section_if_long(segment, end)
        held = source_id in self._waiting
        if not self._live_budget(source_id, end):
            return []
        segment.last_update = end
        segment.section_updates += 1
        segment.live_updates += 1
        if state.bleed is not None and state.bleed(segment.section_start, end):
            return []  # the PC's audio in the mic: no live update for it
        if segment.caption_id is None:
            segment.caption_id = self._new_caption_id()
        lead_in = segment.lead_in if segment.section == 0 else 0.0
        return [
            TranscriptionRequest(
                segment.caption_id,
                SpeechKind.LIVE,
                state.source,
                segment.section_start - lead_in,
                end,
                section=segment.section,
                cut_before=segment.cut_before and segment.section == 0,
                held=held,
            )
        ]
