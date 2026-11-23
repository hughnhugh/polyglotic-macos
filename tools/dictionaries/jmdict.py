"""Reading JMdict, as jmdict-simplified's JSON (one zip, one JSON file).

Each word has an `id` (JMdict's own sequence number, stable across
releases - the key its entry ID is hashed from, decision 0007), its
written forms in kanji (`kanji`) and kana (`kana`), each with a `common`
flag and tags (`sK`: search-only), and senses with English glosses and
`misc` tags (`uk`: usually written in kana alone).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from polyglotic_desktop.ports.word_classes import SenseClasses
from tools.dictionaries.sense_classes import jm

MAX_MEANINGS = 8  # senses per entry, as for Wiktionary's


@dataclass(frozen=True)
class JmdictWord:
    """One JMdict entry. `kanji` and `kana` are its written forms, the
    common ones first as JMdict lists them; `usually_kana` when its first
    sense is marked "usually written using kana alone", or its kanji are
    only for search (`search_only`)."""

    seq: str
    kanji: tuple[str, ...]
    kana: tuple[str, ...]
    common: bool
    usually_kana: bool
    meanings: tuple[str, ...]
    sense_classes: tuple[SenseClasses, ...] = ()

    @property
    def headword(self) -> str:
        """How it's written: its first kanji form, or its kana if it has
        none or is usually written in kana."""
        if self.kanji and not self.usually_kana:
            return self.kanji[0]
        return self.kana[0]

    @property
    def reading(self) -> str:
        return self.kana[0] if self.kanji else ""

    @property
    def written(self) -> tuple[str, ...]:
        """Every form it can be written in, the headword first."""
        return tuple(dict.fromkeys((self.headword, *self.kanji, *self.kana)))


SEARCH_ONLY = "sK"
"""JMdict's tag for a written form kept only so a search finds it."""


def search_only(forms: object) -> bool:
    """Whether a word's kanji forms (`forms`, JMdict's `kanji`) are all
    search-only (`SEARCH_ONLY`): the word is written in kana. The particle
    の is listed with 乃 and 之, both search-only; its entry was headed 乃,
    ranked by 乃 (4,858th), and の, the commonest word, opened on 幅
    ("cloth breadth") and 野 ("field") first (polyglotic-hq 461)."""
    kanji = [f for f in forms if isinstance(f, dict)] if isinstance(forms, list) else []
    return bool(kanji) and all(SEARCH_ONLY in (f.get("tags") or ()) for f in kanji)


def _texts(forms: object) -> list[tuple[str, bool]]:
    out = []
    for form in forms if isinstance(forms, list) else ():
        if isinstance(form, dict) and isinstance(form.get("text"), str):
            out.append((form["text"], bool(form.get("common"))))
    return out


def read(path: Path) -> tuple[dict[str, str], list[JmdictWord]]:
    """The file's header (version, date) and its words."""
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".json")]
        if len(names) != 1:
            raise ValueError(f"{path.name}: expected one JSON file, found {names}")
        data = json.loads(archive.read(names[0]))
    header = {
        "version": str(data.get("version", "")),
        "dictDate": str(data.get("dictDate", "")),
    }
    words = []
    for word in data["words"]:
        kanji, kana = _texts(word.get("kanji")), _texts(word.get("kana"))
        if not kana:
            continue
        senses = [s for s in word.get("sense", ()) if isinstance(s, dict)]
        meanings = []
        classes = []
        for sense in senses:
            glosses = [
                g["text"]
                for g in sense.get("gloss", ())
                if isinstance(g, dict) and isinstance(g.get("text"), str)
            ]
            if glosses:
                meanings.append("; ".join(glosses))
                classes.append(jm(sense.get("partOfSpeech", ())))
        if not meanings:
            continue
        words.append(
            JmdictWord(
                seq=str(word["id"]),
                kanji=tuple(t for t, _ in kanji),
                kana=tuple(t for t, _ in kana),
                common=any(c for _, c in kanji + kana),
                usually_kana=(bool(senses) and "uk" in senses[0].get("misc", ()))
                or search_only(word.get("kanji")),
                meanings=tuple(meanings[:MAX_MEANINGS]),
                sense_classes=tuple(classes[:MAX_MEANINGS]),
            )
        )
    return header, words
