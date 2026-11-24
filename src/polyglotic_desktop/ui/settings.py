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

from polyglotic_desktop.core.learning.curriculum import DEFAULT_SIZE as CURRICULUM_SIZE
from polyglotic_desktop.core.learning.curriculum import MAX_SIZE as CURRICULUM_MAX
from polyglotic_desktop.core.learning.curriculum import MIN_SIZE as CURRICULUM_MIN
from polyglotic_desktop.core.learning.curriculum import ChosenWords
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
from polyglotic_desktop.core.listening.hotkeys import Hotkey
from polyglotic_desktop.core.listening.hotkeys import refusal as hotkey_refusal
from polyglotic_desktop.core.listening.offers import Use, offered
from polyglotic_desktop.core.listening.playout import (
    DELAY_SEC,
    EAGER_DELAY_SEC,
    TRANSLATION_AFTER_RANGE,
    TRANSLATION_AFTER_SEC,
    Ahead,
    PlayoutRules,
    ReadingPath,
)
from polyglotic_desktop.core.listening.preset_reading import (
    VIDEO_LINE_CHOICES,
    VIDEO_LINES,
)
from polyglotic_desktop.core.listening.respeaking import DEFAULT_RESPEAK_KEY
from polyglotic_desktop.core.listening.settling import (
    SETTLE_AFTER_SEC,
    SETTLE_RANGE,
)
from polyglotic_desktop.core.listening.sources import colors_for
from polyglotic_desktop.core.listening.timing import (
    LIVE_UPDATE_INTERVAL_SEC,
    MAX_WAIT_FOR_TEXT_SEC,
    MAX_WAIT_RANGE,
    CaptionMode,
    default_caption_mode,
)
from polyglotic_desktop.core.listening.type_theirs import TypeWhat
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
OPACITY = 0.88
"""How solid the panel is by default: the least at which what was said
and its translation reach 7:1 against it over a white scene behind it,
and the pinyin above them too (polyglotic-hq 584; the user, 2026-11-21:
"Default brightness / vibrance / contrast for everyday mode is not
readable enough"). At 0.72, until then, the translation was at 5.8:1."""
OLD_OPACITY = 0.72
"""The panel's default before 584: a file without the record of changes
holding it can't say it was chosen (`_at_old_default`)."""
# today's overlays' places: presets, or where the learner put them
# ("custom"); and their width, as a share of the screen's
POSITIONS = ("bottom_left", "bottom_centre", "top_centre", "custom")
# how a new caption arrives in the new interface's caption windows (its
# `views.arrivals.Arrival`'s values, which ui can't import)
ARRIVALS = ("step_and_slide", "step")
# the app's own text size, Settings > App (the new interface's
# `style.APP_TEXT_SIZES`' keys, which ui can't import; decisions 0084, 0244)
APP_TEXT_SIZES = ("smaller", "normal", "larger", "largest")
OLD_TEXT_SIZE = "app_text_size"
"""Where 0.1.9 and before kept the app's text size, on their steps (0.9,
1.0, 1.2, 1.45): read once, never written, so a version before them still
finds its own after a rollback (`interface_text_size`; decision 0244)."""
OLD_TEXT_SIZES = {"smaller": "smaller", "larger": "normal", "largest": "larger"}
"""A text size 0.1.9 or before kept, chosen, as the nearest of today's
steps by its size on screen (decision 0244): its Smaller (0.9) is today's
Smaller (1.0), its Larger (1.2) today's Normal (1.3) and its Largest
(1.45) today's Larger (1.45). Its Normal (1.0) isn't here: every file
held it, chosen or not, so it follows today's default (polyglotic-hq
524)."""
MANDARIN_SCRIPTS = ("simplified", "traditional")
MARKS_IN = ("learned", "both", "said")
"""Which line the learner's words are marked in (`marks_in`)."""
"""How Mandarin's captions are written (`mandarin_script`)."""
TRANSCRIPT_LENGTHS = ("newest", "three_hours", "session")
"""How far back a transcript's list may go: `TranscriptLength`'s values."""
FIRST_RUN_STEPS = ("consent", "done")
"""Where first-run set-up resumes after step 1's language relaunch, or done
once set-up finishes (polyglotic-hq 658)."""
WIDTH_SHARES = (0.2, 1.0)
SUBTITLE_SIZE = 0.045
"""Video's subtitles' text: its size as a share of the screen's height -
4.5 %, about 47 px on a 1080p screen, 63 px at 1440p - so it reads as
subtitles on any screen (polyglotic-hq 556; Claude, 2026-11-20: "about
4.5-5 % of it per line"), not a caption window's text size."""
SUBTITLE_SIZES = (0.015, 0.12)
SUBTITLE_WIDTH = 0.8
"""Video's subtitles' width, as a share of the work area (556)."""
SUBTITLE_WIDTHS = (0.3, 1.0)
OLD_LIVE_DEFAULT = 1.5  # the interval before there were caption modes
# the caption mode as versions before 176 kept it: Steady whether chosen or
# not, so only Quick preview and Live updates show a choice
OLD_CAPTION_TIMING = "caption_timing"
BUILT_INS = 7
CAPTION_LAB_VERSION = 2
"""Version 2 expresses Older captions as retained WCAG contrast, not paint alpha."""
FOLLOW_DEFAULT = (
    "dictation",
    "type_theirs",
    "word_links",
    "show_hidden_on_speech",
    "reading_past",
    "whole_system",
    "quiet_words",
    "live_update_interval",
    "max_wait_for_text",
    "text_settles_after",
    "steady_words_ahead",
    "reading_lines",
    "interface_text_size",
    "reading_colour",
    "opacity",
)
"""The settings that follow the app's default until changed on this PC
(`AppSettings.changed`) - turned on for a new learner by polyglotic-hq 478
(the user, 2026-11-18: "Default all functional features as on") and 484
(everything the PC plays: "Make the first time launch easier, everything
the PC plays should be [the default]"); the quiet view's blue words, words
at your edge ticked for a new learner (496, 503); the live-update
interval, 1.0 s since polyglotic-hq 494 (DECISIONS.md #211; 1.5 before:
`OLD_LIVE_DEFAULT`, never counted as changed); Steady's words ahead,
drawn faint since polyglotic-hq 554 (the user, 2026-11-20: "Default faint
ahead"); and the reading lines, on
over every language but the learner's own (the user, 2026-11-18: "default
pinyin/script assistance on for next release"; polyglotic-hq 511) - in a
file from before the record too, where none were on (`[]`, what an
untouched file holds; `from_stored`); the app's text size, larger by
default since polyglotic-hq 524 (decision 0244: one chosen before keeps
its size, `OLD_TEXT_SIZES`); and the readings' colour, grey since
polyglotic-hq 532 (its word link's before); and how solid the panel is,
0.88 since polyglotic-hq 584 (0.72 before: `OLD_OPACITY`, never counted
as changed). Another setting is kept as stored, as before. A name added here later follows its new default
only where the record began before it was changed."""


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
    # None: Windows'. Chosen as first-run step 1 or in Settings (decision 0034, 658)
    interface_language: str | None = None
    # first-run progress kept across the language relaunch (polyglotic-hq 658):
    # "consent" resumes at step 2; "done" once first run finished; None before
    first_run_step: str | None = None
    # languages
    targets: tuple[str, ...] = ("en",)  # an overlay each
    # each target's second language as chosen (target -> second); one not
    # chosen is English's, but English's own (`SECOND_BY_DEFAULT`), and
    # the targets chosen to have none where that would be English
    # (`second_language_of`; polyglotic-hq 555)
    second_languages: dict[str, str] = field(default_factory=dict)
    no_second_language: tuple[str, ...] = ()
    spoken_language: str | None = None  # None: detect
    # Mandarin's captions in "simplified" or "traditional" characters,
    # converted on this PC (polyglotic-hq 375); None: like this PC -
    # Traditional on a Taiwan or Hong Kong Windows (`shows_traditional`)
    mandarin_script: str | None = None
    translate_live: bool = True
    spelling_hints: tuple[str, ...] = ()  # names and slang, for recognition only
    # the Lyrics switch (polyglotic-hq 595, DECISIONS.md #248; decision
    # 0287): a known music player heard on Detect is heard in songs mode -
    # singing sent even where speech detection hears only music
    # (`core.listening.songs`). Off by default: music or singing alone gives
    # no captions until the learner turns it on
    lyrics: bool = False
    preset_languages: dict[str, dict[str, str]] = field(default_factory=dict)
    """The preset's language choices by window key. Missing fields follow
    the window's saved choices. An empty string means Detect or Original only."""
    preset_second_languages: dict[str, str] = field(default_factory=dict)
    """Second languages by translation language. An empty string leaves the line as is."""
    # captions: how the overlays look and when they update
    show_original: bool = True
    # on for a new learner (polyglotic-hq 478): the links with their lines,
    # as a caption window's word links button turns them on (446)
    word_links: str = WordLinks.ARROWS.value
    link_detail: str = LinkDetail.MOST.value
    link_line: str = LinkLine.MEDIUM.value  # a word link's underline (F14)
    link_gap: str = LinkGap.MEDIUM.value  # and how far below the text
    text_scale: float = 1.0
    opacity: float = OPACITY  # the panel's: follows the default until changed
    show_language: bool = True
    fade_after: float | None = None  # seconds of quiet; None: never (the default, F15)
    # how a new caption arrives: "step_and_slide" (the default) or "step"
    # (ui_next.views.arrivals; polyglotic-hq DECISIONS.md #104)
    caption_arrival: str = "step_and_slide"
    # a hidden caption window: minutes it still listens (None: always), and
    # whether it comes back when its app's speech starts (polyglotic-hq 335)
    pause_hidden_after: int | None = PAUSE_AFTER_MIN
    show_hidden_on_speech: bool = True  # on for a new learner (478)
    # the languages with a reading line over their text ("zh": pinyin above
    # Chinese), and its size (core.listening.display; polyglotic-hq 369).
    # Until changed (`FOLLOW_DEFAULT`) every language with one but the
    # learner's own (`main.readings_by_default`; polyglotic-hq 511): () here
    # is "not chosen", not "none"
    reading_lines: tuple[str, ...] = ()
    reading_size: str = ReadingSize.SMALL.value
    # only over the words past what the learner knows: off - readings over
    # every word, as the user's picture shows (2026-11-18, DECISIONS #206)
    reading_past: bool = False
    # English's respelling only over the words past what the learner knows:
    # its own choice, on at first (polyglotic-hq 511, DECISIONS #200)
    respelling_past: bool = True
    # the reading line's colour: its line's, its word link's or one picked
    # (`reading_custom_color`); and linked words in their link's colour (395)
    reading_system: str = ReadingSystem.PINYIN.value  # or zhuyin (395)
    # grey, its word link's where one joins it (532; the link's, else its
    # line's, since 446); follows the default until changed (`FOLLOW_DEFAULT`)
    reading_colour: str = ReadingColour.GREY.value
    reading_custom_color: str = "#9ad0ff"
    # the quiet view (polyglotic-hq 477): on or off, which words it shows in
    # blue (core.learning.curriculum.ChosenWords' values: "curriculum",
    # "edge", "load", "saved") and how many words our curriculum's set
    # holds. Words at your edge are on for a new learner (496); the words
    # follow the default until changed (`FOLLOW_DEFAULT`, 503), and a file
    # from before the record that holds the key keeps its choice
    quiet_view: bool = False
    quiet_words: tuple[str, ...] = ("curriculum", "edge")
    # which line of a clause the learner's words are marked in: "learned"
    # (the line in the language being learned), "both", or "said"
    # (`views.caption_window.MarksIn`, which ui can't import; 526)
    marks_in: str = "learned"
    curriculum_size: int = CURRICULUM_SIZE
    # how strongly captions stand out, soft to crisp, and how vivid their
    # colours are, muted to vivid: -100 to 100 each, 0 the look as it was
    # (ui_next.views.tone; polyglotic-hq 481)
    caption_contrast: int = 0
    caption_vibrance: int = 0
    caption_weight: int = 500  # the captions' font weight: Medium, as always
    caption_edge: str = "none"  # around the letters: "none", "shadow", "outline"
    colour_links_by_word_class: bool = False
    """Use the spoken word's class for both ends of each link. Off for new and
    existing settings until the two language taggers agree reliably (799)."""
    said_in_link_colours: bool = True  # what was said's linked words (431, 446)
    translation_in_link_colours: bool = True  # the translation's (431, 446)
    # Settings > Captions > Lab's experimental values (the new interface's
    # `views.lab.CaptionLab`, which reads each one leniently): only those
    # moved from their defaults; {} untouched (polyglotic-hq 284)
    caption_lab: dict[str, object] = field(default_factory=dict)
    caption_lab_version: int = CAPTION_LAB_VERSION
    # the caption mode the learner chose - Steady, Whole captions, Instant
    # or Calm (a core.listening.timing.CaptionMode's value: "words",
    # "steady", "live", "calm"). None until they choose: the default
    # (`default_caption_mode`, Steady: desktop decision 0246), which can
    # change for everyone who hasn't chosen. A stored "preview" (Quick
    # preview, retired) is read as Steady. Saved as `caption_timing` too,
    # the key versions before 176 read
    caption_mode_chosen: str | None = None
    # Steady's newest word: shown too, a quarter second sooner (the
    # playout's `EAGER_DELAY_SEC`), not held back until the next live
    # update confirms it (polyglotic-hq 526, DECISIONS #233)
    steady_newest_word: bool = False
    # Steady's two zones (decision 0251): the live lines below and the
    # settled transcript above; off: one list of captions, as the other
    # modes show them
    steady_two_zones: bool = True
    # Steady's card stack (decision 0260): each line a card that never
    # changes shape, the stack moved in one glide. It takes the two zones'
    # place; off: the two zones, or the one list
    steady_cards: bool = True
    # what is read first in a paced mode (core.listening.playout's
    # `ReadingPath`): "follow", "acquisition" or "both"; and Acquisition's
    # seconds between a clause and its translation (decision 0253)
    caption_path: str = "both"
    translation_after: float = TRANSLATION_AFTER_SEC
    # Steady's words ahead (karaoke): the words waiting for their moment
    # drawn faint - "none", "waiting", or "all" (the newest word too);
    # core.listening.playout's `Ahead`. Faint ahead by default, followed
    # until changed (`FOLLOW_DEFAULT`; "none" until polyglotic-hq 554)
    steady_words_ahead: str = "waiting"
    # seconds, with Live updates; follows the default until changed
    # (`FOLLOW_DEFAULT`; 1.5 until polyglotic-hq 494)
    live_update_interval: float = LIVE_UPDATE_INTERVAL_SEC
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
    # the word links kept in `language_choices` are the learner's own: a
    # file without this (0.1.10-preview.1 and before) also holds the "Past
    # what you know" those versions chose for each language added, which
    # is cleared once - every word is linked (`ADDED_LINKS`; polyglotic-hq
    # 555). Saved with every file since, so a learner who chooses it again
    # keeps it
    language_links_chosen: bool = True
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
    # Linux on a Wayland desktop: a locked caption window's corner keeps taking
    # the mouse, so resting on its lock offers Unlock over another app's
    # window (`UnlockSpot.catch`; polyglotic-hq 570, DECISIONS #243 item 6).
    # Not in Settings: a switch to take it out again if it gets in the way
    unlock_spot: bool = True
    # Linux: the first lock said at length how to unlock again (polyglotic-hq
    # 570; `main.tell_how_to_unlock`)
    unlock_told: bool = False
    overlay_geometry: dict[str, list[int]] = field(default_factory=dict)
    # the display: the captions' font and colours, the panel behind them,
    # where the overlays go and how wide (project 054)
    caption_font: str | None = None  # a font family; None: the app's own
    # each captioned language's face, by its code: a family, "" its default;
    # a language not named takes `caption_font` (polyglotic-hq 482)
    caption_faces: dict[str, str] = field(default_factory=dict)
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
    # but the captions, which keep their own (polyglotic-hq 292). On the
    # steps of decision 0244, larger than 0.1.9's (`OLD_TEXT_SIZE`, their
    # key): follows the default until changed (`FOLLOW_DEFAULT`)
    interface_text_size: str = "normal"
    # how far back each transcript window's list goes (Settings > App): the
    # newest 1,000 lines, the last three hours or the whole session -
    # `ui_next.views.transcript.TranscriptLength`'s values (polyglotic-hq 334)
    transcript_length: str = "newest"
    # Quit asks to save a transcript of more than 300 lines that isn't saved,
    # with three hours or the whole session kept; "Don't ask again" turns it
    # off, Settings > App > Transcripts back on (polyglotic-hq 334)
    transcript_ask_at_quit: bool = True
    # Say it reads a selection's translation first, not what was said: the
    # side used last, remembered app-wide (polyglotic-hq 495)
    say_it_translation_first: bool = False
    # languages whose "a better voice can be added" notice was ticked
    # "Don't show again" (polyglotic-hq 518)
    better_voice_quiet: tuple[str, ...] = ()
    # the tray said once that closing the main window keeps the app running
    # there (polyglotic-hq 135, finding 10): never again on this PC
    tray_note_shown: bool = False
    # Requested Video timings and the substitutions already explained on this PC.
    video_timing_explained: dict[str, str] = field(default_factory=dict)
    # the main window's size (width, height) as the learner left it, opened
    # at again - kept to the screen and its minimum (polyglotic-hq 586);
    # None: the usual first size
    main_window_size: tuple[int, int] | None = None
    # "Start Polyglotic with Windows?" was asked, after a good session -
    # once only, whatever the answer (polyglotic-hq 176)
    start_with_windows_asked: bool = False
    # on a Mac, "Move Polyglotic to Applications?" was asked, the app run
    # from macOS's temporary copy - once only, whatever the answer
    # (polyglotic-hq 433, decision 0205)
    applications_offered: bool = False
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
    # audio: what's listened to - everything the PC plays for a new learner,
    # from the first launch until they pick apps (polyglotic-hq 484, the
    # user, 2026-11-18; it was nothing until they picked, DECISIONS.md #25,
    # until then). Follows the default until changed (`FOLLOW_DEFAULT`), so
    # a learner from 0.1.7 or before keeps what they had
    whole_system: bool = True  # everything the PC plays, not chosen apps
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
    # dictation (polyglotic-hq 283, decision 0073): on for a new learner
    # (478; off until turned on before) - the mic is sent only while
    # `dictation_key` (a DictationKey as kept:
    # "right_ctrl", "ctrl+alt+d", 283's "insert"...; polyglotic-hq 289) is
    # held; heard as `dictation_language` - None: whatever language is
    # detected, each hold; else that one, forced (one of the speech model's,
    # DICTATION_LANGUAGES); English in Australian spelling if
    # `dictation_australian`
    dictation: bool = True
    dictation_key: str = str(DEFAULT_KEY)
    dictation_language: str | None = None
    dictation_australian: bool = False
    # each hotkey's key (polyglotic-hq 567, decision 0273), by its name
    # (`core.listening.hotkeys.Hotkey`: "lock", "live"...): a DictationKey as
    # kept ("ctrl+alt+l", "f9"), or "" for none; a hotkey not in it has its
    # default (Ctrl+Alt+L, P, H and J; the rest none)
    hotkeys: dict[str, str] = field(default_factory=dict)
    # Type what they said (669) keeps the former re-speaking binding. An
    # empty binding shares the dictation key using the tap-then-hold gesture.
    type_theirs: bool = True
    type_what: str = TypeWhat.ORIGINAL
    respeak_key: str = DEFAULT_RESPEAK_KEY
    # Developer-only opt-in to the former microphone behaviour on that binding.
    legacy_respeaking: bool = False
    # presets for use cases (polyglotic-hq 556, decision 0264; `use_presets`):
    # what each caption shows beside `show_original` - its translation, or
    # none in every window ("Original only", the presets' Show); Video's
    # subtitle place - every caption window at the bottom centre of its
    # screen, `subtitle_width` of it wide, its text `subtitle_size` of its
    # height, two lines tall, each window's own place kept for after; and my speech in
    # every window (True), in none (False) or as each window has it (None)
    show_translation: bool = True
    subtitles: bool = False
    subtitle_size: float = SUBTITLE_SIZE
    subtitle_width: float = SUBTITLE_WIDTH
    video_lines_shown: int = field(default_factory=lambda: VIDEO_LINES.value)
    my_speech: bool | None = None
    # the preset chosen: "everyday" (the base, a new install's),
    # "conversation", "video", "learning", "custom" (a setup from before
    # presets) or one of `own_presets` ("own1"...); each preset's own
    # changes by its key, as saved - only what differs from what it would
    # have; the settings above are the windows', which may hold changes the
    # chosen one hasn't saved (587, `use_presets.edits`); a
    # preset's name where the learner renamed it, an own one's always (on
    # this PC only); Custom and the learner's own presets' keys
    preset: str = "everyday"
    preset_values: dict[str, dict[str, object]] = field(default_factory=dict)
    preset_names: dict[str, str] = field(default_factory=dict)
    preset_parents: dict[str, str] = field(default_factory=dict)
    """Each saved preset's built-in parent key ("video", "learning"...), so
    Save as new keeps its parent's timing recommendation (638)."""
    own_presets: tuple[str, ...] = ()
    # the built-in presets' version these settings follow (`BUILT_INS`): a
    # file from before one changed a built-in's value moves the chosen one,
    # untouched, to its new value on reading (`use_presets.BUILT_IN_BEFORE`)
    built_ins: int = BUILT_INS
    # the settings changed on this PC since this record began (0.1.8), by
    # name - by the learner, or by the app for them: a switch that follows
    # the app's default (`FOLLOW_DEFAULT`) and isn't here takes the default
    # of the version running. Settings from before the record count as all
    # changed: they can't say which were (polyglotic-hq 478, decision 0220)
    changed: tuple[str, ...] = ()

    @property
    def caption_mode(self) -> CaptionMode:
        """The timing in use, shared by capture, playout and the windows."""
        mode = self.requested_caption_mode
        return offered(Use.WATCHING).nearest(mode) if self.video_timing else mode

    @property
    def video_timing(self) -> bool:
        """Video's supported timings also apply to presets that kept its layout."""
        return self.subtitles or self.preset == Use.WATCHING

    @property
    def requested_caption_mode(self) -> CaptionMode:
        """The learner's preference, kept even when Video uses its fallback."""
        if self.caption_mode_chosen is None:
            return default_caption_mode()
        return CaptionMode(self.caption_mode_chosen)

    @property
    def playout_rules(self) -> PlayoutRules:
        """How the paced modes' words are played out (Steady and Calm):
        the newest word held back and 1.75 s behind, or shown too and
        1.5 s behind; the words ahead; Calm's established words only."""
        eager = self.steady_newest_word
        return PlayoutRules(
            delay=EAGER_DELAY_SEC if eager else DELAY_SEC,
            hold_back=0 if eager else 1,
            ahead=Ahead(self.steady_words_ahead),
            established_only=self.caption_mode is CaptionMode.CALM,
            translation_after=self.translation_after if self.acquisition else 0.0,
        )

    @property
    def acquisition(self) -> bool:
        """Acquisition is the path, in a paced mode: what was said first."""
        return (
            self.caption_mode.paced
            and self.caption_path == ReadingPath.ACQUISITION.value
        )

    def second_language_of(self, target: str) -> str | None:
        """The language `target`'s lines already in it are translated into
        (its second language): the learner's choice, else English - but
        for English itself, or where none was chosen (polyglotic-hq 555)."""
        if target in self.preset_second_languages:
            second = self.preset_second_languages[target]
            return second if second and second != target else None
        chosen = self.second_languages.get(target)
        if chosen and chosen != target:
            return chosen
        if target in self.no_second_language:
            return None
        return default_second(target)

    def second_languages_for(self, targets: Iterable[str]) -> dict[str, str]:
        """Each of `targets`' second language (`second_language_of`) that
        has one, beside every one chosen."""
        return {
            target: second
            for target in dict.fromkeys(
                (*self.second_languages, *self.preset_second_languages, *targets)
            )
            if (second := self.second_language_of(target)) is not None
        }

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
        if self.caption_lab.get("load") is not True and not self.load_chosen:
            return None
        return load_rules_from(self.learning_load.get(code))

    @property
    def load_chosen(self) -> bool:
        """The quiet view shows the learning load's words in blue (477): the
        load is kept up, as with the Lab's mode on, without its colours."""
        return ChosenWords.LOAD.value in self.quiet_words

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
        # Kept readable in `AppSettings` for old files, but live translation
        # is no longer a choice and a false value must never be written.
        values.pop("translate_live")
        values["video_layout"] = 2  # Instant now wraps. Older "live" meant Scrolling.
        values["targets"] = list(self.targets)
        values["spelling_hints"] = list(self.spelling_hints)
        values["apps"] = list(self.apps)
        values["reading_lines"] = list(self.reading_lines)
        values["quiet_words"] = list(self.quiet_words)
        values["also_learning"] = list(self.also_learning)
        values["not_now_learning"] = list(self.not_now_learning)
        values["better_voice_quiet"] = list(self.better_voice_quiet)
        values["no_second_language"] = list(self.no_second_language)
        values["changed"] = list(self.changed)
        values["own_presets"] = list(self.own_presets)
        values["preset_values"] = {
            k: {name: list(v) if isinstance(v, tuple) else v for name, v in own.items()}
            for k, own in self.preset_values.items()
        }
        # what versions before 176 read: the mode followed, chosen or not
        values[OLD_CAPTION_TIMING] = self.requested_caption_mode.value
        return values

    @classmethod
    def from_stored(cls, stored: Mapping[str, object]) -> "AppSettings":
        """Settings from what was stored: anything missing or not valid
        takes its default. The one app an older version kept (`app_name`)
        becomes the only app picked."""
        as_filed = stored  # as the file has it, before `_migrated` fills it in
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
        # The retired switch remains a readable dataclass field for callers
        # opening old files, but its stored value has no effect.
        found.pop("translate_live", None)
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
        # every word linked by default again (555): what a version before
        # chose by itself for a language added is cleared, once
        if as_filed.get("language_links_chosen") is not True:
            found.pop("language_links_chosen", None)
            if "language_choices" in found:
                found["language_choices"] = _added_links_cleared(
                    found["language_choices"]
                )
        # a switch nobody changed follows today's default (478); settings
        # without the record (0.1.7 and before, or not valid) can't say
        # which were changed, so each valid one they hold counts as changed -
        # but no reading lines (`[]`), which every untouched file holds: they
        # were never on by default, so they follow it now (polyglotic-hq 511,
        # the user, 2026-11-18: "default pinyin/script assistance on"). A
        # learner who turned them on and off again before can't be told apart
        changed = found.get("changed")
        if changed is None:
            changed = tuple(
                f.name
                for f in fields(cls)
                if f.name in as_filed
                and f.name in found
                and not _at_old_default(f.name, as_filed)
                and not (f.name == "reading_lines" and not found[f.name])
            )
            found["changed"] = changed
        # Before these timing values followed defaults, every file contained
        # 3 seconds. A different valid value was a learner choice and stays;
        # an untouched 3 follows today's quicker defaults.
        for name in ("max_wait_for_text", "text_settles_after"):
            if (
                found.get("built_ins", 0) < 7
                and name in found
                and found[name] != 3.0
                and name not in changed
            ):
                changed = (*changed, name)
                found["changed"] = changed
        if (
            "type_theirs" not in found
            and type(as_filed.get("respeaking")) is bool
            and ("respeaking" in changed or "changed" not in as_filed)
        ):
            found["type_theirs"] = as_filed["respeaking"]
            changed = (*changed, "type_theirs")
            found["changed"] = changed
        # A recorded choice of the shared gesture survives the new default.
        # Also leave a custom binding on F8 alone when upgrading.
        if "respeak_key" not in changed and not found.get("respeak_key"):
            taken = {found.get("dictation_key"), *found.get("hotkeys", {}).values()}
            found["respeak_key"] = (
                "" if DEFAULT_RESPEAK_KEY in taken else DEFAULT_RESPEAK_KEY
            )
        for name in FOLLOW_DEFAULT:
            if name not in changed:
                found.pop(name, None)
        # what's captioned is one choice (484): apps picked by a learner who
        # never chose everything the PC plays - in a record begun while its
        # default was off, or a file without it - are captioned, not everything
        if found.get("apps") and "whole_system" not in changed:
            found["whole_system"] = False
        # a text size 0.1.9 or before kept on its steps, chosen: the nearest
        # of today's, and a choice (decision 0244; its Normal follows today's)
        old_size = _old_text_size(as_filed)
        if old_size is not None:
            found["interface_text_size"] = old_size
            if "interface_text_size" not in found["changed"]:
                found["changed"] = (*found["changed"], "interface_text_size")
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


SECOND_BY_DEFAULT = "en"
"""Every target's second language until the learner chooses, but
English's own (polyglotic-hq 555; the user, 2026-11-20: "Default secondary
language caption to english once their language has been selected"): a
learner reading Japanese captions sees what is already said in Japanese
translated into English, and one reading English sees no second line."""


def default_second(target: str) -> str | None:
    """`target`'s second language until the learner chooses."""
    return None if target == SECOND_BY_DEFAULT else SECOND_BY_DEFAULT


def second_languages_changes(
    value: AppSettings, chosen: Mapping[str, str | None]
) -> dict[str, object]:
    """The settings change that gives each target in `chosen` its second
    language there - None, "" or the target itself for none. The default
    isn't kept as a choice, so it follows the app's; none is kept only where
    the default has one (`no_second_language`). Other targets' stay."""
    seconds = dict(value.second_languages)
    none = [t for t in value.no_second_language if t not in chosen]
    for target, second in chosen.items():
        seconds.pop(target, None)
        default = default_second(target)
        if not second or second == target:
            if default is not None:
                none.append(target)
        elif second != default:
            seconds[target] = second
    return {"second_languages": seconds, "no_second_language": tuple(none)}


def learning_changes(languages: LearningLanguages) -> dict[str, object]:
    """The settings a change to the languages being learned makes. The
    main one applies from the next start."""
    return {
        "learning": languages.main,
        "also_learning": languages.also,
        "not_now_learning": languages.not_now,
    }


ADDED_LINKS = {"links": LinkChoice.PAST_KNOWN.value}
"""The choice 0.1.9 and 0.1.10-preview.1 wrote for each language added, by
themselves (polyglotic-hq 323: words linked only past what the learner
knows): every word is linked by default again since polyglotic-hq 555 (the
user, 2026-11-20: "Default arrow links to every word, even learning
section"), so a file from before has it cleared once
(`language_links_chosen`)."""


def _added_links_cleared(
    choices: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """`choices` without the links a version before 555 chose by itself for
    a language added (`ADDED_LINKS`): those languages link every word. A
    place to start from (`links_from`) or Off was the learner's, and stays;
    so does the rest of each language's choices."""
    cleared: dict[str, dict[str, object]] = {}
    for code, chosen in choices.items():
        kept = dict(chosen)
        if kept.get("links") == ADDED_LINKS["links"] and "links_from" not in kept:
            del kept["links"]
        if kept:
            cleared[code] = kept
    return cleared


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
    "better_voice_quiet",
    "no_second_language",
    "reading_lines",
    "quiet_words",
    "changed",
    "own_presets",
    "main_window_size",
)


def _old_text_size(as_filed: Mapping[str, object]) -> str | None:
    """The app's text size a file from 0.1.9 or before chose, as the
    nearest of today's steps (`OLD_TEXT_SIZES`): None for one written since
    (`interface_text_size`), Normal - which every file held, chosen or not
    - or not valid."""
    if "interface_text_size" in as_filed:
        return None
    old = as_filed.get(OLD_TEXT_SIZE)
    return OLD_TEXT_SIZES.get(old) if isinstance(old, str) else None


def _at_old_default(name: str, as_filed: Mapping[str, object]) -> bool:
    """A setting a file without the record of changes holds at a default
    that can't have been a choice: the live-update interval at 1.5 s, which
    every version before the record saved, chosen or not
    (`_mode_from_interval`) - so it follows today's (1.0 s, polyglotic-hq
    494); and the panel at 72 %, saved by every version before 584 - so
    it follows today's 88 %."""
    if name == "respeak_key":
        return as_filed.get(name) == ""
    if name == "opacity":
        return as_filed.get(name) == OLD_OPACITY
    if name in ("max_wait_for_text", "text_settles_after"):
        return as_filed.get(name) == 3.0
    return name == "live_update_interval" and as_filed.get(name) == OLD_LIVE_DEFAULT


def _contrast_older(lab: object, look: Mapping[str, object]) -> object:
    """An old Lab's paint-alpha Older captions choice in contrast terms.

    A missing value was untouched and deliberately remains missing, so it
    follows the new 90% default.  A present value was a learner choice; keep
    the original row looking as close as the slider's supported range allows.
    """
    if not isinstance(lab, dict) or "older" not in lab:
        return lab
    old = lab.get("older")
    colour = look.get("original_color", ORIGINAL_COLOR)
    panel = look.get("background_color", BACKGROUND_COLOR)
    if not (
        isinstance(old, int | float)
        and not isinstance(old, bool)
        and 0.0 <= old <= 1.0
        and isinstance(colour, str)
        and isinstance(panel, str)
    ):
        return lab
    try:
        full = _wcag_contrast(colour, panel)
        retained = (
            _wcag_contrast(_mixed_colour(panel, colour, float(old)), panel) / full
        )
    except (ValueError, IndexError):
        return lab
    migrated = dict(lab)
    migrated["older"] = round(min(1.0, max(0.5, retained)), 2)
    return migrated


def _mixed_colour(under: str, over: str, alpha: float) -> str:
    """`over` painted at `alpha` on `under`, as a six-digit hex colour."""
    below = tuple(int(under.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    above = tuple(int(over.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    channels = (
        round(a * alpha + b * (1.0 - alpha)) for b, a in zip(below, above, strict=True)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _wcag_contrast(first: str, second: str) -> float:
    """WCAG relative contrast of two six-digit hex colours."""

    def luminance(colour: str) -> float:
        channels = []
        for index in (0, 2, 4):
            value = int(colour.lstrip("#")[index : index + 2], 16) / 255
            channels.append(
                value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            )
        red, green, blue = channels
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _migrate_caption_labs(found: dict[str, object]) -> None:
    """Apply caption Lab version 2 to the flat look and preset-carried looks."""
    version = found.get("caption_lab_version", 1)
    if isinstance(version, int) and not isinstance(version, bool) and version >= 2:
        return
    found["caption_lab"] = _contrast_older(found.get("caption_lab", {}), found)
    presets = found.get("preset_values")
    if isinstance(presets, dict):
        migrated: dict[object, object] = {}
        for key, values in presets.items():
            if isinstance(values, dict) and "caption_lab" in values:
                own = dict(values)
                own["caption_lab"] = _contrast_older(
                    own["caption_lab"], {**found, **values}
                )
                migrated[key] = own
            else:
                migrated[key] = values
        found["preset_values"] = migrated
    found["caption_lab_version"] = CAPTION_LAB_VERSION


OLD_LINK_WORDS = "link_words_coloured"
"""0.1.7's previews' one switch for linked words in their link's colour,
in what was said and the translation alike (395): two since 431."""


def _migrated(stored: Mapping[str, object]) -> Mapping[str, object]:
    """What an older version stored, in today's settings: one app picked
    (`app_name`, before several could be) is `apps` with that app alone;
    overlays moved before there were position presets are where they
    were put ("custom"); and the caption mode chosen, from versions that
    kept the mode followed (`_caption_mode_chosen_from`) - Quick preview,
    retired, read as Steady."""
    found = dict(stored)
    _migrate_caption_labs(found)
    old = found.get("app_name")
    if "apps" not in found and isinstance(old, str):
        found["apps"] = [old]
    if "overlay_position" not in found and found.get("overlay_geometry"):
        found["overlay_position"] = "custom"
    if "caption_mode_chosen" not in found:
        found["caption_mode_chosen"] = _caption_mode_chosen_from(found)
    if found["caption_mode_chosen"] == CaptionMode.PREVIEW.value:
        # Quick preview is retired: who chose it is on Steady (decision 0246)
        found["caption_mode_chosen"] = CaptionMode.STEADY.value
    # The old bottom-centred subtitle renderer was also kept by presets
    # copied from Video. Whole captions remains valid in the other layouts.
    parents = found.get("preset_parents")

    def was_video(key: object, values: Mapping[str, object]) -> bool:
        subtitles = values.get("subtitles")
        return (
            key == "video"
            or subtitles is True
            or (
                subtitles is None
                and isinstance(key, str)
                and isinstance(parents, dict)
                and parents.get(key) == "video"
            )
        )

    def video_mode(key: object, values: Mapping[str, object]) -> Mapping[str, object]:
        mode = values.get("caption_mode_chosen")
        if mode == "delayed_translation":
            return {**values, "caption_mode_chosen": CaptionMode.INSTANT.value}
        if was_video(key, values):
            if mode == CaptionMode.WHOLE.value:
                return {**values, "caption_mode_chosen": CaptionMode.INSTANT.value}
            if mode == CaptionMode.INSTANT.value and found.get("video_layout") != 2:
                return {**values, "caption_mode_chosen": CaptionMode.SCROLLING.value}
        return values

    found = dict(video_mode(found.get("preset"), found))
    presets = found.get("preset_values")
    if isinstance(presets, dict):
        found["preset_values"] = {
            key: video_mode(key, values) if isinstance(values, dict) else values
            for key, values in presets.items()
        }
    old_link_words = found.get(OLD_LINK_WORDS)
    if isinstance(old_link_words, bool):  # 0.1.7's previews: one for both (431)
        # off stays off, now that both are on by default (446)
        found.setdefault("said_in_link_colours", old_link_words)
        found.setdefault("translation_in_link_colours", old_link_words)
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
    if old in (CaptionMode.PREVIEW.value, CaptionMode.INSTANT.value):
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
        return CaptionMode.WHOLE.value
    if (
        isinstance(interval, int | float)
        and not isinstance(interval, bool)
        and interval != OLD_LIVE_DEFAULT
        and LIVE_INTERVALS[0] <= interval <= LIVE_INTERVALS[1]
    ):
        return CaptionMode.INSTANT.value
    return None


def _valid(name: str, value: object, default: object) -> object:
    check = _CHECKS.get(name)
    if check is not None:
        return value if check(value) else _INVALID
    if isinstance(default, bool):
        return value if isinstance(value, bool) else _INVALID
    return _INVALID


def _whole_in(value: object, low: int, high: int) -> bool:
    """A whole number from `low` to `high` (not True or False)."""
    return (
        isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    )


def _window_size(value: object) -> bool:
    """A window's (width, height): two whole numbers, as no screen is
    larger than 16384 px."""
    return (
        isinstance(value, list | tuple)
        and len(value) == 2
        and all(_whole_in(n, 1, 16384) for n in value)
    )


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


def _hotkeys(value: object) -> bool:
    """Hotkeys' keys by their names (polyglotic-hq 567): each a hotkey's,
    to a key one can be or "" (none). One read wrong makes them all their
    defaults - a file edited by hand."""
    if not isinstance(value, dict):
        return False
    names = {h.value for h in Hotkey}
    for name, text in value.items():
        if name not in names or not isinstance(text, str):
            return False
        key = DictationKey.parse(text) if text else None
        if text and (key is None or hotkey_refusal(key) is not None):
            return False
    return True


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


def _preset_languages(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str)
        and isinstance(choices, dict)
        and choices.keys() <= {"spoken_language", "translate_into"}
        and all(isinstance(code, str) for code in choices.values())
        for key, choices in value.items()
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
    "better_voice_quiet": lambda v: _codes(v),
    "interface_language": lambda v: (
        v is None or (isinstance(v, str) and bool(_LANGUAGE_CODE.fullmatch(v)))
    ),
    "first_run_step": lambda v: v is None or v in FIRST_RUN_STEPS,
    "targets": _languages,
    "second_languages": _language_map,
    "no_second_language": _languages,
    "spoken_language": _text_or_none,
    "mandarin_script": lambda v: v is None or v in MANDARIN_SCRIPTS,
    "speaker_device": _text_or_none,
    "mic_device": _text_or_none,
    "dictation_key": _dictation_key,
    "hotkeys": _hotkeys,
    "preset_languages": _preset_languages,
    "preset_second_languages": _language_map,
    "respeak_key": lambda v: v == "" or _dictation_key(v),
    "type_what": lambda v: v in (TypeWhat.ORIGINAL, TypeWhat.TRANSLATION),
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
    "caption_lab_version": lambda v: (
        isinstance(v, int) and not isinstance(v, bool) and v >= 1
    ),
    "reading_lines": lambda v: (
        isinstance(v, list | tuple) and all(x in READING_LANGUAGES for x in v)
    ),
    "reading_size": lambda v: v in {s.value for s in ReadingSize},
    "quiet_words": lambda v: (
        isinstance(v, list | tuple) and all(isinstance(x, str) for x in v)
    ),  # what this app doesn't know is left out where it's read (`chosen_from`)
    "marks_in": lambda v: v in MARKS_IN,
    "caption_contrast": lambda v: _whole_in(v, -100, 100),
    "caption_vibrance": lambda v: _whole_in(v, -100, 100),
    "caption_edge": lambda v: v in ("none", "shadow", "outline"),
    "caption_weight": lambda v: (
        v in (300, 400, 500, 600, 700) and _whole_in(v, 300, 700)
    ),
    "curriculum_size": lambda v: (
        isinstance(v, int)
        and not isinstance(v, bool)
        and CURRICULUM_MIN <= v <= CURRICULUM_MAX
    ),
    "reading_colour": lambda v: v in {c.value for c in ReadingColour},
    "reading_system": lambda v: v in {s.value for s in ReadingSystem},
    "reading_custom_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "language_choices": lambda v: _choices_map(v),
    "learning_load": lambda v: _choices_map(v),
    "known_reset": lambda v: _choices_map(v),
    "caption_mode_chosen": lambda v: v is None or v in {m.value for m in CaptionMode},
    "steady_words_ahead": lambda v: v in {a.value for a in Ahead},
    "caption_path": lambda v: v in {p.value for p in ReadingPath},
    "translation_after": _number_in(*TRANSLATION_AFTER_RANGE),
    "live_update_interval": _number_in(*LIVE_INTERVALS),
    "max_wait_for_text": _number_in(*MAX_WAIT_RANGE),
    "text_settles_after": _number_in(*SETTLE_RANGE),
    "overlay_geometry": _geometry,
    "main_window_size": lambda v: v is None or _window_size(v),
    "caption_font": lambda v: v is None or (isinstance(v, str) and 0 < len(v) <= 100),
    "caption_faces": lambda v: (
        _text_map(v, lambda family: len(family) <= 100)
        and isinstance(v, dict)
        and all(0 < len(code) <= 10 for code in v)
    ),
    "original_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "translation_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "background_color": lambda v: isinstance(v, str) and bool(_COLOR.fullmatch(v)),
    "overlay_position": lambda v: v in POSITIONS,
    "window_theme": lambda v: v in WINDOW_THEMES,
    "theme": lambda v: v in THEMES,
    "interface_text_size": lambda v: v in APP_TEXT_SIZES,
    "transcript_length": lambda v: v in TRANSCRIPT_LENGTHS,
    "overlay_width": _number_in(*WIDTH_SHARES, optional=True),
    "apps": _languages,  # a list of strings
    "source_names": lambda v: _text_map(
        v, lambda name: 0 < len(name) <= MAX_SOURCE_NAME
    ),
    "source_colors": lambda v: _text_map(v, lambda c: bool(_COLOR.fullmatch(c))),
    "spelling_hints": _languages,  # a list of strings
    "video_timing_explained": lambda v: _text_map(v, lambda mode: mode in CaptionMode),
    "app_capture_fell_back": lambda v: _text_map(v, lambda text: len(text) <= 100),
    # read whole by core.listening.maintenance.from_stored, which refuses the rest
    "maintenance": lambda v: isinstance(v, dict) and len(v) <= 3,
    "changed": _languages,  # a list of settings' names
    # presets (556): each value read leniently where it's used (`use_presets`)
    "subtitle_size": _number_in(*SUBTITLE_SIZES),
    "subtitle_width": _number_in(*SUBTITLE_WIDTHS),
    "video_lines_shown": lambda v: type(v) is int and v in VIDEO_LINE_CHOICES,
    "my_speech": lambda v: v is None or isinstance(v, bool),
    "preset": lambda v: isinstance(v, str) and 0 < len(v) <= 20,
    "built_ins": lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 1,
    "preset_values": lambda v: (
        isinstance(v, dict)
        and all(isinstance(k, str) and isinstance(own, dict) for k, own in v.items())
    ),
    "preset_names": lambda v: _text_map(v, lambda name: len(name) <= 100),
    "preset_parents": lambda v: _text_map(v, lambda parent: 0 < len(parent) <= 20),
    "own_presets": _languages,  # their keys: "own1"...
}


def as_valid(name: str, value: object, default: object) -> tuple[object] | None:
    """`value` as setting `name` keeps it, if it's valid for it - a list
    read as a tuple where the setting is one - in a one-item tuple; None
    if it isn't (a preset's stored values, polyglotic-hq 556)."""
    found = _valid(name, value, default)
    if found is _INVALID:
        return None
    if name in _TUPLES and isinstance(found, list | tuple):
        return (tuple(found),)
    return (found,)


def with_changed(before: AppSettings, after: AppSettings) -> AppSettings:
    """`after`, with every setting that differs from `before` named in its
    record of changes (`AppSettings.changed`; 478)."""
    moved = [
        f.name
        for f in fields(AppSettings)
        if f.name != "changed"
        and f.name not in after.changed
        and getattr(before, f.name) != getattr(after, f.name)
    ]
    return replace(after, changed=(*after.changed, *moved)) if moved else after


class Settings(QObject):
    """The current settings: every change saved and announced."""

    changed = Signal()

    def __init__(
        self, store: SettingsStore | None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._store = store
        stored = store.load() if store else {}
        # the presets read beside (polyglotic-hq 556): Custom chosen in a file
        # from before them, the chosen one's changes from the settings
        from polyglotic_desktop.ui import use_presets  # it builds on this module

        read = AppSettings.from_stored(stored)
        self.value = use_presets.from_flat(
            use_presets.follow_reading_defaults(read, stored),
            before_presets="preset" not in stored,
            built_ins=read.built_ins if "built_ins" in stored else 1,
        )
        # keys this version doesn't know (a newer version's, after a rollback)
        # are kept on every save, so going back and forth loses nothing
        # (polyglotic-hq project 107, 104's G11)
        known = {f.name for f in fields(AppSettings)}
        self._unknown = {k: v for k, v in stored.items() if k not in known}

    def update(self, **changes: object) -> None:
        new = replace(self.value, **changes)  # type: ignore[arg-type]
        if new == self.value:
            return
        self.change(with_changed(self.value, new))

    def update_from_bar(self, **changes: object) -> None:
        """Apply and save the fields picked on the bar in one settings write."""
        from polyglotic_desktop.ui import use_presets

        new = with_changed(self.value, replace(self.value, **changes))  # type: ignore[arg-type]
        self.change(use_presets.saved_into(new, changes))

    def change(self, new: AppSettings) -> None:
        """The settings become `new`, saved in the file and announced. A
        change to a preset setting is the windows' at once and leaves the
        chosen preset edited until the learner saves it (polyglotic-hq 587,
        decision 0283; `use_presets`). `update` for a few settings; a
        preset's own steps (`use_presets.chosen`, `saved_into`...) hand the
        whole value."""
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
