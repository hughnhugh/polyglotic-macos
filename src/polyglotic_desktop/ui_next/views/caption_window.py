"""A caption window's own state, as plain Python - no Qt (polyglotic-hq
project 109's structure, section 2).

One caption window per app captioned (at most 3; DECISIONS.md #53), each
with **its own** place, text size, translation size (its translation's
text as a share of what was said's; polyglotic-hq 305), translation
language (or Original only), spoken language (or Detect; polyglotic-hq 263) and "Show
my speech here" (1.1). `WindowChoices` is what a
window remembers between launches, by its source's key - an app's name,
or "system" for everything the PC plays: stored as one setting,
`caption_windows`, beside today's settings (which keep keys they don't
know, so today's interface ignores it).

The first time the new interface runs, the windows take today's values
(`views.migration`, once). After that, a window new to the list copies
the last window's language and text size; its spoken language is
Detect - a new app may speak anything - and "Show my speech here" starts
off (section 2, defaults).

`JoinedChoices`: whether the windows are joined into one, a column each
(109's 2a), and that window's own place - kept beside each
window's own, so separating puts every window back where it was.

`CaptionLook` is the session's look every window shares (the Look panel's
values, today's Captions page). `Notices` picks the one line a window
shows over its top band.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import (
    LinkDetail,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    WordLinks,
)
from polyglotic_desktop.core.listening.hidden import PAUSE_AFTER_MIN
from polyglotic_desktop.core.listening.spoken import SPOKEN_LANGUAGES as SPOKEN
from polyglotic_desktop.core.listening.spoken import with_recent
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.captions import CAPTION_TEXT_SIZES, TEXT_SIZES
from polyglotic_desktop.ui_next.views.lab import CaptionLab
from polyglotic_desktop.ui_next.views.placement import DEFAULT_HEIGHT, Preset, Rect

STORED_KEY = "caption_windows"
"""The setting the windows' own choices are stored under."""

LIMIT = 3
"""Caption windows at most: one per app captioned (DECISIONS.md #53)."""

TEXT_STEP = 0.1
"""A text size step (A- / A+, Ctrl+wheel): 10 % - a caption window's from
60 to 400 % (`CAPTION_TEXT_SIZES`), a transcript's from 70 to 200 %."""
FINE_STEP = 0.05
"""A caption window's text size on its settings' slider: 5 %, to land
between A- and A+'s steps."""

TRANSLATION_SIZES = (0.5, 2.0)
"""A translation's text size, as a share of what was said's: 50 to 200 %
(the user, 2026-11-13: "need to a way to make the translation font size
smaller"; 2026-11-14: "maximal logical customisation"), in TEXT_STEP's
steps; 100 %, the same, is the default. Either line is still drawn within
CAPTION_TEXT_SIZES (`CaptionLayout`)."""


ORIGINAL_ONLY = ""
"""`translate_into` for a window captioned without translation."""

DETECT = "detect"
"""A window's stored spoken language when it is Detect (the protocol's
word for it)."""
SPOKEN_LANGUAGES: tuple[str, ...] = tuple(str(code) for code in SPOKEN)
"""The spoken languages a window can name: every one the speech model can
be told (`core.listening.spoken`; polyglotic-hq 317 - before, English,
Mandarin and Cantonese, as Home's Spoken language offered them: 248's
IA.md 1.1); any other stored value is read as the base's."""


@dataclass(frozen=True, slots=True)
class WindowChoices:
    """What a caption window remembers. `translate_into`: its translation
    language, or ORIGINAL_ONLY. `spoken_language`: the language its app's
    speech is in, one of SPOKEN_LANGUAGES - None: Detect. `geometry`: where
    it was put (None: its default slot). `translation_size`: its
    translation's text as a share of what was said's (TRANSLATION_SIZES)."""

    translate_into: str = "en"
    text_size: float = 1.0
    show_mic: bool = False
    preset: Preset = Preset.BOTTOM_CENTRE
    geometry: Rect | None = None
    spoken_language: str | None = None
    translation_size: float = 1.0

    @property
    def target(self) -> Language | None:
        """The translation shown; None: Original only."""
        return Language(self.translate_into) if self.translate_into else None

    @property
    def spoken(self) -> Language | None:
        """The language its app's speech is in; None: Detect."""
        return Language(self.spoken_language) if self.spoken_language else None

    def to_stored(self) -> dict[str, object]:
        return {
            "translate_into": self.translate_into,
            "text_size": self.text_size,
            "show_mic": self.show_mic,
            "position": self.preset.value,
            "geometry": self.geometry.as_list() if self.geometry else None,
            "spoken_language": self.spoken_language or DETECT,
            "translation_size": self.translation_size,
        }

    @classmethod
    def from_stored(cls, stored: object, base: "WindowChoices") -> "WindowChoices":
        """A window's stored choices: anything missing or not valid takes
        `base`'s."""
        if not isinstance(stored, Mapping):
            return base
        found: dict[str, object] = {}
        language = stored.get("translate_into")
        if isinstance(language, str):
            found["translate_into"] = language
        size = text_size(stored.get("text_size"))
        if size is not None:
            found["text_size"] = size
        # a stored "mode" is left: every window is a panel, one saved as a
        # Strip too (the Strip went, polyglotic-hq 272)
        if isinstance(stored.get("show_mic"), bool):
            found["show_mic"] = stored["show_mic"]
        if stored.get("position") in {p.value for p in Preset}:
            found["preset"] = Preset(stored["position"])
        geometry = rect_from(stored.get("geometry"))
        if geometry is not None and stored.get("mode") == STRIP:
            geometry = as_panel(geometry)
        if geometry is not None or stored.get("geometry", 0) is None:
            found["geometry"] = geometry
        spoken = stored.get("spoken_language")
        if spoken == DETECT or spoken in SPOKEN_LANGUAGES:
            found["spoken_language"] = None if spoken == DETECT else spoken
        share = translation_size(stored.get("translation_size"))
        if share is not None:
            found["translation_size"] = share
        return replace(base, **found)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JoinedChoices:
    """The joined window (109's 2a): whether the windows are joined - the
    learner's choice, kept until "Separate windows", so a new app adds a
    column - and the joined window's own place. Each window's own is kept
    apart, for separating."""

    on: bool = False
    preset: Preset = Preset.BOTTOM_CENTRE
    geometry: Rect | None = None
    shares: tuple[float, ...] = ()
    """Each column's share of its width, as the dividers were dragged
    (polyglotic-hq 284); () or another number of columns: equal."""

    def to_stored(self) -> dict[str, object]:
        return {
            "on": self.on,
            "position": self.preset.value,
            "geometry": self.geometry.as_list() if self.geometry else None,
            "shares": [round(s, 4) for s in self.shares],
        }

    @classmethod
    def from_stored(cls, stored: object) -> "JoinedChoices":
        """Anything missing or not valid: separate windows, the defaults."""
        if not isinstance(stored, Mapping):
            return cls()
        found: dict[str, object] = {}
        if isinstance(stored.get("on"), bool):
            found["on"] = stored["on"]
        if stored.get("position") in {p.value for p in Preset}:
            found["preset"] = Preset(stored["position"])
        geometry = rect_from(stored.get("geometry"))
        if geometry is not None and stored.get("mode") == STRIP:
            geometry = as_panel(geometry)
        found["geometry"] = geometry
        shares = stored.get("shares")
        if (
            isinstance(shares, list)
            and 2 <= len(shares) <= LIMIT
            and all(
                isinstance(s, int | float) and not isinstance(s, bool) for s in shares
            )
            and all(0 < s < 1 for s in shares)
        ):
            found["shares"] = tuple(float(s) for s in shares)
        return cls(**found)  # type: ignore[arg-type]


@dataclass
class StoredWindows:
    """Every window's choices by its key, and the last window changed - a
    new window copies its language and text size. `first_use`:
    today's values were just moved over (`views.migration`) and no window
    has been opened yet - a window for a source today's settings didn't
    name takes them too. `joined`: whether they're joined, and the joined
    window's place. `looked_up`: a word has been looked up on this PC, so
    "Click any word" is never said again (polyglotic-hq 176).
    `recent_spoken`: the spoken languages the learner named last, newest
    first - put first in every spoken-language list (polyglotic-hq 317).
    `declined_spoken`: by a window's key, the languages it was asked to
    always hear as and the learner said "Not now" to - never asked again
    (317). `reading_hinted`: a window has said once that pinyin can go
    above Chinese (369)."""

    by_key: dict[str, WindowChoices] = field(default_factory=dict)
    last: WindowChoices = field(default_factory=WindowChoices)
    first_use: bool = False
    joined: JoinedChoices = field(default_factory=JoinedChoices)
    looked_up: bool = False
    recent_spoken: tuple[str, ...] = ()
    declined_spoken: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reading_hinted: bool = False

    def spoken_declined(self, key: str, code: str) -> None:
        """The window of `key` was asked to always hear `code` and the
        learner said "Not now": never asked again."""
        before = self.declined_spoken.get(key, ())
        if code not in before:
            self.declined_spoken[key] = (*before, code)

    def spoken_named(self, code: str | None) -> None:
        """A window was set to hear `code` (None: Detect): first among the
        recent ones, if it's a language."""
        self.recent_spoken = with_recent(self.recent_spoken, code)

    def for_new(self, index: int) -> WindowChoices:
        """The `index`-th window, new to the list: the last one's language,
        text size and translation size, at its default place, my speech
        off. On first
        use, today's values: my speech as "Caption my own speech" was, and
        the overlays' position - where the first was put, for the first."""
        last = self.last
        if not self.first_use:
            return WindowChoices(
                last.translate_into,
                last.text_size,
                translation_size=last.translation_size,
            )
        if index == 0:
            return last
        preset = Preset.BOTTOM_CENTRE if last.preset is Preset.CUSTOM else last.preset
        return replace(last, preset=preset, geometry=None)

    def only_offered(self, offered: Collection[str]) -> "StoredWindows":
        """These choices with each translation language one of `offered` or
        ORIGINAL_ONLY: one that isn't - taken off the list (DECISIONS.md
        #40), a newer version's, edited by hand - would go to the server as
        a source's targets. A window's then takes the last window's; the
        last window's, the default's (polyglotic-hq project 117, Low 10)."""

        def kept(choices: WindowChoices, fallback: str) -> WindowChoices:
            language = choices.translate_into
            if language == ORIGINAL_ONLY or language in offered:
                return choices
            return replace(choices, translate_into=fallback)

        last = kept(self.last, WindowChoices().translate_into)
        by_key = {k: kept(c, last.translate_into) for k, c in self.by_key.items()}
        return replace(self, by_key=by_key, last=last)

    def to_stored(self) -> dict[str, object]:
        return {
            "windows": {k: c.to_stored() for k, c in self.by_key.items()},
            "last": self.last.to_stored(),
            "joined": self.joined.to_stored(),
            "looked_up": self.looked_up,
            "reading_hinted": self.reading_hinted,
            "recent_spoken": list(self.recent_spoken),
            "declined_spoken": {k: list(v) for k, v in self.declined_spoken.items()},
        }

    @classmethod
    def from_stored(
        cls, own: Mapping[str, object], base: WindowChoices
    ) -> "StoredWindows":
        """The windows' choices from their own setting (`STORED_KEY`'s
        value); anything missing or not valid takes `base`'s (today's
        values: `views.migration.stored_windows`)."""
        last = WindowChoices.from_stored(own.get("last"), base)
        windows = own.get("windows")
        by_key = {}
        if isinstance(windows, Mapping):
            by_key = {
                str(key): WindowChoices.from_stored(value, last)
                for key, value in windows.items()
            }
        recent = own.get("recent_spoken")
        declined = own.get("declined_spoken")
        return cls(
            by_key,
            last,
            joined=JoinedChoices.from_stored(own.get("joined")),
            looked_up=own.get("looked_up") is True,
            reading_hinted=own.get("reading_hinted") is True,
            recent_spoken=with_recent(
                (c for c in recent if isinstance(c, str))
                if isinstance(recent, list)
                else (),
                None,
            ),
            declined_spoken={
                str(key): tuple(c for c in codes if c in SPOKEN_LANGUAGES)
                for key, codes in declined.items()
                if isinstance(codes, list)
            }
            if isinstance(declined, Mapping)
            else {},
        )


def text_size(value: object) -> float | None:
    """A caption window's stored text size, if it is one
    (CAPTION_TEXT_SIZES: 60 to 400 %), to two places."""
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and CAPTION_TEXT_SIZES[0] <= value <= CAPTION_TEXT_SIZES[1]
    ):
        return round(float(value), 2)
    return None


def translation_size(value: object) -> float | None:
    """A stored translation size, if it is one (TRANSLATION_SIZES), to two
    places."""
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and TRANSLATION_SIZES[0] <= value <= TRANSLATION_SIZES[1]
    ):
        return round(float(value), 2)
    return None


def stepped_translation(size: float, steps: int) -> float:
    """A translation size `steps` steps of TEXT_STEP up (or down), kept
    within TRANSLATION_SIZES."""
    low, high = TRANSLATION_SIZES
    return round(min(high, max(low, size + steps * TEXT_STEP)), 2)


STRIP = "strip"
"""A stored window's "mode" when it was a Strip: the height followed its
newest caption. The Strip went (polyglotic-hq 272: "The strip toggle feels
bad, probably remove that"); such a window opens as a panel (`as_panel`)."""


def as_panel(strip: Rect) -> Rect:
    """A window saved as a Strip, as a panel: at least DEFAULT_HEIGHT tall,
    grown upwards from its bottom edge (most sat at the bottom; opening
    pulls it back onto its screen, `placement.at_start`)."""
    height = max(strip.height, DEFAULT_HEIGHT)
    return Rect(strip.x, strip.bottom - height, strip.width, height)


def rect_from(value: object) -> Rect | None:
    """A stored place (x, y, width, height), if it is one."""
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(n, int) and not isinstance(n, bool) for n in value)
        and value[2] > 0
        and value[3] > 0
    ):
        return Rect(*value)
    return None


@dataclass(frozen=True, slots=True)
class CaptionLook:
    """How every caption window looks (the Look panel; today's Captions
    page): colours as "#rrggbb", the panel's opacity, the font family
    (None: Polyglotic (Default)), what shows above and in each caption, and when
    a quiet window fades (seconds; None: never)."""

    opacity: float = 0.72
    background: str = "#0a0c10"
    original: str = "#ffffff"
    translation: str = "#ffd76e"
    font: str | None = None
    show_original: bool = True
    show_language: bool = True
    show_source: bool = True
    show_delay: bool = False  # each caption's delay on the line above it (271)
    fade_after: float | None = None

    word_links: WordLinks = WordLinks.OFF
    link_detail: LinkDetail = LinkDetail.MOST
    link_line: LinkLine = LinkLine.MEDIUM
    link_gap: LinkGap = LinkGap.MEDIUM
    """A word link's underline: how thick, and how far below the text's
    descenders (F14, 249)."""
    introductions: WordIntroductions = WordIntroductions.A_FEW
    """How many new words finished captions point out (Learning's)."""
    preview: bool = False
    """Quick preview: live captions are a provisional line."""
    arrival: Arrival = Arrival.STEP_AND_SLIDE
    """How a new caption arrives: step and slide (D), the older ones a step
    back and the text rising into place - or the step alone (B), which is
    also what D becomes with Windows' animations off (`views.arrivals`;
    DECISIONS.md #104)."""
    lab: CaptionLab = field(default_factory=CaptionLab)
    """Settings > Captions > Lab's experimental values (`views.lab`; 284)."""
    pause_hidden_after: int | None = PAUSE_AFTER_MIN
    """Minutes a hidden window still listens before its listening pauses;
    None: never (`core.listening.hidden`, polyglotic-hq 335)."""
    show_on_speech: bool = False
    """A hidden window comes back when its app's speech starts (335)."""
    reading_lines: tuple[str, ...] = ()
    """The languages whose text carries its reading line above it, what
    was said and translations alike ("zh": pinyin above Chinese;
    polyglotic-hq 369, decision 0155) - off for every language at first."""
    reading_size: ReadingSize = ReadingSize.SMALL
    """How big a reading is beside its text."""
    reading_past: bool = False
    """Readings only over the words past what the learner knows (the
    words word links "past what I know" would link, decision 0130)."""
    reading_system: ReadingSystem = ReadingSystem.PINYIN
    """Chinese's reading line in pinyin or zhuyin (395)."""
    reading_colour: ReadingColour = ReadingColour.SAME
    """What colour a reading is drawn in (polyglotic-hq 395)."""
    reading_custom: str = "#9ad0ff"
    """The colour picked for readings, with `reading_colour` CUSTOM (kept
    while another is chosen, so Custom brings it back)."""
    said_in_link_colours: bool = False
    """Linked words in what was said take their link's colour, as their
    underline has (395)."""
    translation_in_link_colours: bool = False
    """Linked words in the translation take their link's colour - each on
    its own (431: the user, 2026-11-17, "toggleable separately"). With
    both, and pinyin in its word link's colour, a word, its pinyin and its
    translation all match."""


INTRO_SEC = 8.0
"""How long a caption window put somewhere new shows itself when fading is
off (with fading on: the fade-after time) - DECISIONS.md #56."""


def intro_seconds(fade_after: float | None) -> float:
    """How long a caption window just put somewhere new - by Reset
    position, joining or separating - shows itself before it may fade
    (polyglotic-hq DECISIONS.md #56): the fade-after time, or INTRO_SEC
    when fading is off. A window with nothing to read yet shows anyway,
    waiting for audio (`shows`)."""
    return fade_after or INTRO_SEC


def shows(
    *,
    awake: bool,
    introducing: bool,
    empty: bool,
    quiet: float,
    fade_after: float | None,
) -> bool:
    """Whether a caption window shows, or fades out. It shows while it's
    `awake` (hovered, its band or a notice showing, paused, scrolled back,
    the listening mark), while `introducing` itself somewhere new
    (DECISIONS.md #56) and while it's `empty`: its app is chosen and it
    waits for audio, saying so, until its first captions (the user,
    polyglotic-hq 270/272: "Caption screen should open up once you connect
    an app ... displaying waiting for audio" - in place of #56's few
    seconds for a new window). With captions, it fades after `fade_after`
    seconds of `quiet` (None: never)."""
    if awake or introducing or empty:
        return True
    return not fade_after or quiet <= fade_after


class Notice(StrEnum):
    """What a caption window says on its notice line, by name (the
    wording: `caption_window.notice_text`, 087 section 5.5): the session's
    states, today's free minutes used, and a busy time."""

    PAUSED = "paused"
    RECONNECTING = "reconnecting"
    SERVER_BUSY = "server_busy"
    """Waiting to reconnect because the server is full - not the learner's
    connection (`server_busy`; polyglotic-hq 208)."""
    # waiting to reconnect, and why the server can't be reached
    # (core.listening.unreachable; polyglotic-hq 251)
    OFFLINE = "offline"
    """This PC seems to be offline."""
    CANT_REACH = "cant_reach"
    """Nothing answered: the learner's internet, or our server."""
    SERVER_RESTARTING = "server_restarting"
    SERVER_PROBLEM = "server_problem"
    """Our server failed the session."""
    BLOCKED = "blocked"
    """A proxy or firewall on this network: Home says what to do."""
    NOT_SECURE = "not_secure"
    """The secure connection failed: Home says what to do."""
    CLOCK = "clock"
    """This PC's date or time looks wrong: Home says where to set it."""
    TOO_MANY_SESSIONS = "too_many_sessions"
    """Open on too many of the account's PCs: Home says what to do."""
    TOO_MANY_TRIES = "too_many_tries"
    """Too many failed sign-ins from this network: it waits."""
    MAINTENANCE = "maintenance"
    """Polyglotic's server is in a planned maintenance window: Home says
    until when (polyglotic-hq 319)."""
    NOT_SIGNED_IN = "not_signed_in"
    UPDATE_NEEDED = "update_needed"
    STOPPED = "stopped"
    PLUS_ENDED = "plus_ended"
    """The server closed listening because Plus ended (4009; polyglotic-hq 185)."""
    MINUTES_USED = "minutes_used"
    """Today's free minutes are used (the server says none are left)."""
    FAILING = "failing"
    """Captions are failing on the server (core.listening.failing)."""
    UNSTABLE = "unstable"
    """The connection keeps dropping (core.listening.unstable)."""
    BUSY = "busy"
    """A busy time: the server slows live updates (`pace`) - said briefly."""


COUNTING = (
    Notice.RECONNECTING,
    Notice.SERVER_BUSY,
    Notice.OFFLINE,
    Notice.CANT_REACH,
    Notice.SERVER_RESTARTING,
    Notice.SERVER_PROBLEM,
    Notice.TOO_MANY_TRIES,
)
"""The notices that count down to the next try. The ones the learner can
do something about (a blocked network, the PC's clock) say "see Home"
instead: there's no room for both on a caption window."""


def minutes_used_up(left: float | None) -> bool:
    """Whether the server's count says no captioning minutes are left
    (protocol.md, `minutes`; None: no limit)."""
    return left is not None and left <= 0


def slowed_now(before: bool, busy: bool, timing: CaptionMode) -> bool:
    """Whether to say "busy time": the server's pace hint has just begun
    slowing live updates (`busy`, from not), and the learner's timing
    shows them - Quick preview or Live updates; Steady has none, so
    nothing changes for that learner and nothing is said (087 section 5.5:
    the fact, never noise over a game)."""
    return busy and not before and timing is not CaptionMode.STEADY


NOTICE_SEC = 6.0
"""A server notice shows this long (today's)."""
SNAP_NOTICE_SEC = 1.0
"""A preset's name shows this long when a dragged window snaps to it."""


class Notices:
    """The one notice line a window shows: the newest brief notice (a
    server notice, a busy time, a preset's name on snapping) while it
    lasts, and otherwise the session's state - Paused before anything
    else, then today's free minutes used, then captions failing on the
    server, then the connection's state - and while it has none to say
    (listening), an unstable connection - and with none of those, a `hint`
    ("Click any word", until the first lookup). A new notice replaces the
    one before. Times in seconds on one clock; nothing here reads it."""

    def __init__(self) -> None:
        self.paused = False
        self.minutes_used = False
        self.failing = False
        self.unstable = False
        self.state: Notice | None = None
        self.retry_at: float | None = None
        self.hint: str | None = None
        self._brief: tuple[str, float] | None = None

    def brief(self, text: str, now: float, seconds: float = NOTICE_SEC) -> None:
        self._brief = (text, now + seconds)

    def showing(self, now: float) -> tuple[Notice | None, str | None]:
        """What shows now: a brief notice's text, or the state (or
        neither)."""
        if self._brief is not None:
            if now < self._brief[1]:
                return None, self._brief[0]
            self._brief = None
        if self.paused:
            return Notice.PAUSED, None
        if self.minutes_used:
            return Notice.MINUTES_USED, None
        if self.failing:
            return Notice.FAILING, None
        if self.state is None and self.unstable:
            return Notice.UNSTABLE, None
        if self.state is None and self.hint:
            return None, self.hint
        return self.state, None

    def retry_in(self, now: float) -> int | None:
        """Whole seconds until the next try to reconnect, while waiting."""
        if self.state not in COUNTING or self.retry_at is None:
            return None
        return max(0, round(self.retry_at - now))

    def next_change(self, now: float) -> float | None:
        """When what shows may change by itself (a brief notice ending, the
        retry count ticking down) - None if it won't."""
        due = []
        if self._brief is not None:
            due.append(self._brief[1])
        if self.retry_in(now) and not (
            self.paused or self.minutes_used or self.failing
        ):
            due.append(now + 1.0)
        return min(due) if due else None


def stepped(size: float, steps: int, sizes: tuple[float, float] = TEXT_SIZES) -> float:
    """A text size `steps` steps of TEXT_STEP up (or down), kept within
    `sizes` (a transcript's TEXT_SIZES; a caption window's
    CAPTION_TEXT_SIZES)."""
    low, high = sizes
    return round(min(high, max(low, size + steps * TEXT_STEP)), 2)
