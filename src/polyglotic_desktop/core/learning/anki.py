"""Words for Anki as a CSV file (MVP.md; projects 015 and 089) - and
saved sentences (polyglotic-hq 459: "Anki card Front and back should be
similar to how words works now"): a sentence's note has its own GUID
(`sentence_guid`), what was said on the front with its saved words in
`<b>`, and on the back the same with its key word links underlined, each
link its own colour on both sides (`LINK_COLOURS`), then the translation
and who said it. In the CSV, a sentence is a row after the words, as
Basic's front and back; in the deck file, a note type of its own per
language (`ports.anki_deck.DeckSentence`).

Anki imports UTF-8 text with fields separated by commas, a field holding a
comma, a quote or a line break in quotation marks, and (from Anki 2.1.54)
`#key:value` header lines at the top (docs.ankiweb.net, "Importing text
files", read 2026-11-06):
- `#separator:Comma` and `#html:true` (fields may hold HTML);
- `#guid column:8`: the column holding each note's own ID. Anki matches
  notes by it when it's given, so re-importing a file updates the notes
  already made rather than duplicating them, and two words with the same
  headword (行 háng, 行 xíng) stay two notes. Without it Anki compares the
  first field, and they would clash;
- `#notetype:Basic` and `#deck:Polyglotic`: what the import dialog starts
  with (a column can name them per row instead);
- `#tags column:3`: the column of space-separated tags.

There is no `#columns:` line naming the columns (polyglotic-hq 237, from
223's QA). With names, Anki maps a note type's fields to the columns of
the same name, and its first field to column 1 whatever that column's name
(rslib's CSV metadata, 26.09.4). In an Anki whose collection began in
another language, Basic has another name (问答题, 基本型, Einfach) and so
do its fields (正面, 背面): no name matched, the back got nothing, and
every card's back was empty. With no names, Anki maps the fields in order
- the front from column 1, the back from column 2 - in any language. The
cost: the import dialog names each column by its number and the first
word's value ("1: 榴莲 (榴槤)"), not "Front" or "Reading"; Help lists them.

So the file works as it is with Anki's own Basic note type (front, back),
whatever Anki's language, and the same words come again as separate
columns (`COLUMNS`: reading, meaning, sentence, translation) for a note
type of the learner's own, mapped in the import dialog. The sentence has
the word in `<b>`; every text is escaped, because the file says it holds
HTML.

The word is column 1 and the GUID the last (polyglotic-hq project 162), so
a note type's first field gets the word, never the GUID. A file written
before, with the GUID first, says so in its own header and still finds
its notes.

A spreadsheet opening the file would take a cell starting with `=`, `+`,
`-` or `@` (their full-width forms too, or a tab or line break) as a
formula - and a line heard in a video can start with one ("- Who's
there?"). So a text cell's first such character is written as its HTML
character reference (`&#45;`): Anki shows the same text, and a
spreadsheet sees text. (A leading apostrophe, the usual fix, would show
on the learner's card.)

The same words also go into a deck file (`.apkg`, decision 0028) as
`DeckNote`s with the same GUIDs and escaped text; `ports.anki_deck` states
what writes the file. Importing one after the other never doubles a word:
Anki finds its note by the GUID and, the note types differing (Basic, ours),
leaves it as the first file made it (tests/test_anki_import.py).

The GUID is made from the dictionary entry's ID, so it stays the same
whenever the word is exported. (An entry merged into another by a
dictionary update gets the other's ID, and so a new note.)

Each deck note carries when the word last changed in the app (`changed`),
not when the file was written: Anki updates a note it has only from a
newer one ("update if newer", its import screen's default), so exporting
an unchanged word again leaves the learner's own edits to its note - the
Notes field, their tags, Anki's "leech" and "marked" - as they are, and a
word that changed updates (polyglotic-hq project 162). An update replaces
the whole note, the learner's edits with it.
"""

import csv
import html
import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from polyglotic_desktop.core.learning.saved_words import SavedWord
from polyglotic_desktop.core.learning.sentences import SavedSentence
from polyglotic_desktop.ports.anki_deck import DeckNote, DeckSentence

HEADERS = (
    "#separator:Comma",
    "#html:true",
    "#guid column:8",
    "#notetype:Basic",
    "#deck:Polyglotic",
    "#tags column:3",
)
COLUMNS = (  # the columns in order - named in Help, not in the file (237)
    "Front",
    "Back",
    "Tags",
    "Reading",
    "Meaning",
    "Sentence",
    "Translation",
    "GUID",
)
TAG = "polyglotic"
"""Every note's tag. A saved word's category goes under it, as Anki's
hierarchical tag `polyglotic::Tricky`: ours stay together in Anki's
browser, never clash with a learner's own top-level "Tricky", and
searching `tag:polyglotic` finds them all (polyglotic-hq project 162)."""
FORMULA_STARTS = frozenset("=+-@\t\r\n＝＋－＠")
"""What makes a spreadsheet read a cell as a formula, the full-width forms
in some locales (OWASP, "CSV Injection", read 2026-11-07)."""


@dataclass(frozen=True)
class AnkiNote:
    """A word to export: its dictionary entry's text, the line it was met in
    (empty if none was kept) and that line's translation, the saved-word
    category it's in (empty if none), when the learner added it and when
    the word last changed in the app (its text or its line)."""

    entry_id: str
    headword: str  # simplified Chinese, or the word in any other language
    traditional: str  # "" for every language but Chinese
    reading: str
    meaning: str
    sentence: str
    translation: str
    category: str
    added: datetime
    changed: datetime


def guid(entry_id: str) -> str:
    """The note's stable ID: from the dictionary entry, nothing else."""
    return f"polyglotic:{entry_id}"


def display_headword(note: AnkiNote) -> str:
    """Both scripts when they differ ("电脑 (電腦)")."""
    if note.traditional and note.traditional != note.headword:
        return f"{note.headword} ({note.traditional})"
    return note.headword


def marked_sentence(note: AnkiNote) -> str:
    """The sentence as HTML with the word in `<b>`: its simplified or
    traditional form where it occurs (a Chinese form anywhere; an English
    one as a whole word, any case; a word of any other language as a
    whole word in any case - "Дом" for дом, never the дом in домой -
    unless it is written without spaces between words, as Japanese and
    Thai are: then anywhere). Unchanged if the word isn't found in it -
    an inflected form, say."""
    sentence = note.sentence
    for form in sorted({note.headword, note.traditional} - {""}, key=len, reverse=True):
        if _unspaced(form):
            at = sentence.find(form)
            span = (at, at + len(form)) if at >= 0 else None
        else:
            whole = re.search(
                rf"(?<!\w){re.escape(form)}(?!\w)", sentence, re.IGNORECASE
            )
            span = whole.span() if whole else None
        if span:
            start, end = span
            return (
                html.escape(sentence[:start], quote=False)
                + "<b>"
                + html.escape(sentence[start:end], quote=False)
                + "</b>"
                + html.escape(sentence[end:], quote=False)
            )
    return html.escape(sentence, quote=False)


def _has_han(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


# scripts written without spaces between words: kana, Han, Thai, Lao,
# Burmese, Khmer
_UNSPACED = (
    ("぀", "ヿ"),
    ("一", "鿿"),
    ("฀", "໿"),
    ("က", "႟"),
    ("ក", "៿"),
)


def _unspaced(text: str) -> bool:
    return any(low <= c <= high for c in text for low, high in _UNSPACED)


def language(note: AnkiNote) -> str:
    """`zh` for a Chinese word (it has a Han character), else `en` - a
    word of Chinese's or English's learning data."""
    return "zh" if _has_han(note.headword) else "en"


def deck_note(note: AnkiNote, pack_language: str | None = None) -> DeckNote:
    """The word as a note for the deck file: the same escaped text and the
    same GUID and tags as the CSV. `pack_language`: the language the word
    is learned in, for a pack language's learning data (`ru`; decision
    0175) - a Japanese word has Han characters and isn't Chinese; None:
    Chinese's or English's, told by the word (`language`)."""
    escape = html.escape
    return DeckNote(
        guid(note.entry_id),
        pack_language or language(note),
        escape(note.headword, quote=False),
        escape(note.traditional, quote=False)
        if note.traditional != note.headword
        else "",
        escape(note.reading, quote=False),
        escape(note.meaning, quote=False),
        marked_sentence(note),
        escape(note.translation, quote=False),
        note.entry_id,
        tuple(_tags(note).split()),
        note.changed,
    )


def deck_notes(
    notes: Iterable[AnkiNote], pack_language: str | None = None
) -> tuple[DeckNote, ...]:
    """The words as deck notes, oldest first - the CSV's order; each in
    `pack_language` if one is given (`deck_note`)."""
    return tuple(
        deck_note(n, pack_language)
        for n in sorted(notes, key=lambda n: (n.added, n.entry_id))
    )


def _tags(note: AnkiNote) -> str:
    tags = [TAG]
    if note.category:
        tags.append(f"{TAG}::" + "_".join(note.category.split()))
    return " ".join(tags)


def _back(reading: str, meaning: str, sentence: str, translation: str) -> str:
    parts = [f"<div>{p}</div>" for p in (reading, meaning) if p]
    if sentence:
        parts.append("<hr>")
        parts.append(f"<div>{sentence}</div>")
        if translation:
            parts.append(f"<div>{translation}</div>")
    return "".join(parts)


def _cell(text: str) -> str:
    """An HTML text cell that no spreadsheet runs as a formula."""
    if text and text[0] in FORMULA_STARTS:
        return f"&#{ord(text[0])};{text[1:]}"
    return text


def anki_csv(
    notes: Iterable[AnkiNote], sentences: Iterable["SentenceNote"] = ()
) -> str:
    """The words as the text of a CSV file for Anki, oldest first, then the
    saved sentences (`sentence_csv_rows`). Write it as UTF-8."""
    out = io.StringIO()
    out.write("\n".join(HEADERS) + "\n")
    writer = csv.writer(out, lineterminator="\n")
    escape = html.escape
    for note in sorted(notes, key=lambda n: (n.added, n.entry_id)):
        reading = escape(note.reading, quote=False)
        meaning = escape(note.meaning, quote=False)
        sentence = marked_sentence(note)
        translation = escape(note.translation, quote=False)
        writer.writerow(
            (
                _cell(escape(display_headword(note), quote=False)),
                _cell(_back(reading, meaning, sentence, translation)),
                _tags(note),
                _cell(reading),
                _cell(meaning),
                _cell(sentence),
                _cell(translation),
                guid(note.entry_id),
            )
        )
    writer.writerows(sentence_csv_rows(sentences))
    return out.getvalue()


# -- saved sentences (polyglotic-hq 459) ---------------------------------------------

SENTENCE_TAG = f"{TAG}::sentence"
"""A saved sentence's tag, besides `TAG` and its category's: Anki's browser
finds every sentence with `tag:polyglotic::sentence`."""
LINK_COLOURS = ("#e0559a", "#2f9e8f", "#d98a1c", "#6a7fdb", "#8e5bd8", "#3f9e4d")
"""The underlines of linked words, by link, in turn: a word and what it
is in the translation share one. Mid-tone, so each shows on Anki's day
and night backgrounds alike; inline, so a CSV's Basic cards show them
too."""


def sentence_guid(sentence_id: str) -> str:
    """A saved sentence's note's stable ID: from the sentence's own ID."""
    return f"polyglotic:sentence:{sentence_id}"


@dataclass(frozen=True)
class SentenceNote:
    """A saved sentence as a note: `front` - what was said, its saved words
    in `<b>` - `original` and `translation` with their linked words
    underlined in the link's colour (all three HTML, escaped), the
    speakers' labels, its category's name, when it was saved."""

    sentence_id: str
    front: str
    original: str
    translation: str
    speakers: str
    category: str
    saved_at: datetime


def sentence_note(
    sentence: SavedSentence, words: Sequence[SavedWord], category: str
) -> SentenceNote:
    """`sentence` as a note: its saved `words` (those of its learning data)
    marked on the front, its key links underlined on the back."""
    originals: list[tuple[str, list[tuple[int, int, str]]]] = []
    translations: list[tuple[str, list[tuple[int, int, str]]]] = []
    link = 0
    for part in sentence.parts:
        on_original: list[tuple[int, int, str]] = []
        on_translation: list[tuple[int, int, str]] = []
        for each in part.links:
            if not each.key:
                continue
            style = _underline(LINK_COLOURS[link % len(LINK_COLOURS)])
            on_original.append((*each.original, style))
            on_translation.append((*each.translation, style))
            link += 1
        originals.append((part.original, on_original))
        translations.append((part.translation, on_translation))
    return SentenceNote(
        sentence.id,
        _with_words(sentence.original, words),
        _rendered(sentence.original, originals),
        _rendered(sentence.translation, translations),
        " · ".join(html.escape(s, quote=False) for s in sentence.speakers),
        category,
        sentence.saved_at,
    )


def _underline(colour: str) -> str:
    return f'<span style="border-bottom: 2px solid {colour}">'


def _with_words(text: str, words: Sequence[SavedWord]) -> str:
    """`text` as HTML, each saved word's form in it in `<b>` - a Chinese
    or Japanese form anywhere, any other a whole word in any case - longest
    first, never overlapping."""
    spans: list[tuple[int, int]] = []
    forms = sorted({f for w in words for f in w.forms if f}, key=len, reverse=True)
    for form in forms:
        if _unspaced(form):
            pattern = re.escape(form)
        else:
            pattern = rf"(?<!\w){re.escape(form)}(?!\w)"
        for found in re.finditer(pattern, text, re.IGNORECASE):
            start, end = found.span()
            if not any(a < end and start < b for a, b in spans):
                spans.append((start, end))
    return _spanned(text, [(a, b, "<b>") for a, b in sorted(spans)])


def _spanned(text: str, spans: Sequence[tuple[int, int, str]]) -> str:
    """`text` as HTML with each `[start, end)` in the tag given (`<b>` or a
    `<span ...>`): escaped, and overlapping or out-of-range spans left
    out."""
    out = []
    at = 0
    for start, end, tag in sorted(spans):
        if start < at or end > len(text) or start >= end:
            continue
        close = "</b>" if tag == "<b>" else "</span>"
        out.append(html.escape(text[at:start], quote=False))
        out.append(tag + html.escape(text[start:end], quote=False) + close)
        at = end
    out.append(html.escape(text[at:], quote=False))
    return "".join(out)


def _rendered(
    joined: str, pieces: Sequence[tuple[str, list[tuple[int, int, str]]]]
) -> str:
    """`joined` (the parts' text as the sentence joined it) as HTML, each
    part's spans in place: each part found in it in turn. A part not found
    there (it shouldn't be) leaves the rest unmarked."""
    out = []
    at = 0
    for text, spans in pieces:
        trimmed = text.strip()
        if not trimmed:
            continue
        lead = len(text) - len(text.lstrip())
        start = joined.find(trimmed, at)
        if start < 0:
            break
        out.append(html.escape(joined[at:start], quote=False))
        shifted = [(a - lead, b - lead, tag) for a, b, tag in spans]
        out.append(_spanned(trimmed, shifted))
        at = start + len(trimmed)
    out.append(html.escape(joined[at:], quote=False))
    return "".join(out)


def _sentence_tags(note: SentenceNote) -> str:
    tags = [TAG, SENTENCE_TAG]
    if note.category:
        tags.append(f"{TAG}::" + "_".join(note.category.split()))
    return " ".join(tags)


def sentence_csv_rows(notes: Iterable[SentenceNote]) -> list[tuple[str, ...]]:
    """The sentences as rows of the CSV (`COLUMNS`), oldest first: Basic's
    front is what was said, its saved words in bold; the back the same with
    its links underlined, the translation, and who said it. Reading and
    Meaning empty."""
    rows: list[tuple[str, ...]] = []
    for note in sorted(notes, key=lambda n: (n.saved_at, n.sentence_id)):
        back = f"<div>{note.original}</div><div>{note.translation}</div>"
        if note.speakers:
            back += f"<div>{note.speakers}</div>"
        rows.append(
            (
                _cell(note.front),
                _cell(back),
                _sentence_tags(note),
                "",
                "",
                _cell(note.original),
                _cell(note.translation),
                sentence_guid(note.sentence_id),
            )
        )
    return rows


def deck_sentences(
    notes: Iterable[SentenceNote], language: str
) -> tuple[DeckSentence, ...]:
    """The sentences as notes for the deck file, oldest first, in
    `language`'s sentence note type and sub-deck (the language they were
    spoken in)."""
    return tuple(
        DeckSentence(
            sentence_guid(note.sentence_id),
            language,
            note.front,
            note.original,
            note.translation,
            note.speakers,
            note.sentence_id,
            tuple(_sentence_tags(note).split()),
            note.saved_at,
        )
        for note in sorted(notes, key=lambda n: (n.saved_at, n.sentence_id))
    )
