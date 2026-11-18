"""A selection in a caption window or a transcript, as a sentence to save
(polyglotic-hq 459; the user, 2026-11-14: "a sentence could span across
multiple lines ... it should carry the original translation"). Plain
Python, no Qt.

`selected_sentence` takes what is selected - each row's selected
characters, in reading order - and makes the parts `Vocabulary.save_sentence`
keeps, one a clause:
- **the side dragged across** keeps what was selected of it; **the other
  side** of each clause it touches is kept whole (a translation can't be
  cut where the original was); both sides held: each as selected;
- **its word links**, those whose words are inside both, renumbered to
  where the kept text starts - the caption's own, every one (`caption_of`),
  not only those the window shows;
- **the speaker** each caption showed under ("You", the app's name), so a
  selection across two speakers keeps each line's;
- **each side joined** as the transcript joins clauses (decision 0126);
- **its language:** the first line's spoken language - which learning
  file it goes in (`Learner.of`) - and its translation's.

`worth_saving`: whether a selection is more than a word - a sentence
offered to save - or a word, which its lookup already saves.

`sides_aloud`: the same selection's sides to read aloud ("Say it",
polyglotic-hq 495), each with where its text is shown, so the word being
said lights there.

Holds caption text: never log it.
"""

import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from polyglotic_desktop.core.learning.sentences import SentenceLink, SentencePart
from polyglotic_desktop.core.listening.caption_model import Words
from polyglotic_desktop.core.listening.display import LIVE_TRAIL, CaptionRow, RowKind
from polyglotic_desktop.core.listening.history import Caption, is_cjk, join_text
from polyglotic_desktop.core.listening.read_aloud import Origin, Stretch
from polyglotic_desktop.ui_next.views.captions import Line

Piece = tuple[Line, CaptionRow, int, int]
"""A row with something selected in it: its line, the row, and the
selected characters `[start, end)` of its text."""


@dataclass(frozen=True)
class Selected:
    """A selection as a sentence to save: its parts, each side joined, the
    language it was spoken in (its first line's; None if unknown) and the
    language of its translation ("" for none)."""

    parts: tuple[SentencePart, ...]
    original: str
    translation: str
    language: str | None
    translation_language: str


def _shown(line: Line, row: CaptionRow) -> str:
    return row.text.removesuffix(LIVE_TRAIL) if line.live else row.text


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    """`[start, end)` of `text` without the spaces at its ends."""
    end = min(end, len(text))
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


CaptionOf = Callable[[int], Caption | None]
"""A line's caption by its key (`CaptionLines.caption`): every word link
its clauses have, shown or not."""


@dataclass(frozen=True)
class _Clause:
    """A clause the selection touches: its line, its rows by side, and each
    side's kept characters `[start, end)` and text - the side dragged
    across as selected, the other whole."""

    line: Line
    clause: int
    rows: dict[RowKind, CaptionRow]
    clips: dict[RowKind, tuple[int, int]]
    texts: dict[RowKind, str]


def _clauses(pieces: Sequence[Piece]) -> list[_Clause]:
    """`pieces` by clause, in reading order, each with what it keeps of
    each side; a clause with nothing but spaces kept is left out."""
    clauses: dict[tuple[int, int], tuple[Line, dict[RowKind, tuple[int, int]]]] = {}
    for line, row, start, end in pieces:
        line_clause = (line.key, row.clause)
        held = clauses.setdefault(line_clause, (line, {}))[1]
        old = held.get(row.kind)
        held[row.kind] = (min(start, old[0]), max(end, old[1])) if old else (start, end)
    found = []
    for (_, clause), (line, held) in clauses.items():
        rows = {r.kind: r for r in line.rows if r.clause == clause}
        texts: dict[RowKind, str] = {}
        clips: dict[RowKind, tuple[int, int]] = {}
        for kind in (RowKind.ORIGINAL, RowKind.TRANSLATION):
            side = rows.get(kind)
            if side is None:
                texts[kind], clips[kind] = "", (0, 0)
                continue
            text = _shown(line, side)
            start, end = held.get(kind, (0, len(text)))
            clips[kind] = _trimmed(text, start, end)
            texts[kind] = text[clips[kind][0] : clips[kind][1]]
        if texts[RowKind.ORIGINAL] or texts[RowKind.TRANSLATION]:
            found.append(_Clause(line, clause, rows, clips, texts))
    return found


def selected_sentence(
    pieces: Sequence[Piece],
    speaker: Callable[[Line], str],
    caption_of: CaptionOf | None = None,
) -> Selected | None:
    """`pieces` (in reading order) as a sentence; None when nothing but
    spaces is selected. `speaker` names a line's speaker; `caption_of`
    gives a line's caption, for its word links - all of them, whether the
    window shows them or not (word links off, or only those past what the
    learner knows); without it, those its rows show."""
    parts: list[SentencePart] = []
    language: str | None = None
    translation_language = ""
    first = True
    for held in _clauses(pieces):
        line, clause, rows = held.line, held.clause, held.rows
        texts, clips = held.texts, held.clips
        original_row = rows.get(RowKind.ORIGINAL)
        translation_row = rows.get(RowKind.TRANSLATION)
        if first:
            language = original_row.language if original_row else None
            first = False
        if translation_row is not None and not translation_language:
            translation_language = translation_row.language or ""
        parts.append(
            SentencePart(
                texts[RowKind.ORIGINAL],
                texts[RowKind.TRANSLATION],
                _links(
                    original_row,
                    translation_row,
                    clips,
                    _caption_links(
                        caption_of, line, clause, original_row, translation_row
                    ),
                ),
                speaker(line),
            )
        )
    if not parts:
        return None
    return Selected(
        tuple(parts),
        join_text(p.original for p in parts),
        join_text(p.translation for p in parts),
        language,
        translation_language,
    )


def _caption_links(
    caption_of: CaptionOf | None,
    line: Line,
    clause: int,
    original: CaptionRow | None,
    translation: CaptionRow | None,
) -> list[tuple[tuple[int, int], tuple[int, int], bool]] | None:
    """The clause's own word links into the translation shown - when its
    rows show its text as it is (a live caption's, or one settling, may
    not); None to take the rows' instead."""
    if caption_of is None or original is None or translation is None:
        return None
    caption = caption_of(line.key)
    if caption is None or clause >= len(caption.clauses):
        return None
    held = caption.clauses[clause]
    target = translation.target or translation.language
    if target is None or held.original != original.text:
        return None
    if held.translations.get(target) != translation.text:
        return None
    return [(k.original, k.translation, k.key) for k in held.links.get(target, ())]


def _links(
    original: CaptionRow | None,
    translation: CaptionRow | None,
    clips: dict[RowKind, tuple[int, int]],
    caption: list[tuple[tuple[int, int], tuple[int, int], bool]] | None = None,
) -> tuple[SentenceLink, ...]:
    """The clause's word links inside both kept sides, from where each
    side's kept text starts: the caption's own (`caption`), else those its
    rows show."""
    if original is None or translation is None:
        return ()
    (o_start, o_end), (t_start, t_end) = (
        clips[RowKind.ORIGINAL],
        clips[RowKind.TRANSLATION],
    )
    if caption is None:
        across = {each.link: each for each in translation.links}
        caption = [
            ((each.start, each.end), (other.start, other.end), each.key)
            for each in original.links
            if (other := across.get(each.link)) is not None
        ]
    found = []
    for (a, b), (c, d), key in caption:
        if not (o_start <= a and b <= o_end):
            continue
        if not (t_start <= c and d <= t_end):
            continue
        found.append(
            SentenceLink(
                (a - o_start, b - o_start),
                (c - t_start, d - t_start),
                key,
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class SideAloud:
    """One side of a selection, to read aloud (polyglotic-hq 495): `kind`,
    what was said or the translation; `language`, the one its first clause
    is in; `stretches`, what it keeps of each clause, as `read_aloud` takes
    them; `shown`, where each stretch is in the window - its line's key and
    its characters on that side, so a stretch's characters `[a, b)` are
    `Words(kind, clause, start + a, start + b)`."""

    kind: RowKind
    language: str
    stretches: tuple[Stretch, ...]
    shown: tuple[tuple[int, Words], ...]

    def lit(self, origins: Sequence[Origin]) -> dict[int, list[Words]]:
        """The characters to light, by line key, for what `read_aloud`'s
        `came_from` gives."""
        found: dict[int, list[Words]] = {}
        for stretch, start, end in origins:
            if not 0 <= stretch < len(self.shown):
                continue
            key, where = self.shown[stretch]
            found.setdefault(key, []).append(
                Words(where.side, where.clause, where.start + start, where.start + end)
            )
        return found


def sides_aloud(pieces: Sequence[Piece]) -> tuple[SideAloud, ...]:
    """The sides of a selection that can be read aloud, one a language, in
    the order each first appears (what was said first in a clause): each
    clause gives a side the row that is in its language - what was said,
    or the translation - so a selection across both directions (Chinese
    said and translated into English, English said and translated into
    Chinese) reads all its Chinese in Chinese and all its English in
    English, not a mixture (the user, 2026-11-18). As `selected_sentence`
    keeps them: the side dragged across as selected, the other side of each
    clause it touches whole. A row with no text, or whose language isn't
    known, is left out; a clause gives a language once (what was said
    first)."""
    order: list[str] = []
    kinds: dict[str, RowKind] = {}
    stretches: dict[str, list[Stretch]] = {}
    shown: dict[str, list[tuple[int, Words]]] = {}
    for held in _clauses(pieces):
        given: set[str] = set()
        for kind in (RowKind.ORIGINAL, RowKind.TRANSLATION):
            row = held.rows.get(kind)
            if row is None or not held.texts[kind] or not row.language:
                continue
            language = str(row.language)
            if language in given:
                continue
            given.add(language)
            if language not in kinds:
                order.append(language)
                kinds[language] = kind
                stretches[language], shown[language] = [], []
            start, end = held.clips[kind]
            stretches[language].append(Stretch(held.texts[kind], held.line.key))
            shown[language].append(
                (held.line.key, Words(kind, held.clause, start, end))
            )
    return tuple(
        SideAloud(
            kinds[language],
            language,
            tuple(stretches[language]),
            tuple(shown[language]),
        )
        for language in order
    )


def worth_saving(selected: Selected | None) -> bool:
    """More than a word: two clauses or more, or text with a space between
    words - or, where words aren't spaced (Chinese, Japanese, Thai), four
    letters or more. A word's own lookup saves a word."""
    if selected is None:
        return False
    if len(selected.parts) > 1:
        return True
    text = selected.original or selected.translation
    letters = [c for c in text if unicodedata.category(c)[0] in "LMN"]
    if " " in text.strip() and len(letters) > 1:
        return True
    unspaced = [c for c in letters if is_cjk(c) or 0x0E00 <= ord(c) <= 0x0EFF]
    return len(unspaced) >= 4
