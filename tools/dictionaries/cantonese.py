"""Reading the Cantonese pack's sources (polyglotic-hq 371 and 450;
decision 0160): CC-Canto and its Cantonese readings for CC-CEDICT,
rime-cantonese's everyday readings, and HKCanCor's word counts.

What speech says weighs above what writing says (polyglotic-hq 467):
- **Ranks.** Written Chinese (wordfreq) is Mandarin's: 的, 是, 在 and 他
  were among the pack's 60 commonest words, where Cantonese says and
  captions write 嘅, 係, 喺 and 佢. A word written `WRITTEN_ONLY` times or
  more as often as speech has it (HKCanCor's words, and the words of real
  Cantonese captions, `captions/yue.txt`) counts in writing only as often
  as speech has it (`Said.written`).
- **Readings.** A word HKCanCor's speakers say one way most of the time is
  read that way (`Everyday.heard`): 會 wui5 ("will"), not the literary
  wui6 that rime-cantonese weighs first.

Jyutping is written in the pack with each tone number raised (hai⁶, not
hai6): the card and the reading line show it as the pack has it (371
measured raised tones 26 % wider than the characters' own text, plain
digits 34 %).
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from polyglotic_desktop.core.lexicon.chinese import is_han
from polyglotic_desktop.core.lexicon.han import cut, runs

RAISED = str.maketrans("0123456", "⁰¹²³⁴⁵⁶")
"""Jyutping's tone numbers, raised."""

_CANTO = re.compile(r"^(\S+) (\S+) \[([^\]]*)\] \{([^}]*)\}(?: /(.*)/)?\s*(?:#.*)?$")
"""A line of CC-Canto or of its readings file:
`Traditional Simplified [pin1 yin1] {jyut6 ping3} /meaning/meaning/`, and
now and then a note after it (`# adapted from cc-cedict`)."""
_NUMBERED = re.compile(r"(?:^|\s+)\d+\.\s+")
"""Where CC-Canto numbers the senses it writes as one ("1. three 2. ...")."""
_SYLLABLE = re.compile(r"^[a-z]+[1-6]$")
"""One Jyutping syllable with its tone."""


def raised(jyutping: str) -> str:
    """`jyutping` with its tone numbers raised: "hai6" -> "hai⁶"."""
    return jyutping.translate(RAISED)


def is_jyutping(reading: str) -> bool:
    """Whether `reading` is all Jyutping syllables, each with its tone
    (CC-Canto writes a few with letters for English, "AA ji1")."""
    syllables = reading.split()
    return bool(syllables) and all(_SYLLABLE.match(s) for s in syllables)


@dataclass(frozen=True)
class CantoLine:
    traditional: str
    simplified: str
    pinyin: str
    jyutping: str
    meanings: tuple[str, ...]


def _zip_lines(path: Path) -> Iterator[str]:
    """The lines of the one text file in a zip archive (cantonese.org's)."""
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".txt"))
        with archive.open(name) as f:
            for line in f:
                yield line.decode("utf-8")


def parse(lines: Iterable[str]) -> Iterator[CantoLine]:
    """Every entry of CC-Canto's format; Jyutping and pinyin with single
    spaces, Jyutping in lower case."""
    for line in lines:
        if line.startswith("#"):
            continue
        match = _CANTO.match(line)
        if not match:
            continue
        traditional, simplified, pinyin, jyutping, meanings = match.groups()
        yield CantoLine(
            traditional,
            simplified,
            " ".join(pinyin.split()),
            " ".join(jyutping.lower().split()),
            senses(meanings or ""),
        )


def senses(meanings: str) -> tuple[str, ...]:
    """A line's meanings, one a sense: those it numbers inside one meaning
    ("1. three 2. (slang) love affair") apart."""
    out: list[str] = []
    for meaning in meanings.split("/"):
        meaning = meaning.strip()
        if meaning.startswith("1. "):
            out += [m.strip() for m in _NUMBERED.split(meaning) if m.strip()]
        elif meaning:
            out.append(meaning)
    return tuple(out)


ASIDE = ("(slang)", "surname ", "chinese surname", "(noun) chinese surname")
"""How CC-Canto and CC-CEDICT start a meaning a learner rarely means: slang
(四 "(slang) labourer") and surnames (年 "surname Nian")."""


_VARIANT_TARGET = re.compile(r"variant of ([^\s\[|,;]+)")
"""The word a "variant of" meaning points to (CC-CEDICT: "variant of
了解[liao3 jie3]", "variant of 爾|尔[er3]")."""


def pointer_only(
    words: Iterable[tuple[str, tuple[str, ...]]], variant_of: tuple[str, ...]
) -> dict[str, str]:
    """Each headword whose entries ((headword, meanings) pairs) only say
    "variant of" (`variant_of`) -> the word its first one points to
    (polyglotic-hq 467): 瞭解 -> 了解, 尒 -> 爾. Such a form opens on that
    word's entries, then its own, and isn't ranked by written Chinese: its
    Simplified form is the other word's (尔's share ranked 尒 2,048th)."""
    by_word: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for word, meanings in words:
        by_word[word].append(meanings)
    out: dict[str, str] = {}
    for word, own in by_word.items():
        if all(m.startswith(variant_of) for meanings in own for m in meanings):
            found = _VARIANT_TARGET.search(own[0][0]) if own[0] else None
            if found:
                out[word] = found.group(1)
    return out


TAGGED = ("(noun)", "(verb)", "(adjective)", "(adverb)", "(slang)")
"""How CC-Canto starts a line of its own, a part of speech first: "(noun)
1. city; 2. capital" for 都, "(noun) 1. The short form of France" for 法."""


def one_entry(lines: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    """The meanings of CC-Canto's lines of one word and reading, as one
    entry: plain lines (those adapted from CC-CEDICT: 都 "all", 法 "law")
    before lines it starts with a part of speech (`TAGGED`), which add a
    rarer or a Cantonese meaning; else in the file's order
    (polyglotic-hq 467)."""
    lines = list(lines)
    tagged = [line for line in lines if line and line[0].lower().startswith(TAGGED)]
    plain = [line for line in lines if line not in tagged]
    return tuple(dict.fromkeys(m for line in (*plain, *tagged) for m in line))


def meaning_pieces(meanings: Iterable[str]) -> set[str]:
    """Meanings in comparable pieces: each meaning's parts between ";" and
    ",", in lower case, of three letters or more - CC-Canto writes "to know"
    and "to be aware" where CC-CEDICT writes "to know; to be aware"."""
    return {
        piece
        for m in meanings
        for piece in (p.strip().lower() for p in re.split(r"[;,]", m))
        if len(piece) >= 3
    }


def read_canto(path: Path) -> list[CantoLine]:
    """CC-Canto's entries (its zip, as cantonese.org publishes it)."""
    return list(parse(_zip_lines(path)))


def pinyin_key(pinyin: str) -> str:
    """How a CC-CEDICT entry's pinyin is matched with the readings file's:
    lower case, no spaces, ü as v."""
    return pinyin.lower().replace("u:", "v").replace(" ", "")


def read_readings(path: Path) -> dict[tuple[str, str, str], list[str]]:
    """(Traditional, Simplified, `pinyin_key`) -> the Jyutping readings the
    readings file gives that CC-CEDICT entry, in its order."""
    found: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for line in parse(_zip_lines(path)):
        key = (line.traditional, line.simplified, pinyin_key(line.pinyin))
        if line.jyutping not in found[key]:
            found[key].append(line.jyutping)
    return dict(found)


def _rime_rows(path: Path) -> Iterator[list[str]]:
    """The rows of a rime dictionary file, after its `...` header."""
    body = False
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not body:
                body = line == "..."
                continue
            if line and not line.startswith("#"):
                yield line.split("\t")


def read_rime_words(path: Path) -> dict[str, list[str]]:
    """A word -> its readings, as rime-cantonese's word list gives them
    (its file order)."""
    found: dict[str, list[str]] = defaultdict(list)
    for row in _rime_rows(path):
        if len(row) >= 2 and row[1] not in found[row[0]]:
            found[row[0]].append(row[1])
    return dict(found)


def _weight(text: str) -> float:
    """A rime weight: "5%" -> 5; none given is the full weight (100)."""
    text = text.strip()
    return float(text.rstrip("%")) if text else 100.0


def read_rime_chars(path: Path) -> dict[str, dict[str, float]]:
    """A character -> each of its readings and its weight (none given:
    100), as rime-cantonese's character list gives them."""
    found: dict[str, dict[str, float]] = defaultdict(dict)
    for row in _rime_rows(path):
        if len(row) >= 2 and len(row[0]) == 1:
            weight = _weight(row[2]) if len(row) > 2 else 100.0
            found[row[0]][row[1]] = max(found[row[0]].get(row[1], 0.0), weight)
    return dict(found)


ReadsEveryday = Callable[[str, Collection[str] | None], str | None]
"""A word's everyday reading, of the readings given if any (`Everyday`)."""


class Everyday:
    """A written form's everyday Jyutping: as HKCanCor's speakers say it,
    if they mostly say it one way (`heard`: a word -> its readings in
    HKCanCor, counted; `Everyday.heard`). Else by rime-cantonese: a word's
    reading in its word list (of several, the one its characters are most
    often read; then its first) - else, character by character, each
    character's weightiest reading, a tie going to the reading more of the
    word list's words give it (`uses`)."""

    def __init__(
        self,
        words: Mapping[str, list[str]],
        chars: Mapping[str, Mapping[str, float]],
        heard: Mapping[str, Counter[str]] | None = None,
    ) -> None:
        self._words = words
        self._chars = chars
        self._heard = heard or {}
        self._uses: Counter[tuple[str, str]] = Counter()
        for word, readings in words.items():
            syllables = readings[0].split()
            if len(syllables) == len(word):
                self._uses.update(zip(word, syllables, strict=True))

    def char(self, ch: str) -> str | None:
        readings = self._chars.get(ch)
        if not readings:
            return None
        return max(readings, key=lambda r: (readings[r], self._uses[(ch, r)], -len(r)))

    def __call__(self, form: str, among: Collection[str] | None = None) -> str | None:
        """`form`'s everyday reading, a syllable a character - None if a
        character has none. Of `among` (the readings a word's entries have)
        if given: HKCanCor's speakers' if it is one of them, else
        rime-cantonese's if it is, else None - so a word read a way none of
        its entries is (成日 seng4 jat6, where CC-Canto writes "seng4 yat6")
        keeps its entries in rime-cantonese's order."""
        for reading in (self.heard(form), self.rime(form)):
            if reading is not None and (among is None or reading in among):
                return reading
        return None

    def rime(self, form: str) -> str | None:
        """`form`'s everyday reading by rime-cantonese alone."""
        readings = self._words.get(form)
        if readings:
            if len(readings) == 1:
                return readings[0]
            return max(
                readings, key=lambda r: (self._score(form, r), -readings.index(r))
            )
        syllables = [self.char(ch) for ch in form]
        if not all(syllables):
            return None
        return " ".join(s for s in syllables if s)

    def heard(self, form: str) -> str | None:
        """The reading HKCanCor's speakers give `form`: if they say it
        `HEARD_LEAST` times or more, that way `HEARD_SHARE` of the time or
        more, and rime-cantonese reads each character that way too - else
        None."""
        heard = self._heard.get(form)
        if not heard:
            return None
        reading, n = heard.most_common(1)[0]
        syllables = reading.split()
        if (
            n < HEARD_LEAST
            or n < HEARD_SHARE * sum(heard.values())
            or len(syllables) != len(form)
        ):
            return None
        known = all(
            s in self._chars.get(ch, {}) for ch, s in zip(form, syllables, strict=True)
        )
        return reading if known else None

    def _score(self, form: str, reading: str) -> float:
        syllables = reading.split()
        if len(syllables) != len(form):
            return 0.0
        return sum(
            self._chars.get(ch, {}).get(s, 0.0)
            for ch, s in zip(form, syllables, strict=True)
        )


_HKCANCOR_WORD = re.compile(r"^\s*([^/\s]+)/[^/]*/[^/]*/\s*$")
"""A word of HKCanCor's tagged sentences: `word/part of speech/jyutping/`."""


def hkcancor_counts(path: Path) -> Counter[str]:
    """How often each word is said in HKCanCor (its own word split), from
    its UTF-8 zip; words of Chinese characters only (not punctuation)."""
    counts: Counter[str] = Counter()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            text = archive.read(name).decode("utf-8", errors="replace")
            for line in text.splitlines():
                match = _HKCANCOR_WORD.match(line)
                if match and any(is_han(ch) for ch in match.group(1)):
                    counts[match.group(1)] += 1
    return counts


FIRST_SENSES: Mapping[str, tuple[str, ...]] = {
    "呢": (
        (
            "(sentence-final particle) used in questions to link back to prior "
            'discourse or context ("what about...?", "and...?")'
        ),
    ),
    "都": ("all", "also"),
    "就": ("then", "at once", "only"),
    "喇": ("sentence-final particle, indicating now",),
    "又": ("(once) again", "also"),
    "話": ("to talk", "to tell", "spoken words"),
    "去": ("to go", "to go to (a place)"),
    "可以": ("can", "may"),
    "知": ("to know", "to be aware"),
    "睇": ("to see", "to look at (Cantonese)", "to watch"),
    "因為": ("because; owing to; on account of",),
    "過": ("(experienced action marker)", "to cross", "to pass (time)"),
    "俾": ("to give", "to let", "by"),
    "可能": ("maybe", "perhaps", "possible"),
    "等": ("to wait for", "to let"),
    "不過": ("but", "however"),
    "將": (
        "(introduces object of main verb, used in the same way as 把bǎ [把])",
        "will",
        "shall",
    ),
    "公司": ("company; firm; corporation",),
    "出": ("to go out", "to come out"),
    "間": ("classifier for rooms", "classifier for shops, office or buildings"),
    "時": ("when", "time", "hour"),
    "張": ("classifier for flat objects, sheet", "sheet of paper"),
    "太": ("too (much)", "very", "extremely"),
    "走": ("to leave", "to go away", "to run", "to walk"),
    "長": ("long", "length"),
    "定": ("to decide", "surely", "certainly"),
    "十": ("ten",),
    "飲": ("to drink", "beverage"),
    "種": ("kind", "type", "classifier for types, kinds, sorts"),
    "難": ("difficult", "difficult (to...)", "problem"),
    "書": ("a book", "a letter"),
    "條": (
        (
            "classifier for long thin things (ribbon, river, road, trousers, "
            "people (in slangs) etc)"
        ),
        "strip",
    ),
    "卻": ("but", "yet", "however"),
    "及": ("and", "to reach"),
    "小": ("small", "tiny", "few"),
    "所": (
        "place",
        "classifier for houses, small buildings, institutions etc",
        "that which",
    ),
    "地": ("ground", "earth", "region"),
    "更": ("more", "even more", "further"),
    "帶": ("to bring", "to take along", "to lead"),
    "算": ("to regard as", "to calculate", "let it be"),
    "社會": ("society",),
    "寫": ("to write",),
    "貴": ("expensive", "noble"),
    "愛": ("to love", "to like"),
    "部": ("classifier for works of literature, films, machines etc", "department"),
    "好似": ("to seem", "to be like"),
    "所以": ("so", "therefore", "as a result"),
    "認為": ("to believe; to think; to consider; to feel",),
    "所有": ("all",),
    "講": ("to speak", "to explain"),
    "養": ("to raise (animals)", "to bring up (children)", "to keep (pets)"),
    "次": ("classifier for enumerated events: time", "next in sequence"),
    "搞": ("to do", "to make", "to mess up"),
    "乜": ("(Cantonese) what?",),
    "要": ("to want", "to need", "must"),
    "攞": ("to get", "to fetch", "to take"),
    "讓": ("to let sb do sth", "to allow", "to yield"),
    "想": ("to want", "to think", "to wish"),
    "驚": ("to be scared", "to be frightened", "to startle"),
    "跟": ("to follow closely", "with", "and (in addition to)"),
    "叫": ("to call", "to be called", "to ask"),
    "本": ("classifier for books, periodicals, files etc", "this", "origin"),
    "考": ("to take an exam", "to test", "to examine"),
    # CC-Canto's own line comes after the line adapted from CC-CEDICT
    # (`one_entry`); for these Cantonese words its line is the everyday one
    "唔": ("(verb) don't; doesn't; aren't", "(Cantonese) not"),
    "咩": (
        "(adverb) what?",
        "what",
        (
            "final particle which transforms statements into questions that "
            "indicate doubt or surprise (Cantonese)"
        ),
    ),
    "蚊": ("dollar", "(noun) 1. money; (coin)", "mosquito"),
    "邊": ("which", "where", "side"),
    "夠": ("to be enough", "adequate"),
    "耐": ("(slang) long duration of time", "long period of time"),
    "細": ("small", "tiny", "little"),
    "戲": ("(noun) movie", "drama", "play"),
    "揸": ("to hold", "to drive", "to grasp"),
    "抵": ("bargain", "to make up for"),
    "拎": ("to take away", "to bring over", "to lift"),
    "關": ("to close", "to shut", "to turn off"),
    "教": ("to teach", "to instruct", "teaching"),
    "埋": ("to move closer to", "closer together", "as well"),
    "點": (
        "how?",
        (
            "(adverb) 1. What; 2. How (noun) 1. snack (dim sum); 2. hour; (verb) "
            "1. examine; 2. check; (verb) (of head) to nod"
        ),
        "o'clock",
    ),
    "還": ("to give back", "to return something", "still"),
    "衰": ("bad", "to be down on luck", "to decline"),
    "派": ("to dispatch", "to send", "clique"),
    # found by the fresh audit sample (seed 467), both in the top 50
    "個": ("classifier for people or objects in general or an action", "individual"),
    "幾": ("how many", "how much", "several"),
}
"""A word -> the meanings its card opens on, in order: of its entries read
as its first is (its everyday reading), the one with the first of them
comes first, those meanings first in it. Read by hand on the pack's 300
commonest words (polyglotic-hq 467), where CC-Canto's first meaning is a
rare one (都 "(noun) 1. city; 2. capital", 公司 "(noun) 1. shops") or a
learner meets another (將 as the object marker, 時 "when")."""

OWN_SENSES: Mapping[str, tuple[str, ...]] = {
    "同": ("and; with (我同你, you and I)",),
    "年前": ("(after a number) ... years ago (幾年前, a few years ago)",),
    "晒": ("(after a verb) all; completely (食晒, eat it all up)",),
    "話": ("to say (佢話, he says)",),
    "定": ("or (in a question: 你去定唔去, are you going or not?)",),
}
"""Meanings neither CC-Canto nor CC-CEDICT gives a common word, written for
the pack (polyglotic-hq 467): its card opens on them. 同 is Cantonese's
commonest "and"; 年前 after a number is "years ago" (幾年前 is cut 幾 +
年前, and CC-CEDICT's 年前 is only "by the end of the year")."""


HEARD_LEAST = 5
"""How often HKCanCor must have a word said before its speakers' reading
is the everyday one (`Everyday.heard`)."""
HEARD_SHARE = 0.6
"""The share of a word's sayings in HKCanCor one reading must have to be
the everyday one (polyglotic-hq 467 chose both on half of HKCanCor's
recordings and measured them on the other half)."""

_SYLLABLES = re.compile(r"[a-z]+[1-6]")
_TOKEN = re.compile(r"^\s*([^/\s]+)/[^/]*/([^/]*)/\s*$")
"""A word of HKCanCor's tagged sentences, and its Jyutping (no spaces)."""


@dataclass(frozen=True)
class Utterance:
    """A sentence of HKCanCor: its words (its own split) and each word's
    Jyutping, a space between syllables ("" where its syllables don't
    match its characters); `file`, the recording it is from."""

    file: str
    words: tuple[str, ...]
    readings: tuple[str, ...]


def hkcancor_utterances(path: Path) -> list[Utterance]:
    """HKCanCor's sentences, from its UTF-8 zip, in its files' order."""
    out: list[Utterance] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            text = archive.read(name).decode("utf-8", errors="replace")
            for block in text.split("<sent_tag>")[1:]:
                words: list[str] = []
                readings: list[str] = []
                for line in block.split("</sent_tag>")[0].splitlines():
                    match = _TOKEN.match(line)
                    if not match:
                        continue
                    word, jyutping = match.groups()
                    syllables = _SYLLABLES.findall(jyutping)
                    words.append(word)
                    fits = len(syllables) == len(word)
                    readings.append(" ".join(syllables) if fits else "")
                if words:
                    out.append(Utterance(name, tuple(words), tuple(readings)))
    return out


def heard_readings(utterances: Iterable[Utterance]) -> dict[str, Counter[str]]:
    """Each word of Chinese characters -> how often HKCanCor's speakers
    say it each way."""
    heard: dict[str, Counter[str]] = defaultdict(Counter)
    for u in utterances:
        for word, reading in zip(u.words, u.readings, strict=True):
            if reading and all(is_han(ch) for ch in word):
                heard[word][reading] += 1
    return dict(heard)


CAPTIONS = Path(__file__).parent / "captions" / "yue.txt"
"""Real Cantonese captions, a clause a line (`captions/README.md`)."""

SAID_RUN = 4
"""The most HKCanCor words a form is counted across (`said`): HKCanCor
writes 一個 ("one", "a") as 一 + 個, and the dictionaries have it whole."""

WRITTEN_ONLY = 50
"""How many times as often as speech a word must be written to count as
written only (`Said.written`). At 50: 的, 是, 在, 了, 不, 他, 這, 說,
我們, 們 and 誰 are; 被, 從, 時 and 以及, which the captions say, aren't;
at 100, 不 wasn't (polyglotic-hq 467)."""


@dataclass(frozen=True)
class Said:
    """How often each word is said: `counts` of `total` words."""

    counts: Mapping[str, int]
    total: int

    def written(self, word: str, share: float) -> float:
        """`word`'s share of written Chinese as its rank counts it: as it is,
        unless that is `WRITTEN_ONLY` times or more what speech gives the
        word (said once more than it is: nothing is never said) - then only
        what speech gives it. A Mandarin word Cantonese doesn't say (的 for
        嘅, 是 for 係, 他 for 佢) is ranked as rarely as speech says it."""
        bound = (self.counts.get(word, 0) + 1) / max(self.total, 1)
        return bound if share >= WRITTEN_ONLY * bound else share


def said(
    utterances: Iterable[Utterance], captions: Iterable[str], forms: Collection[str]
) -> Said:
    """How often each word of Chinese characters is said: HKCanCor's words,
    and each of `forms` (the pack's written forms) also where it is a run of
    up to `SAID_RUN` of them; and the captions' words, each caption cut
    into `forms` (fewest words, as the split cuts, `han.cut`)."""
    counts: Counter[str] = Counter()
    total = 0
    for u in utterances:
        han = [all(is_han(ch) for ch in w) for w in u.words]
        total += sum(han)
        for i in range(len(u.words)):
            for k in range(1, SAID_RUN + 1):
                if i + k > len(u.words) or not all(han[i : i + k]):
                    break
                word = "".join(u.words[i : i + k])
                if k == 1 or word in forms:
                    counts[word] += 1
    for caption in captions:
        for start, end, chinese in runs(caption):
            if not chinese:
                continue
            run = caption[start:end]
            for a, b in cut(run, forms, {}):
                counts[run[a:b]] += 1
                total += 1
    return Said(counts, total)


def captions(path: Path = CAPTIONS) -> list[str]:
    """The captions' clauses (`CAPTIONS`)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]
