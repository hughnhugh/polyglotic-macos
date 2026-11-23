"""Korean's own rules for its pack (polyglotic-hq 510, 516).

- **Counting words:** wordfreq counts Korean by its parts, as an analyser
  cuts it: a noun without its particles (학교 for 학교에서), a particle
  alone (는, 을), a verb's or an adjective's stem (있 for 있다, 먹 for
  먹었다) and its past fused onto the stem where the stem ends in a vowel
  (갔 for 갔다, 했 for 했다). So a predicate is ranked by its stem and its
  fused past (`predicate_counts`): 가다, whose stem 가 is the subject
  particle's spelling too, had been the 3,268th word and 먹다 unranked.
- **Which entry first:** Wiktionary lists a word's entries by etymology,
  so a form that is also a rarer word opened on that word: 대한 (대하다's
  "about", the 170th word) on "great khan", 마다 (the particle "every") on
  "to smash", 갈 (가다's "will go") on "common reed". A particle alone
  opens on the dictionary's particle (`PARTICLE_FIRST`), and the forms
  read by hand among the commonest opens on their predicate
  (`PREDICATE_FIRST`); a word with an adverb, a determiner or another
  small word's entry of its own keeps it first (하지만, "but", not 하다),
  and so does a predicate's own dictionary form (들리다, "to be heard",
  not 듣다, whose passive it is).
- **First meanings:** the commonest words' first meanings, read by hand
  where Wiktionary's first isn't the one a learner meets (`FIRST_SENSES`,
  as Thai's: polyglotic-hq 461): 있다 is "to be; to exist" before "to
  stay".
- **Words only under their hanja:** English Wiktionary has many
  Sino-Korean words only as their hanja's page ("海上: hanja form of
  해상 (“maritime”)"); such a word with no page of its own gets an entry
  with those meanings (`hanja_words`): 해상, 묵상, 분출.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Iterator

from polyglotic_desktop.core.lexicon.korean_forms import ENDINGS, INFIXES, PARTICLES
from tools.dictionaries import kaikki

_FIRST, _LAST = 0xAC00, 0xD7A3
_HANGUL = re.compile(f"^[{chr(_FIRST)}-{chr(_LAST)}]+$")
SMALL = frozenset(PARTICLES) | frozenset(ENDINGS)
"""The app's particles and endings (`core.lexicon.korean_forms`)."""
NO_STEM = frozenset(INFIXES) | {"째", "들"}
"""What wordfreq counts that is no stem, though a predicate's stem is
spelled so: the past and the honorific (시: 셨 is 시 + 었, not 시다's,
"to be sour", past), the ordinal -째 (째다, "to cleave"), the plural
-들 (polyglotic-hq 516)."""
PREDICATES = frozenset({"verb", "adj"})

PARTICLE_FIRST = frozenset(
    {
        *("의", "에", "을", "은", "는", "과", "랑", "며", "려", "이다", "씩"),
        *("에서", "마다", "이랑", "도록", "다가", "아서", "어도", "아도"),
        *("아야", "어야", "구나"),
    }
)
"""Particles and endings whose own entries are rarer words than they are
(의, "righteousness"; 마다, "to smash"; 에서, "Esau"): alone (after a
quote or a bracket) each opens on the dictionary's particle, -의, -마다.
Read by hand; not those that are common words alone too - 이 ("this"),
나 ("I"), 다 ("all"), 도 ("degree"), 만 ("ten thousand"), 보다 ("to
see"), 같이 ("together"), 어서 ("quickly")."""

OPENS_ON = {
    "대한": "대하다",  # ~에 대한, "about": not "great khan"
    "위해": "위하다",  # ~을 위해, "for": not "harm"
    "지난": "지나다",  # 지난 주, "last week": not Jinan
    "가요": "가다",
    "가라": "가다",
    "원한": "원하다",
    "심해": "심하다",
    "야한": "야하다",
    "가": "가다",
    "갈": "가다",
    "간": "가다",
    "들": "들다",
    "해": "하다",
    "와": "오다",
    "올": "오다",
    "알": "알다",
    "볼": "보다",
    "마": "말다",  # 하지 마, "don't"
    "놀": "놀다",
    "써": "쓰다",
    "빈": "비다",
    "울": "울다",
    "켜": "켜다",
    "떨": "떨다",
    "쏠": "쏘다",
    "해서": "하다",  # 해서, "so; and then": not "regular script"
    "해도": "하다",  # 해도, "even if one does": not "chart (of the sea)"
    "본": "보다",  # 본 적이 있다, "have seen": not "root, basis"
    "준": "주다",  # 준 것, "given": not a family name
    "누가": "누구",  # 누구 + 가, "who": not "nougat"
    "게": "것",  # 것이 written short (그런 게 아니라): not "crab"
    "걸": "것",  # 것을 written short: not "3 points in yunnori"
}
"""Forms of a common predicate (or 것 written short) that are rarer words of
their own too, read by hand among the words wordfreq ranks highest
(polyglotic-hq 516): each opens on that word, then its own entries. Left as they are, where the
word is as common alone: 날 (day), 줄 (how to), 길 (road), 살 (years of
age), 피해 (damage), 배우자 (spouse)."""

FIRST_SENSES: dict[str, tuple[str, ...]] = {
    "있다": ("to be (in a place); to exist", "to have"),
    "우리": ("we, us",),
    "등": ("et cetera",),
    "적": ("time, occurrence, experience",),
    "안": ("not",),
    "못": ("cannot", "poorly"),
    "중": ("in the course of; during", "amongst"),
    "개": ("general counter for objects",),
    "분": ("person",),
    "명": ("Counter for people",),
    "살": ("years of age",),
    "년": ("year",),
    "내": ("allomorph of 나",),
    "네": ("yes",),
    "씨": ("sir or madam; Mr. or Ms.",),
    "자신": ("oneself (as a reflexive pronoun",),
    "바로": ("right now",),
    "단": ("only",),
    "천": ("thousand",),
    "새": ("new, novel; fresh",),
    "좀": ("(used to soften requests) please",),
    "건": ("topic-marked form of 거",),
    "밝히다": ("to make clear, reveal, disclose, uncover",),
    "나다": ("to appear, arise, occur, take place",),
    "개발": ("development",),
    "결과": ("result; outcome",),
    "시장": ("market",),
    "제도": ("system",),
    "대상": ("target; object",),
    "교수": ("professor",),
    "우수": ("excellence",),
    "기관": ("agency",),
    "약간": ("a little, a bit; somewhat",),
    "산성": ("acidity",),
}
"""A word -> the meanings its card opens on, in order (Thai's
`FIRST_SENSES`), each the start of one of Wiktionary's: the entry with the
first comes first among the word's entries, and those of its meanings
listed, first in it. Read by hand on the pack's 300 commonest words
(polyglotic-hq 516), where a word met alone in a caption opened on a
rarer sense: 있다 on "to stay", 안 (not) on "inside", 년 (year) on an
insult, 새 (new) on "bird"."""

OWN_FIRST_POS = frozenset(
    {"adv", "det", "conj", "intj", "pron", "num", "counter", "particle"}
)
"""A word with an entry of its own in one of these keeps its entries first
before a predicate it is also a form of (하지만, "but"; 그래도,
"nevertheless")."""

_SEE = re.compile(r"^See the entry at (?P<target>-?[가-힣]+-?)(?:[ .(]|$)")


def _dicts(value: object) -> list[dict[str, object]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def see_also_target(gloss: str) -> str | None:
    """The word a gloss only points to: "See the entry at -는 (-neun)." is
    -는's (`prepared`)."""
    found = _SEE.match(gloss)
    return found.group("target") if found else None


def hanja_words(objects: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """An entry, as kaikki writes one, for each hangul word English
    Wiktionary has only under its hanja, with what those hanja pages say
    it means ("海上: hanja form of 해상 (“maritime”)": 해상, "maritime") and
    their romanization; a word with a page of its own is passed over.
    One entry per word and part of speech, its hanja pages' meanings in
    their order."""
    pages: set[str] = set()
    meanings: dict[tuple[str, str], list[str]] = defaultdict(list)
    romanized: dict[str, str] = {}
    for obj in objects:
        word = obj.get("word")
        if not isinstance(word, str):
            continue
        if _HANGUL.match(word):
            pages.add(word)
            continue
        pos = str(obj.get("pos") or "")
        if pos in kaikki.NO_WORD_POS or pos == "character":
            continue
        for sense in _dicts(obj.get("senses")):
            if "hanja" not in _items(sense.get("tags")):
                continue
            for target in _dicts(sense.get("form_of")):
                hangul = str(target.get("word") or "")
                extra = str(target.get("extra") or "").strip()
                if not _HANGUL.match(hangul) or not extra:
                    continue
                said = extra.split("“", 1)[1] if "“" in extra else extra
                if "“" not in said:  # "left atrium”)", the quote's end left over
                    said = said.replace("”)", "").replace("”", "")
                if said not in meanings[(hangul, pos)]:
                    meanings[(hangul, pos)].append(said)
                romanized.setdefault(hangul, kaikki.romanization(obj))
    return [
        {
            "word": hangul,
            "pos": pos,
            "lang_code": "ko",
            "forms": [{"form": romanized[hangul], "tags": ["romanization"]}],
            "senses": [{"glosses": [m]} for m in said],
        }
        for (hangul, pos), said in meanings.items()
        if hangul not in pages
    ]


def prepared(
    objects: Iterable[dict[str, object]], added: Iterable[dict[str, object]] = ()
) -> Iterator[dict[str, object]]:
    """The extract's objects as the pack reads them: a sense that only says
    "See the entry at -는" made a form of -는 (a particle's own spelling,
    alone, had shown that line and no meaning), then `added`
    (`hanja_words`)."""
    for obj in objects:
        senses = obj.get("senses")
        if isinstance(senses, list):
            for sense in senses:
                glosses = sense.get("glosses") if isinstance(sense, dict) else None
                target = see_also_target(str(glosses[-1])) if glosses else None
                if target and target != obj.get("word") and not sense.get("form_of"):
                    sense["form_of"] = [{"word": target}]
                    sense["tags"] = [*(sense.get("tags") or ()), "form-of"]
        yield obj
    yield from added


def stem(word: str) -> str | None:
    """A predicate's stem (같 for 같다), or None for no predicate's
    dictionary form."""
    return word[:-1] if len(word) >= 2 and word.endswith("다") else None


def fused_past(stem: str) -> str | None:
    """The stem with the past 았/었 fused onto its last syllable, as
    wordfreq counts it (가 갔, 하 했, 보 봤, 되 됐, 마시 마셨): None where
    the stem ends in a consonant (먹 + 었 stay apart)."""
    code = ord(stem[-1]) - _FIRST
    if not 0 <= code <= _LAST - _FIRST or code % 28:
        return None
    initial, medial = code // (21 * 28), (code // 28) % 21
    merged = {0: 0, 4: 4, 8: 9, 13: 14, 18: 4, 20: 6, 11: 10, 1: 1, 5: 5}
    if initial == 18 and medial == 0:  # 하 + 였: 했
        merged = {0: 1}
    if medial not in merged:
        return None
    return stem[:-1] + chr(_FIRST + (initial * 21 + merged[medial]) * 28 + 20)


STEM_SHARED = frozenset({"먹다", "알다", "살다", "울다", "놀다", "작다"})
"""Predicates whose stem is a word of its own too, but whose stem's count
wordfreq gives is mostly the predicate's (먹, inkstick; 알, egg; 작, a
work): read by hand. Not the others - 길 (road) made 길다 the 96th word, 우리 (we) 우리다
(to infuse) the 63rd, and 날 (day) opened on 날다, "to fly"."""


def predicate_counts(
    word: str, words: Collection[str], pages: Collection[str]
) -> tuple[str, ...]:
    """The written forms whose frequencies a predicate's (`word`) are, as
    wordfreq counts Korean, beside its own: its stem where the stem's page
    is only a hanja syllable's or a jamo's (크 for 크다), or the stem is a
    word too but its count is the predicate's (`STEM_SHARED`); and its
    fused past (갔: 가, the stem of 가다, is the subject particle's spelling,
    and counts for the particle). A stem with no page is the predicate's
    form instead (`stem_forms`), and so counts for it."""
    found = stem(word)
    if found is None or found in NO_STEM:
        return ()
    paged = found in pages and found not in SMALL and not affix(found, pages)
    out = [found] if paged and (found not in words or word in STEM_SHARED) else []
    past = fused_past(found)
    if past and past not in pages:  # 갔, though 가 is -가's spelling too
        out.append(past)
    return tuple(out)


def stem_forms(word: str, words: Collection[str], pages: Collection[str]) -> str | None:
    """A predicate's stem as one of its forms (있 for 있다; 크 for 크다,
    whose page is only a jamo's name): only where the stem is no word of
    its own (`words`), no particle, no ending and no affix."""
    found = stem(word)
    if found is None or found in words or found in SMALL or found in NO_STEM:
        return None
    return None if affix(found, pages) else found


def affix(text: str, words: Collection[str]) -> bool:
    """Whether the dictionary lists `text` as a suffix or a prefix (-째,
    "-th": 첫째, 둘째): wordfreq's count of it is the affix's, so it ranks
    no predicate - 째다, "to cleave", had been the 235th word."""
    return f"-{text}" in words or f"{text}-" in words


NO_WORD = frozenset({"syllable", "root", "character", "symbol", "letter"})
"""Entries no caption's word opens on for a learner: a hanja syllable's
reading (랑, 浪), a root only used in a 하다 verb, a letter."""
_JAMO = re.compile(r"\bjamo\b|Hangul (?:letter|consonant|vowel)", re.IGNORECASE)


def no_word(meanings: Iterable[str]) -> bool:
    """Whether an entry's every meaning (as the draft writes them, "(pos)
    gloss") is no word a learner meets (`NO_WORD`, or a jamo's name: 크,
    "alternative name for the jamo 키읔"). wordfreq's count of the
    spelling is a stem's (크 of 크다) or a particle's: such entries take
    none, or a jamo's name was the 222nd word."""
    said = list(meanings)
    return bool(said) and all(
        m.split(")", 1)[0].lstrip("(") in NO_WORD or bool(_JAMO.search(m)) for m in said
    )
