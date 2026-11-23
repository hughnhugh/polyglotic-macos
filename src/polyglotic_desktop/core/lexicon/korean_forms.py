"""Korean words as a dictionary lists them: what a word in a caption may be
made from, for a pack that hasn't got the word itself (polyglotic-hq 448,
510).

Korean writes a word and the small words after it together, between
spaces: 학교에서 is 학교 (school) + 에서 (at), 학생들은 학생 (student) + 들
(plural) + 은 (topic). A verb or an adjective is its stem and endings:
먹었는데 is 먹 (eat) + 었 (past) + 는데 (but); the dictionary lists it as
stem + 다, 먹다. Wiktionary's tables list a verb's commonest forms (먹어요,
먹었다, 먹습니다), not most of its connective endings, and a noun's not at
all. `bases` takes particles off a noun and endings off a predicate and
gives what the word may be made from, the least cut off first; the pack
decides: a guess is looked up only when the word itself isn't found, and
the first guess the pack has is the one shown (`core.lexicon.basic`).

The rules are this module's own, from the grammar every Korean course
teaches: the particles and their order (plural 들 before a case particle);
the endings, the past 었/았/였 and the honorific 시 before them; the
endings that are a final consonant on the stem's last syllable (가 + ㄴ다:
간다; 가 + ㅂ니다: 갑니다); and the vowels that merge with 어/아 (보 + 아:
봐, 하 + 여: 해, 마시 + 어: 마셔). Of the irregular stems, ㅂ's (덥다: 더워)
and ㄷ's (듣다: 들어) and ㄹ's lost before ㄴ (살다: 사는) are guessed. A
noun + 하다 word the dictionary hasn't got is guessed as its noun (중요한:
중요, importance), and a noun + 적 (-ic) as the noun. No analyser's code or
data is used.
"""

from __future__ import annotations

_FIRST, _LAST = 0xAC00, 0xD7A3
_FINALS = 28
_MEDIALS = 21

_H = 18  # the initial (초성) ㅎ
# finals (종성) by their index
_N, _L, _M, _B, _SS = 4, 8, 16, 17, 20
_D, _S = 7, 19
# medials (중성) by their index
_A, _AE, _EO, _E, _YEO, _O, _WA, _WAE, _OE, _U, _WO, _EU, _I = (
    0,
    1,
    4,
    5,
    6,
    8,
    9,
    10,
    11,
    13,
    14,
    18,
    20,
)
_MERGED = {
    _A: (_A, _EU),  # 가 + 아: 가; 바쁘 + 아: 바빠
    _AE: (_AE, _A),  # 내 + 어: 내; 하 + 여: 해
    _EO: (_EO, _EU),  # 서 + 어: 서; 쓰 + 어: 써
    _E: (_E,),
    _YEO: (_I,),  # 마시 + 어: 마셔
    _WA: (_O,),  # 보 + 아: 봐
    _WO: (_U,),  # 주 + 어: 줘
    _WAE: (_OE,),  # 되 + 어: 돼
}
"""A stem's last vowel, by the vowel it and 어/아 merge into."""

PARTICLES = tuple(
    sorted(
        {
            *("이", "가", "은", "는", "을", "를", "의", "에", "와", "과", "도"),
            *("만", "로", "랑", "나", "야", "아", "께", "요"),
            *("에서", "에게", "한테", "께서", "으로", "에는", "에도", "와는"),
            *("과는", "이나", "이랑", "처럼", "까지", "부터", "보다", "마다"),
            *("조차", "마저", "밖에", "이란", "이며", "이고", "이다", "이야"),
            *("에서는", "에서도", "에서의", "에게는", "에게도", "에게서", "한테서"),
            *("으로는", "으로도", "으로서", "으로써", "로서", "로써", "로는", "로도"),
            *("이라도", "라도", "이라고", "라고", "이라는", "라는", "까지는", "부터는"),
            *("이에요", "예요", "입니다", "이었다", "였다", "이었고", "인데", "이지만"),
            *("으로부터", "로부터", "에서부터", "만큼", "같이", "보다는", "에의"),
            *("인", "이자", "이든", "이라", "다", "이지", "인지", "만의", "에만"),
            *("에서만", "까지도", "로만", "으로만", "밖에는", "이었던", "였던"),
            *("였으므로", "이었으므로", "였으며", "이었으며", "였고", "였습니다"),
            *("이었습니다", "이어서", "이면", "이라면", "이니까", "인데요", "일"),
            *("이라면서", "라면서", "이라며", "라며", "이라서", "라서"),
        },
        key=len,
        reverse=True,
    )
)
"""What follows a noun: the particles, and the copula's commonest forms."""

ENDINGS = tuple(
    sorted(
        {
            *("다", "요", "고", "지", "게", "면", "니", "자", "서", "며", "죠"),
            *("어", "아", "여", "는", "은", "을", "기", "음", "던", "냐", "까"),
            *("어요", "아요", "여요", "지만", "으면", "니까", "는데", "은데", "도록"),
            *("려고", "으며", "다가", "지요", "네요", "어서", "아서", "여서", "어도"),
            *("아도", "어야", "아야", "다고", "는다", "거나", "든지", "는지", "은지"),
            *("을지", "기에", "기로", "을까", "을게", "게요", "군요", "구나", "잖아"),
            *(
                "나요",
                "세요",
                "는데요",
                "으니까",
                "으려고",
                "는다고",
                "잖아요",
                "습니다",
            ),
            *("습니까", "으세요", "어서요", "는가", "더니", "으니", "기도", "기는"),
            *("기가", "기를", "고요", "다는", "었다", "았다", "였다", "어야지"),
            *("으므로", "므로", "더라도", "듯이", "듯", "지도", "면서", "으면서"),
            *("거든", "는다면", "다면", "려면", "으려면", "도록", "자마자", "고서"),
            *("나", "든", "으나", "던가", "는다는", "다는"),
            *("려", "으려", "려는", "으려는", "려다", "으려다"),
        },
        key=len,
        reverse=True,
    )
)
"""A predicate's endings, after its stem or its past or honorific."""

FINAL_ENDINGS = {
    "니다": _B,  # 갑니다: 가 + ㅂ니다
    "니까": _B,
    "다": _N,  # 간다: 가 + ㄴ다
    "다고": _N,
    "다는": _N,  # 한다는: 하 + ㄴ다는
    "다면": _N,  # 간다면: 가 + ㄴ다면
    "다며": _N,
    "데": _N,  # 큰데: 크 + ㄴ데
    "지": _L,  # 갈지: 가 + ㄹ지
    "까": _L,  # 갈까: 가 + ㄹ까
    "게": _L,  # 갈게: 가 + ㄹ게
    "": 0,  # 간, 갈, 감: 가 + ㄴ, ㄹ, ㅁ (any final)
}
"""Endings that start with a final consonant on the stem's last syllable,
by what follows that consonant ("" for none) and the consonant."""
_ANY_FINAL = (_N, _L, _M)
INFIXES = ("었", "았", "였", "겠", "시", "으시", "셨", "었었")
"""What stands between a stem and its ending: the past, the future or
guess, the honorific."""
LIGHT_VERBS = ("하다", "되다", "당하다", "시키다", "있다", "없다")
"""The verbs a noun becomes a verb with (공부하다, 마무리되다, 살해당하다),
and 있다 and 없다 written closed after one (의미있는: 의미 있는, "meaningful";
polyglotic-hq 516)."""
_WITH_EU = "으을은음"
"""How an ending starts that takes 으 after a consonant: after a vowel or
ㄹ it is written without it (가 + 을: 갈; 살 + 을: 살)."""
COMMON_NOUNS = frozenset(
    {
        *("일", "말", "물", "길", "집", "밥", "글", "불", "돈", "손", "눈", "문"),
        *("몸", "맛", "날", "술", "책", "꿈", "땅", "꽃", "옷", "차", "달", "별"),
        *("산", "강", "섬", "숲", "돌", "빛", "힘", "피", "잠", "숨", "배", "발"),
        *("팔", "목", "입", "귀", "코", "앞", "뒤", "옆", "위", "밖", "속", "끝"),
        *("곳", "것", "줄", "죄", "법", "병", "약", "표", "방", "벽", "상", "판"),
        *("정", "맘", "꼴", "짐", "털", "뿔", "빵", "국", "떡", "쌀", "콩", "공"),
    }
)
"""Everyday nouns of one syllable: with a particle on (일을, 물이), each is
that noun before any predicate it might be a form of - 일을 had opened on
일다 (to rise), 물을 on 묻다 (to ask), 집을 on 집다 (to pick up). Another
noun of one syllable comes after the predicate (먹은 is 먹다's, not 먹,
inkstick). Read by hand (polyglotic-hq 516)."""
PARTICLES_ON_PARTICLES = 3
"""How many particles (or a particle and the copula) a noun may carry in
turn: 월까지이다 is 월 + 까지 + 이다 (polyglotic-hq 516)."""
STACKED_LAST = frozenset(
    {
        *("은", "는", "도", "만", "의", "요", "이", "가", "을", "를", "인지"),
        *("이다", "인데", "이고", "이며", "이라고", "이라는", "이라면서", "라면서"),
        *("이었다", "였다", "이지만", "이야", "이에요", "예요", "입니다", "인", "일"),
    }
)
"""The particles and copula forms that come last after another particle
(까지는, 에서도, 만이, 까지이다); only after one of them is another taken
off - 고속도로 (expressway) isn't 고속 + 도 + 로."""


def _syllable(char: str) -> tuple[int, int, int] | None:
    code = ord(char) - _FIRST
    if not 0 <= code <= _LAST - _FIRST:
        return None
    return code // (_MEDIALS * _FINALS), (code // _FINALS) % _MEDIALS, code % _FINALS


def _join(initial: int, medial: int, final: int) -> str:
    return chr(_FIRST + (initial * _MEDIALS + medial) * _FINALS + final)


def _final(char: str) -> int | None:
    found = _syllable(char)
    return found[2] if found else None


def _is_hangul(word: str) -> bool:
    return bool(word) and all(_syllable(c) is not None for c in word)


def _unmerged(initial: int, medial: int) -> tuple[int, ...]:
    """The vowels a stem's last syllable may have had before 어/아 merged
    into it (`_MERGED`), likeliest first: 해 and 했 are 하다's (하 + 여)
    before any stem in 해 - 해다, a rare spelling of it, had come first, so
    했다 opened on "newborn baby" (polyglotic-hq 516)."""
    vowels = _MERGED.get(medial, (medial,))
    if initial == _H and medial == _AE:
        return (_A, _AE)
    return vowels


def _stems(rest: str) -> list[str]:
    """The stems `rest` (a predicate with its ending taken off) may be: as
    it is, its last vowel unmerged from 어/아, its past or honorific taken
    off first."""
    found: list[str] = []
    todo = [rest]
    for infix in INFIXES:
        if rest.endswith(infix) and len(rest) > len(infix):
            todo.append(rest[: -len(infix)])
    for stem in todo:
        found.append(stem)
        last = _syllable(stem[-1])
        if last is None:
            continue
        initial, medial, final = last
        if final == _SS:  # 갔: 가 + 았; 했: 하 + 였; 봤: 보 + 았
            for vowel in _unmerged(initial, medial):
                found.append(stem[:-1] + _join(initial, vowel, 0))
        elif final == 0 and medial in _MERGED:  # 봐, 해, 마셔
            unmerged = [
                stem[:-1] + _join(initial, v, 0) for v in _unmerged(initial, medial)
            ]
            if initial == _H and medial == _AE:  # 해: 하 + 여, before 해 itself
                found[-1:] = unmerged
            else:
                found += unmerged
        if final == 0 and stem[-1] in "라러" and len(stem) > 1:  # 따라, 몰라
            before = _syllable(stem[-2])
            if before is not None:
                found.append(stem[:-1] + "르")  # 따르
                if before[2] == _L:  # 몰라: 모르
                    found.append(stem[:-2] + _join(before[0], before[1], 0) + "르")
        if final == 0 and stem[-1] in "워와우" and len(stem) > 1:  # 더워: 덥
            before = _syllable(stem[-2])
            if before is not None and before[2] == 0:
                found.append(stem[:-2] + _join(before[0], before[1], _B))
        if final == _L:  # 들어: 듣
            found.append(stem[:-1] + _join(initial, medial, _D))
        if final == 0 and len(stem) >= 1:  # 사는: 살
            found.append(stem[:-1] + _join(initial, medial, _L))
    return found


def _predicates(word: str) -> list[tuple[int, str]]:
    """(how much was cut, the dictionary form: stem + 다) for each stem
    `word` may be a predicate's form of."""
    out: list[tuple[int, str]] = []
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) > len(ending):
            rest = word[: -len(ending)]
            stems = _stems(rest)
            if ending[0] in _WITH_EU:  # after a consonant, not ㄹ (살다 + 을: 살)
                last = _syllable(rest[-1])
                final = last[2] if last else 0
                if final == 0:
                    continue
                if final == _L:  # 들으면: only ㄷ's ㄹ (듣다)
                    stems = [s for s in stems if s[-1:] and _final(s[-1]) == _D]
            out += [(len(ending), s + "다") for s in stems]
    for after, final in FINAL_ENDINGS.items():
        if after and not word.endswith(after):
            continue
        rest = word[: len(word) - len(after)] if after else word
        last = _syllable(rest[-1]) if rest else None
        if last is None or (final and last[2] != final):
            continue
        if not final and last[2] not in _ANY_FINAL:
            continue
        stem = rest[:-1] + _join(last[0], last[1], 0)
        out += [(len(after) + 1, s + "다") for s in _stems(stem)]
    out += [(0, s + "다") for s in _stems(word) if s != word]  # 통해: 통하 + 여
    # a passive or "become" in 어지다 the dictionary hasn't got is its
    # verb's: 숨겨지다 (be hidden) is 숨기다 (hide) + 어지다 (516)
    out += [
        (cut + 2, s + "다")
        for cut, verb in list(out)
        if verb.endswith("지다") and len(verb) > 3
        for s in _stems(verb[:-2])
        if s != verb[:-2]
    ]
    # a noun + 하다 (되다, 당하다, 시키다) word the dictionary hasn't got is
    # its noun's (중요한: 중요; 마무리되었으며: 마무리)
    out += [
        (cut + len(light), verb[: -len(light)])
        for cut, verb in list(out)
        for light in LIGHT_VERBS
        if verb.endswith(light) and len(verb) > len(light) + 1
    ]
    return out


def _nouns(word: str, left: int = PARTICLES_ON_PARTICLES) -> list[tuple[int, str]]:
    """(how much was cut, the noun) for each noun `word` may be with its
    particles (and plural 들) on - up to `left` of them, taken off in turn."""
    out: list[tuple[int, str]] = []
    for particle in PARTICLES:
        if word.endswith(particle) and len(word) > len(particle):
            noun = word[: -len(particle)]
            out.append((len(particle), noun))
            if left > 1 and particle in STACKED_LAST:  # 월까지이다: 월까지, 월
                out += [(len(particle) + c, n) for c, n in _nouns(noun, left - 1)]
            if noun.endswith("들") and len(noun) > 1:
                out.append((len(particle) + 1, noun[:-1]))
            if noun.endswith("적") and len(noun) > 2:  # 세계적으로: 세계
                out.append((len(particle) + 1, noun[:-1]))
    if word.endswith("적") and len(word) > 2:  # 유전적: 유전
        out.append((1, word[:-1]))
    if word.endswith("들") and len(word) > 1:
        out.append((1, word[:-1]))
    return out


_SMALL = frozenset(PARTICLES) | frozenset(ENDINGS)
VERB_PREFIXES = ("내", "되", "휘", "짓", "처", "엇")
"""What a verb may start with that the dictionary may not list it with:
내뿜다 (spew out) is 내- (out) + 뿜다 (spout); 되돌다 (turn back), 되- +
돌다 (polyglotic-hq 516)."""


def bases_after_bracket(word: str) -> tuple[str, ...]:
    """What `word` is where it is written right after a closing bracket or
    quote: a particle or an ending there belongs to the word inside -
    (성지)이 is 성지 + -이, the subject particle, not 이 ("this") - and is
    the dictionary's (-이); anything else, nothing said (polyglotic-hq 516)."""
    return (f"-{word}",) if word in _SMALL else ()


COMPOUND_ENDS = {
    **{end: f"-{end}" for end in ("성", "류", "실", "용", "화")},
    **dict.fromkeys(("값", "객", "길", "법", "산", "죄", "초", "층", "팀", "표"), ""),
    **dict.fromkeys(("감", "업", "식", "인", "체", "판", "점"), ""),
}
"""The syllables a Korean compound may end in as a part of one syllable
(`compounds`), each with how the pack lists it: a Sino-Korean suffix (-성,
-ness: 식물성; -화, -ization: 시각화) or a word ("" - itself: 층, floor:
바깥층; 팀, team: 대표팀). Read by hand: only those whose first meaning is
the compound's - not 자 ("-자" is "let's", 者 has no entry), 물 (water, not
物 "thing"), 장 (sauce) - and not any syllable, which a name written in
hangul ends in too (파티마, Fatima, isn't 파티 + -마) (polyglotic-hq 516)."""
COMPOUND_STARTS = {"대": "대-", "신": "신-", "각": "", "친": ""}
"""The prefixes a Korean compound may start with as a part of one syllable,
as `COMPOUND_ENDS`: 대- (great: 대도시), 신- (new: 신제품), 각 (each: 각국)."""


def nouns(word: str) -> list[str]:
    """The nouns `word` may be with its particles off (학교에서: 학교), the
    least cut off first - the shorter guesses of `bases`, nouns only."""
    return list(dict.fromkeys(noun for _, noun in sorted(_nouns(word)) if noun))


CONTRACTED = {"이건": "이것", "그건": "그것", "저건": "저것", "이게": "이것"}
CONTRACTED |= {"그게": "그것", "건": "것", "걸": "것", "게": "것"}
"""것 (thing) and its pronouns with 은, 이 or 을 written short: 이건 is 이것은."""


def bases(word: str) -> tuple[str, ...]:
    """What `word` may be made from, likeliest first: a noun of two
    syllables or more (or an everyday one of one: `COMMON_NOUNS`) without
    its particles (학교는 is 학교; 일을, 일), then a predicate's dictionary
    form (stem + 다), then another noun of one syllable (먹는 is 먹다, not
    the noun 먹, ink) - each the least cut off first. A
    particle or an ending alone (after a quote or a bracket: '브로드사이드'라고)
    is first the dictionary's, written with a hyphen: -라고 (polyglotic-hq
    516)."""
    if not _is_hangul(word):
        return ()
    found = [
        (0 if len(noun) > 1 or noun in COMMON_NOUNS else 2, cut, noun)
        for cut, noun in _nouns(word)
    ]
    if word in _SMALL:
        found.insert(0, (-1, 0, "-" + word))
    if word in CONTRACTED:
        found.insert(0, (0, 0, CONTRACTED[word]))
    if word.endswith("히") and len(word) > 2:  # 단호히: 단호하다, 단호
        found += [(1, 1, word[:-1] + "하다"), (1, 2, word[:-1])]
    if word.endswith("치") and len(word) > 2:  # 의도치: 의도하지, written short
        found += [(1, 1, word[:-1] + "하다"), (1, 2, word[:-1])]
    found += [(1, cut, verb) for cut, verb in _predicates(word)]
    found += [  # 내뿜는: 내뿜다, then 뿜다
        (1, cut + 1, verb[1:])
        for _, cut, verb in list(found)
        if verb.endswith("다") and verb.startswith(VERB_PREFIXES) and len(verb) > 2
    ]
    return tuple(
        dict.fromkeys(
            base
            for _, _, base in sorted(found, key=lambda f: f[:2])
            if base and base != word
        )
    )
