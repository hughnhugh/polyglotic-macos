"""The three shared panels' views - Languages, Timing and Look - as plain
Python, no Qt (polyglotic-hq project 109's structure, sections 1.1 and 4).

Each setting has one owner, and its control is drawn once: a panel is one
widget class bound to one view, and every panel showing a value binds to
the same view - Settings > Captions, every transcript's rail - so a
change made in one shows in all of them at once.

A view holds one value and two directions:
- **the learner's change** (a command: `set_spoken`, `set_mode`, ...): the
  value changes, every panel bound to it is told (`subscribe`), and the
  view hands the new value on (`on_change`) - `main` saves it with the
  settings, and the caption windows follow;
- **a change made elsewhere** (a hotkey, another version's sync, a reset):
  `follow(value)` - the panels are told; nothing is handed on.

The views:
- `LanguagesView` - the session's languages (`SessionLanguages`): what's
  learned, the spoken language, a second language for each language in
  use, live translation, names and slang. "Translate into" is not here:
  each window has its own (DECISIONS.md #53);
- `WindowLanguageView` - one window's language and "Show my speech here"
  (`WindowLanguage`), shown under "This window" in its transcript's rail;
- `TimingView` - the caption timing, the live-update interval and the
  longest wait for text;
- `LookView` - how every caption window looks (`CaptionLook`, today's
  Captions page without the preview, the text size and the width).

Holds no caption text.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from polyglotic_desktop.core.learning.curriculum import ChosenWords
from polyglotic_desktop.core.lexicon.pack_download import PackProgress
from polyglotic_desktop.core.listening.display import (
    LinkDetail,
    LinkGap,
    LinkLine,
    ReadingColour,
    ReadingSize,
    ReadingSystem,
    WordLinks,
)
from polyglotic_desktop.core.listening.playout import (
    TRANSLATION_AFTER_SEC,
    Ahead,
    ReadingPath,
)
from polyglotic_desktop.core.listening.settling import SETTLE_AFTER_SEC
from polyglotic_desktop.core.listening.timing import (
    LIVE_UPDATE_INTERVAL_SEC,
    MAX_WAIT_FOR_TEXT_SEC,
    CaptionMode,
)
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import (
    ORIGINAL_ONLY,
    CaptionLook,
    MarksIn,
    TextEdge,
)
from polyglotic_desktop.ui_next.views.lab import CaptionLab
from polyglotic_desktop.ui_next.views.presets import (
    BY_KEY,
    hex_colour,
    preset_of,
    with_look,
)
from polyglotic_desktop.ui_next.views.tone import (
    CONTRAST_RANGE,
    THICKNESSES,
    VIBRANCE_RANGE,
)

MAX_HINTS = 100
"""Names and slang at most (protocol.md's limit on spelling hints)."""
LIVE_CHOICES = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
"""The live-update intervals offered, in seconds (today's). Not past 6 s:
the longest wait for text (2 to 6 s) comes first, so a longer one would
never be followed (polyglotic-hq 295)."""
WAIT_CHOICES = (2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
TRANSLATION_AFTER_CHOICES = (1.0, 2.0, 3.0, 5.0)
"""Acquisition's seconds between a clause and its translation, offered."""
"""The longest waits for text offered, in seconds: MAX_WAIT_RANGE, with the
user's "2.5-3 seconds" (polyglotic-hq 270's feedback) among them."""
SETTLE_CHOICES = (0.0, 1.0, 2.0, 3.0)
"""How long shown text may still change, as offered, in seconds: the user's
"0s - 3seconds" (polyglotic-hq 309), each one measured on the recordings
(decision 0099). 0: a word stays as first shown (but a live caption's
last word, which may be half said)."""
FADE_CHOICES: tuple[float | None, ...] = (None, 5.0, 8.0, 15.0, 30.0)
"""Fade after quiet, in seconds; None: never (today's)."""
ORIGINAL_CHOICES = ("#ffffff", "#e6e6e6", "#cfe8ff", "#d8ffd0", "#fff4c2")
TRANSLATION_CHOICES = ("#ffd76e", "#ffb347", "#7fe3ff", "#a5f28a", "#ff9ecf")
BACKGROUND_CHOICES = ("#0a0c10", "#000000", "#1b2a41", "#1f2d22", "#2d1f2f")
"""The colours that read on a caption window, the defaults first (today's)."""
READING_CHOICES = ("#9ad0ff", "#ffffff", "#ffd76e", "#a5f28a", "#ff9ecf")
"""Pinyin's own colours that read on a caption window (395)."""
COLOUR_CHOICES = {
    "original": ORIGINAL_CHOICES,
    "translation": TRANSLATION_CHOICES,
    "background": BACKGROUND_CHOICES,
    "reading": READING_CHOICES,
}


class Shared[T]:
    """One value the panels show, and who to tell when it changes."""

    def __init__(self, value: T, on_change: Callable[[T], None] | None = None) -> None:
        self.value = value
        self.on_change = on_change
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """`listener` is called after every change; call what this returns
        to stop (a panel does when it goes)."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def follow(self, value: T) -> None:
        """The value as it is now, changed elsewhere: shown, not handed on."""
        if value != self.value:
            self.value = value
            self._announce()

    def change(self, value: T) -> None:
        """The learner's change: shown in every panel, then handed on."""
        if value == self.value:
            return
        self.value = value
        self._announce()
        if self.on_change is not None:
            self.on_change(value)

    def _announce(self) -> None:
        for listener in list(self._listeners):
            listener()


# -- Languages -------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionLanguages:
    """The session's languages. `spoken`: None to detect. `second_languages`: for a language in use, the language its
    lines already in it are translated into. `in_use`: the windows'
    languages, a second-language row each. `live_updates`: the caption
    timing is Live updates, the only one live translation applies to."""

    spoken: str | None = None
    second_languages: Mapping[str, str] = field(default_factory=dict)
    translate_live: bool = True
    spelling_hints: tuple[str, ...] = ()
    in_use: tuple[str, ...] = ()
    live_updates: bool = False
    recent_spoken: tuple[str, ...] = ()
    """The spoken languages named last, newest first (the caption windows'):
    first in the list (polyglotic-hq 317)."""
    mandarin_script: str | None = None
    """Mandarin's captions in "simplified" or "traditional" characters, as
    chosen; None: as this PC reads Chinese (`traditional_here`; 375)."""
    traditional_here: bool = False
    """This PC reads Chinese in Traditional (Taiwan's or Hong Kong's)."""
    lyrics: bool = False
    """The Lyrics switch: music players heard on Detect in songs mode
    (polyglotic-hq 595, decision 0287)."""

    @property
    def traditional(self) -> bool:
        """Mandarin's captions are shown in Traditional characters."""
        if self.mandarin_script is None:
            return self.traditional_here
        return self.mandarin_script == "traditional"


HINT_SEPARATORS = re.compile("[,，、;；]")
"""What separates names and slang: commas, and the Chinese comma, list
mark and semicolons - "yyds、绝绝子" is two (249)."""


def hints_from(text: str) -> tuple[str, ...]:
    """Names and slang as typed - separated by commas - each once, in
    order, at most MAX_HINTS."""
    parts = (h.strip() for h in HINT_SEPARATORS.split(text))
    found = dict.fromkeys(h for h in parts if h)
    return tuple(found)[:MAX_HINTS]


def captioned(languages: SessionLanguages) -> tuple[str, ...]:
    """The languages captions are in, each once, for Look's face rows
    (polyglotic-hq 482): what's spoken - as chosen, or heard lately - then
    each window's language and the second ones. Mandarin shown in
    Traditional characters is "zh-hant", the faces it's drawn in."""
    found = (
        languages.spoken,
        *languages.recent_spoken,
        *languages.in_use,
        *languages.second_languages.values(),
    )
    traditional = languages.traditional
    shown = (
        "zh-hant" if code == "zh" and traditional else code
        for code in found
        if code and code != ORIGINAL_ONLY
    )
    return tuple(dict.fromkeys(shown))


class LanguagesView(Shared[SessionLanguages]):
    def set_spoken(self, code: str | None) -> None:
        self.change(replace(self.value, spoken=code or None))

    def set_second(self, target: str, second: str | None) -> None:
        """Lines already in `target` are translated into `second` (None:
        not translated)."""
        seconds = dict(self.value.second_languages)
        if second and second != target:
            seconds[target] = second
        else:
            seconds.pop(target, None)
        self.change(replace(self.value, second_languages=seconds))

    def set_translate_live(self, on: bool) -> None:
        self.change(replace(self.value, translate_live=on))

    def set_hints(self, text: str) -> None:
        self.change(replace(self.value, spelling_hints=hints_from(text)))

    def set_traditional(self, on: bool) -> None:
        script = "traditional" if on else "simplified"
        self.change(replace(self.value, mandarin_script=script))

    def set_lyrics(self, on: bool) -> None:
        self.change(replace(self.value, lyrics=on))


@dataclass(frozen=True, slots=True)
class WindowLanguage:
    """One caption window's language - or ORIGINAL_ONLY - and whether it
    shows my speech; `label` is its app's name as the learner sees it."""

    label: str
    translate_into: str = "en"
    show_mic: bool = False

    @property
    def original_only(self) -> bool:
        return self.translate_into == ORIGINAL_ONLY


class WindowLanguageView(Shared[WindowLanguage]):
    def set_translate_into(self, code: str) -> None:
        """A language's code, or ORIGINAL_ONLY."""
        self.change(replace(self.value, translate_into=code))

    def set_show_mic(self, on: bool) -> None:
        self.change(replace(self.value, show_mic=on))


# -- Timing ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Timing:
    """The caption timing, how often Live updates update, the longest
    wait for text in every mode (seconds; core.listening.timing's
    `max_wait`, polyglotic-hq 277), and how long shown text may still
    change (`settle_after`, seconds; core.listening.settling, 309)."""

    mode: CaptionMode = CaptionMode.WHOLE
    live_interval: float = LIVE_UPDATE_INTERVAL_SEC
    max_wait: float = MAX_WAIT_FOR_TEXT_SEC
    settle_after: float = SETTLE_AFTER_SEC
    newest_word: bool = False
    """Steady's newest word shown too, a little sooner (526)."""
    words_ahead: Ahead = Ahead.WAITING
    """Steady's waiting words drawn faint ahead (karaoke): on by default
    (polyglotic-hq 554)."""
    two_zones: bool = True
    """Steady's live lines below and the settled transcript above (526)."""
    path: ReadingPath = ReadingPath.BOTH
    """What is read first in a paced mode (decision 0253)."""
    translation_after: float = TRANSLATION_AFTER_SEC
    """Acquisition's seconds between a clause and its translation."""
    cards: bool = True
    """Steady's card stack is on (decision 0260): the two zones' switch
    then changes nothing, and isn't offered."""

    video: bool = False
    """The Video timing panel offers live or finished translations."""

    @property
    def live_every(self) -> float:
        """How often Live updates' text updates, as followed: its interval,
        or the longest wait for text when that's shorter - speech never
        runs longer than the longest wait without a live update, whatever
        the interval (core.listening.timing; polyglotic-hq 295)."""
        return min(self.live_interval, self.max_wait)


def interval_choices(current: float) -> list[float]:
    """The intervals to offer: LIVE_CHOICES, and the current one in order
    if it isn't among them (one set by hand: it showed as "Off" once -
    polyglotic-hq projects 043 and 061)."""
    return sorted({*LIVE_CHOICES, current})


def wait_choices(current: float) -> list[float]:
    """The longest waits for text to offer: WAIT_CHOICES, and the current
    one in order if it isn't among them (one set by hand)."""
    return sorted({*WAIT_CHOICES, current})


def settle_choices(current: float) -> list[float]:
    """The times to settle to offer: SETTLE_CHOICES, and the current one
    in order if it isn't among them (one set by hand)."""
    return sorted({*SETTLE_CHOICES, current})


class TimingView(Shared[Timing]):
    def set_mode(self, mode: CaptionMode) -> None:
        self.change(replace(self.value, mode=mode))

    def set_live_interval(self, seconds: float) -> None:
        self.change(replace(self.value, live_interval=seconds))

    def set_max_wait(self, seconds: float) -> None:
        self.change(replace(self.value, max_wait=seconds))

    def set_settle_after(self, seconds: float) -> None:
        self.change(replace(self.value, settle_after=seconds))

    def set_newest_word(self, on: bool) -> None:
        self.change(replace(self.value, newest_word=on))

    def set_words_ahead(self, ahead: Ahead) -> None:
        self.change(replace(self.value, words_ahead=ahead))

    def set_two_zones(self, on: bool) -> None:
        self.change(replace(self.value, two_zones=on))

    def set_cards(self, on: bool) -> None:
        self.change(replace(self.value, cards=on))

    def set_path(self, path: ReadingPath) -> None:
        self.change(replace(self.value, path=path))

    def set_translation_after(self, seconds: float) -> None:
        self.change(replace(self.value, translation_after=seconds))


# -- Look ------------------------------------------------------------------------------


def look_defaults(now: CaptionLook, first: CaptionLook | None = None) -> CaptionLook:
    """The look as Polyglotic first had it - `first`, the app's defaults
    (`main`'s; 478: word links on), or the plain look - but Quick
    preview's line is the timing's, so it stays as it is, and the Lab has
    its own reset; what happens to a hidden window isn't the look
    (polyglotic-hq 335), nor which words are learned in the quiet view
    (477)."""
    return replace(
        first if first is not None else CaptionLook(),
        preview=now.preview,
        lab=now.lab,
        pause_hidden_after=now.pause_hidden_after,
        show_on_speech=now.show_on_speech,
        quiet_words=now.quiet_words,
        curriculum_size=now.curriculum_size,
    )


LINKS_WHEN_ON = WordLinks.ARROWS
"""What a caption window's word links button turns on when no other way
of showing them was chosen (249, F9): the links with their lines (the
user, 2026-11-17, polyglotic-hq 446: "default switch on with arrows")."""


def learning_view(
    look: CaptionLook,
    on: bool,
    links: WordLinks,
    readings: tuple[str, ...] = (),
    before: CaptionLook | None = None,
) -> CaptionLook:
    """The look with the whole learning view on, in one click - a caption
    window's word links button (polyglotic-hq 446; the user, 2026-11-17:
    "essentially this should be the one click default"): word links shown
    as `links`, linked words in their link's colour in what was said and
    in the translation, pinyin in its word link's colour (a colour the
    learner picked stays theirs, and Grey - the default, which takes the
    link's colour where one joins a word: 532), and the reading lines of the window's
    languages (`readings`: "zh" for a Chinese window) - so a word, its
    pinyin and its translation all match.

    Off again: word links off, and the rest back to what it was in
    `before` (the look when the one click turned them on), as the
    filled lines button does (372); not known (turned on in Settings, or
    before a restart), only word links go off."""
    if on:
        colour = look.reading_colour
        return replace(
            look,
            word_links=links,
            said_in_link_colours=True,
            translation_in_link_colours=True,
            reading_colour=colour
            if colour in (ReadingColour.CUSTOM, ReadingColour.GREY)
            else ReadingColour.LINK,
            reading_lines=tuple(sorted({*look.reading_lines, *readings})),
        )
    if before is None:
        return replace(look, word_links=WordLinks.OFF)
    return replace(
        look,
        word_links=WordLinks.OFF,
        said_in_link_colours=before.said_in_link_colours,
        translation_in_link_colours=before.translation_in_link_colours,
        reading_colour=before.reading_colour,
        reading_lines=before.reading_lines,
    )


@dataclass(frozen=True)
class FaceDownloads:
    """The downloaded caption faces as Look's Fonts card shows them
    (polyglotic-hq 482): what each one offered comes to for this app, by
    its pack's name (none until the list is read), the packs on this PC,
    and each download under way or stopped."""

    sizes: Mapping[str, int] = field(default_factory=dict)
    here: frozenset[str] = frozenset()
    progress: Mapping[str, PackProgress] = field(default_factory=dict)


class DownloadsView(Shared[FaceDownloads]):
    """The downloaded faces, and the way to ask for one (`main`'s)."""

    def __init__(
        self,
        value: FaceDownloads | None = None,
        want: Callable[[str, bool], None] = lambda _pack, _anyway: None,
        refresh: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(value or FaceDownloads())
        self.want = want
        """A face's pack downloaded (`anyway`: on a metered connection too)."""
        self.refresh = refresh
        """The list read again, for the sizes (the card shown)."""


def quiet_view(
    look: CaptionLook,
    on: bool,
    readings: tuple[str, ...] = (),
    before: CaptionLook | None = None,
    links: WordLinks = LINKS_WHEN_ON,
) -> CaptionLook:
    """The look with the quiet view on (polyglotic-hq 477) - word links
    off, and the reading lines of the window clicked on (`readings`: "zh"
    for a Chinese window: a reading over every word) - or off again, the
    word links, their colours and the reading lines back as they were in
    `before` (the look when it was turned on), so links show as the
    learner had them (polyglotic-hq 555; 523 found them left off). Not
    known (turned on before a restart): word links shown as `links` -
    on every word by default - and the rest as it is."""
    if on:
        return replace(
            look,
            quiet=True,
            word_links=WordLinks.OFF,
            reading_lines=tuple(sorted({*look.reading_lines, *readings})),
        )
    if before is None:
        return replace(look, quiet=False, word_links=links)
    return replace(
        look,
        quiet=False,
        word_links=before.word_links,
        said_in_link_colours=before.said_in_link_colours,
        translation_in_link_colours=before.translation_in_link_colours,
        reading_colour=before.reading_colour,
        reading_lines=before.reading_lines,
    )


class LookView(Shared[CaptionLook]):
    """How every caption window looks."""

    def __init__(
        self,
        value: CaptionLook,
        on_change: Callable[[CaptionLook], None] | None = None,
        first: CaptionLook | None = None,
    ) -> None:
        super().__init__(value, on_change)
        self.first = first
        """The look as Polyglotic first has it - the app's defaults, which
        Reset to defaults goes back to (`look_defaults`); None: the plain
        look."""
        self.links_when_on = LINKS_WHEN_ON
        """How word links show when a caption window's button turns them on:
        the way last chosen in Look, while the app runs."""
        self.unfilled: CaptionLab | None = None
        """The Lab as it was when a caption window's filled lines button
        turned them on (372), while the app runs: off puts it back."""
        self.unlined: CaptionLab | None = None
        """...and when its parts lined up button turned them on."""
        self.unlinked: CaptionLook | None = None
        """The look as it was when a caption window's word links button
        turned the learning view on (446), while the app runs: off puts it
        back (`learning_view`)."""
        self.unquieted: CaptionLook | None = None
        """The look as it was when a caption window's quiet button turned
        the quiet view on (477), while the app runs: off puts its reading
        lines back."""
        self.started_from: str | None = None
        """The colour preset the look's colours last were (`presets`), while
        the app runs: custom colours are "Custom, from" it."""
        self._remember(saved=True)

    def _remember(self, saved: bool = False) -> None:
        links = self.value.word_links
        # a saved Underline is what the button itself turned on before 446,
        # not a way chosen: the button's next click shows the lines (446)
        if links is not WordLinks.OFF and not (saved and links is WordLinks.COLOURS):
            self.links_when_on = links
        preset = preset_of(self.value)
        if preset is not None:
            self.started_from = preset.key

    def follow(self, value: CaptionLook) -> None:
        super().follow(value)
        self._remember()

    def change(self, value: CaptionLook) -> None:
        super().change(value)
        self._remember()

    def set_preset(self, key: str) -> None:
        """A colour preset (`presets.PRESETS`): its three colours and how
        solid its panel is - the slider still moves after."""
        preset = BY_KEY[key]
        self.change(
            replace(
                self.value,
                original=preset.original,
                translation=preset.translation,
                background=preset.background,
                opacity=preset.opacity,
            )
        )

    def set_recommended(self, key: str) -> None:
        """A recommended look (`presets.LOOKS`, polyglotic-hq 532): its
        colours, caption text, readings and Chinese faces at once - each
        changed as freely after."""
        self.change(with_look(self.value, key))

    def set_opacity(self, opacity: float) -> None:
        self.change(replace(self.value, opacity=round(min(1.0, max(0.0, opacity)), 2)))

    def set_contrast(self, value: int) -> None:
        """How strongly captions stand out (`views.tone`; 481): soft to crisp."""
        low, high = CONTRAST_RANGE
        self.change(replace(self.value, contrast=max(low, min(high, value))))

    def set_vibrance(self, value: int) -> None:
        """How vivid captions' colours are (481): muted to vivid."""
        low, high = VIBRANCE_RANGE
        self.change(replace(self.value, vibrance=max(low, min(high, value))))

    def set_thickness(self, weight: int) -> None:
        """The captions' font weight (481): one of `THICKNESSES`."""
        if weight not in THICKNESSES:
            raise ValueError(weight)
        self.change(replace(self.value, thickness=weight))

    def set_edge(self, edge: str) -> None:
        """What's drawn around captions' letters (an `TextEdge`'s value; 481)."""
        self.change(replace(self.value, edge=TextEdge(edge)))

    def set_face(self, language: str, family: str | None) -> None:
        """`language`'s captions in `family` (None: its default) - Look's
        row for it (polyglotic-hq 482). The one font chosen for every
        language before 482 stays the others'."""
        faces = dict(self.value.faces)
        faces[language] = family or ""
        self.change(replace(self.value, faces=tuple(sorted(faces.items()))))

    def set_colour(self, which: str, colour: str) -> None:
        """`which`: "original", "translation" or "background"; `colour`: any
        exact colour ("#ffd76e", as typed or picked: `presets.hex_colour`)."""
        exact = hex_colour(colour)
        if which not in COLOUR_CHOICES or exact is None:
            raise ValueError(which, colour)
        self.change(replace(self.value, **{which: exact}))  # type: ignore[arg-type]

    def set_show_original(self, on: bool) -> None:
        self.change(replace(self.value, show_original=on))

    def set_show_language(self, on: bool) -> None:
        self.change(replace(self.value, show_language=on))

    def set_show_source(self, on: bool) -> None:
        self.change(replace(self.value, show_source=on))

    def set_word_links(self, links: WordLinks) -> None:
        """Word links shown some way turn the quiet view off (477)."""
        quiet = self.value.quiet and links is WordLinks.OFF
        self.change(replace(self.value, word_links=links, quiet=quiet))

    def set_quiet(self, on: bool, readings: tuple[str, ...] = ()) -> None:
        """A caption window's quiet button, or Settings' (477): the quiet
        view on - word links off, as their button turns them off, and
        `readings`, the reading lines of the window clicked - or off,
        its word links and reading lines back as they were (555)."""
        if on == self.value.quiet:
            return
        look = self.value
        if on:
            self.unquieted = look  # its word links as they were too (555)
            if look.word_links is not WordLinks.OFF:  # as their own button would
                look = learning_view(look, False, self.links_when_on, (), self.unlinked)
                self.unlinked = None
        self.change(quiet_view(look, on, readings, self.unquieted, self.links_when_on))
        if not on:
            self.unquieted = None

    def set_quiet_word(self, which: ChosenWords, on: bool) -> None:
        """One of the quiet view's chosen words - our curriculum, the
        learning load, saved words - ticked or not."""
        now = set(self.value.quiet_words)
        now = now | {which} if on else now - {which}
        self.change(replace(self.value, quiet_words=frozenset(now)))

    def set_curriculum_size(self, size: int) -> None:
        self.change(replace(self.value, curriculum_size=size))

    def set_marks_in(self, where: MarksIn) -> None:
        self.change(replace(self.value, marks_in=where))

    def set_links_shown(self, on: bool, readings: tuple[str, ...] = ()) -> None:
        """A caption window's word links button (249, F9): the whole
        learning view in one click (`learning_view`, 446) - word links the
        way they were last shown, with their lines if they never were, and
        `readings`, the reading lines of the window clicked - or off,
        back to how it was before."""
        if on == (self.value.word_links is not WordLinks.OFF):
            return
        look = self.value
        if on:
            if look.quiet:  # the quiet view off first, as its own button would
                look = quiet_view(look, False, (), self.unquieted, self.links_when_on)
                self.unquieted = None
            self.unlinked = look
        self.change(
            learning_view(look, on, self.links_when_on, readings, self.unlinked)
        )
        if not on:
            self.unlinked = None

    def set_readings_shown(self, on: bool, readings: tuple[str, ...] = ()) -> None:
        """The preset dropdown's Readings (polyglotic-hq 556): `readings` -
        the reading lines of the window clicked - on beside those already
        on, or every reading line off."""
        lines = tuple(sorted({*self.value.reading_lines, *readings})) if on else ()
        if on and not lines:
            return  # nothing in that window has a reading to show
        self.change(replace(self.value, reading_lines=lines))

    def set_link_detail(self, detail: LinkDetail) -> None:
        self.change(replace(self.value, link_detail=detail))

    def set_link_line(self, line: LinkLine) -> None:
        """Thin, Medium or Thick - in place of the Lab's thickness, if one
        was set there (284)."""
        self.change(
            replace(
                self.value, link_line=line, lab=replace(self.value.lab, link_px=None)
            )
        )

    def set_link_gap(self, gap: LinkGap) -> None:
        self.change(replace(self.value, link_gap=gap))

    def set_reading_line(self, language: str, on: bool) -> None:
        """`language`'s reading line on or off - pinyin above Chinese, in
        captions and translations alike (369, decision 0155)."""
        now = set(self.value.reading_lines)
        now = now | {language} if on else now - {language}
        self.change(replace(self.value, reading_lines=tuple(sorted(now))))

    def set_reading_size(self, size: ReadingSize) -> None:
        self.change(replace(self.value, reading_size=size))

    def set_reading_past(self, past: bool) -> None:
        """Pinyin over every word, or only over those past what the
        learner knows."""
        self.change(replace(self.value, reading_past=past))

    def set_respelling_past(self, past: bool) -> None:
        """English's respelling over every word, or only over those past
        what the learner knows (polyglotic-hq 511)."""
        self.change(replace(self.value, respelling_past=past))

    def set_reading_system(self, system: ReadingSystem) -> None:
        """Chinese's readings in pinyin or zhuyin (395)."""
        self.change(replace(self.value, reading_system=system))

    def set_reading_colour(self, colour: ReadingColour) -> None:
        """Pinyin in its line's colour, its word link's, or the one picked
        (395)."""
        self.change(replace(self.value, reading_colour=colour))

    def set_reading_custom(self, colour: str) -> None:
        """The colour picked for pinyin ("#rrggbb"): chosen as it's picked."""
        self.change(
            replace(
                self.value, reading_custom=colour, reading_colour=ReadingColour.CUSTOM
            )
        )

    def set_said_in_link_colours(self, on: bool) -> None:
        """Linked words in what was said in their link's colour, or their
        line's (395, 431)."""
        self.change(replace(self.value, said_in_link_colours=on))

    def set_translation_in_link_colours(self, on: bool) -> None:
        """Linked words in the translation in their link's colour, or their
        line's (431)."""
        self.change(replace(self.value, translation_in_link_colours=on))

    def set_fade_after(self, seconds: float | None) -> None:
        self.change(replace(self.value, fade_after=seconds))

    def set_pause_hidden_after(self, minutes: int | None) -> None:
        """How long a hidden window listens (None: always; 335)."""
        self.change(replace(self.value, pause_hidden_after=minutes))

    def set_show_on_speech(self, on: bool) -> None:
        """A hidden window comes back when its app's speech starts (335)."""
        self.change(replace(self.value, show_on_speech=on))

    def set_arrival(self, arrival: str) -> None:
        """How new captions arrive (an `Arrival`'s value; 267)."""
        self.change(replace(self.value, arrival=Arrival(arrival)))

    def reset(self) -> None:
        """The look as Polyglotic first had it - the look only: the
        windows' places are Home's "Reset positions" (248's section 2.2)."""
        self.change(look_defaults(self.value, self.first))

    def set_lab(self, lab: CaptionLab) -> None:
        """Settings > Captions > Lab's values (`views.lab`, 284)."""
        self.change(replace(self.value, lab=lab))

    def set_filled(self, on: bool) -> None:
        """A caption window's filled lines button (372): New layout, Line by
        line and captions run on, together - off again, back to what they
        were before it turned them on (`CaptionLab.with_filled`), as kept
        while the app runs."""
        lab = self.value.lab
        if on == lab.filled:
            return
        if on:
            self.unfilled = lab
        self.set_lab(lab.with_filled(on, self.unfilled))
        if not on:
            self.unfilled = None

    def set_lined_up(self, on: bool) -> None:
        """A caption window's parts lined up button (372): on, with New
        layout - however captions fill the width; off again, New layout
        back to what it was before (`CaptionLab.with_lined_up`), as kept
        while the app runs."""
        lab = self.value.lab
        if on == lab.lined_up:
            return
        if on:
            self.unlined = lab
        self.set_lab(lab.with_lined_up(on, self.unlined))
        if not on:
            self.unlined = None

    def reset_lab(self) -> None:
        """ "Reset the lab": every Lab value back to the app without it."""
        self.set_lab(CaptionLab())
