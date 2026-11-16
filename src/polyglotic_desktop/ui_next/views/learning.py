"""The Learning page, as plain Python (polyglotic-hq 262; 248's IA.md,
section 3.6): a card per language being learned, and what each says and
offers - facts, not words; the page words them.

Every full language learned is open at once, each with its own
dictionary and learning data (`running`: those `main` opened at the
start, and any added since - `main` opens it at once; DECISIONS #110,
decision 0095), and Words keeps a section for each. Another full language
can be made the main one (`switched_to`: Words' first section, Home's),
from the next start.
"""

import unicodedata
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from enum import StrEnum

from polyglotic_desktop.core.learning.first_known import (
    FIRST_KNOWN,
    QuickMarks,
    marks_more,
)
from polyglotic_desktop.core.learning.languages import (
    LearningLanguages,
    Tier,
    tier_of,
)
from polyglotic_desktop.core.learning.levels import (
    DEFAULT_WINDOW,
    UNLIMITED,
    WINDOW_SIZES,
    KnownLine,
    LanguageChoices,
    LinkChoice,
    WindowSize,
    window_size,
)
from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem
from polyglotic_desktop.ui_next.views import known_words
from polyglotic_desktop.ui_next.views.words import LevelLine, level_line


@dataclass(frozen=True)
class PackLine:
    """A basic language's dictionary pack, as its card says it (decision
    0122): offered with its size, downloading or standing still, or on
    this PC with its version."""

    size: int = 0
    """What this app would download for it, in bytes - gzipped (0: not
    known yet)."""
    recorded_offered: int = 0
    """Its commonest words recorded, downloaded by themselves after it: their
    size, gzipped, where the list has them for this app (decision 0192; 0:
    none)."""
    installed_version: str = ""
    installed_size: int = 0
    progress: PackProgress | None = None
    """A download under way, or standing still (None: none)."""
    newer_app: bool = False
    """Only a newer Polyglotic reads its packs."""
    update_size: int = 0
    """A newer version waits for a connection that isn't metered (its
    size; 0: none)."""
    credits: str = ""
    """Whose data it is, from the list: shown as it is (names, not words) -
    and who said its recorded words, from their file."""
    recorded_size: int = 0
    """Its commonest words are recorded on this PC: the file's size
    (decision 0133; 0: none)."""
    unlisted: bool = False
    """No list is held, and the last try couldn't read one (offline, a
    server error, refused): whether a pack can be had isn't known - not
    "checking" for good, and no promise either way. Retry asks again."""
    not_offered: bool = False
    """No pack for it can be had: the list this app holds has none for it
    (none built yet: Vietnamese, 2026-11-14), or none is published at all
    (the storage answers 404 - before the first upload). Nothing to
    download yet (329's QA, 330); Retry looks again. Not when it isn't
    known (no list held, none read): then it can't be told."""
    checking: bool = False
    """The list held - kept from an earlier run, or read over an hour ago -
    is being checked again and has no pack for it (polyglotic-hq 425):
    until the answer, it isn't said to have none."""

    @property
    def installed(self) -> bool:
        return bool(self.installed_version)


class PackKnown(StrEnum):
    """Whether a basic language's pack can be had, as far as this app
    knows - what its card and "Learn another language" may say: no line
    promises a download the app can't know exists (polyglotic-hq 330; the
    release may come before any list is published)."""

    OFFERED = "offered"
    """The list held has one for it (or a download of it is under way)."""
    NONE_YET = "none_yet"
    """None can be had: not in the list held, or none published (a 404)."""
    UNKNOWN = "unknown"
    """No list held: none read yet, or it couldn't be read."""
    CHECKING = "checking"
    """Not offered in the list held, which is old and being checked again
    (polyglotic-hq 425): no promise either way, and it says it's checking."""


def pack_known(line: PackLine | None) -> PackKnown:
    """What `line` says of whether its pack can be had (None: no line)."""
    if line is None:
        return PackKnown.UNKNOWN
    progress = line.progress
    if line.not_offered or (
        progress is not None and progress.problem is Problem.NOT_OFFERED
    ):
        return PackKnown.NONE_YET
    if line.size or line.newer_app or line.installed or progress is not None:
        return PackKnown.OFFERED
    if line.checking:
        return PackKnown.CHECKING
    return PackKnown.UNKNOWN


@dataclass(frozen=True)
class InstalledPackLine:
    """A pack on this PC, on Learning's list of them."""

    code: str
    version: str
    size: int


@dataclass(frozen=True)
class QuickMarksLine:
    """ "Mark the first N words known" on a language's card, and taking it
    back (polyglotic-hq 342; `core.learning.first_known`)."""

    known: int | None
    """About how many words the known line holds now - estimated at the
    starting level while none is set (None: a level scheme this version
    doesn't know)."""
    undo: LevelLine | None = None
    """Undo is offered: back to this level."""
    marked: int = 0
    """With Undo: about how many more words the last quick mark made
    known."""
    reset: LevelLine | None = None
    """Reset is offered: back to this level."""
    reset_changes: int = 0
    """About how many words Reset makes new again."""

    def offered(self, first: int) -> bool:
        """Whether marking the first `first` words known marks any more."""
        return marks_more(self.known, first)

    @property
    def choices(self) -> tuple[int, ...]:
        """The quick choices that mark more than the line holds now."""
        return tuple(n for n in FIRST_KNOWN if self.offered(n))


def quick_marks_line(
    code: str, line: KnownLine | None, marks: QuickMarks, marked: int = 0
) -> QuickMarksLine:
    """What the card says of quick marks for the language `code`, whose
    known line is `line` now, with Undo and Reset as `marks` offers them;
    `marked`: how many more words the last quick mark made known."""
    known = (
        known_words.words_known(line)
        if line is not None
        else known_words.not_sure(code)  # the starting level's words
    )
    reset = marks.reset_to
    back = (
        None
        if reset is None
        else known_words.words_known(reset.line)
        if reset.line is not None
        else known_words.not_sure(code)
    )
    return QuickMarksLine(
        known,
        undo=level_line(marks.undo_to.line) if marks.undo_to is not None else None,
        marked=marked if marks.undo_to is not None else 0,
        reset=level_line(reset.line) if reset is not None else None,
        reset_changes=max(0, (known or 0) - (back or 0)) if reset is not None else 0,
    )


@dataclass(frozen=True)
class LanguageCard:
    """One language's card on Learning."""

    code: str
    tier: Tier
    main: bool = False
    """The main language - now, or from the next start."""
    running: bool = False
    """Its dictionary and learning data are open now: lookups, the level,
    word introductions."""
    level: LevelLine | None = None
    """The level of a language that keeps learning data - a full
    dictionary's, or a pack language's while its learning data is open
    (decision 0175) - if it's known. None: a pack language not open (its
    pack isn't here), or one without a dictionary."""
    pack_here: bool = False
    """A basic dictionary's pack is on this PC: its lookups work."""
    pack: PackLine | None = None
    """Its pack, offered, coming or here (a basic dictionary only)."""
    pack_known: PackKnown | None = None
    """A basic language without its pack on this PC: whether one can be had
    (`pack_known`) - the card says there's no dictionary yet, or makes no
    promise either way, rather than one "once it's downloaded" (329's QA,
    K11; 330). None: not a basic language, or its pack is here. On the card
    itself, not only its pack's line, so the card is worded again when it
    changes."""
    choices: LanguageChoices = field(default_factory=LanguageChoices)
    """What the learner chose for it: the learning window's size, and
    which words are linked (polyglotic-hq 323)."""
    in_words: bool = False
    """Its level is a number of words (not one kept from before 323, and
    not unset): the learning window is the next words past it."""
    quick: QuickMarksLine | None = None
    """"Mark the first N words known", with Undo and Reset (342): where the
    level can be changed now. None: not offered."""
    recorded_size: int = 0
    """A full dictionary's commonest words are recorded on this PC (decision
    0197): the file's size (0: none). A basic one's say so on its pack's
    line (`PackLine.recorded_size`)."""
    recorded_credits: str = ""
    """Who said them, under what licence, from their file."""

    @property
    def no_pack_yet(self) -> bool:
        """None of its pack can be had: the card says no dictionary yet."""
        return self.pack_known is PackKnown.NONE_YET

    @property
    def window(self) -> WindowSize | None:
        """The learning window's size, where the card offers it: the
        language in use, its level in words. None: not offered."""
        if not (self.can_change_level and self.in_words):
            return None
        size = self.choices.window_size
        return DEFAULT_WINDOW if size is None else size

    @property
    def ranked(self) -> bool:
        """A dictionary ranks its words: "past what you know" has a place
        to start from - a full one's, or a basic one's pack on this PC
        (its frequency ranks, decision 0120; polyglotic-hq 338). Without
        one, only key words are linked."""
        return self.tier is Tier.FULL or self.pack_here

    @property
    def links_from_line(self) -> bool:
        """Links can start at what the learner knows: their level is kept
        (a full dictionary's, or an open pack language's). A pack
        language's that isn't open start at a number of words
        (`UNKNOWN_LEVEL_LINKS_FROM` until chosen)."""
        return self.level is not None

    @property
    def offers_links_from(self) -> bool:
        """Where links start can be chosen: only while they follow what's
        known, in a language whose words are ranked."""
        return self.ranked and self.choices.links is LinkChoice.PAST_KNOWN

    @property
    def key_words_only(self) -> bool:
        """Links follow what's known, and nothing ranks its words."""
        return not self.ranked and self.choices.links is LinkChoice.PAST_KNOWN

    @property
    def can_change_level(self) -> bool:
        """Its level is open learning data's: changed at once."""
        return self.running and self.level is not None

    @property
    def can_switch(self) -> bool:
        """A full dictionary that isn't the main one: it can be made main."""
        return self.tier is Tier.FULL and not self.main


class Custom(StrEnum):
    """The learning window's "Custom" choice on a card: a number the
    learner types (decision 0144)."""

    CUSTOM = "custom"


WINDOW_CHOICES: tuple[WindowSize | Custom, ...] = (
    *WINDOW_SIZES,
    UNLIMITED,
    Custom.CUSTOM,
)
"""The learning window's choices on a language's card, in order."""


def window_choice(size: WindowSize) -> WindowSize | Custom:
    """Which of `WINDOW_CHOICES` a window's size shows as: its own, or
    "Custom" for a number of the learner's own."""
    return size if size is UNLIMITED or size in WINDOW_SIZES else Custom.CUSTOM


def typed_window(text: str) -> int | None:
    """The number of words typed for a custom window, within its bounds:
    digits, with any separators between them ("3,000", "3 000", "3.000"),
    full-width ones too ("２，０００": a Chinese or Japanese keyboard in
    full-width mode - 361). None: no number in it."""
    text = unicodedata.normalize("NFKC", text)  # full-width digits and commas
    digits = "".join(c for c in text if not c.isspace() and c not in ",.'’")
    if not digits.isdigit() or not digits.isascii():
        return None
    return window_size(int(digits))


def cards(
    languages: LearningLanguages,
    running: Collection[str],
    level_of: Callable[[str], KnownLine | None],
    packs: Collection[str] = (),
    choices_of: Callable[[str], LanguageChoices] | None = None,
    pack_line: Callable[[str], PackLine | None] = lambda _: None,
    quick_of: Callable[[str], tuple[QuickMarks, int]] | None = None,
    recorded_of: Callable[[str], tuple[int, str]] = lambda _: (0, ""),
) -> tuple[LanguageCard, ...]:
    """The cards, the main language first: `running`, the languages
    whose dictionary and learning data are open now (the full ones, and
    each pack language learned whose pack is here: decision 0175);
    `level_of`, a language's level (an open one's, live; another full
    one's as it was kept);
    `packs`, the basic dictionaries on this PC; `choices_of`, what the
    learner chose for a language (None: nothing, anywhere); `pack_line`, a
    basic language's pack as its card says it; `quick_of`, a language's
    Undo and Reset after quick marks, and how many words the last marked
    (None: no quick marks offered); `recorded_of`, a full dictionary's
    recorded words on this PC: their size and credits (decision 0197)."""
    found = []
    for code in languages.all:
        tier = tier_of(code)
        main = code == languages.main
        keeps = tier is Tier.FULL or code in running  # learning data
        line = level_of(code) if keeps else None
        level = level_line(line) if keeps else None
        pack_here = tier is Tier.BASIC and code in packs
        pack = pack_line(code) if tier is Tier.BASIC else None
        recorded_size, recorded_credits = (
            recorded_of(code) if tier is Tier.FULL else (0, "")
        )
        quick = None
        if quick_of is not None and code in running:
            quick = quick_marks_line(code, line, *quick_of(code))
        found.append(
            LanguageCard(
                code,
                tier,
                main=main,
                running=code in running,
                level=level,
                pack_here=pack_here,
                pack=pack,
                pack_known=(
                    pack_known(pack) if tier is Tier.BASIC and not pack_here else None
                ),
                choices=choices_of(code) if choices_of else LanguageChoices(),
                in_words=line is not None and not line.by_level,
                quick=quick,
                recorded_size=recorded_size,
                recorded_credits=recorded_credits,
            )
        )
    return tuple(found)


def offered(languages: LearningLanguages, codes: Collection[str]) -> list[str]:
    """The languages "Learn another language" offers, from `codes` (every
    caption language, learned codes, in the order to show them): those not
    learned yet, each once. Full and basic dictionaries aren't put first -
    each says its tier (polyglotic-hq 293: Chinese and English on top made
    the app look as if it were only for them)."""
    return [c for c in dict.fromkeys(codes) if not languages.learns(c)]
