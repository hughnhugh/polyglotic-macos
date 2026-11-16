"""Spanish's own rules for its pack: pronominal verbs, and pronouns attached
to a verb (polyglotic-hq project 174's hard forms: "levántate", "vámonos",
"cómetelo").

Wiktionary gives a pronominal verb's senses under the plain verb, marked
reflexive ("to get up" is under levantar), and "levantarse" only as
"levantar combined with se". A learner hearing "levántate" wants "to get
up", not "to lift": so each verb with reflexive senses gets an entry of
its own for its pronominal infinitive (levantarse, those senses), and a
form whose attached pronoun is reflexive - the verb's own person: te with
tú, nos with nosotros, se with usted(es), él, ella, an infinitive or a
gerund - counts for that entry. "dímelo" stays decir: me isn't tú's.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.dictionaries.kaikki import MAX_MEANINGS, Combined, Language, WiktEntry

VERB_ENDINGS = ("ar", "er", "ir", "ír")


def is_reflexive(form: Combined) -> bool:
    """Whether the first pronoun attached is the verb's own person's."""
    first = form.pronouns[0] if form.pronouns else ""
    tags = form.tags
    if "infinitive" in tags or "gerund" in tags:
        return first == "se"
    if "first-person" in tags:
        return first == ("nos" if "plural" in tags else "me")
    if "second-person" in tags:
        if "plural" in tags:
            return first in ("os", "se")  # vosotros, ustedes
        return first == ("se" if "formal" in tags else "te")
    if "third-person" in tags:
        return first == "se"
    return False


@dataclass(frozen=True)
class Pronominal:
    entries: list[WiktEntry]
    """The new entries: "levantarse", with levantar's reflexive senses."""
    forms: dict[str, str]
    """A form with a reflexive pronoun attached -> its pronominal verb."""


def pronominal(language: Language) -> Pronominal:
    words = {e.word for e in language.entries}
    entries: dict[str, WiktEntry] = {}
    for e in language.entries:
        senses = language.reflexive.get(e.key)
        if not senses or e.pos != "verb" or not e.word.endswith(VERB_ENDINGS):
            continue
        word = f"{e.word}se"
        if word in words or word in entries:
            continue  # an entry of its own already, or a first etymology's
        number = e.key.split("|")[2]
        entries[word] = WiktEntry(
            f"{word}|verb|{number}", word, "verb", tuple(senses[:MAX_MEANINGS])
        )
    forms = {
        c.form: f"{c.lemma}se"
        for c in language.combined
        if is_reflexive(c) and f"{c.lemma}se" in entries and c.form != f"{c.lemma}se"
    }
    return Pronominal(list(entries.values()), forms)
