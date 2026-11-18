"""AnkiDeckWriter: a deck file Anki opens with one double-click (project 099).

Core decides what each word's note holds (`core.learning.anki`); the
adapter that implements this port puts the notes into a `.apkg` file with
Polyglotic's own note types. Text fields are HTML, already escaped.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class DeckNote:
    """One word as an Anki note. `guid` is the note's stable ID (the same
    as the CSV's, so the two files never double a word); `language` is
    `zh` or `en`, which picks the note type and the sub-deck; `changed` is
    when the word last changed in the app, the note's time in the file
    (Anki updates a note it has only from a newer one)."""

    guid: str
    language: str
    word: str
    traditional: str  # "" for English, or when the same as `word`
    reading: str
    meaning: str
    sentence: str  # HTML, the word in <b>
    translation: str
    entry_id: str
    tags: tuple[str, ...]
    changed: datetime


@dataclass(frozen=True)
class DeckSentence:
    """A saved sentence as an Anki note (polyglotic-hq 459): `front` is
    what was said with its saved words in <b>; `original` and
    `translation` have their linked words underlined (HTML, escaped);
    `speakers` who said it. `language` - the language it was spoken in -
    picks the sentence note type and the sub-deck; `changed` is when it
    was saved."""

    guid: str
    language: str
    front: str
    original: str
    translation: str
    speakers: str
    sentence_id: str
    tags: tuple[str, ...]
    changed: datetime


class AnkiDeckWriter(Protocol):
    def build(
        self,
        notes: Sequence[DeckNote],
        *,
        listen: bool = False,
        recall: bool = False,
        sentences: Sequence[DeckSentence] = (),
    ) -> bytes:
        """The `.apkg` file's bytes: the notes under the deck "Polyglotic",
        in a sub-deck per language. `listen` and `recall` switch on the
        optional card types for these notes. `sentences` go into their
        language's sub-deck, in a note type of their own."""
        ...
