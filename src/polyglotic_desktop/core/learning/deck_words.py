"""Deck words: the line a word was in when the learner put it in the deck.

A word going into the deck ("Learn", "Add to deck") from a caption keeps
what a card made from it needs: the dictionary entry's text, the caption
line (the sentence), that line's translation and the time. It stays on
this PC, like a saved word's source sentence - only the status goes to the
server. It is **not** a saved word: saving puts a word in a category,
colours it in captions and syncs; learning is a status. The two can both
be true of a word (decision 0026).
"""

from dataclasses import dataclass
from datetime import datetime

from polyglotic_desktop.core.shared import EntryId


@dataclass(frozen=True)
class DeckWord:
    entry_id: EntryId
    headword: str
    traditional: str  # "" for English
    reading: str
    meaning: str
    sentence: str  # the line it was in; "" if put in the deck without one
    translation: str
    learned_at: datetime
