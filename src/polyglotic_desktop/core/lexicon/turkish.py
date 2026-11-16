"""Turkish words as a dictionary lists them: what a word in a caption may
be made from, for a pack that hasn't got the word itself (polyglotic-hq
388).

Turkish builds a word by adding suffixes to a stem, one after another:
evlerimizde is ev (house) + ler (plural) + imiz (our) + de (in), "in our
houses"; verilebilecek is ver (give) + il (passive) + ebil (can) + ecek
(future). Wiktionary's tables list about a hundred forms of a noun and
nine hundred of a verb, but not the participles, the verbal nouns or
"can", nor a case after them: a fifth of the probe's words were missing
in the installed app, which has no simplemma (decision 0123). `bases`
takes suffixes off a word, from its end, in the order Turkish puts them
on (`_SUFFIXES`), and gives the stems it may be made from, the least cut
off first - a verb's stem as the infinitive the dictionary lists it by
(ver: vermek). The pack decides: a guess is looked up only when the word
itself isn't found, and the first guess the pack has is the one shown
(`core.lexicon.basic`).

The rules are this module's own, from the grammar every Turkish course
teaches: the suffixes and their order; the buffer letters y, n and s,
written after a vowel only, and a suffix starting with a vowel after a
consonant only; a stem's p, ç, t, k written b, c, d, ğ before a vowel,
and the high vowel some nouns lose (şehir: şehri). Vowel harmony is
written loosely - every vowel is tried - for loanwords keep their own
(saat: saati). No analyser's code or data is used.

Names take their suffixes after an apostrophe (Afrika'daki), so a
capitalised word inside a sentence is a name, cut only where a compound
name's last word ends in its possessive (Pasifik Okyanusu: okyanus):
`name_bases`. Turkish's capital of i is İ, and of ı I: Python's lower
case of "İki" is "i̇ki", with a combining dot, and of "Işık" "işık", so
neither was found (`lower`).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

_ARCHIPHONEMES = {
    "I": "ıiuü",  # the high vowel, by four-way harmony
    "A": "ae",  # the low vowel, by two-way harmony
    "D": "dt",  # d, t after a voiceless consonant
    "C": "cç",
    "K": "kğ",  # k, ğ before a vowel
}


@dataclass(frozen=True)
class _Slot:
    """Where a suffix stands in a word: what it makes (a noun "N", a verb
    "V" or a finished word "*") and its place among those (the higher,
    the later it is put on); what must stand before it, with suffixes up
    to which place."""

    makes: str
    place: int
    before: str
    before_place: int


_COPULA = _Slot("*", 6, "*", 5)  # -dir, -ydi, -sin: after a noun or a tense
_CONVERB = _Slot("*", 6, "V", 4)  # -erek, -ip, -ince, -meden
_TENSE = _Slot("V", 5, "V", 4)  # -iyor, -miş, -di, -ir, -ecek, -meli
_NEGATIVE = _Slot("V", 4, "V", 3)  # -me, -eme
_ABILITY = _Slot("V", 4, "V", 4)  # -ebil, after a negative too: gelmeyebilir
_VOICE = _Slot("V", 3, "V", 3)  # -il, -in, -dir, -t, -iş: passive, causative...
_VERB_OF_NOUN = _Slot("V", 3, "N", 0)  # -le, -leş: tamamla, of tamam
_NOUN_OF_VERB = _Slot("N", 0, "V", 4)  # -en, -dik, -me, -mek, -iş, -ecek
_CASE = _Slot("N", 3, "N", 2)  # -i, -e, -de, -den, -in, -le
_KI = _Slot("N", 0, "N", 3)  # -ki after a case: evdeki, "the one in the house"
_POSSESSIVE = _Slot("N", 2, "N", 1)  # -im, -in, -i, -imiz, -iniz, -leri
_PLURAL = _Slot("N", 1, "N", 0)  # -ler
_NOUN_OF_NOUN = _Slot("N", 0, "N", 0)  # -lik, -li, -siz, -ci, -sel, -ce

_SUFFIXES = (
    (_COPULA, "DIr DIrlAr"),
    (_TENSE, "Iyor mIş DI Ar Ir +r mAz +yAmAz AmAz mAlI sA +yAcAK AcAK"),
    (_COPULA, "+yDI DI +ymIş mIş +ysA sA +yken ken +yIm Im sIn +yIz Iz"),
    (_COPULA, "sInIz +nIz sInlAr lAr +m +n +k"),
    (_CONVERB, "+yArAk ArAk +yIp Ip +yIncA IncA mAdAn mAksIzIn DIkçA +yAlI AlI"),
    (_NEGATIVE, "mA mI +yAmA AmA"),
    (_ABILITY, "+yAbil Abil"),
    (_VOICE, "Il In +n DIr t Ir Iş"),
    (_VERB_OF_NOUN, "lA lAş lAn lAt"),
    (_NOUN_OF_VERB, "+yAn An DIK mAk mA +yIş Iş +yAcAK AcAK mAzlIK +yIcI IcI"),
    (_CASE, "+yI I +yA A DA DAn +nIn In +ylA lA CA ~nI ~nA ~ndA ~ndAn ~nlA"),
    (_KI, "ki"),
    (_POSSESSIVE, "Im +m In +n +sI I ImIz +mIz InIz +nIz lArI"),
    (_PLURAL, "lAr"),
    (_NOUN_OF_NOUN, "lIK lI sIz CI sAl CIK DAş CA"),
)
"""Every suffix, as a pattern of `_ARCHIPHONEMES`, by its slot. One
written with a buffer letter is a pattern of its own: "+" after a vowel
(the y of -yAn, the n of -nIn), "~" after the high vowel of a possessive
(evi-n-de). One starting with a vowel stands after a consonant. Where two
readings cut a word alike, the one listed first is tried first: -dir is
"is" (vardır: var) before it is a causative; -di a verb's past (yazdı:
yazmak) before a noun's "was"."""

_VOWELS = frozenset("aeıioöuü")
_BACK = frozenset("aıou")
_HIGH_VOWELS = frozenset("ıiuü")


def _spelled(pattern: str) -> list[str]:
    """Every way a suffix's pattern is written ("DA": da, de, ta, te)."""
    return ["".join(p) for p in product(*(_ARCHIPHONEMES.get(c, c) for c in pattern))]


_Rule = tuple[str, _Slot, frozenset[str] | None, int]


def _rules() -> dict[str, list[_Rule]]:
    """The last letter of a suffix -> (the suffix as written, its slot, the
    letters the stem before it must end in (None: any), its order in
    `_SUFFIXES`)."""
    consonant = frozenset("bcçdfgğhjklmnprsştvyz")
    out: dict[str, list[_Rule]] = {}
    for order, (slot, patterns) in enumerate(_SUFFIXES):
        for pattern in patterns.split():
            needs: frozenset[str] | None = None
            if pattern[0] == "+":
                needs, pattern = _VOWELS, pattern[1:]
            elif pattern[0] == "~":
                needs, pattern = _HIGH_VOWELS, pattern[1:]
            elif pattern[0] in "IA":
                needs = consonant
            for text in _spelled(pattern):
                rules = out.setdefault(text[-1], [])
                if not any(r[:3] == (text, slot, needs) for r in rules):
                    rules.append((text, slot, needs, order))
    return out


_BY_LAST_LETTER = _rules()
_HARDENED = {"b": "p", "c": "ç", "d": "t", "ğ": "k", "g": "k"}
"""A stem's last consonant before a vowel -> as the dictionary writes it
(kitabı: kitap; ağacı: ağaç; kanadı: kanat; çocuğu: çocuk; rengi: renk)."""
_HIGH = {"a": "ı", "ı": "ı", "o": "u", "u": "u", "e": "i", "i": "i", "ö": "ü", "ü": "ü"}
"""A vowel -> the high vowel that harmonises with it."""
_IYOR = ("ıyor", "iyor", "uyor", "üyor")
MAX_SUFFIXES = 7
"""The most suffixes taken off one word (kullanılmamasından has six)."""
SHORTEST = 2
"""The shortest stem guessed (ol, et, ev, su)."""
SHORTEST_NAME = 3
"""The shortest stem a name is cut to (Adası: ada; not Bali: bal)."""


def lower(word: str) -> str:
    """`word` in lower case as Turkish writes it: I is ı, İ is i."""
    return word.replace("I", "ı").replace("İ", "i").lower()


def _last_vowel(stem: str) -> str:
    return next((c for c in reversed(stem) if c in _VOWELS), "")


def infinitive(stem: str) -> str:
    """A verb's stem as the dictionary lists it: ver, vermek; al, almak."""
    return stem + ("mak" if _last_vowel(stem) in _BACK else "mek")


def _restored(stem: str, suffix: str) -> list[str]:
    """The stem as the dictionary may write it, `suffix` taken off: as cut,
    then with its last consonant hard again before a vowel (kitab:
    kitap), the high vowel it lost put back (şehr: şehir; burn: burun), or
    the vowel -Iyor took (anl: anla; söyl: söyle)."""
    out = [stem]
    if suffix[0] not in _VOWELS or len(stem) < 2:
        return out
    last = stem[-1]
    if last in _HARDENED:
        out.append(stem[:-1] + _HARDENED[last])
    if last not in _VOWELS and stem[-2] not in _VOWELS:
        vowel = _HIGH.get(_last_vowel(stem), "")
        if vowel:
            out.append(stem[:-1] + vowel + last)
    if suffix.startswith(_IYOR) and last not in _VOWELS:
        out += [stem + "a", stem + "e"]
    return out


def stems(word: str) -> list[tuple[str, str]]:
    """Every (stem, what it is: "N", "V" or "*") a lower-case `word` may be
    made from, its suffixes taken off in Turkish's order: the least cut
    off first, then the fewest suffixes, then by `_SUFFIXES`' order. A
    stem as the dictionary writes it (kitab: kitap) counts as cut a letter
    shorter, after a stem as cut: budur is bu + dur before it is but (a
    buttock); kızla kız + la, not kızıl."""
    found: dict[tuple[str, str], tuple[int, int, int]] = {}
    seen: set[tuple[str, str, int]] = set()
    todo = [(word, "*", 6, 0)]
    while todo:
        stem, makes, place, taken = todo.pop()
        if taken >= MAX_SUFFIXES:
            continue
        for text, slot, needs, rule in _BY_LAST_LETTER.get(stem[-1:], ()):
            cut = len(stem) - len(text)
            if cut < SHORTEST or not stem.endswith(text):
                continue
            if slot.place > place or makes not in ("*", slot.makes):
                continue
            if needs is not None and stem[cut - 1] not in needs:
                continue
            for n, base in enumerate(_restored(stem[:cut], text)):
                order = (-cut + (n > 0), taken + 1, rule)
                key = (base, slot.before)
                found[key] = min(found.get(key, order), order)
                state = (base, slot.before, slot.before_place)
                if state not in seen:
                    seen.add(state)
                    todo.append((base, slot.before, slot.before_place, taken + 1))
    return [key for key, _ in sorted(found.items(), key=lambda item: item[1])]


def bases(word: str) -> tuple[str, ...]:
    """What a Turkish word may be made from, likeliest first: the word in
    Turkish lower case (Işık: ışık); then the stems its suffixes leave,
    the least cut off first - a verb's as its infinitive (verilen:
    vermek; never as written, which finds other words: vardı-r is no
    form of varmak, bırak-ılan no conjunction), a noun's as written
    (evlerinde: ev). Each, after it, with the circumflex the dictionary
    writes and captions mostly don't (imkanı: imkân). A name's suffixes
    after its apostrophe are cut off (`name_bases`). Guesses only: tried
    when the pack hasn't got the word."""
    if "'" in word or "’" in word:
        return name_bases(word)
    plain = lower(word)
    out = [plain] if plain != word.lower() else []
    for stem, makes in stems(plain):
        if makes == "V":
            out.append(infinitive(stem))
        elif makes == "N":
            out += [stem, circumflexed(stem)]
        else:
            out += [stem, circumflexed(stem), infinitive(stem)]
    return tuple(dict.fromkeys(w for w in out if w != word))


_CIRCUMFLEXED = (("ka", "kâ"), ("ga", "gâ"), ("la", "lâ"))


def circumflexed(word: str) -> str:
    """`word` with the â the dictionary writes after k, g and l, where
    captions often write a (imkan: imkân; rüzgar: rüzgâr; lazım: lâzım)."""
    for plain, marked in _CIRCUMFLEXED:
        word = word.replace(plain, marked)
    return word


_NAME_ENDINGS = tuple(
    (text, needs)
    for pattern, needs in (("I", None), ("sI", _VOWELS), ("lArI", None), ("lAr", None))
    for text in _spelled(pattern)
)
"""What a compound name's last word may end in: its possessive (Birleşik
Devletleri, Pasifik Okyanusu, Kilimanjaro Dağı) or plural."""


def name_bases(word: str) -> tuple[str, ...]:
    """What a name may be, likeliest first: the name before its apostrophe
    (Afrika'daki: Afrika), its İ as i (İsveç'te: isveç), then without a
    compound name's possessive or plural (Okyanusu'nda: Okyanus;
    Devletler'deki: Devlet) - cut no further: Roma'da is no form of rom
    (rum), nor Atlantik one of atlamak."""
    head = word.replace("’", "'").split("'")[0]
    out = [head]
    for text, needs in _NAME_ENDINGS:
        cut = len(head) - len(text)
        if (
            head.endswith(text)
            and cut >= SHORTEST_NAME
            and (needs is None or head[cut - 1] in needs)
            and (cut > SHORTEST_NAME or needs is not None)
        ):
            out.append(head[:cut])
    out += [w.replace("İ", "i") for w in out if "İ" in w]
    return tuple(dict.fromkeys(w for w in out if w != word))
