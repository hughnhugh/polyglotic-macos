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
Detect - a new app may speak anything - unless the learner chose "Start
new windows like this" (`StoredWindows.start_like_this`: then it is the
last window's too; polyglotic-hq 465), and "Show my speech here" starts
off (section 2, defaults).

The very first caption window on a PC sets itself up (polyglotic-hq 465,
449's 3A): its three language choices are asked in it - and in every
window that opens after, until the learner chooses "Use as my default" in
one (polyglotic-hq 478; `StoredWindows.set_up`, kept). Its answers are then
how new windows start. A new learner's first window shows my speech too
(`StoredWindows.first_window`; 478, the user, 2026-11-18: "record user mic
in first window is the default"), with its switch in the set-up to turn it
off. Home's sample's window is neither: it's a trial, not what the learner
captions.

`JoinedChoices`: whether the windows are joined into one, a column each
(109's 2a), and that window's own place - kept beside each
window's own, so separating puts every window back where it was.

`CaptionLook` is the session's look every window shares (the Look panel's
values, today's Captions page). `Notices` picks the one line a window
shows over its top band.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from polyglotic_desktop.core.learning.curriculum import DEFAULT_CHOSEN, ChosenWords
from polyglotic_desktop.core.learning.curriculum import DEFAULT_SIZE as CURRICULUM_SIZE
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
from polyglotic_desktop.core.listening.sources import SAMPLE
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

TRANSLATION_SIZES = CAPTION_TEXT_SIZES
"""A translation's independent text size: 60 to 400 %, the same range as
what was said (`CAPTION_TEXT_SIZES`; polyglotic-hq 655). Changing one never
changes the other."""

LEGACY_TRANSLATION_SHARES = (
    0.5,
    2.0,
)  # constant: pre-655 relative translation_size bounds
"""Range of pre-655 relative `translation_size` shares, kept for migrating
old settings files and writing rollback-safe legacy shares."""


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
        low, high = LEGACY_TRANSLATION_SHARES
        legacy_share = round(
            min(
                high,
                max(
                    low,
                    self.translation_size / max(self.text_size, CAPTION_TEXT_SIZES[0]),
                ),
            ),
            2,
        )
        return {
            "translate_into": self.translate_into,
            "text_size": self.text_size,
            "show_mic": self.show_mic,
            "position": self.preset.value,
            "geometry": self.geometry.as_list() if self.geometry else None,
            "spoken_language": self.spoken_language or DETECT,
            "translation_size": legacy_share,
            "translation_text_size": self.translation_size,
        }

    @classmethod
    def from_stored(cls, stored: object, base: "WindowChoices") -> "WindowChoices":
        """A window's stored choices: anything missing or not valid takes
        `base`'s. A file from before 655 holds no `translation_text_size`:
        its single `text_size` (and any pre-655 relative `translation_size`
        share) becomes an independent `translation_size` keeping the exact
        same rendered size on update."""
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
        if "translation_text_size" in stored:
            independent = translation_size(stored.get("translation_text_size"))
            if independent is not None:
                found["translation_size"] = independent
        else:
            legacy = _legacy_translation_share(stored.get("translation_size"))
            if size is not None or legacy is not None:
                caption = size if size is not None else base.text_size
                share = legacy if legacy is not None else 1.0
                low, high = TRANSLATION_SIZES
                found["translation_size"] = round(
                    min(high, max(low, caption * share)), 2
                )
        return replace(base, **found)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class JoinedChoices:
    """The joined window (109's 2a): whether the windows are joined - so a
    new app adds a column - and the joined window's own place. Each
    window's own is kept apart, for separating.

    Joined by default: a second app's window joins the first's as it opens
    (the user, 2026-11-20, polyglotic-hq 554: "windows should start joined
    by default when new windows are added"); one window alone shows on its
    own. "Separate windows" is the learner's choice (`chosen`), kept: new
    windows then open on their own until "Join windows"."""

    on: bool = True
    preset: Preset = Preset.BOTTOM_CENTRE
    geometry: Rect | None = None
    shares: tuple[float, ...] = ()
    """Each column's share of its width, as the dividers were dragged
    (polyglotic-hq 284); () or another number of columns: equal."""
    chosen: bool = False
    """The learner joined or separated the windows: `on` is theirs, kept.
    Until then it follows the default."""

    def to_stored(self) -> dict[str, object]:
        return {
            "on": self.on,
            "chosen": self.chosen,
            "position": self.preset.value,
            "geometry": self.geometry.as_list() if self.geometry else None,
            "shares": [round(s, 4) for s in self.shares],
        }

    @classmethod
    def from_stored(cls, stored: object) -> "JoinedChoices":
        """Anything missing or not valid: the defaults. Joined or separate
        as the learner chose; never chosen, the default (joined). Versions
        before 554 kept no record of a choice, and saved "on" false for
        everyone who never joined: separate counts as chosen only where
        the windows had been joined - a joined window's place or its
        columns' widths kept."""
        if not isinstance(stored, Mapping):
            return cls()
        found: dict[str, object] = {}
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
        on, chosen = stored.get("on"), stored.get("chosen")
        if not isinstance(chosen, bool):  # before 554
            chosen = on is True or geometry is not None or "shares" in found
        if chosen and isinstance(on, bool):
            found["on"], found["chosen"] = on, True
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
    above Chinese (369). `set_up`: "Use as my default" was chosen in a
    window's set-up (478), or there were windows before it came (polyglotic-hq
    465; a window's chip turns it off again, "Ask when a window opens"): never asked
    again. `start_like_this`: "Start new windows like this" - a new window
    takes the last one's spoken language too, not Detect (465)."""

    by_key: dict[str, WindowChoices] = field(default_factory=dict)
    last: WindowChoices = field(default_factory=WindowChoices)
    first_use: bool = False
    joined: JoinedChoices = field(default_factory=JoinedChoices)
    looked_up: bool = False
    recent_spoken: tuple[str, ...] = ()
    declined_spoken: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reading_hinted: bool = False
    respeaking_hinted: bool = False
    set_up: bool = False
    start_like_this: bool = False
    kept_languages: dict[str, str] = field(default_factory=dict)
    """While every window shows the original only (a preset's Show,
    polyglotic-hq 556): each window's translation language from before, by
    its key, given back when translations show again."""
    preset_sizes: dict[str, tuple[float, float]] = field(default_factory=dict)
    """Each preset's remembered (caption_size, translation_size) pair (655),
    saved when the learner adjusts a size or leaves a preset so switching back
    restores it while untouched presets start from their tuned defaults."""

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

    @property
    def first_window(self) -> bool:
        """The next window opened is a new learner's first: Use as my default
        isn't chosen and no window is kept but the sample's (478)."""
        return not self.set_up and all(key == SAMPLE for key in self.by_key)

    def for_new(
        self,
        index: int,
        key: str = "",
        set_up: bool = False,
        music_player: bool = False,
        my_speech: bool | None = None,
    ) -> WindowChoices:
        """The `index`-th window, new to the list (its key `key`): the last
        one's language, text size and translation size, at its default
        place, my speech off - and its spoken language with "Start new
        windows like this", else Detect (465). On first
        use, today's values: my speech as "Caption my own speech" was, and
        the overlays' position - where the first was put, for the first.
        Where the first window's set-up is offered (`set_up`: `main`'s), a
        new learner's first window shows my speech (`first_window`; not the
        sample's), and the set-up shows its switch (478). When the active
        preset names `my_speech` (Conversation: True; Video: False), a new
        window follows it (651; still off on the sample). A music player's
        window (`music_player`) starts on Detect whatever the others name:
        told a language, the speech model turns music into words like
        "The." (polyglotic-hq 558, 568) - its own window can still name one."""
        first = set_up and self.first_window and key != SAMPLE
        last = self.last
        if not self.first_use:
            choices = WindowChoices(
                last.translate_into,
                last.text_size,
                translation_size=last.translation_size,
                spoken_language=last.spoken_language if self.start_like_this else None,
            )
        elif index == 0:
            choices = last
        else:
            preset = (
                Preset.BOTTOM_CENTRE if last.preset is Preset.CUSTOM else last.preset
            )
            choices = replace(last, preset=preset, geometry=None)
        if music_player:
            choices = replace(choices, spoken_language=None)
        if key == SAMPLE:
            return replace(choices, show_mic=False)
        if my_speech is not None:
            return replace(choices, show_mic=my_speech)
        return replace(choices, show_mic=True) if first else choices

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
        stored: dict[str, object] = {
            "windows": {k: c.to_stored() for k, c in self.by_key.items()},
            "last": self.last.to_stored(),
            "joined": self.joined.to_stored(),
            "looked_up": self.looked_up,
            "reading_hinted": self.reading_hinted,
            "respeaking_hinted": self.respeaking_hinted,
            "recent_spoken": list(self.recent_spoken),
            "declined_spoken": {k: list(v) for k, v in self.declined_spoken.items()},
            "set_up": self.set_up,
            "start_like_this": self.start_like_this,
            "kept_languages": dict(self.kept_languages),
        }
        if self.preset_sizes:
            stored["preset_sizes"] = {
                k: [a, b] for k, (a, b) in self.preset_sizes.items()
            }
        return stored

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
            respeaking_hinted=own.get("respeaking_hinted") is True,
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
            # windows from before the set-up came (0.1.7): already set up;
            # since, as the learner left it - asked on every open until Use
            # as my default (478)
            set_up=own.get("set_up") is True or ("set_up" not in own and bool(by_key)),
            start_like_this=own.get("start_like_this") is True,
            kept_languages=_kept_languages(own.get("kept_languages")),
            preset_sizes=_preset_sizes(own.get("preset_sizes")),
        )


def _preset_sizes(value: object) -> dict[str, tuple[float, float]]:
    """Each preset's saved (caption_size, translation_size) pair, validated."""
    if not isinstance(value, Mapping):
        return {}
    found: dict[str, tuple[float, float]] = {}
    for key, pair in value.items():
        if not isinstance(pair, list | tuple) or len(pair) != 2:
            continue
        cap, trans = text_size(pair[0]), translation_size(pair[1])
        if cap is not None and trans is not None:
            found[str(key)] = (cap, trans)
    return found


def _kept_languages(value: object) -> dict[str, str]:
    """The windows' languages kept while the original only shows (556):
    a window's key to a language's code; anything else left out."""
    if not isinstance(value, Mapping):
        return {}
    return {
        str(k): v for k, v in value.items() if isinstance(v, str) and 0 < len(v) <= 10
    }


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


def _legacy_translation_share(value: object) -> float | None:
    """A pre-655 stored relative translation share (50 to 200 %), if valid."""
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and LEGACY_TRANSLATION_SHARES[0] <= value <= LEGACY_TRANSLATION_SHARES[1]
    ):
        return round(float(value), 2)
    return None


def translation_size(value: object) -> float | None:
    """A stored independent translation size, if it is one (TRANSLATION_SIZES),
    to two places."""
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


class TextEdge(StrEnum):
    """What's drawn around captions' letters (Visibility; polyglotic-hq
    481): `views.tone.EDGE_PASSES` says how."""

    NONE = "none"
    """Nothing: the panel alone keeps them readable (today's)."""
    SHADOW = "shadow"
    """A soft shadow down and to the right."""
    OUTLINE = "outline"
    """An outline all round: the most readable over a busy, bright video."""


class MarksIn(StrEnum):
    """Which line of a clause the learner's words are marked in - word
    introductions, saved words, the quiet view's chosen words (polyglotic-hq
    526; the user, 2026-11-19: words were highlighted in the translation)."""

    LEARNED = "learned"
    """The line in the language being learned: what was said when its
    language is learned, else its translation when that is. The default."""
    BOTH = "both"
    """Every line in a language the learner learns (as before 526)."""
    SAID = "said"
    """What was said only."""


def rows_marked(
    rows: Sequence[tuple[int, bool, bool]], marks_in: MarksIn
) -> frozenset[int]:
    """Which of a caption's rows get the learner's marks. `rows`: each
    row's clause, whether it is what was said, and whether its language is
    one the learner learns."""
    learned = {n for n, (_, _, learns) in enumerate(rows) if learns}
    if marks_in is MarksIn.BOTH:
        return frozenset(learned)
    said = {n for n in learned if rows[n][1]}
    if marks_in is MarksIn.SAID:
        return frozenset(said)
    covered = {rows[n][0] for n in said}  # clauses whose own words are learned
    return frozenset(said | {n for n in learned if rows[n][0] not in covered})


@dataclass(frozen=True, slots=True)
class CaptionLook:
    """How every caption window looks (the Look panel; today's Captions
    page): colours as "#rrggbb", the panel's opacity, the font family
    (None: Polyglotic (Default)), what shows above and in each caption, and when
    a quiet window fades (seconds; None: never)."""

    opacity: float = 0.88  # Classic's, the app's (0.72 until polyglotic-hq 584)
    background: str = "#0a0c10"
    original: str = "#ffffff"
    translation: str = "#ffd76e"
    font: str | None = None
    """The learner's font for every language's captions before 482 (one
    Font row): still each language's without a face of its own (`faces`)."""
    faces: tuple[tuple[str, str], ...] = ()
    """Each captioned language's face, by its code ("zh", "zh-hant" for
    Mandarin shown in Traditional): a family, or "" for the language's
    default (Look's rows, polyglotic-hq 482; `face_chosen`)."""
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
    respelling_past: bool = True
    """English's respelling the same way - its own choice, on at first
    (polyglotic-hq 511, DECISIONS #200: "only over new words")."""
    reading_system: ReadingSystem = ReadingSystem.PINYIN
    """Chinese's reading line in pinyin or zhuyin (395)."""
    reading_colour: ReadingColour = ReadingColour.GREY
    """What colour a reading is drawn in (polyglotic-hq 395): a muted grey
    by default, its word link's where one joins it, so word links on show
    a word and its pinyin alike (446) and the rest sit behind their text
    (532)."""
    reading_custom: str = "#9ad0ff"
    """The colour picked for readings, with `reading_colour` CUSTOM (kept
    while another is chosen, so Custom brings it back)."""
    said_in_link_colours: bool = True
    """Linked words in what was said take their link's colour, as their
    underline has (395)."""
    quiet: bool = False
    """The quiet view (polyglotic-hq 477; the user, 2026-11-18: "the quiet
    alternative of all word links and underlines removed"): every caption
    mode in Quick preview's grey and gold, italic and a size step bigger,
    a reading over every word, and only the chosen words (`quiet_words`)
    in blue - no underlines, no link colours, no arrows; a word's partner
    shows on hover. On with word links off, and the reverse
    (`views.panels.quiet_view`)."""
    quiet_words: frozenset[ChosenWords] = DEFAULT_CHOSEN
    """Which words the quiet view shows in blue: the union of what's
    ticked - our curriculum (the default), the learning load, saved words
    (DECISIONS #201)."""
    marks_in: MarksIn = MarksIn.LEARNED
    """Which line of a clause the learner's words are marked in."""
    curriculum_size: int = CURRICULUM_SIZE
    """How many words our curriculum's active set holds (473: 50)."""
    translation_in_link_colours: bool = True
    """Linked words in the translation take their link's colour - each on
    its own (431: the user, 2026-11-17, "toggleable separately"). With
    both to colour each side by its own word class. Both on by default (the user, 2026-11-17, 446:
    "default this setting to be on"): with word links off they change
    nothing."""
    contrast: int = 0
    """How strongly captions stand out from their panel: soft (-100,
    towards Quick preview's faintness) to crisp (100, every line at full
    ink); 0 is the look as it was (`views.tone`; polyglotic-hq 481)."""
    vibrance: int = 0
    """How vivid captions' colours are: muted (-100) to vivid (100); 0 is
    the look as it was (`views.tone.vibrant`; 481)."""
    thickness: int = 500
    """The captions' font weight (`views.tone.THICKNESSES`): Medium, 500,
    as they've always asked for (481)."""
    edge: TextEdge = TextEdge.NONE
    """What's drawn around the letters (Visibility, `views.tone.TextEdge`):
    nothing, as always (481)."""


def face_chosen(look: CaptionLook, language: str) -> str | None:
    """The face the learner chose for `language`'s captions: its own row's
    (`faces`), else the one font chosen for every language before 482;
    None for the language's default."""
    return dict(look.faces).get(language, look.font or "") or None


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
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    CROSS_BORDER_CONSENT_REQUIRED = "cross_border_consent_required"
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
    return busy and not before and timing is not CaptionMode.WHOLE


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
