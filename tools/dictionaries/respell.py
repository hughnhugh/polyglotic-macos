"""English respelling: how an English word sounds, in plain letters, for
learners (polyglotic-hq 449 prototyped the rules, 471 settled them and
picked the pronunciations).

    uv run python -m tools.dictionaries.respell --out build/dictionaries/respelling

writes `respelling-en.tsv` (word, respelling, alternates) for the
commonest English words (wordfreq; 10,000 by default) and `CREDITS.md`.
The English dictionary's build (`build.respellings`) writes the same
respellings into its files, for the reading line over English
(polyglotic-hq 511); this command writes them as a table to read.

**The shape** is the user's own examples (2026-11-17): syllables joined by
hyphens, the stressed one in capitals - KAY-oss, ri-SEET, SUT-uhl,
KER-nuhl, WENZ-day, uh-NEM-uh-nee.

**The sounds** are CMUdict's (American English), one spelling per sound:
- syllables: consonants go to the later syllable as far as English lets
  a syllable start, but a stressed short vowel keeps one (SUT-uhl), and a
  stressed vowel coloured by r keeps the r (STOR-ee, VAIR-ee; di-REK-ter);
- schwa is "uh", AH stressed before a consonant "u" (SUT-), AA "o" before
  a consonant and "ah" at a syllable's end, "ar", "or", "air", "eer" and
  "oor" before r ("air" for the a of carry too: American English says
  carry, marry and Mary alike - KAIR-ee), the voiced th "dh" (DHUH);
- the long i is "eye" when no consonant comes before it (EYE-luhnd,
  EYESS), else `Style.long_i`: "y", with an "e" after one closing
  consonant other than s or r (Wikipedia's respelling key: NYTE, TYME,
  MY, LY-brair-ee);
- the vowel of "book" is `Style.book` ("uu": BUUK, PUUL - "oo" would make
  pull "pool" and full "fool");
- a word-final unstressed "ee" (happy) is `Style.happy` (HAP-ee);
- an s closing a syllable is "ss" where the word ends or a vowel follows
  (KAY-oss, RESS-uh-pee: "os" reads as "oz"), else "s" (KWES-chuhn).

**Which pronunciation:** CMUdict lists about 1,700 of the commonest
10,000 more than one way, and its first isn't always the usual one
(anemone, wednesday). `respell_picks.tsv` holds 471's pick for each word
where it differs from CMUdict's first, and the alternates worth showing:
the CMUdict pronunciation nearest the first American one Wiktionary lists,
and, for heteronyms (record: REK-erd / ri-KORD), the commoner sense first
and the other with its label, chosen by hand. A word not in the file gets
CMUdict's first pronunciation that has a stressed syllable (CMUdict lists
the weak "uhnd" before "and").

Words CMUdict lacks are tried under their American spelling (organised,
programmes) and with their apostrophe (dont); the rest (about 1 %:
abbreviations, new names) get no respelling.
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.dictionaries import sources, wordfreq_ranks

PICKS = Path(__file__).with_name("respell_picks.tsv")

VOWELS = {
    "AA": "ah",
    "AE": "a",
    "AH": "uh",
    "AO": "aw",
    "AW": "ow",
    "AY": "y",
    "EH": "e",
    "ER": "er",
    "EY": "ay",
    "IH": "i",
    "IY": "ee",
    "OW": "oh",
    "OY": "oy",
    "UH": "uu",
    "UW": "oo",
}
CONSONANTS = {
    "B": "b",
    "CH": "ch",
    "D": "d",
    "DH": "dh",
    "F": "f",
    "G": "g",
    "HH": "h",
    "JH": "j",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ng",
    "P": "p",
    "R": "r",
    "S": "s",
    "SH": "sh",
    "T": "t",
    "TH": "th",
    "V": "v",
    "W": "w",
    "Y": "y",
    "Z": "z",
    "ZH": "zh",
}
SHORT = frozenset({"AE", "EH", "IH", "AH", "AA", "UH"})
WITH_R = {
    "AE": "air",
    "EH": "air",
    "IH": "eer",
    "AO": "or",
    "UH": "oor",
    "AA": "ar",
    "IY": "eer",
}
_ONSETS = (
    "B|CH|D|DH|F|G|HH|JH|K|L|M|N|P|R|S|SH|T|TH|V|W|Y|Z|ZH|"
    "P L|P R|B L|B R|T R|D R|K L|K R|G L|G R|F L|F R|TH R|SH R|"
    "S P|S T|S K|S M|S N|S L|S W|T W|D W|K W|G W|TH W|HH W|"
    "K Y|B Y|F Y|HH Y|M Y|P Y|V Y|N Y|"
    "S P L|S P R|S T R|S K R|S K W|S K Y|S P Y"
)
ONSETS = frozenset(tuple(onset.split()) for onset in _ONSETS.split("|"))
"""The consonant clusters an English syllable can start with."""

WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
"""A word the table covers: letters, with at most one inner apostrophe."""

AMERICAN = (
    (r"isation$", "ization"),
    (r"ise$", "ize"),
    (r"ised$", "ized"),
    (r"ising$", "izing"),
    (r"our$", "or"),
    (r"ours$", "ors"),
    (r"oured$", "ored"),
    (r"re$", "er"),
    (r"res$", "ers"),
    (r"ogramme$", "ogram"),
    (r"ogrammes$", "ograms"),
    (r"ence$", "ense"),
    (r"lled$", "led"),
    (r"lling$", "ling"),
    (r"yse$", "yze"),
    (r"ogue$", "og"),
)
"""British endings and their American spelling, to find a word CMUdict
lists only the American way."""
CLITICS = (("nt", "n't"), ("s", "'s"), ("re", "'re"), ("ve", "'ve"), ("ll", "'ll"))
"""Endings written without their apostrophe (dont, thats)."""

Sound = tuple[str, int | None]


@dataclass(frozen=True)
class Style:
    """The spellings that are a matter of taste (471's choices for the user)."""

    long_i: str = "y-e"
    """After a consonant: "y-e" (NYTE, MY), "igh" (NIGHT, MIGH) or "y" (NYT)."""
    book: str = "uu"
    """The vowel of book: "uu", "oo" or "u"."""
    happy: str = "ee"
    """A word-final unstressed ee (happy): "ee", "i" or "y"."""


DEFAULT = Style()


@dataclass(frozen=True)
class Respelling:
    word: str
    respelling: str
    alternates: tuple[str, ...]
    """Other ways the word is said, each "SPELLING" or "SPELLING (label)"."""


def sounds(pronunciation: str) -> list[Sound]:
    """A CMUdict pronunciation's sounds: (sound, stress), stress None for a
    consonant."""
    found: list[Sound] = []
    for token in pronunciation.split():
        match = re.fullmatch(r"([A-Z]+)([012])?", token)
        if not match or (match[1] not in VOWELS and match[1] not in CONSONANTS):
            raise ValueError(f"not a CMUdict sound: {token!r}")
        if (match[1] in VOWELS) != (match[2] is not None):
            raise ValueError(
                f"a vowel needs its stress, a consonant has none: {token!r}"
            )
        found.append((match[1], int(match[2]) if match[2] else None))
    return found


def syllables(word: Sequence[Sound]) -> list[list[Sound]]:
    vowels = [i for i, (_, stress) in enumerate(word) if stress is not None]
    if not vowels:
        return [list(word)]
    cuts = [0]
    for here, after in itertools.pairwise(vowels):
        between = [sound for sound, _ in word[here + 1 : after]]
        take = 0  # how many of them start the later syllable
        for n in range(len(between), 0, -1):
            if tuple(between[len(between) - n :]) in ONSETS:
                take = n
                break
        sound, stress = word[here]
        if stress == 1 and sound in SHORT and between and take == len(between):
            take -= 1  # a stressed short vowel keeps one: SUT-uhl
        elif (
            between[:1] == ["R"]
            and sound in ("EH", "IH", "AO", "UH")
            and (stress or sound == "EH")
            and take == len(between)
        ):
            # air, eer, or: an r colours a stressed vowel, and any e (STOR-ee,
            # LY-brair-ee; but di-REK-ter)
            take -= 1
        cuts.append(after - take)
    cuts.append(len(word))
    return [list(word[a:b]) for a, b in itertools.pairwise(cuts)]


def _spelled(
    syllable: Sequence[Sound], last: bool, open_after: bool, style: Style
) -> str:
    """`open_after`: the word ends here, or the next syllable starts with a
    vowel."""
    at = next((i for i, (_, stress) in enumerate(syllable) if stress is not None), None)
    if at is None:  # no vowel at all: hmm, shh
        return "".join(CONSONANTS[sound] for sound, _ in syllable).upper()
    vowel, stress = syllable[at]
    onset = [sound for sound, _ in syllable[:at]]
    coda = [sound for sound, _ in syllable[at + 1 :]]
    tail = [CONSONANTS[sound] for sound in coda]
    if coda == ["S"] and open_after:
        tail = ["ss"]  # oss, not os ("os" reads as "oz")
    if coda[:1] == ["R"] and vowel in WITH_R:
        nucleus, tail = WITH_R[vowel], tail[1:]
    elif vowel == "AA":
        nucleus = "o" if coda else "ah"
    elif vowel == "AH":
        nucleus = "u" if stress == 1 and coda else "uh"
    elif vowel == "AY":
        if not onset:
            nucleus = "eye"
        elif style.long_i == "igh":
            nucleus = "igh"
        else:
            nucleus = "y"
            if style.long_i == "y-e" and len(coda) == 1 and coda[0] not in ("R", "S"):
                tail = [*tail, "e"]  # NYTE, TYME
    elif vowel == "UH":
        nucleus = style.book
    elif vowel == "IY" and stress == 0 and last and not coda:
        nucleus = style.happy
    else:
        nucleus = VOWELS[vowel]
    text = "".join(CONSONANTS[sound] for sound in onset) + nucleus + "".join(tail)
    return text.upper() if stress == 1 else text


def respelled(pronunciation: str, style: Style = DEFAULT) -> str:
    """One CMUdict pronunciation ("K EY1 AA0 S"), respelled ("KAY-oss")."""
    parts = syllables(sounds(pronunciation))
    texts = [
        _spelled(
            part,
            i == len(parts) - 1,
            i == len(parts) - 1 or parts[i + 1][0][1] is not None,
            style,
        )
        for i, part in enumerate(parts)
    ]
    if len(texts) == 1:
        return texts[0].upper()
    return "-".join(texts)


def read_cmudict(text: str) -> dict[str, list[str]]:
    """CMUdict's words, each with its pronunciations in CMUdict's order."""
    entries: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.split(" #")[0].strip()
        if not line:
            continue
        word, said = line.split(" ", 1)
        entries.setdefault(re.sub(r"\(\d+\)$", "", word), []).append(said.strip())
    return entries


@dataclass(frozen=True)
class Pick:
    pronunciation: str
    alternates: tuple[tuple[str, str], ...]
    """(pronunciation, label) - the label "" for a plain variant."""


def read_picks(text: str) -> dict[str, Pick]:
    """`respell_picks.tsv`: word, pronunciation, alternates ("PRON" or
    "PRON (label)", joined by "; "), and why."""
    picks: dict[str, Pick] = {}
    for line in text.splitlines():
        if not line or line.startswith(("#", "word\t")):
            continue
        word, said, alternates = line.split("\t")[:3]
        found: list[tuple[str, str]] = []
        for item in filter(None, (a.strip() for a in alternates.split(";"))):
            match = re.fullmatch(r"([A-Z012 ]+?)(?: \((.+)\))?", item)
            if not match:
                raise ValueError(f"{word}: not an alternate: {item!r}")
            found.append((match[1], match[2] or ""))
        picks[word] = Pick(said, tuple(found))
    return picks


def _cmudict_spelling(word: str, cmudict: Mapping[str, list[str]]) -> str | None:
    """The spelling CMUdict lists `word` under: itself, its American
    spelling, or with its apostrophe."""
    if word in cmudict:
        return word
    for ending, american in AMERICAN:
        other = re.sub(ending, american, word)
        if other != word and other in cmudict:
            return other
    for ending, clitic in CLITICS:
        if word.endswith(ending) and word[: -len(ending)] + clitic in cmudict:
            return word[: -len(ending)] + clitic
    return None


def respelling(
    word: str,
    cmudict: Mapping[str, list[str]],
    picks: Mapping[str, Pick],
    style: Style = DEFAULT,
) -> Respelling | None:
    key = _cmudict_spelling(word, cmudict)
    if key is None:
        return None
    pick = picks.get(word) or picks.get(key)
    if pick is None:
        listed = cmudict[key]
        pick = Pick(next((s for s in listed if "1" in s), listed[0]), ())
    first = respelled(pick.pronunciation, style)
    alternates = []
    for other, label in pick.alternates:
        spelled = respelled(other, style)
        if spelled != first:
            alternates.append(f"{spelled} ({label})" if label else spelled)
    return Respelling(word, first, tuple(dict.fromkeys(alternates)))


def table(
    words: Iterable[str],
    cmudict: Mapping[str, list[str]],
    picks: Mapping[str, Pick],
    style: Style = DEFAULT,
) -> list[Respelling]:
    return [r for w in words if (r := respelling(w, cmudict, picks, style))]


def commonest(frequencies: Mapping[str, float], top: int) -> list[str]:
    """The `top` commonest words the table covers, commonest first."""
    ranked = sorted(frequencies, key=lambda w: (-frequencies[w], w))
    return [w for w in ranked if WORD.fullmatch(w)][:top]


def write(rows: Iterable[Respelling], path: Path) -> None:
    lines = ["word\trespelling\talternates"]
    lines += [f"{r.word}\t{r.respelling}\t{' / '.join(r.alternates)}" for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def credits() -> str:
    lines = ["# English respelling: sources", ""]
    for source in (sources.CMUDICT, sources.WORDFREQ):
        lines.append(
            f"- **{source.title}**, {source.version}. {source.licence}. "
            f"{source.notice}. Used for {source.used_for}."
        )
    lines += [
        (
            "- **Wiktionary** (https://en.wiktionary.org), CC BY-SA 4.0: which of "
            "CMUdict's pronunciations is the usual American one "
            "(`respell_picks.tsv`, polyglotic-hq 471)."
        ),
        "",
        "## CMUdict's licence",
        "",
        CMUDICT_LICENCE,
    ]
    return "\n".join(lines) + "\n"


CMUDICT_LICENCE = """Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
   The contents of this file are deemed to be source code.

2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in
   the documentation and/or other materials provided with the
   distribution.

This work was supported in part by funding from the Defense Advanced
Research Projects Agency, the Office of Naval Research and the National
Science Foundation of the United States of America, and by member
companies of the Carnegie Mellon Sphinx Speech Consortium. We acknowledge
the contributions of many volunteers to the expansion and improvement of
this dictionary.

THIS SOFTWARE IS PROVIDED BY CARNEGIE MELLON UNIVERSITY ``AS IS'' AND
ANY EXPRESSED OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL CARNEGIE MELLON UNIVERSITY
NOR ITS EMPLOYEES BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--sources", type=Path, default=Path("build/dictionaries/sources")
    )
    parser.add_argument(
        "--out", type=Path, default=Path("build/dictionaries/respelling")
    )
    parser.add_argument("--top", type=int, default=10_000)
    args = parser.parse_args(argv)
    cmudict = read_cmudict(
        sources.fetch(sources.CMUDICT, args.sources).read_text(encoding="utf-8")
    )
    frequencies = wordfreq_ranks.frequencies(
        sources.fetch(sources.WORDFREQ, args.sources)
    )
    words = commonest(frequencies, args.top)
    rows = table(words, cmudict, read_picks(PICKS.read_text(encoding="utf-8")))
    args.out.mkdir(parents=True, exist_ok=True)
    write(rows, args.out / "respelling-en.tsv")
    (args.out / "CREDITS.md").write_text(credits(), encoding="utf-8", newline="\n")
    print(f"{len(rows)} of {len(words)} words respelled, in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
