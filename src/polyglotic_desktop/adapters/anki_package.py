"""Anki deck file (.apkg) with Polyglotic's own note types (project 099).

genanki (MIT) writes the collection's tables; this module is the note
types - fields, cards, Margin's card style (decision 0028) - and the zip.
Anki identifies things by number, so the note types and decks have fixed
IDs, and each note its GUID (`polyglotic:<entry ID>`): importing again
updates the notes in place, and a word the CSV brought first isn't doubled.

A note type and a sub-deck per language learned: Chinese's and English's,
and one for each pack language (decision 0175; polyglotic-hq 391) -
"Polyglotic Russian" in `Polyglotic::Russian` - with the same fields and
cards, the language's own voice for Anki's text-to-speech, and its IDs
worked out from its code (`_ids`), so a language added later needs no
table here and keeps its IDs for good.

The fields, in 085's order: Word, Reading, Meaning, Sentence (the word in
`<b>`), Translation, WordAudio, SentenceAudio, Source, Traditional, Notes,
the two flags Listen and Recall, and EntryID (last). Cards: Recognise always;
Listen and Recall only for notes whose flag field isn't empty (the
field's text is the card's label, which also tells Anki the card is wanted).
Each back adds only what its front didn't show (polyglotic-hq 162):
- Recognise: the word and its line, the word read aloud (085's choice, for
  now); the back adds the reading, the meaning and the line's translation;
- Listen: the word heard; the back is the whole note;
- Recall: the meaning and the line's translation, never the reading (IPA
  nearly spells an English word; pinyin would make it "write it from the
  pinyin") or the line itself (it holds the word); the back adds the word,
  its reading and its line, and says it.
Audio is
Anki's own text-to-speech (`{{tts}}`) until a word has a sound file. The
clip fields stay empty for now.

Anki updates what it already has from a file only when the file's copy is
newer (its import screen's default, "If newer"). So each note's time is
when its word last changed in the app (`DeckNote.changed`) and each note
type's is `NOTE_TYPES_CHANGED`, not the time of writing: exporting again
leaves the learner's own edits alone - to a note or to our note types -
until we change that word, or the cards (polyglotic-hq project 162).

The temporary collection is made in a folder of ours and deleted before
the bytes are returned (genanki's own `write_to_file` leaves its file in
the system's temp folder, and these are the learner's words).
"""

import io
import itertools
import json
import re
import sqlite3
import tempfile
import time
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from polyglotic_desktop.ports.anki_deck import DeckNote

if TYPE_CHECKING:
    import genanki

DECK = "Polyglotic"
_CODE = re.compile(r"[a-z]{2,3}")
"""A learned language's code (`core.lexicon.packs.CODE`'s rule)."""
NOTE_TYPES_CHANGED = datetime(2026, 11, 7, 12, 5, tzinfo=UTC)
"""When the note types' cards or style last changed: their time in every
file. Anki updates its copy of a note type only from a newer one, and only
while the fields and card types match by name and number. So:
- set this to the time of any change to `_templates` or `CSS` (the
  fingerprint in tests/test_anki_package.py fails until it is), and the
  change reaches every deck already imported, except where the learner
  has edited our note type since;
- never add, remove or rename a field or card type: Anki would make a
  second note type and leave every word already imported on the first
  ("conflicting", tests/test_anki_import.py)."""
_LANGUAGES = {
    # code: (note type ID, deck ID, sub-deck, tts voice, note type name)
    "zh": (1_791_606_001, 1_791_606_101, "Chinese", "zh_CN", "Polyglotic Chinese"),
    "en": (1_791_606_002, 1_791_606_102, "English", "en_US", "Polyglotic English"),
}
_PACK_LANGUAGES = {
    # code: (sub-deck and note type name, tts voice)
    "ja": ("Japanese", "ja_JP"),
    "es": ("Spanish", "es_ES"),
    "ko": ("Korean", "ko_KR"),
    "fr": ("French", "fr_FR"),
    "de": ("German", "de_DE"),
    "pt": ("Portuguese", "pt_BR"),
    "it": ("Italian", "it_IT"),
    "ru": ("Russian", "ru_RU"),
    "vi": ("Vietnamese", "vi_VN"),
    "nl": ("Dutch", "nl_NL"),
    "id": ("Indonesian", "id_ID"),
    "ar": ("Arabic", "ar_SA"),
    "hi": ("Hindi", "hi_IN"),
    "pl": ("Polish", "pl_PL"),
    "tr": ("Turkish", "tr_TR"),
    "ms": ("Malay", "ms_MY"),
    "th": ("Thai", "th_TH"),
    "tl": ("Filipino", "fil_PH"),
    "cs": ("Czech", "cs_CZ"),
    "uk": ("Ukrainian", "uk_UA"),
    "yue": ("Cantonese", "zh_HK"),
    "sv": ("Swedish", "sv_SE"),
    "da": ("Danish", "da_DK"),
    "fi": ("Finnish", "fi_FI"),
}
"""The pack languages by name, each with the voice Anki's text-to-speech
asks for. One not here yet still exports, named by its code."""
_PACK_FONTS = {
    "ja": '"Yu Gothic UI", "Meiryo", "Hiragino Sans", "Noto Sans JP", sans-serif',
    "ko": '"Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
}
"""The word's and the sentence's fonts where a language needs its own: a
Chinese font draws Japanese kanji in their Chinese forms. Every other
pack language has the card's own font."""
_CJK_FONTS = '"Microsoft YaHei UI", "PingFang SC", "Noto Sans SC", sans-serif'


def _ids(code: str) -> tuple[int, int]:
    """A pack language's note type ID and deck ID, from its code alone
    (two or three letters, each 1 to 26, as a number in base 27): the same
    in every export and every version, and never Chinese's or English's."""
    n = 0
    for letter in code[:3]:
        n = n * 27 + (ord(letter) - ord("a") + 1 if "a" <= letter <= "z" else 0)
    return 1_791_610_000 + n, 1_791_640_000 + n


def _language(code: str) -> tuple[int, int, str, str, str]:
    """(note type ID, deck ID, sub-deck, tts voice, note type name)."""
    if code in _LANGUAGES:
        return _LANGUAGES[code]
    name, voice = _PACK_LANGUAGES.get(code, (code, code))
    return (*_ids(code), name, voice, f"Polyglotic {name}")


def _css(code: str) -> str:
    """The cards' style: Chinese's and English's as they always were; a
    pack language's with its own fonts for the word and the sentence."""
    if code in _LANGUAGES:
        return CSS
    rule = f".word, .sentence {{ font-family: {_CJK_FONTS}; }}\n"
    assert rule in CSS
    fonts = _PACK_FONTS.get(code)
    own = f".word, .sentence {{ font-family: {fonts}; }}\n" if fonts else ""
    return CSS.replace(rule, own)


FIELDS = (
    "Word",
    "Reading",
    "Meaning",
    "Sentence",
    "Translation",
    "WordAudio",
    "SentenceAudio",
    "Source",
    "Traditional",
    "Notes",
    "Listen",
    "Recall",
    "EntryID",
)

# Margin: the day and night colours of project 091's direction A, a pink
# marker under the word. No JavaScript; Anki adds .nightMode in night mode.
CSS = """\
.card {
  font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  font-size: 18px; line-height: 1.5; text-align: center;
  background: #f5f6f7; color: #172033;
  --rule: #d8dce3; --dim: #4b5568; --mark: #ffa8cc;
}
.card.nightMode, .nightMode .card {
  background: #11151d; color: #e9ecf1;
  --rule: #2a3140; --dim: #a3abb9; --mark: #5c2440;
}
.word, .sentence { font-family: "Microsoft YaHei UI", "PingFang SC", "Noto Sans SC", sans-serif; }
.word { font-size: 2.2em; line-height: 1.3; }
.sentence { font-size: 1.35em; line-height: 1.5; }
.sentence b, .word b {
  font-weight: inherit; white-space: nowrap;
  box-shadow: inset 0 -0.16em 0 var(--mark);
}
.reading { font-size: 1.3em; }
.meaning { font-size: 1em; }
.translation, .trad, .notes { color: var(--dim); font-size: .9em; }
.label { color: var(--dim); font-size: .7em; letter-spacing: .08em; text-transform: uppercase; }
hr { border: 0; border-top: 1px solid var(--rule); margin: 14px auto; width: 100%; }
"""


def _templates(voice: str) -> list[dict[str, str]]:
    def audio(field: str) -> str:
        return f"{{{{{field}}}}}"

    word_sound = f"{audio('WordAudio')}{{{{^WordAudio}}}}{{{{tts {voice}:Word}}}}{{{{/WordAudio}}}}"
    sentence_sound = (
        f"{audio('SentenceAudio')}"
        f"{{{{^SentenceAudio}}}}{{{{tts {voice}:Sentence}}}}{{{{/SentenceAudio}}}}"
    )
    word = '<div class="word">{{Word}}</div><div class="trad">{{Traditional}}</div>'
    reading = '<div class="reading">{{Reading}}</div>'
    meaning = '<div class="meaning">{{Meaning}}</div>'
    sentence = '<div class="sentence">{{Sentence}}</div>'
    translation = '<div class="translation">{{Translation}}</div>'
    notes = '<div class="notes">{{Notes}}</div>'
    return [
        {
            "name": "Recognise",
            "qfmt": (
                '<div class="word">{{Word}}</div>'
                "{{#Sentence}}" + sentence + "{{/Sentence}}" + word_sound
            ),
            "afmt": (
                "{{FrontSide}}<hr id=answer>"
                '<div class="trad">{{Traditional}}</div>'
                + reading
                + meaning
                + "{{#Translation}}<hr>"
                + translation
                + "{{/Translation}}"
                + notes
                + sentence_sound
            ),
        },
        {
            "name": "Listen",
            "qfmt": (
                '{{#Listen}}<div class="label">{{Listen}}</div>'
                + word_sound
                + "{{/Listen}}"
            ),
            "afmt": (
                "{{FrontSide}}<hr id=answer>"
                + word
                + reading
                + meaning
                + "{{#Sentence}}<hr>"
                + sentence
                + translation
                + "{{/Sentence}}"
                + notes
            ),
        },
        {
            "name": "Recall",
            "qfmt": (
                '{{#Recall}}<div class="label">{{Recall}}</div>'
                + meaning
                + "{{#Translation}}"
                + translation
                + "{{/Translation}}"
                + "{{/Recall}}"
            ),
            "afmt": (
                "{{FrontSide}}<hr id=answer>"
                + word
                + reading
                + "{{#Sentence}}<hr>"
                + sentence
                + "{{/Sentence}}"
                + notes
                + word_sound
            ),
        },
    ]


def _model(language: str) -> "genanki.Model":
    import genanki

    model_id, _, _, voice, name = _language(language)
    return genanki.Model(
        model_id,
        name,
        fields=[{"name": f} for f in FIELDS],
        templates=_templates(voice),
        css=_css(language),
        sort_field_index=0,
    )


class GenankiDeckWriter:
    """`AnkiDeckWriter` with genanki."""

    def build(
        self, notes: Sequence[DeckNote], *, listen: bool = False, recall: bool = False
    ) -> bytes:
        import genanki  # here, not at start: it and yaml take about 70 ms

        models: dict[str, Any] = {}
        decks: dict[str, Any] = {}

        def made(code: str) -> None:
            if code not in models:
                _, deck_id, sub, _, _ = _language(code)
                models[code] = _model(code)
                decks[code] = genanki.Deck(deck_id, f"{DECK}::{sub}")

        used: set[str] = set()
        for note in notes:
            code = note.language if _CODE.fullmatch(note.language) else "en"
            made(code)
            used.add(code)
            values = {
                "Word": note.word,
                "Reading": note.reading,
                "Meaning": note.meaning,
                "Sentence": note.sentence,
                "Translation": note.translation,
                "Traditional": note.traditional,
                "EntryID": note.entry_id,
                "Listen": "Listen" if listen else "",
                "Recall": "Recall" if recall else "",
            }
            decks[code].add_note(
                genanki.Note(
                    models[code],
                    fields=[values.get(f, "") for f in FIELDS],
                    guid=note.guid,
                    tags=list(note.tags),
                )
            )
        made("en")  # an empty export is still a file with a deck
        package: Any = genanki.Package(
            [decks[c] for c in sorted(used)] or [decks["en"]]
        )
        return _zip(package, {note.guid: note.changed for note in notes})


def _zip(package: Any, note_times: Mapping[str, datetime]) -> bytes:
    with tempfile.TemporaryDirectory(prefix="polyglotic-apkg-") as folder:
        database = Path(folder) / "collection.anki2"
        now = time.time()
        connection = sqlite3.connect(database)
        try:
            cursor = connection.cursor()
            package.write_to_db(cursor, now, itertools.count(int(now * 1000)))
            _stamp(cursor, note_times)
            connection.commit()
        finally:
            connection.close()
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(database, "collection.anki2")
            archive.writestr("media", "{}")
    return out.getvalue()


def _stamp(cursor: sqlite3.Cursor, note_times: Mapping[str, datetime]) -> None:
    """Each note's time is its word's last change, each note type's the
    cards' (genanki gives everything the time of writing)."""
    cursor.executemany(
        "UPDATE notes SET mod = ? WHERE guid = ?",
        ((_seconds(at), guid) for guid, at in note_times.items()),
    )
    (models,) = cursor.execute("SELECT models FROM col").fetchone()
    note_types = json.loads(models)
    for note_type in note_types.values():
        note_type["mod"] = _seconds(NOTE_TYPES_CHANGED)
    cursor.execute("UPDATE col SET models = ?", (json.dumps(note_types),))


def _seconds(at: datetime) -> int:
    """Anki's times: whole seconds since 1970."""
    return max(0, int(at.timestamp()))
