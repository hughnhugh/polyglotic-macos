"""Caption display rules: what an overlay shows for a caption, and where
captions go - the rules, out of Qt, so they can be tested.

From the proof of concept's `ui/overlay.py` (`caption_lines`,
`_first_rewritten`, `_following_top`) and its design notes
(`docs/line-by-line-captions.md`, `docs/word-links.md`):

- **Clause rows.** A caption shows a clause at a time: what was said
  (white - left out if the overlay hides originals and there's a
  translation), then its translation (yellow) into the overlay's target
  language - or, for a clause already in it, into the overlay's **second
  language**. A live caption's last row trails off. The server keeps a
  second-language line under its target (`translation_shown`), so the row
  says the language it is written in, for its font and reading line
  (polyglotic-hq 427).
- **Word links** are drawn only on settled clauses, never on a live
  caption's last (its words are still changing). The link number tracks
  a counterpart for hover and arrows; each end has its own word class;
  "key words" leaves out minor links; if a cap is set, the surest stay,
  key links first; numbered in reading order **across the whole
  caption** - each clause's after the ones before it - so no two links
  of a caption share a number, whichever of its clauses share a line
  (polyglotic-hq 340, decision 0132: numbered from 0 in each clause, two
  clauses on one line of a caption that fills the width shared a colour).
  A clause that comes later renumbers none before it.
- **A word's counterpart** (polyglotic-hq 328): the words of the other
  row its links join it to, for the lookup card's "Here:" line - from
  every link, drawn or not; finished captions only.
- **Crossfade from the first rewritten row:** rows above it are unchanged
  and stay as they are.
- **One-way layout:** following the live end, no placed caption moves
  down. A caption shrinking leaves space at the bottom; growth uses it
  first; a live caption that has to push leaves headroom to grow into.
- **Quick preview's line** (polyglotic-hq project 064; 049's wireframes,
  3.2): with the preview on, a live caption is provisional - what was
  said, with its translation under it once the server sends one
  (polyglotic-hq 268, DECISIONS.md #101), but no word links (the overlay
  also draws it dim and italic, with no marks) - until its finished
  caption replaces it.
- **Established text** (polyglotic-hq 494, decision 0228;
  `core.listening.established`): a live caption's rows say how much of
  their start is established - drawn as a finished caption's, the rest as
  text still being spoken; a translation row only when its clause is
  established to its end. A row also says which of its words a quiet
  correction recolours (`CaptionRow.corrected`).
- **The listening mark** (every caption timing: polyglotic-hq 260):
  shown from the moment a source's speech is under way until its
  finished caption arrives - a live update, Quick preview's line among
  them, doesn't end it (`ListeningMark`).

The overlay draws what these return; nothing here knows Qt.
"""

import math
import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from polyglotic_desktop.core.listening.captions import (
    Clause,
    Language,
    WordClass,
    WordLink,
    line_language,
)
from polyglotic_desktop.core.listening.established import (
    Span,
    per_clause,
    spans_per_clause,
)
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ports.word_classes import ClassEvidenceFor

LIVE_TRAIL = " …"
"""How a live caption's last row ends: the speech is still going on."""


class RowKind(StrEnum):
    ORIGINAL = "original"  # white: what was said, in its own language
    TRANSLATION = "translation"  # yellow: always a translation


class LongLines(StrEnum):
    """Order of original and translated rows in a long caption."""

    GROUPED = "grouped"
    DISPLAY_NEW_LINES = "display_new_lines"


class WordLinks(StrEnum):
    """How word links are shown (a setting)."""

    OFF = "off"
    HOVER = "hover"  # only for the word pointed at
    COLOURS = "colours"  # linked words underlined in the same colour
    ARROWS = "arrows"  # and joined by curves between the rows


class LinkDetail(StrEnum):
    """Which word links are shown (a setting)."""

    KEY = "key"  # key links only: content words
    MOST = "most"  # minor links too: pronouns, 是, 这个 and the like


class LinkLine(StrEnum):
    """How thick a word link's underline is (a setting; the user's
    rehearsal feedback F14, polyglotic-hq 249)."""

    THIN = "thin"
    MEDIUM = "medium"
    THICK = "thick"


class LinkGap(StrEnum):
    """How far below the text - below its descenders - a word link's
    underline is (a setting, F14)."""

    CLOSE = "close"
    MEDIUM = "medium"
    FAR = "far"


class ReadingSize(StrEnum):
    """How big a reading line's text is beside the text it reads - pinyin
    above Chinese (a setting; polyglotic-hq 369, decision 0155)."""

    SMALL = "small"
    MEDIUM = "medium"


class ReadingColour(StrEnum):
    """What colour a reading line is drawn in (a setting; polyglotic-hq
    395, the user's preview-1 feedback, 2026-11-16: "pinyin should have
    the option of matching the word link colour ... There should be option
    to customise pinyin colour")."""

    SAME = "same"
    """Its line's: what was said's colour, or the translation's."""
    LINK = "link"
    """Its word's link colour, where a link joins it; elsewhere its line's."""
    GREY = "grey"
    """A muted grey, under its text; its word's link colour where a link
    joins it - the default (polyglotic-hq 532, the user, 2026-11-19: "the
    default pinyin/alternate reading font colour on quiet mode (maybe even
    arrowlink default) should be greyish")."""
    CUSTOM = "custom"
    """One colour the learner picks."""


class ReadingSystem(StrEnum):
    """How a Chinese reading line is written (a setting; polyglotic-hq 395:
    Taiwan's readers learn zhuyin, not pinyin). Cantonese's is Jyutping
    whichever is chosen."""

    PINYIN = "pinyin"
    ZHUYIN = "zhuyin"
    """Bopomofo (注音), from the same pinyin (`core.lexicon.zhuyin`)."""


class JapaneseReading(StrEnum):
    """How Japanese pronunciation help is shown."""

    KANA = "kana"
    ROMAJI = "romaji"
    BOTH = "both"
    OFF = "off"


READING_LANGUAGES = ("zh", "yue", "ja", "en", "ru", "ko", "hi")
"""The languages a reading line can be put over (decision 0155): Chinese,
read in pinyin (or zhuyin), Cantonese, read in Jyutping (decision 0160;
the user, 2026-11-17: "the same level as pinyin and zhuyin"), Japanese,
in furigana, English, respelled as it sounds (KAY-oss; polyglotic-hq
511, DECISIONS #200), Russian, its stress marked (молоко́), Korean, in
Revised Romanization (hangugeo), and Hindi, in Latin letters (kitāb; all
511)."""


@dataclass(frozen=True, slots=True)
class DisplayOptions:
    """The settings that change what an overlay's rows say."""

    show_original: bool = True
    word_links: WordLinks = WordLinks.OFF
    link_detail: LinkDetail = LinkDetail.MOST
    max_links: int | None = None  # per clause; None: every link (for now)
    preview: bool = False  # live captions are Quick preview's provisional line
    trail: bool = True
    """A live caption's last row trails off (`LIVE_TRAIL`). Off in the
    paced modes: their words come one by one, and the next is always on
    its way (polyglotic-hq 526)."""


@dataclass(frozen=True, slots=True)
class LinkedWords:
    """Words of a row - `text[start:end]` - linked to words of the other
    row of its clause. `link` numbers the link within the caption, in
    reading order. `pos` is the class of this end of the link.
    `key`: a key link (content words), not a minor one."""

    start: int
    end: int
    link: int
    key: bool = True
    pos: WordClass | None = None


@dataclass(frozen=True, slots=True)
class CaptionRow:
    """One row an overlay shows for a caption. `clause` is the clause it
    shows; `starts_clause` is true for the first row of the clause's pair.
    `language` is the row's language (for its font and reading line), None
    if unknown. `target`: a translation row's target - what its clause
    keeps its line and links under (`translation_shown`); None: its
    `language`. `established`: on a live caption, how many characters at
    its start are established - drawn as final (decision 0228); None on a
    finished caption, all of whose text is. `corrected`: its words a quiet
    correction recolours, `[start, end)` - what was said only."""

    text: str
    kind: RowKind
    language: Language | None
    clause: int
    starts_clause: bool
    links: tuple[LinkedWords, ...] = ()
    target: Language | None = None
    established: int | None = None
    corrected: tuple[Span, ...] = ()
    continues: bool = False


@dataclass(frozen=True, slots=True)
class TranslationShown:
    """A clause's translation as a window shows it: its `text`, the
    `language` it is written in, and the `target` its clause keeps it and
    its links under (`Clause.translations`, `.links`)."""

    text: str
    language: Language
    target: Language


def translation_shown(
    clause: Clause,
    said_in: Language | None,
    target: Language,
    second: Language | None,
) -> TranslationShown | None:
    """The translation a window into `target` shows for `clause`, of a
    caption said in `said_in` - None for none. A clause already in the
    target is translated into its `second` language, kept under the target
    - so its language is the second's (`line_language`: the server says
    which, clause by clause; polyglotic-hq 427 and 497: read as English, a
    Chinese line had no pinyin over it). A line kept under the second
    language itself (a second target too) is shown where the target has
    none."""
    text = clause.translations.get(target)
    if text:
        return TranslationShown(
            text, line_language(clause, target, said_in, second), target
        )
    if second is not None and second != target:
        text = clause.translations.get(second)
        if text:
            return TranslationShown(
                text, clause.written_in.get(second) or second, second
            )
    return None


def with_link_classes(
    caption: Caption,
    target: Language,
    second: Language | None,
    evidence_for: ClassEvidenceFor,
) -> Caption:
    """Resolve each finished clause once, before links are grouped or filtered."""
    clauses = []
    for n, clause in enumerate(caption.clauses):
        shown = translation_shown(clause, caption.language, target, second)
        if shown is None or (caption.live and n == len(caption.clauses) - 1):
            clauses.append(clause)
            continue
        links = clause.links.get(shown.target, ())
        valid = [
            link
            for link in links
            if _fits(link.original, len(clause.original))
            and _fits(link.translation, len(shown.text))
        ]
        original = (
            _resolved_classes(
                clause.original, caption.language, valid, evidence_for, translated=False
            )
            if caption.language is not None and len(caption.languages_heard) <= 1
            else {}
        )
        translated = _resolved_classes(
            shown.text, shown.language, valid, evidence_for, translated=True
        )
        if original or translated:
            classes = tuple(
                replace(
                    link,
                    original_pos=original.get(link.original, link.original_pos),
                    translation_pos=translated.get(
                        link.translation, link.translation_pos
                    ),
                )
                for link in links
            )
            if classes != links:
                clause = replace(clause, links={**clause.links, shown.target: classes})
        clauses.append(clause)
    return (
        replace(caption, clauses=tuple(clauses))
        if tuple(clauses) != caption.clauses
        else caption
    )


def _resolved_classes(
    text: str,
    language: Language,
    links: Sequence[WordLink],
    evidence_for: ClassEvidenceFor,
    *,
    translated: bool,
) -> dict[Span, WordClass | None]:
    choices: dict[Span, set[WordClass | None]] = {}
    for link in links:
        span, pos = (
            (link.translation, link.translation_pos)
            if translated
            else (link.original, link.original_pos)
        )
        choices.setdefault(span, set()).add(pos)
    return (
        {
            span: evidence.resolve(_agreed_class(choices[span]))
            for span, evidence in evidence_for(text, language, choices.keys()).items()
        }
        if choices
        else {}
    )


def caption_rows(
    caption: Caption,
    target: Language,
    second: Language | None,
    options: DisplayOptions,
) -> list[CaptionRow]:
    """The rows `target`'s overlay shows for `caption`: a clause at a time,
    so a clause whose words didn't change keeps its rows."""
    provisional = caption.live and options.preview  # Quick preview's line
    linking = (
        options.word_links is not WordLinks.OFF
        and options.show_original
        and not provisional
    )
    rows: list[CaptionRow] = []
    last = len(caption.clauses) - 1
    numbered = 0  # links numbered in the clauses before: the next one's first
    established = per_clause(caption.clauses, caption.established)
    corrected = spans_per_clause(caption.clauses, caption.corrected)
    for n, clause in enumerate(caption.clauses):
        final = established[n] if caption.live else None
        shown = translation_shown(clause, caption.language, target, second)
        translation = shown.text if shown is not None else None
        settled = not (caption.live and n == last)
        original_links: tuple[LinkedWords, ...] = ()
        translation_links: tuple[LinkedWords, ...] = ()
        if linking and shown is not None and settled:
            original_links, translation_links = numbered_links(
                clause.links.get(shown.target, ()),
                options.link_detail,
                options.max_links,
                len(clause.original),
                len(shown.text),
            )
            if numbered:
                original_links = _from(original_links, numbered)
                translation_links = _from(translation_links, numbered)
            numbered += len({words.link for words in translation_links})
        starts = True
        if translation is None or options.show_original:
            rows.append(
                CaptionRow(
                    clause.original,
                    RowKind.ORIGINAL,
                    caption.language,
                    n,
                    starts,
                    original_links,
                    established=final,
                    corrected=corrected[n],
                    continues=clause.original_continues,
                )
            )
            starts = False
        if shown is not None:
            rows.append(
                CaptionRow(
                    shown.text,
                    RowKind.TRANSLATION,
                    shown.language,
                    n,
                    starts,
                    translation_links,
                    shown.target,
                    continues=shown.target in clause.translations_continued,
                    established=None
                    if final is None
                    else len(shown.text)
                    if clause.original and final == len(clause.original)
                    else 0,
                )
            )
    if caption.live and rows and options.trail:
        end = rows[-1]
        rows[-1] = replace(end, text=end.text + LIVE_TRAIL)
    return rows


def _from(links: tuple[LinkedWords, ...], first: int) -> tuple[LinkedWords, ...]:
    """A clause's `links`, numbered from `first` on."""
    return tuple(replace(words, link=words.link + first) for words in links)


def numbered_links(
    links: Sequence[WordLink],
    detail: LinkDetail,
    cap: int | None = None,
    original_length: int | None = None,
    translation_length: int | None = None,
) -> tuple[tuple[LinkedWords, ...], tuple[LinkedWords, ...]]:
    """A clause's word links as (words in the original, words in the
    translation), each numbered by link - from 0: `caption_rows` numbers
    them on across the caption. One link per counterpart in the
    translation: original words that say the same thing share it (a word
    said twice). "Key words" leaves out minor links. With `cap`, the
    surest stay - key links first. Numbered in reading order of the
    original. Spans outside the texts' lengths, if given, are dropped."""
    kept = group_links(
        [link for link in links if detail is LinkDetail.MOST or link.key],
        original_length,
        translation_length,
    )
    kept.sort(key=lambda group: (not group.key, -group.confidence))
    if cap is not None:
        kept = kept[:cap]
    kept.sort(key=lambda group: group.original[0])
    original = sorted(
        (
            LinkedWords(a, b, number, group.key, pos)
            for number, group in enumerate(kept)
            for (a, b), pos in zip(group.original, group.original_pos, strict=True)
        ),
        key=lambda w: (w.start, w.end),
    )
    translation = sorted(
        (
            LinkedWords(*group.translation, number, group.key, group.translation_pos)
            for number, group in enumerate(kept)
        ),
        key=lambda w: (w.start, w.end),
    )
    return tuple(original), tuple(translation)


@dataclass(frozen=True, slots=True)
class GroupedLink:
    """One counterpart and its linked original spans, in reading order."""

    original: tuple[Span, ...]
    translation: Span
    key: bool
    confidence: float
    original_pos: tuple[WordClass | None, ...]
    translation_pos: WordClass | None


def _agreed_class(choices: set[WordClass | None]) -> WordClass | None:
    return next(iter(choices)) if len(choices) == 1 else None


def group_links(
    links: Sequence[WordLink],
    original_length: int | None,
    translation_length: int | None,
) -> list[GroupedLink]:
    groups: dict[Span, list[WordLink]] = {}
    for link in links:
        if _fits(link.original, original_length) and _fits(
            link.translation, translation_length
        ):
            groups.setdefault(link.translation, []).append(link)
    found = []
    for translation, matching in groups.items():
        matching.sort(key=lambda link: link.original)
        original_classes: dict[Span, set[WordClass | None]] = {}
        for link in matching:
            original_classes.setdefault(link.original, set()).add(link.original_pos)
        found.append(
            GroupedLink(
                tuple(link.original for link in matching),
                translation,
                any(link.key for link in matching),
                max(0.0, max(link.confidence for link in matching)),
                tuple(
                    _agreed_class(original_classes[link.original]) for link in matching
                ),
                _agreed_class({link.translation_pos for link in matching}),
            )
        )
    return found


def _fits(span: tuple[int, int], length: int | None) -> bool:
    start, end = span
    return 0 <= start < end and (length is None or end <= length)


COUNTERPART_GAP = " … "
"""Between the pieces of a counterpart that aren't side by side in their
row ("turn … off")."""


@dataclass(frozen=True, slots=True)
class Counterpart:
    """What words of a row say in the other row of their clause: `words`,
    in `language` (None if unknown) - a lookup card's "Here:" line."""

    words: str
    language: Language | None
    pos: WordClass | None = None


def counterpart(
    caption: Caption, rows: Sequence[CaptionRow], index: int, span: tuple[int, int]
) -> Counterpart | None:
    """The counterpart of the words at `span` in `rows[index]` (`caption`'s
    rows, as `caption_rows` gave them): the words of the other row of their
    clause - the translation shown with it, or, for a translation row, what
    was said - that the clause's word links join to them (polyglotic-hq
    328, from 326's design).

    Every link counts, key or minor, drawn or not: the Look's settings and
    which links the learner sees change only what's drawn. Several pieces
    come in that row's own order, joined where only spaces lie between
    them, else with `COUNTERPART_GAP`; punctuation at a piece's ends is
    left out, and a piece that is nothing but punctuation goes.

    None for none: no link (a particle, a word the translation dropped), no
    other row (captions only), or a caption still being spoken - its words
    and links can still change, and an open card doesn't follow them (the
    marks' rule: finished captions only)."""
    if caption.live or not 0 <= index < len(rows):
        return None
    row = rows[index]
    if not 0 <= row.clause < len(caption.clauses):
        return None
    clause = caption.clauses[row.clause]
    if row.kind is RowKind.ORIGINAL:
        partner = next(
            (
                r
                for r in rows
                if r.clause == row.clause and r.kind is RowKind.TRANSLATION
            ),
            None,
        )
        if partner is None or partner.language is None:
            return None
        language: Language | None = partner.language
        kept = partner.target or partner.language
        mine, other = clause.original, clause.translations.get(kept, "")
        pairs = [
            (k.original, k.translation, k.original_pos)
            for k in clause.links.get(kept, ())
        ]
    else:
        if row.language is None:
            return None
        language = caption.language
        kept = row.target or row.language
        mine, other = clause.translations.get(kept, ""), clause.original
        pairs = [
            (k.translation, k.original, k.translation_pos)
            for k in clause.links.get(kept, ())
        ]
    start, end = span
    matches = [
        (theirs, pos)
        for ours, theirs, pos in pairs
        if _fits(ours, len(mine))
        and _fits(theirs, len(other))
        and ours[0] < end
        and start < ours[1]
    ]
    words = _pieces(other, sorted({theirs for theirs, _ in matches}))
    pos = _agreed_class({pos for _, pos in matches})
    return Counterpart(words, language, pos) if words else None


def _pieces(text: str, spans: Sequence[tuple[int, int]]) -> str:
    """`text`'s `spans` (in order) as words: side by side or with only
    spaces between, one piece; trimmed of punctuation; then joined."""
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and not text[merged[-1][1] : start].strip():
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    pieces = (_trimmed(text[start:end]) for start, end in merged)
    return COUNTERPART_GAP.join(p for p in pieces if p)


def _trimmed(text: str) -> str:
    """`text` without spaces or punctuation at either end."""

    def edge(c: str) -> bool:
        return c.isspace() or unicodedata.category(c).startswith("P")

    start, end = 0, len(text)
    while start < end and edge(text[start]):
        start += 1
    while end > start and edge(text[end - 1]):
        end -= 1
    return text[start:end]


def clause_versions(caption: Caption, clause: int) -> dict[str, str]:
    """A clause in every language it's shown in - what was said first,
    then its translations - by language code: the lookup context's
    versions for a word in one of its rows."""
    shown = caption.clauses[clause]
    versions = {str(caption.language or ""): shown.original}
    versions.update({str(k): v for k, v in shown.translations.items() if v})
    return versions


def first_rewritten(old: Sequence[str], new: Sequence[str]) -> int | None:
    """The index of the first row of `new` that rewrites its row in `old`
    rather than only growing it (a live caption's last row) - `len(new)`
    if only rows at the end went - or None if nothing was rewritten. The
    overlay crossfades from there down; the rows above stay as they are."""
    for i, (a, b) in enumerate(zip(old, new, strict=False)):
        grew = i == len(old) - 1 and b.startswith(a.removesuffix(LIVE_TRAIL))
        if a != b and not grew:
            return i
    return len(new) if len(new) < len(old) else None


@dataclass(frozen=True, slots=True)
class Placed:
    """A caption in an overlay's stack: its height, and where its top was
    placed last (None if it's arriving)."""

    height: float
    top: float | None


def stack_height(items: Sequence[Placed], gap: float) -> float:
    return sum(i.height for i in items) + gap * max(0, len(items) - 1)


def following_top(
    items: Sequence[Placed],
    canvas_height: float,
    gap: float,
    last_is_live: bool,
    headroom: float,
    reanchor: bool,
) -> float:
    """Where the top of the stack goes while following the live end: as
    low as it can be while it fits on the canvas and no caption already
    placed moves down (the one-way layout). So a caption shrinking - the
    finished pass merging rows, a caption withdrawn - doesn't pull the
    ones above down: those below move up, and space is left at the
    bottom. A caption growing pushes the ones above up - or first grows
    into that space. A live caption at the bottom that has to push
    leaves `headroom` spare to grow into, so the stack steps up now and
    then rather than with every update. `reanchor`: settle at the bottom
    afresh (after a resize, a restyle or scrolling back)."""
    bottom = canvas_height - stack_height(items, gap)
    if reanchor or not items:
        return bottom
    placed = math.inf  # the lowest top that moves no placed caption down
    offset = 0.0
    for item in items:
        if item.top is not None:
            placed = min(placed, item.top - offset)
        offset += item.height + gap
    if placed <= bottom:
        return placed
    if last_is_live:
        return bottom - headroom
    return bottom


MARK_WAIT_SEC = 3.0
"""Once speech stops, the listening mark waits at most this long for its
caption (the server takes a second or so; none comes for speech too short
to send, mic bleed, or speech lost)."""


@dataclass(slots=True)
class _Heard:
    seen: float  # when its speech was last seen under way
    stopped: float | None = None  # when it was first seen stopped
    answered: float = -math.inf  # when a caption from it last arrived


class ListeningMark:
    """When the overlays show the listening mark - the quiet sign that
    speech is being heard, so the wait for a finished caption (in Steady
    a median ~3.6s from the first word) reads as "coming", not "broken"
    (polyglotic-hq project 049's wireframes, 3.2). It never shows text.
    In every caption timing, for the mic's speech as for an app's (260,
    the user's F33: "a loading bar whilst there is speech being recorded
    / processed either through my own mic or others").

    Shown from the moment a source's speech is under way until a finished
    caption from that source arrives after the speech stopped, or
    MARK_WAIT_SEC if none does. `heard` is fed which sources are under
    way, every so often; `captioned` each finished or withdrawn caption -
    never a live update: Quick preview's line and Live updates' rewrites
    come while the speech is still being finished. Times are on one
    clock, in seconds; nothing here reads one."""

    def __init__(self) -> None:
        self._heard: dict[SourceId, _Heard] = {}

    def heard(self, under_way: Collection[SourceId], at: float) -> None:
        """The sources whose speech is under way at `at`."""
        for source_id in under_way:
            found = self._heard.get(source_id)
            if found is None:
                self._heard[source_id] = _Heard(at)
            else:
                found.seen, found.stopped = at, None
        for source_id, found in list(self._heard.items()):
            if source_id in under_way or found.stopped is not None:
                continue
            if found.answered > found.seen:
                # its caption came before the speech was seen to stop
                del self._heard[source_id]
            else:
                found.stopped = at

    def captioned(self, source_id: SourceId, at: float) -> None:
        """A finished caption (or a withdrawal) from `source_id` arrived."""
        found = self._heard.get(source_id)
        if found is None:
            return
        if found.stopped is not None:
            del self._heard[source_id]
        else:
            found.answered = at

    def speaking(self) -> bool:
        """Whether any source's speech is under way - heard, and not seen to
        stop since: a caption arriving now has another on its way (the
        caption window's arrival slides quicker; polyglotic-hq 267)."""
        return any(found.stopped is None for found in self._heard.values())

    def showing(self, at: float) -> bool:
        for source_id, found in list(self._heard.items()):
            if found.stopped is not None and at - found.stopped > MARK_WAIT_SEC:
                del self._heard[source_id]
        return bool(self._heard)
