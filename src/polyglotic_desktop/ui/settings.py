"""The settings the interface offers, remembered through the `SettingsStore`
port.

`AppSettings` lists every setting with its default - the proof of
concept's `settings.py` catalogue, without its model, translator,
assistant and Discord keys - and reads stored values leniently: a value
missing, of the wrong type or out of range falls back to its default, so
an old or hand-edited file never stops the app. `Settings` holds the
current ones, saves every change and says so (`changed`).

What reaches the server (spoken language, targets, second languages,
live translation) is `main`'s to turn into the connection's
`ListeningSettings`, and the caption windows' look (`main.caption_look`);
capture reads the source choice. Keys only today's overlays used
(`targets`, `text_scale`, `overlay_geometry`, `overlay_position`,
`overlay_width`) stay: the new interface's settings migration reads them
once, and an older app run afterwards still finds them (polyglotic-hq
RELEASING.md section 5). Holds no caption text.
"""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any

from PySide6.QtCore import QObject, Signal

from polyglotic_desktop.core.learning.first_known import Before
from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.languages import FULL, LearningLanguages
from polyglotic_desktop.core.learning.levels import LanguageChoices, LinkChoice
from polyglotic_desktop.core.learning.load import (
    MAX_SIZE,
    MIN_SIZE,
    Counting,
    LoadRules,
)
from polyglotic_desktop.core.listening.dictation import DICTATION_LANGUAGES
from polyglotic_desktop.core.listening.dictation_keys import (
    DEFAULT_KEY,
    DictationKey,
    refusal,
)
from polyglotic_desktop.core.listening.display import (
    READING_LANGUAGES,
    LinkDetail,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    WordLinks,
)
from polyglotic_desktop.core.listening.hidden import PAUSE_AFTER_MIN, PAUSE_CHOICES
from polyglotic_desktop.core.listening.settling import (
    SETTLE_AFTER_SEC,
    SETTLE_RANGE,
)
from polyglotic_desktop.core.listening.sources import colors_for
from polyglotic_desktop.core.listening.timing import (
    MAX_WAIT_FOR_TEXT_SEC,
    MAX_WAIT_RANGE,
    CaptionMode,
    default_caption_mode,
)
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ui.languages import NOT_OFFERED
from polyglotic_desktop.ui.theme import (
    DEFAULT_THEME,
    SOURCE_COLORS,
    THEMES,
    WINDOW_THEMES,
)

TEXT_SCALES = (0.7, 2.0)
MAX_SOURCE_NAME = 40  # characters in a source's label
SOURCE_KEY_SYSTEM, SOURCE_KEY_MIC = "system", "mic"  # beside apps' names
SOURCE_KEY_EVERYTHING_ELSE = "everything_else"  # beside the one app picked
SOURCE_KEY_SAMPLE = "sample"  # Home's sample, while it's on (polyglotic-hq 176)
_COLOR = re.compile("#[0-9a-f]{6}")
_LANGUAGE_CODE = re.compile("[a-z]{2,3}(_[A-Z]{2})?")  # an interface language
_LEARNED_CODE = re.compile("[a-z]{2,3}")  # a language learned (`learned_code`)
LIVE_INTERVALS = (0.5, 20.0)  # seconds, with Live updates
ORIGINAL_COLOR = "#ffffff"  # white is what was said, in its own language
TRANSLATION_COLOR = "#ffd76e"  # yellow is always a translation
BACKGROUND_COLOR = "#0a0c10"  # the panel behind the text, near black
# today's overlays' places: presets, or where the learner put them
# ("custom"); and their width, as a share of the screen's
POSITIONS = ("bottom_left", "bottom_centre", "top_centre", "custom")
# how a new caption arrives in the new interface's caption windows (its
# `views.arrivals.Arrival`'s values, which ui can't import)
ARRIVALS = ("step_and_slide", "step")
# the app's own text size, Settings > App (the new interface's
# `style.APP_TEXT_SIZES`' keys, which ui can't import; decision 0084)
APP_TEXT_SIZES = ("smaller", "normal", "larger", "largest")
MANDARIN_SCRIPTS = ("simplified", "traditional")
"""How Mandarin's captions are written (`mandarin_script`)."""
TRANSCRIPT_LENGTHS = ("newest", "three_hours", "session")
"""How far back a transcript's list may go: `TranscriptLength`'s values."""
WIDTH_SHARES = (0.2, 1.0)
OLD_LIVE_DEFAULT = 1.5  # the interval before there were caption modes
# the caption mode as versions before 176 kept it: Steady whether chosen or
# not, so only Quick preview and Live updates show a choice
OLD_CAPTION_TIMING = "caption_timing"


@dataclass(frozen=True)
class AppSettings:
    # the language being learned, whose learning data runs: "zh" or "en"
    # (core.learning.languages' FULL); None until chosen on Learning - the
    # first run asks none (polyglotic-hq 293) - and a change applies from
    # the next start. With it,
    # on Learning, the others learned too, in the order added (any caption
    # language's code), and those a lookup asked about once and was told
    # "Not now" (core.learning.languages.LearningLanguages)
    learning: str | None = None
    also_learning: tuple[str, ...] = ()
    not_now_learning: tuple[str, ...] = ()
    # the interface's own language ("en", "zh_CN"; ui.interface_language) -
    # None: Windows'. It applies from the next start (decision 0034)
    interface_language: str | None = None
    # languages
    targets: tuple[str, ...] = ("en",)  # an overlay each
    second_languages: dict[str, str] = field(default_factory=dict)  # target -> second
    spoken_language: str | None = None  # None: detect
    # Mandarin's captions in "simplified" or "traditional" characters,
    # converted on this PC (polyglotic-hq 375); None: like this PC -
    # Traditional on a Taiwan or Hong Kong Windows (`shows_traditional`)
    mandarin_script: str | None = None
    translate_live: bool = True
    spelling_hints: tuple[str, ...] = ()  # names and slang, for recognition only
    # captions: how the overlays look and when they update
    show_original: bool = True
    word_links: str = WordLinks.OFF.value
    link_detail: str = LinkDetail.MOST.value
    link_line: str = LinkLine.MEDIUM.value  # a word link's underline (F14)
    link_gap: str = LinkGap.MEDIUM.value  # and how far below the text
    text_scale: float = 1.0
    opacity: float = 0.72
    show_language: bool = True
    fade_after: float | None = None  # seconds of quiet; None: never (the default, F15)
    # how a new caption arrives: "step_and_slide" (the default) or "step"
    # (ui_next.views.arrivals; polyglotic-hq DECISIONS.md #104)
    caption_arrival: str = "step_and_slide"
    # a hidden caption window: minutes it still listens (None: always), and
    # whether it comes back when its app's speech starts (polyglotic-hq 335)
    pause_hidden_after: int | None = PAUSE_AFTER_MIN
    show_hidden_on_speech: bool = False
    # the languages with a reading line over their text ("zh": pinyin above
    # Chinese), and its size (core.listening.display; polyglotic-hq 369)
    reading_lines: tuple[str, ...] = ()
    reading_size: str = ReadingSize.SMALL.value
    reading_past: bool = False  # only over the words past what the learner knows
    # the reading line's colour: its line's, its word link's or one picked
    # (`reading_custom_color`); and linked words in their link's colour (395)
    reading_system: str = ReadingSystem.PINYIN.value  # or zhuyin (395)
    reading_colour: str = ReadingColour.SAME.value
    reading_custom_color: str = "#9ad0ff"
    link_words_coloured: bool = False
    # Settings > Captions > Lab's experimental values (the new interface's
    # `views.lab.CaptionLab`, which reads each one leniently): only those
    # moved from their defaults; {} untouched (polyglotic-hq 284)
    caption_lab: dict[str, object] = field(default_factory=dict)
    # the caption mode the learner chose - Steady, Quick preview or Live
    # updates (a core.listening.timing.CaptionMode's value). None until they
    # choose: the default (`default_caption_mode`, Steady: polyglotic-hq
    # DECISIONS.md #107), which can change for everyone who hasn't chosen. Saved
    # as `caption_timing` too, the key versions before 176 read
    caption_mode_chosen: str | None = None
    live_update_interval: float = 1.5  # seconds, with Live updates
    # the longest wait for text, in every caption mode: speech never runs
    # longer than this many seconds without a line on screen (2 to 6;
    # core.listening.timing's `max_wait`, polyglotic-hq 277)
    max_wait_for_text: float = MAX_WAIT_FOR_TEXT_SEC
    # how long shown text may still change, in seconds (0 to 3; 0: never
    # once shown - core.listening.settling's `SETTLE_RANGE`, polyglotic-hq
    # 309, decision 0099)
    text_settles_after: float = SETTLE_AFTER_SEC
    # word introductions (Learning; core.learning.highlights.WordIntroductions):
    # Off, A few per caption (the cap, "common words only") or Every new word.
    # Kept as two keys, so a version that knows only `common_words_only`
    # still has the cap chosen; turned off, the cap is kept for coming back
    common_words_only: bool = True
    marks_off: bool = False
    # what the learner chose for each language they learn, by its code
    # (core.learning.levels.LanguageChoices, read leniently): the learning
    # window's size. Only languages with a choice; {} none (polyglotic-hq 323)
    language_choices: dict[str, dict[str, object]] = field(default_factory=dict)
    # the learning load's rules for each language learned, by its code
    # (core.learning.load.LoadRules, read leniently): its size, the meetings
    # a stage, what counts as one, the most in a colour. Only what was
    # chosen; {} none. Whether the mode is on is the Lab's (`caption_lab`'s
    # "load": polyglotic-hq 324)
    learning_load: dict[str, dict[str, object]] = field(default_factory=dict)
    # where each language learned goes back to on Learning's Reset after
    # "Mark the first N words known" (core.learning.first_known.Before, read
    # leniently): its known line before the first quick mark; {} none was
    # set. Only languages with a Reset offered (polyglotic-hq 342)
    known_reset: dict[str, dict[str, object]] = field(default_factory=dict)
    locked: bool = False
    overlay_geometry: dict[str, list[int]] = field(default_factory=dict)
    # the display: the captions' font and colours, the panel behind them,
    # where the overlays go and how wide (project 054)
    caption_font: str | None = None  # a font family; None: the app's own
    original_color: str = ORIGINAL_COLOR  # what was said
    translation_color: str = TRANSLATION_COLOR
    background_color: str = BACKGROUND_COLOR  # the panel, at `opacity`
    overlay_position: str = "bottom_centre"  # a preset, or "custom": dragged
    overlay_width: float | None = None  # a share of the screen; None: half
    # the main window (Settings, Appearance): its theme - "margin", "glaze" or
    # "signal" (project 098) - and light or dark: "system", "light" or "dark"
    theme: str = DEFAULT_THEME
    window_theme: str = "dark"
    # the app's own text size (Settings > App), on top of Windows' Text size:
    # "smaller", "normal", "larger" or "largest" - every window of the app
    # but the captions, which keep their own (polyglotic-hq 292)
    app_text_size: str = "normal"
    # how far back each transcript window's list goes (Settings > App): the
    # newest 1,000 lines, the last three hours or the whole session -
    # `ui_next.views.transcript.TranscriptLength`'s values (polyglotic-hq 334)
    transcript_length: str = "newest"
    # Quit asks to save a transcript of more than 300 lines that isn't saved,
    # with three hours or the whole session kept; "Don't ask again" turns it
    # off, Settings > App > Transcripts back on (polyglotic-hq 334)
    transcript_ask_at_quit: bool = True
    # the tray said once that closing the main window keeps the app running
    # there (polyglotic-hq 135, finding 10): never again on this PC
    tray_note_shown: bool = False
    # "Start Polyglotic with Windows?" was asked, after a good session -
    # once only, whatever the answer (polyglotic-hq 176)
    start_with_windows_asked: bool = False
    # Home's line asking for the level (the first run doesn't: polyglotic-hq
    # 293) was answered Not now - never again; setting the level ends it too
    level_line_dismissed: bool = False
    # the version whose release notes the learner has seen: Home's What's
    # new card shows each newer version's after an update, until it's
    # closed; a fresh install starts at its own (polyglotic-hq 345,
    # `core.releases.notes`). None: kept by no version yet (0.1.5 and before)
    whats_new_seen: str | None = None
    # the account's test group, as the server last said (`welcome.cohort`);
    # None signed out or not yet known. The alpha's testers get "Report a
    # problem" with everything attached (polyglotic-hq 275)
    cohort: str | None = None
    # the planned maintenance window the server last told of (its times and
    # how far this PC's clock was ahead of the server's: core.listening.
    # maintenance's `stored`), so the app still says it after a restart while
    # the server can't be reached; empty: none (polyglotic-hq 319)
    maintenance: dict[str, object] = field(default_factory=dict)
    # audio: what's listened to - nothing until the learner picks (the
    # first run starts paused: polyglotic-hq DECISIONS.md #25)
    whole_system: bool = False  # everything the PC plays, not chosen apps
    # the apps picked, by name (they stay on this PC): each captioned at once,
    # as a source of its own
    apps: tuple[str, ...] = ()
    # everything else the PC plays too, in a window of its own - with one
    # app picked only (`captions_everything_else`; DECISIONS.md #59)
    everything_else: bool = False
    caption_mic: bool = False  # the user's own speech, captioned "You"
    # which speakers everything the PC plays is heard from, and which mic
    # is captioned (and dictation's): the OS's id for each, kept on this PC
    # only (polyglotic-hq 372) - None: Windows' default, also used while
    # the one chosen isn't plugged in
    speaker_device: str | None = None
    mic_device: str | None = None
    # capturing apps one by one failed on this PC, where Windows doesn't
    # promise it (Windows 10 version 2004 to 22H2; decision 0076): the
    # Windows build and app version it failed with ("windows", "app") and
    # why ("why": Windows' code, "no answer" or "silent") - content-free.
    # Empty: it didn't, or it's tried again (a Windows or app update, or
    # Home's "Try apps again")
    app_capture_fell_back: dict[str, str] = field(default_factory=dict)
    # each source's label, on this PC only - by key: an app's name, or
    # "system" (everything the PC plays), "everything_else" (beside one
    # app) or "mic": the learner's own name
    # for it (none: its own), and its colour (none: one of SOURCE_COLORS)
    source_names: dict[str, str] = field(default_factory=dict)
    source_colors: dict[str, str] = field(default_factory=dict)
    show_source: bool = True  # each caption's source above it, in its colour
    # each caption's delay on the line above it: from its speech's start and
    # end to shown, and the server's share (polyglotic-hq 271; the tray's
    # "Show each caption's delay"). For finding out why captions come late.
    show_delay: bool = False
    # dictation (polyglotic-hq 283, decision 0073): off until turned on - the
    # mic is then sent only while `dictation_key` (a DictationKey as kept:
    # "right_ctrl", "ctrl+alt+d", 283's "insert"...; polyglotic-hq 289) is
    # held; heard as `dictation_language` - None: whatever language is
    # detected, each hold; else that one, forced (one of the speech model's,
    # DICTATION_LANGUAGES); English in Australian spelling if
    # `dictation_australian`
    dictation: bool = False
    dictation_key: str = str(DEFAULT_KEY)
    dictation_language: str | None = None
    dictation_australian: bool = False

    @property
    def caption_mode(self) -> CaptionMode:
        """The mode the learner chose, or the default if they haven't."""
        if self.caption_mode_chosen is None:
            return default_caption_mode()
        return CaptionMode(self.caption_mode_chosen)

    @property
    def learning_languages(self) -> LearningLanguages:
        """The languages being learned (Learning's list)."""
        return LearningLanguages.of(
            self.learning, self.also_learning, self.not_now_learning
        )

    def choices_for(self, code: str) -> LanguageChoices:
        """What the learner chose for the language `code` (its learning
        window's size); the defaults where nothing was."""
        return LanguageChoices.from_stored(self.language_choices.get(code))

    def reset_point(self, code: str) -> Before | None:
        """Where Reset takes the language `code`'s known line back to after
        a quick mark; None: no Reset is offered (polyglotic-hq 342)."""
        stored = self.known_reset.get(code)
        return Before.from_stored(stored) if stored is not None else None

    def load_rules_for(self, code: str) -> LoadRules | None:
        """The learning load's rules for the language `code` - the
        defaults where nothing was chosen - or None while the Lab's mode is
        off (polyglotic-hq 324)."""
        if self.caption_lab.get("load") is not True:
            return None
        return load_rules_from(self.learning_load.get(code))

    @property
    def word_introductions(self) -> WordIntroductions:
        """How many new words captions point out (Learning's choice)."""
        return WordIntroductions.of(self.marks_off, self.common_words_only)

    @property
    def live_interval(self) -> float | None:
        """The live-update interval the caption mode follows (None: none)."""
        return self.caption_mode.live_update_interval(self.live_update_interval)

    def to_stored(self) -> dict[str, object]:
        values = asdict(self)
        values["targets"] = list(self.targets)
        values["spelling_hints"] = list(self.spelling_hints)
        values["apps"] = list(self.apps)
        values["reading_lines"] = list(self.reading_lines)
        values["also_learning"] = list(self.also_learning)
        values["not_now_learning"] = list(self.not_now_learning)
        # what versions before 176 read: the mode followed, chosen or not
        values[OLD_CAPTION_TIMING] = self.caption_mode.value
        return values

    @classmethod
    def from_stored(cls, stored: Mapping[str, object]) -> "AppSettings":
        """Settings from what was stored: anything missing or not valid
        takes its default. The one app an older version kept (`app_name`)
        becomes the only app picked."""
        stored = _migrated(stored)
        defaults = cls()
        found: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in stored:
                continue
            value = _valid(f.name, stored[f.name], getattr(defaults, f.name))
            if value is not _INVALID:
                found[f.name] = (
                    tuple(value)
                    if f.name in _TUPLES and isinstance(value, list | tuple)
                    else value
                )
        # Languages that were offered once and aren't now (DECISIONS.md #40):
        # off the choices, and the default if that leaves none
        if removed_targets(stored):
            kept = tuple(t for t in found["targets"] if t not in NOT_OFFERED)
            found["targets"] = kept or defaults.targets
        if "second_languages" in found:
            found["second_languages"] = {
                t: s
                for t, s in found["second_languages"].items()
                if t not in NOT_OFFERED and s not in NOT_OFFERED
            }
        return replace(defaults, **found)

    @property
    def source_chosen(self) -> bool:
        """The learner has picked what to caption: apps, or everything the
        PC plays. Until then nothing the PC plays is captioned."""
        return self.whole_system or bool(self.apps)

    @property
    def captions_everything_else(self) -> bool:
        """Everything else the PC plays is captioned, in a window of its
        own beside the one app picked: Windows leaves only one app out of a
        capture, so only with one app (polyglotic-hq DECISIONS.md #59). Not
        with everything the PC plays, nor where apps can't be captioned on
        their own (older Windows 10, or where trying it failed: decision
        0076) - `main` checks that."""
        return self.everything_else and not self.whole_system and len(self.apps) == 1

    def source_colors_for(self, others: Iterable[str] = ()) -> dict[str, str]:
        """Each source's colour, by key: the learner's choice, or the first
        of SOURCE_COLORS no other source has - handed out to the mic (blue,
        as "You" always was), then what's captioned (everything the PC
        plays, or the apps picked and everything else), then `others`, in
        that order."""
        captioned = [SOURCE_KEY_SYSTEM] if self.whole_system else list(self.apps)
        if self.captions_everything_else:
            captioned.append(SOURCE_KEY_EVERYTHING_ELSE)
        keys = [SOURCE_KEY_MIC, *captioned, *others]
        return colors_for(list(dict.fromkeys(keys)), self.source_colors, SOURCE_COLORS)


def learning_changes(languages: LearningLanguages) -> dict[str, object]:
    """The settings a change to the languages being learned makes. The
    main one applies from the next start."""
    return {
        "learning": languages.main,
        "also_learning": languages.also,
        "not_now_learning": languages.not_now,
    }


ADDED_LANGUAGE_LINKS = LinkChoice.PAST_KNOWN
"""Which words are linked in a language added from now on, until the
learner chooses (polyglotic-hq 323): only those past what they know - key
words, where no dictionary ranks them. A language learned before keeps
every word linked."""


def added_language_changes(
    value: AppSettings, languages: LearningLanguages
) -> dict[str, object]:
    """The settings change for the languages being learned becoming
    `languages` (`learning_changes`), and each one newly added starting
    with `ADDED_LANGUAGE_LINKS` - unless it has choices already (learned
    before, stopped, and added again: they were kept)."""
    changes = learning_changes(languages)
    before = value.learning_languages
    choices = {k: dict(v) for k, v in value.language_choices.items()}
    for code in languages.all:
        if not before.learns(code) and code not in choices:
            choices[code] = LanguageChoices(links=ADDED_LANGUAGE_LINKS).to_stored()
    if choices != value.language_choices:
        changes["language_choices"] = choices
    return changes


def language_choices_changes(
    value: AppSettings, code: str, choices: LanguageChoices
) -> dict[str, object]:
    """The settings change that keeps `choices` for the language `code`:
    the other languages' as they are, and no entry for one with nothing
    chosen."""
    kept = {k: dict(v) for k, v in value.language_choices.items() if k != code}
    stored = choices.to_stored()
    if stored:
        kept[code] = stored
    return {"language_choices": kept}


def reset_point_changes(
    value: AppSettings, code: str, before: Before | None
) -> dict[str, object]:
    """The settings change that keeps `before` as where Reset takes the
    language `code` back to (None: no Reset), the others as they are."""
    kept = {k: dict(v) for k, v in value.known_reset.items() if k != code}
    if before is not None:
        kept[code] = before.to_stored()
    return {"known_reset": kept}


def introductions_changes(choice: WordIntroductions) -> dict[str, object]:
    """The settings Learning's word introductions change to `choice`."""
    return {"marks_off": choice.off, "common_words_only": choice.common_only}


def removed_targets(stored: Mapping[str, object]) -> tuple[str, ...]:
    """The target languages a stored setting names that aren't offered any
    more, in the order stored."""
    targets = stored.get("targets")
    if not _languages(targets):
        return ()
    assert isinstance(targets, list | tuple)
    return tuple(t for t in targets if t in NOT_OFFERED)


_INVALID = object()
_TUPLES = (  # stored as lists
    "targets",
    "spelling_hints",
    "apps",
    "also_learning",
    "not_now_learning",
    "reading_lines",
)


def _migrated(stored: Mapping[str, object]) -> Mapping[str, object]:
    """What an older version stored, in today's settings: one app picked
    (`app_name`, before several could be) is `apps` with that app alone;
    overlays moved before there were position presets are where they
    were put ("custom"); and the caption mode chosen, from versions that
    kept the mode followed (`_caption_mode_chosen_from`)."""
    found = dict(stored)
    old = found.get("app_name")
    if "apps" not in found and isinstance(old, str):
        found["apps"] = [old]
    if "overlay_position" not in found and found.get("overlay_geometry"):
        found["overlay_position"] = "custom"
    if "caption_mode_chosen" not in found:
        found["caption_mode_chosen"] = _caption_mode_chosen_from(found)
    return found


def _caption_mode_chosen_from(stored: Mapping[str, object]) -> str | None:
    """The caption mode chosen, for settings saved by a version before 176
    (polyglotic-hq project 176). Those kept the mode followed
    (`caption_timing`), Steady by default, and saved it whether it was
    chosen or not - so Quick preview and Live updates were chosen, and
    Steady, or anything not valid, wasn't: it follows today's default.
    Settings from before there were modes have only a live-update interval
    (`_mode_from_interval`)."""
    old = stored.get(OLD_CAPTION_TIMING)
    if OLD_CAPTION_TIMING not in stored:
        return _mode_from_interval(stored.get("live_update_interval", OLD_LIVE_DEFAULT))
    if old in (CaptionMode.PREVIEW.value, CaptionMode.LIVE.value):
        return str(old)
    return None


def _mode_from_interval(interval: object) -> str | None:
    """The caption mode chosen, for settings saved before there were modes,
    from their live-update interval. Every version saved the interval, so a
    changed one is the only sign of a choice: the old default (1.5s) - or
    anything not valid - wasn't one; Off (None: finished captions only) was,
    and Steady is the nearest mode to it; any other interval was chosen, so
    it stays, with Live updates."""
    if interval is None:
        return CaptionMode.STEADY.value
    if (
        isinstance(interval, int | float)
        and not isinstance(interval, bool)
        and interval != OLD_LIVE_DEFAULT
        and LIVE_INTERVALS[0] <= interval <= LIVE_INTERVALS[1]
    ):
        return CaptionMode.LIVE.value
    return None


def _valid(name: str, value: object, default: object) -> object:
    check = _CHECKS.get(name)
    if check is not None:
        return value if check(value) else _INVALID
    if isinstance(default, bool):
        return value if isinstance(value, bool) else _INVALID
    return _INVALID


def _number_in(
    low: float, high: float, optional: bool = False
) -> Callable[[object], bool]:
    def check(value: object) -> bool:
        if value is None:
            return optional
        return (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and low <= value <= high
        )

    return check


def _text_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def _dictation_key(value: object) -> bool:
    """A key dictation can be held on (polyglotic-hq 289): one kept by
    this version or 283's, and not one refused (a key that types...)."""
    key = DictationKey.parse(value) if isinstance(value, str) else None
    return key is not None and refusal(key) is None


def _languages(value: object) -> bool:
    return isinstance(value, list | tuple) and all(isinstance(v, str) for v in value)


def _codes(value: object) -> bool:
    """A list of languages' codes (`ja`, `zh`, `yue`)."""
    return isinstance(value, list | tuple) and all(
        isinstance(v, str) and bool(_LEARNED_CODE.fullmatch(v)) for v in value
    )


def _language_map(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


def _text_map(value: object, valid: Callable[[str], bool]) -> bool:
    """A map of strings to strings, each value `valid`."""
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) and valid(v) for k, v in value.items()
    )


def load_rules_from(stored: object) -> LoadRules:
    """A language's learning load rules as the settings keep them: anything
    missing or not valid takes its default."""
    if not isinstance(stored, dict):
        return LoadRules()
    default = LoadRules()

    def count(name: str, least: int, most: int, otherwise: int) -> int:
        value = stored.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return otherwise
        return value if least <= value <= most else otherwise

    counting = stored.get("counting")
    return LoadRules(
        size=count("size", MIN_SIZE, MAX_SIZE, default.size),
        step=count("step", 1, 50, default.step),
        counting=Counting(counting)
        if isinstance(counting, str) and counting in set(Counting)
        else default.counting,
        stage_limit=count("limit", 0, MAX_SIZE, default.stage_limit),
    )


def load_rules_changes(
    value: AppSettings, code: str, rules: LoadRules
) -> dict[str, object]:
    """The settings change that keeps `rules` for the language `code`'s
    learning load: only what differs from the defaults, the other
    languages' as they are."""
    default = LoadRules()
    stored: dict[str, object] = {}
    if rules.size != default.size:
        stored["size"] = rules.size
    if rules.step != default.step:
        stored["step"] = rules.step
    if rules.counting is not default.counting:
        stored["counting"] = rules.counting.value
    if rules.stage_limit != default.stage_limit:
        stored["limit"] = rules.stage_limit
    kept = {k: dict(v) for k, v in value.learning_load.items() if k != code}
    if stored:
        kept[code] = stored
    return {"learning_load": kept}


def _choices_map(value: object) -> bool:
    """Languages' codes, each to a map of its choices (read leniently by
    `LanguageChoices.from_stored`: one value not valid loses only itself)."""
    return isinstance(value, dict) and all(
        isinstance(k, str)
        and bool(_LEARNED_CODE.fullmatch(k))
        and isinstance(v, dict)
        and all(isinstance(name, str) for name in v)
        for k, v in value.items()
    )


def _geometry(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str)
        and isinstance(v, list)
        and len(v) == 4
        and all(isinstance(n, int) for n in v)
        for k, v in value.items()
    )


_CHECKS: dict[str, Callable[[object], bool]] = {
    "learning": lambda v: v is None or v in FULL,
    "also_learning": lambda v: _codes(v),
    "not_now_learning": lambda v: _codes(v),
    "interface_language": lambda v: (
        v is None or (isinstance(v, str) and bool(_LANGUAGE_CODE.fullmatch(v)))
    ),
    "targets": _languages,
    "second_languages": _language_map,
    "spoken_language": _text_or_none,
    "mandarin_script": lambda v: v is None or v in MANDARIN_SCRIPTS,
    "speaker_device": _text_or_none,
    "mic_device": _text_or_none,
    "dictation_key": _dictation_key,
    "dictation_language": lambda v: v is None or v in DICTATION_LANGUAGES,
    "cohort": _text_or_none,
    "whats_new_seen": _text_or_none,
    "word_links": lambda v: v in {w.value for w in WordLinks},
    "link_detail": lambda v: v in {d.value for d in LinkDetail},
    "link_line": lambda v: v in {w.value for w in LinkLine},
    "link_gap": lambda v: v in {g.value for g in LinkGap},
    "text_scale": _number_in(*TEXT_SCALES),
    "opacity": _number_in(0.0, 1.0),
    "fade_after": _number_in(1.0, 600.0, optional=True),
    "caption_arrival": lambda v: v in ARRIVALS,
    "pause_hidden_after": lambda v: (
        v is None
        or (isinstance(v, int) and not isinstance(v, bool) and v in PAUSE_CHOICES)
    ),
    "caption_lab": lambda v: isinstance(v, dict) and all(isinstance(k, str) for k in v),
    "reading_lines": lambda v: (
        isinstance(v, list | tuple) and all(x in READING_LANGUAGES for x in v)
    ),
    "reading_size": lambda v: v in {s.value for s in ReadingSize},
    "reading_colour": lambda v: v in {c.value for c in ReadingColour},
    "reading_system": lambda v: v in {s.value for s in ReadingSystem},
    "reading_custom_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "language_choices": lambda v: _choices_map(v),
    "learning_load": lambda v: _choices_map(v),
    "known_reset": lambda v: _choices_map(v),
    "caption_mode_chosen": lambda v: v is None or v in {m.value for m in CaptionMode},
    "live_update_interval": _number_in(*LIVE_INTERVALS),
    "max_wait_for_text": _number_in(*MAX_WAIT_RANGE),
    "text_settles_after": _number_in(*SETTLE_RANGE),
    "overlay_geometry": _geometry,
    "caption_font": lambda v: v is None or (isinstance(v, str) and 0 < len(v) <= 100),
    "original_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "translation_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "background_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "overlay_position": lambda v: v in POSITIONS,
    "window_theme": lambda v: v in WINDOW_THEMES,
    "theme": lambda v: v in THEMES,
    "app_text_size": lambda v: v in APP_TEXT_SIZES,
    "transcript_length": lambda v: v in TRANSCRIPT_LENGTHS,
    "overlay_width": _number_in(*WIDTH_SHARES, optional=True),
    "apps": _languages,  # a list of strings
    "source_names": lambda v: _text_map(
        v, lambda name: 0 < len(name) <= MAX_SOURCE_NAME
    ),
    "source_colors": lambda v: _text_map(v, lambda c: bool(_COLOR.fullmatch(c))),
    "spelling_hints": _languages,  # a list of strings
    "app_capture_fell_back": lambda v: _text_map(v, lambda text: len(text) <= 100),
    # read whole by core.listening.maintenance.from_stored, which refuses the rest
    "maintenance": lambda v: isinstance(v, dict) and len(v) <= 3,
}


class Settings(QObject):
    """The current settings: every change saved and announced."""

    changed = Signal()

    def __init__(
        self, store: SettingsStore | None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._store = store
        stored = store.load() if store else {}
        self.value = AppSettings.from_stored(stored)
        # keys this version doesn't know (a newer version's, after a rollback)
        # are kept on every save, so going back and forth loses nothing
        # (polyglotic-hq project 107, 104's G11)
        known = {f.name for f in fields(AppSettings)}
        self._unknown = {k: v for k, v in stored.items() if k not in known}

    def update(self, **changes: object) -> None:
        new = replace(self.value, **changes)  # type: ignore[arg-type]
        if new == self.value:
            return
        self.value = new
        if self._store is not None:
            # the file's other keys as they are now: saved, changed or
            # removed since by another part of the app (the new interface's
            # caption windows keep theirs in the same file). Nothing read -
            # the file gone or unreadable for a moment - keeps the last ones
            # known rather than losing them.
            stored = self._store.load()
            if stored:
                known = {f.name for f in fields(AppSettings)}
                self._unknown = {k: v for k, v in stored.items() if k not in known}
            self._store.save({**self._unknown, **new.to_stored()})
        self.changed.emit()
