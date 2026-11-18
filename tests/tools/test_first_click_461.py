"""First clicks that opened on the wrong entry in 448's and 461's audits of
the published packs (polyglotic-hq 448, 461): a verb's aspect partner and a
participle opened on the other verb before their own entry; an entry whose
only line points at another word showed that line and no meaning; Hindi's
के लिए opened on लेना, "to take", and its future forms found nothing."""

from __future__ import annotations

from tools.dictionaries import kaikki, packs


def sense(gloss: str, *tags: str) -> dict[str, object]:
    return {"glosses": [gloss], "tags": list(tags)}


def form_of(gloss: str, lemma: str, *tags: str) -> dict[str, object]:
    return {
        "glosses": [gloss],
        "form_of": [{"word": lemma}],
        "tags": ["form-of", *tags],
    }


def obj(word: str, pos: str, *senses: dict[str, object], **more: object) -> dict:
    return {"word": word, "pos": pos, "senses": list(senses), **more}


def row(form: str, *tags: str) -> dict[str, object]:
    return {"form": form, "tags": list(tags)}


def test_a_verbs_aspect_partner_is_no_form_of_it() -> None:
    """Polish's zacząć lists zaczynać, its imperfective partner, in its
    table: another verb with its own page, not an inflection, so zaczynać
    opens on its own entry. Its inflections, aspect tag and all, stay."""
    lines = [
        obj(
            "zacząć",
            "verb",
            sense("to start, to begin", "perfective"),
            forms=[
                row("zaczynać", "imperfective"),
                row("zaczął", "masculine", "past", "perfective", "singular"),
            ],
        ),
        obj("zaczynać", "verb", sense("to start, to begin", "imperfective")),
    ]
    words = kaikki.read_language(lines)
    assert "zaczynać" not in words.forms
    assert words.forms["zaczął"] == {"zacząć"}
    assert kaikki.aspect_partner({"imperfective", "rare"})
    assert not kaikki.aspect_partner({"imperfective", "infinitive"})


def test_a_participle_that_is_an_adjective_of_its_own_comes_first() -> None:
    """German's "fehlend" is fehlen's present participle and an adjective,
    "missing": its card had opened on fehlen, "to be absent"."""
    lines = [
        obj(
            "fehlen",
            "verb",
            sense("to be absent"),
            forms=[row("fehlend", "participle", "present"), row("fehlt", "present")],
        ),
        obj(
            "fehlend",
            "verb",
            form_of("present participle of fehlen", "fehlen", "participle", "present"),
        ),
        obj("fehlend", "adj", sense("missing")),
    ]
    words = kaikki.read_language(lines)
    used, _ = packs.own_first(words, None)
    assert "fehlend" in used
    assert "fehlt" not in used


def test_an_entry_that_only_points_at_a_word_opens_on_that_word() -> None:
    """Hindi's इश्क is only "nuqtaless form of इश्क़ (iśq)", with no
    form-of link: it is now that word's form, whose entry comes first - its
    own stays, so its ID does. A gloss that goes on to say what it means,
    or names no kind of form, stays a meaning."""
    lines = [
        obj("इश्क़", "noun", sense("love")),
        obj("इश्क", "noun", sense("nuqtaless form of इश्क़ (iśq)", "masculine")),
        obj(
            "possiamo",
            "verb",
            sense("first-person plural present indicative of potere"),
        ),
        obj("potere", "verb", sense("to be able to")),
        obj("régimen", "noun", sense("a form of government")),
        obj("ความดี", "noun", sense("abstract noun of ดี (dii): goodness")),
    ]
    words = kaikki.read_language(lines)
    assert words.forms["इश्क"] == {"इश्क़"}
    assert words.lemma_first["इश्क"] == {"इश्क़"}
    assert {e.key for e in words.entries} >= {"इश्क|noun|", "possiamo|verb|"}
    assert ("possiamo", "potere") in words.verb_forms
    assert "régimen" not in words.forms and "ความดี" not in words.forms
    assert kaikki.referred_to(sense("form of address")) == []


def test_hindi_future_forms_are_found_as_captions_write_them() -> None:
    """Wiktionary's tables write बनायेगी (will make); captions write
    बनाएगी. Not inside a cluster: प्यार stays as it is."""
    assert packs.hindi_spellings("बनायेगी") == {"बनाएगी"}
    assert packs.hindi_spellings("गये") == {"गए"}
    assert packs.hindi_spellings("जायेंगे") == {"जाएँगे", "जाएंगे"}
    assert packs.hindi_spellings("प्यार") == set()


def test_the_second_word_of_a_hindi_postposition_has_its_meanings() -> None:
    """के लिए ("for") gives लिए an entry of its own: लिए alone had opened
    on लेना, "to take", whose form it also is."""
    lines = [
        obj(
            "के लिए",
            "postp",
            {"glosses": ["marks a recipient or beneficiary: for", "benefactive"]},
        ),
        obj("के साथ", "postp", sense("with")),
        obj("आम तौर पर", "adv", sense("usually")),
        obj("में से", "postp", sense("through")),
    ]
    found = packs.phrase_words(lines, packs.HINDI.phrase_heads)
    assert [(o["word"], o["pos"]) for o in found] == [
        ("लिए", "postp"),
        ("साथ", "postp"),
    ]
    assert found[0]["senses"] == [
        {"glosses": ["के लिए: marks a recipient or beneficiary: for"]}
    ]
