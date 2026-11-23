"""Chinese: word split, everyday readings, parts and reverse lookup.

From the proof of concept's `dictionary.py` (CC-CEDICT, the word split
that keeps whole phrases and chengyu together, everyday readings, English
to Chinese), reading entries through the `DictionaryFile` port instead of
holding the whole dictionary in memory.

Some rules run when the dictionary file is built rather than in the app,
so that loading is instant: `everyday_first` (the order of a word's
entries) and `index_words` (the reverse lookup's index). They live here so
the rule has one home; `tools/dictionaries` calls them.
"""

import bisect
import itertools
import math
import re
import threading
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from polyglotic_desktop.core.lexicon import spoken
from polyglotic_desktop.core.lexicon.entries import (
    SCHEMES,
    DictionaryEntry,
    entry_facts,
    is_number_word,
    words_in_runs,
)
from polyglotic_desktop.core.lexicon.pinyin import mark_pinyin
from polyglotic_desktop.core.lexicon.readings import Reading
from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine
from polyglotic_desktop.ports.dictionary import DictionaryFile, EntryRecord

MAX_WORD = 20  # characters - CC-CEDICT's longest entries are whole proverbs
# Reverse lookup ranks at most this many entries per English word form, the
# commonest: "to" is in about 35,000 meanings, and ranking them all takes 2s.
REVERSE_CANDIDATES = 2000

# Readings put first by hand, where the rules in everyday_first get it wrong:
# - characters read differently alone than in most of the words that contain
#   them: function words (还 hái, though huán is in more words), and words
#   whose lone use is the common one (更 gèng "more", though gēng is in 更新
#   and 变更; 将 jiāng "will", not jiàng as in 将军);
# - longer words whose everyday reading `_says_most` misses (生意 shēng yi,
#   "business", not shēng yì, "vitality"; 大都 dà dōu, "mostly", not dà dū).
# polyglotic-hq 364 and 366, judged by hand against pypinyin's phrases.
EVERYDAY_READINGS = {
    "还": "hái", "還": "hái", "都": "dōu", "了": "le", "着": "zhe", "著": "zhe",
    "得": "de", "的": "de", "吧": "ba", "呢": "ne", "啊": "a", "吗": "ma",
    "嗎": "ma", "嘛": "ma", "呀": "ya", "么": "me", "麼": "me", "哪": "nǎ",
    "更": "gèng", "将": "jiāng", "將": "jiāng", "为": "wèi", "為": "wèi",
    "应": "yīng", "應": "yīng", "教": "jiāo", "曾": "céng", "薄": "báo",
    "大都": "dà dōu", "开通": "kāi tōng", "開通": "kāi tōng",
    "播种": "bō zhǒng", "播種": "bō zhǒng", "省事": "shěng shì",
    "说道": "shuō dào", "說道": "shuō dào", "杆子": "gān zi",
    "本事": "běn shi", "生意": "shēng yi", "妻子": "qī zi",
    "下调": "xià tiáo", "下調": "xià tiáo", "起来": "qǐ lai", "起來": "qǐ lai",
}  # fmt: skip

READINGS_KEPT = 20000
"""Words whose syllables are kept for reading lines (`_syllables`)."""
LONE_READINGS = {"贾": "jiǎ", "賈": "jiǎ"}
"""How a character standing as a word by itself is read on a reading line,
where that isn't the reading its entries put first: 贾 alone is nearly
always the surname Jiǎ, not gǔ, "merchant". 364 judged 98 more lone
readings on FLEURS text; the file's order (`everyday_first`, 366) gives
them all, and a test on the real CC-CEDICT holds it there."""
WORD_READINGS = {
    "都会": ["dōu", "huì"],
    "都會": ["dōu", "huì"],
    "上都": ["shàng", "dōu"],
    "手把": ["shǒu", "bǎ"],
}
"""Words the word split takes for one that are nearly always two in
speech (都会 "will all", not dū huì, "a metropolis")."""
_WEI_AFTER = frozenset(
    "作成称稱名变變视視定改转轉列评評誉譽分设設译譯认認化乃沦淪布义義建选選封升判划劃归歸"
)
_WEI_BEFORE = frozenset("主首例止生准準限期食")
_COUNTS = frozenset("一二两兩三四五六七八九十百千几幾每这這那哪半数數0123456789")
_GROWS = frozenset("得了着著出成满滿在")
_CLAUSE_END = frozenset('，。；：！？,.;:!?（）()“”"')
_MUST_AFTER = frozenset("就还還也必总總非都又才便我你他她它们們咱您须須")
_PLACE_BEFORE = frozenset(
    "之的是和与與及或上下里裡内內外中区區点點方带帶也都就在有为為"
)
_HEAVY_AFTER = frozenset("很太更最较較不得")
_AGAIN = frozenset(
    "写寫做开開回建启啟装裝组組申审審演播返拾读讀看听聽说說算选選排印考修整设設置发發来來走试試拍画畫编編订訂"
)


def is_han(char: str) -> bool:
    """A Chinese character (CJK Unified Ideographs, Extension A, the
    compatibility ideographs, Extensions B-F, and 〇). Written as code
    points: the compatibility block starts at U+F900, and its first
    character looks the same as U+8C48 - written as a character, the range
    once took in Hangul, the private use area and more (polyglotic-hq 337)."""
    return (
        "\u3400" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        or "\U00020000" <= char <= "\U0002ffff"
        or char == "\u3007"
    )


def has_han(text: str) -> bool:
    return any(is_han(c) for c in text)


def entry_from_record(record: EntryRecord) -> DictionaryEntry:
    """A CC-CEDICT entry with its pinyin tone-marked. Capitalised pinyin
    marks a proper noun - a name or place - in CC-CEDICT."""
    return DictionaryEntry(
        entry_id=EntryId(record.entry_id),
        headword=record.headword,
        traditional=record.traditional,
        reading=mark_pinyin(record.reading),
        meanings=record.meanings,
        sense_classes=record.sense_classes,
        sense_prefixes=record.sense_prefixes,
        frequency_rank=record.frequency_rank,
        levels=record.levels,
        is_name=_is_name(record),
        spoken_rank=spoken.MANDARIN.rank(record.headword),
        is_filler=spoken.MANDARIN.is_filler(record.headword),
    )


def facts_from_record(record: EntryRecord, scheme_id: str) -> EntryFacts:
    """`entry_from_record(record).facts(scheme_id)`, without marking the
    pinyin - most of making an entry (polyglotic-hq project 212)."""
    return entry_facts(
        EntryId(record.entry_id),
        record.frequency_rank,
        record.levels,
        _is_name(record),
        scheme_id,
        is_number_word(record.headword, record.levels),
        spoken.MANDARIN.rank(record.headword),
        spoken.MANDARIN.is_filler(record.headword),
    )


def _is_name(record: EntryRecord) -> bool:
    return record.reading[:1].isupper()


# -- rules applied when the file is built ---------------------------------------


def count_reading_uses(entries: Iterable[DictionaryEntry]) -> Counter[tuple[str, str]]:
    """How many words use each reading of each character: (char, syllable)
    -> words. CC-CEDICT has no frequencies, but this is a good stand-in for
    a character's everyday reading (足: zú in 329 words, jù in none)."""
    uses: Counter[tuple[str, str]] = Counter()
    for e in entries:
        syllables = e.reading.lower().split()
        if len(e.headword) > 1 and len(syllables) == len(e.headword):
            for form in {e.headword, e.traditional}:
                uses.update(zip(form, syllables, strict=True))
    return uses


def everyday_first(
    word: str, entries: Iterable[DictionaryEntry], uses: Counter[tuple[str, str]]
) -> list[DictionaryEntry]:
    """`word`'s entries in the order a lookup shows them: real meanings
    before "variant of", common words before names, then the reading
    likeliest in speech: one put first by hand (`EVERYDAY_READINGS`); for a
    character, then the reading most words use; for a longer word, the
    reading that says the most (`_says_most`), and where two say as much,
    the file's order."""
    return sorted(
        entries,
        key=lambda e: (
            e.variant_only,
            e.is_name,
            e.reading != EVERYDAY_READINGS.get(word, e.reading),
            _says_most(e) if len(word) > 1 else (0, 0),
            -uses[word, e.reading.lower()],
        ),
    )


_NOTE = re.compile(r"^\([^)]*\)\s*")
"""A note before a sense: "(of time, a video clip) to run in reverse"."""
_NOT_A_SENSE = re.compile(r"CL:|see |also ")
"""What CC-CEDICT puts among a word's senses that isn't one: its measure
word, "see also 老公[lao3 gong1]", "also written ..."."""


def _says_most(entry: DictionaryEntry) -> tuple[int, int]:
    """How a longer word's readings are ordered - lowest first. CC-CEDICT's
    file order puts the rarer reading first for many (结果 jiē guǒ "to bear
    fruit" before jié guǒ "result"; 教授 jiāo shòu "to teach" before jiào
    shòu "professor"; 重点 chóng diǎn before zhòng diǎn). A reading that is
    a noun or an adjective comes before one that is only a verb, then the
    one with more senses. A note on how else it is said, its measure word
    or a "see also" isn't a sense; a sense that is only a note in brackets
    ("(after a verb, indicates ...)": 出来 as a verb's ending) names
    nothing (polyglotic-hq 364 and 366)."""
    senses = [
        _NOTE.sub("", sense.strip())
        for meaning in entry.meanings
        for sense in meaning.split(";")
        if "pr. [" not in sense and not _NOT_A_SENSE.match(sense.strip())
    ]
    names = any(sense and not sense.startswith("to ") for sense in senses)
    return int(not names), -len(senses)


_INDEX_WORD = re.compile(r"[a-z]+")


def index_words(entry: DictionaryEntry) -> set[str]:
    """The English words reverse lookup finds `entry` by - none for a
    "variant of" entry, and not from measure words ("CL:")."""
    if entry.variant_only:
        return set()
    words: set[str] = set()
    for meaning in entry.meanings:
        if not meaning.startswith("CL:"):
            words.update(_INDEX_WORD.findall(meaning.lower()))
    return words


# -- reverse lookup helpers -----------------------------------------------------

_STOP = {
    "a", "an", "the", "to", "of", "it", "its", "is", "am", "are", "was", "were",
    "be", "been", "will", "would", "have", "has", "and", "or", "in", "on", "at",
    "for", "with", "this", "that", "i", "you", "me", "my", "your", "s", "so",
    "just", "like", "do",
}  # fmt: skip
# A reading's first meaning starting so: rarely the one being said
_OBSCURE = (
    "(archaic)", "(literary)", "(old)", "(dialect)", "(Cantonese)",
    "old variant", "surname", "used in",
)  # fmt: skip
_CONTRACTIONS = {"re": " are", "m": " am", "ll": " will", "ve": " have", "d": " would"}


def _plain(text: str) -> str:
    """A meaning (or English query) compared plainly: lower case, no
    "(coll.)"-style notes, no articles, no leading "to"."""
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    text = " ".join(
        w for w in re.findall(r"[a-z']+", text) if w not in ("a", "an", "the")
    )
    return re.sub(r"^to ", "", text)


def _stems(word: str) -> list[str]:
    """The word and what it may be in a meaning: games -> game, overdoing
    -> overdo, lagging -> lag."""
    forms = [word]
    for suffix, back in (
        ("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
    ):  # fmt: skip
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = word[: -len(suffix)] + back
            forms.append(stem)
            if len(stem) > 3 and stem[-1] == stem[-2]:  # lagging -> lagg -> lag
                forms.append(stem[:-1])
    return forms


_NO_RANK = 10**9
"""Past every frequency rank."""


def _commonness(rank: int | None) -> float:
    """Higher for commoner words: about log2 of a count, from the rank."""
    return 0.0 if rank is None else max(0.0, 21 - math.log2(rank))


COMMON_PARTS = 3000
"""How common both words of a phrase must be (each among the commonest
this many) for the split to take the two words over the phrase: an
unranked dictionary form that is two such words (`_two_common_words`)
isn't a word to the split, unless it is a name, an idiom or a word a
syllabus lists (polyglotic-hq 359, decision 0151)."""


def _two_common_words(form: str, commonness: Mapping[str, float]) -> bool:
    """Whether `form` is two words that are each among the `COMMON_PARTS`
    commonest (中的: 中 + 的)."""
    least = _commonness(COMMON_PARTS)
    return any(
        commonness.get(form[:k], 0.0) >= least
        and commonness.get(form[k:], 0.0) >= least
        for k in range(1, len(form))
    )


SOUND_CHARACTERS = frozenset(
    "阿埃艾爱安昂奥巴拜班邦包保鲍贝本比彼毕宾波伯博布查达戴丹道德登迪蒂丁"
    "杜敦多厄恩尔法菲费芬丰冯弗福富盖甘冈高戈格根古圭哈海汉豪赫亨胡霍基吉"
    "加贾杰金卡凯坎康考柯科克肯库夸奎昆拉莱赖兰朗劳勒雷蕾黎里利莉丽列林琳"
    "隆卢鲁路伦罗洛马玛迈麦曼芒梅门蒙米密摩莫默姆穆纳娜奈南内尼涅宁纽努诺"
    "欧帕潘庞佩彭皮珀普齐奇恰乔切钦琼丘瑞若萨塞赛桑瑟森沙莎绍舍施什舒斯松"
    "苏索塔泰坦汤唐特提廷图托瓦万旺威韦维温沃乌伍西希锡夏谢辛休修雅亚扬耶"
    "伊依因尤约泽扎詹朱兹佐茨"
)
"""Characters Chinese spells foreign names with by their sound (德克萨斯
Texas, 奥巴马 Obama, 尼古西亚 Nicosia): the common ones of Xinhua's
transliteration tables. A name made only of them has no words inside it -
its pieces (萨斯, 巴马, 西亚) are other words that happen to sound alike.
Hand-picked; a name it misses still shows its pieces, as before."""

NAME_PIECE_RANK = 2000
"""A lone character of a run of `SOUND_CHARACTERS` rarer than this as a
word by itself marks the run a name (勒 of 米勒 is the 4,201st word, 尔 of
杜瓦尔 the 2,242nd): a commoner one (米 154th, 马 360th) is as often a word
of its own, and 班, 1,831st, made 班里 and 本班 names in 485's meetings
(polyglotic-hq 496)."""

SOUNDS_KEPT = 5000
"""Characters' and words' readings kept for `named_by_sound`."""


SPELLINGS_MOST = 512
"""A word with more ways to say it than this (many characters of many
readings) isn't checked: a name is a few characters."""


def names_spelt_by_sound(text: str, words: Sequence[WordInLine]) -> list[WordInLine]:
    """`words` - a line's, in order - with each piece of a foreign name the
    dictionary hasn't got taken for a name (`EntryFacts.is_name`): a run of
    words side by side, each made only of `SOUND_CHARACTERS` and either one
    character or a name, two characters or more, not one character said
    again (查查, "have a look"), and with a lone character rarer than
    `NAME_PIECE_RANK` as a word by itself. 杜瓦尔 is split 杜|瓦|尔 and
    米勒 米|勒: each piece is a name, not a word to learn (polyglotic-hq
    496: of the 33 runs it found in 491's live Mandarin, 100 FLEURS
    sentences and 485's 10,540 meeting lines, 31 were names)."""
    out = list(words)
    i = 0
    while i < len(out):
        j = i
        while j < len(out) and _sound_piece(text, out[j]):
            if j > i and out[j - 1].end != out[j].start:
                break
            j += 1
        if j == i:
            i += 1
            continue
        run = text[out[i].start : out[j - 1].end]
        if (
            len(run) >= 2
            and len(set(run)) > 1
            and any(
                w.end - w.start == 1
                and (
                    w.entry.frequency_rank is None
                    or w.entry.frequency_rank > NAME_PIECE_RANK
                )
                for w in out[i:j]
            )
        ):
            for k in range(i, j):
                if not out[k].entry.is_name:
                    out[k] = replace(out[k], entry=replace(out[k].entry, is_name=True))
        i = j
    return out


def as_names(
    words: Sequence[WordInLine], spans: Iterable[tuple[int, int]]
) -> list[WordInLine]:
    """`words` with each one inside a span of `spans` taken for a name: a
    word link joins a name's pieces (礼凡 of 张礼凡, split 礼|凡, is one
    link to "Lifan"), so a name found by its link holds them all."""
    found = list(spans)
    if not found:
        return list(words)
    return [
        replace(w, entry=replace(w.entry, is_name=True))
        if not w.entry.is_name and any(a <= w.start and w.end <= b for a, b in found)
        else w
        for w in words
    ]


def _sound_piece(text: str, word: WordInLine) -> bool:
    piece = text[word.start : word.end]
    return all(c in SOUND_CHARACTERS for c in piece) and (
        len(piece) == 1 or word.entry.is_name
    )


def _unaccented(text: str) -> str:
    """`text` without its accents (Lǚ, Zé)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _cuts(start: int, end: int, span: tuple[int, int]) -> bool:
    """Whether the piece `[start, end)` cuts into `span` - overlaps it
    without holding it whole."""
    inside, outside = span
    overlaps = start < outside and inside < end
    return overlaps and not (start <= inside and outside <= end)


def _alone(text: str, spans: Sequence[tuple[int, int]], at: int, reading: str) -> str:
    """How the character that is word `at` of `text` by itself is read,
    where the words around it say (`reading`: its reading otherwise):

    - 为 is wéi ("to be, as") after a lone 以 in its clause (以…为…),
      before 所 in it (为…所…), after a verb that takes it (称为, 视为,
      命名为), before a number or a clause's end - and wèi ("for")
      otherwise. The rule that is wrong most often: the two are told
      apart by the sentence's grammar, which a dictionary doesn't have.
    - 地 between two words is the adverb's de, unless what follows says
      it's a place (购物地之一).
    - 只 after a number is the measure word zhī.
    - 长 before 得, 了 or 出 is zhǎng, to grow.
    - 得 after 就 or a pronoun, before a verb, is děi, must.
    - 重 before a verb is chóng, again."""
    start, end = spans[at]
    char = text[start:end]
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    if char in "为為":
        first = at
        while first and text[spans[first - 1][1] - 1] not in _CLAUSE_END:
            first -= 1
        last = at + 1
        while last < len(spans) and text[spans[last][0]] not in _CLAUSE_END:
            last += 1
        if (
            before in _WEI_AFTER
            or after in _WEI_BEFORE
            or not is_han(after)
            or any(text[a:b] == "以" for a, b in spans[first:at])
            or any(text[a:b] == "所" for a, b in spans[at + 1 : last])
        ):
            return "wéi"
        return "wèi"
    if char in "只隻" and before and before in _COUNTS:
        return "zhī"
    if char in "长長" and after and after in _GROWS:
        return "zhǎng"
    if char == "得" and (not is_han(before) or before in _MUST_AFTER) and is_han(after):
        return "děi"
    if char == "重" and after and after in _AGAIN and before not in _HEAVY_AFTER:
        return "chóng"
    if char == "地" and is_han(before) and is_han(after) and after not in _PLACE_BEFORE:
        return "de"
    return reading


class ChineseDictionary:
    """CC-CEDICT for Chinese learners: lookups in either script, the word
    split, parts, pinyin for a phrase, and English to Chinese.

    Opening one reads nothing. The word split needs every headword and
    frequency rank (about 0.2 s for CC-CEDICT, polyglotic-hq project 110):
    `prepare` reads them - call it off the interface thread at start, and
    ask `ready` before splitting on it (polyglotic-hq project 136);
    otherwise the first split, `is_word` or `parts` does. Lookups are
    queries."""

    def __init__(self, file: DictionaryFile) -> None:
        self._file = file
        self._left_to_words: dict[str, bool] = {}
        """Unranked forms of two common words met by the split, and whether
        each is a phrase the split leaves for its words (`_is_phrase`)."""
        self._split: dict[str, float] | None = None
        """Every written form in the dictionary, with its commonness (0.0
        for the many without a frequency rank): one mapping, so each form is
        held once (polyglotic-hq project 136: about 25 MB for CC-CEDICT)."""
        self._preparing = threading.Lock()
        self._read: dict[str, list[str] | None] = {}
        """Words read for a reading line (`_syllables`)."""
        self._syllabus: dict[str, tuple[list[tuple[int, int, str]], set[str]]] = {}
        """Each level scheme's words by place, once read (`_leveled`)."""
        self._form_sounds: dict[str, set[str]] = {}
        """Characters' and words' readings without tones (`_sounds`)."""
        self._simplified_of: Mapping[str, str] = {}
        """Traditional characters -> the Simplified ones they were converted
        from (`read_traditional`); {} while Traditional isn't shown."""

    def read_traditional(self, simplified_of: Mapping[str, str]) -> None:
        """From now on, find words in Traditional text by their Simplified
        form too (`traditional.TraditionalChinese.simplified_of`): the
        converter writes Taiwan's and OpenCC's forms, and CC-CEDICT hasn't
        every one (佈滿 is its 布滿, 上週 its 上周), so a converted line
        would split - and count words - unlike the line it came from
        (polyglotic-hq 375). {} forgets them: Traditional no longer shown,
        lookups, splits and readings are a Simplified reader's again (442).
        Safe from any thread: set in one step."""
        self._simplified_of = dict(simplified_of)
        self._read = {}  # readings found, or not, by the forms before

    def simplified(self, text: str) -> str:
        """`text` with each converted Traditional character back as its
        Simplified one - the same length; `text` as it is until Traditional
        is shown (`read_traditional`)."""
        of = self._simplified_of
        return "".join(of.get(c, c) for c in text) if of else text

    @property
    def ready(self) -> bool:
        """Whether the word split's data is read: `split`, `words_in` and
        `parts` answer without reading it first."""
        return self._split is not None

    def prepare(self) -> None:
        """Reads what the word split needs, once. Safe to call from another
        thread while this one is used: the data is set in one step, and a
        second caller waits for the first instead of reading it again."""
        if self._split is not None:
            return
        with self._preparing:
            if self._split is None:
                commonness = {
                    form: _commonness(rank)
                    for form, rank in self._file.frequency_ranks().items()
                }
                for form in self._file.headwords():
                    commonness.setdefault(form, 0.0)
                self._split = commonness

    def _split_data(self) -> dict[str, float]:
        """The headwords and their commonness, read now if not yet."""
        self.prepare()
        assert self._split is not None
        return self._split

    @property
    def has_sense_classes(self) -> bool:
        return getattr(self._file, "has_sense_classes", True)

    def lookup(self, word: str) -> list[DictionaryEntry]:
        """Every entry for `word` (in either script), everyday reading first.
        Once Traditional is shown (`read_traditional`), a Traditional form
        the dictionary hasn't got, or has only as "variant of" (宣佈:
        "variant of 宣布"), is found by its Simplified one - so the line
        counts the word a learner knows, not a variant of it (375)."""
        entries = [entry_from_record(r) for r in self._file.records(word)]
        if self._simplified_of and all(e.variant_only for e in entries):
            simplified = self.simplified(word)
            if simplified != word:
                instead = [entry_from_record(r) for r in self._file.records(simplified)]
                # a variant's own reading first: 瞭 is 了's liǎo, not le
                said = {e.reading for e in entries}
                instead.sort(key=lambda e: bool(said) and e.reading not in said)
                if instead and not instead[0].variant_only:
                    return instead
        return entries

    def entry(self, entry_id: EntryId) -> DictionaryEntry | None:
        """The entry with this ID - or the one it was merged into."""
        record = self._file.record(entry_id)
        return entry_from_record(record) if record else None

    def facts(self, entry_id: EntryId, scheme_id: str) -> EntryFacts | None:
        """`entry(entry_id).facts(scheme_id)`, read without making the entry:
        what Learning asks for every word met (polyglotic-hq project 212)."""
        record = self._file.record(entry_id)
        return facts_from_record(record, scheme_id) if record else None

    def words_in_ranks(self, runs: Sequence[tuple[int, int]]) -> list[int]:
        """How many words (written forms) each run of frequency ranks
        (first, last) has - the sizes of Words' bands."""
        last = max((last for _, last in runs), default=0)
        return words_in_runs(self._file.words_ranked(last), runs)

    def words_past(
        self, after: int, limit: int, scheme_id: str
    ) -> list[tuple[int, EntryFacts]]:
        """The words placed past `after`, earliest first: each with its
        place and the facts of the entry a caption counts it for
        (`words_in`: its everyday reading's) - what a learning load takes
        in (polyglotic-hq 324). A word's place is its frequency rank, or
        the size of its level's vocabulary in the syllabus `scheme_id`
        where that is smaller (as Learning places it: 游戏 is the 2,847th
        word in written text and an HSK 3 word, so its place is 1,000).

        Read `limit` ranked words at a time; the syllabus's words placed
        up to where that reading ends come with them, so the answer can be
        longer than `limit`. Empty: no more words."""
        leveled, in_syllabus = self._leveled(scheme_id)
        found: list[tuple[int, int, str]] = []
        rank_after = after
        while not found:
            ranked = self._file.headwords_ranked(rank_after, limit)
            end = ranked[-1][1] if len(ranked) >= limit else _NO_RANK
            found = [(r, r, word) for word, r in ranked if word not in in_syllabus]
            first = bisect.bisect_right(leveled, (after, _NO_RANK, ""))
            last = bisect.bisect_right(leveled, (end, _NO_RANK, ""))
            found += leveled[first:last]
            if end == _NO_RANK:
                break
            rank_after = after = end
        words = []
        for place, _, headword in sorted(found):
            records = self._file.records(headword)
            if records:
                words.append((place, facts_from_record(records[0], scheme_id)))
        return words

    def _leveled(self, scheme_id: str) -> tuple[list[tuple[int, int, str]], set[str]]:
        """The syllabus's words as (place, rank, headword), earliest first
        (a word without a rank after those with one), and their headwords
        - read once a scheme (about 11,000 for HSK 3.0). None for a scheme
        that doesn't say how many words each level holds."""
        if scheme_id not in self._syllabus:
            scheme = SCHEMES.get(scheme_id)
            sizes = scheme.sizes if scheme else ()
            placed = []
            for headword, level, rank in (
                self._file.headwords_at_levels(scheme_id) if sizes else ()
            ):
                if 1 <= level <= len(sizes):
                    size = sizes[level - 1]
                    place = size if rank is None else min(rank, size)
                    placed.append((place, rank or _NO_RANK - 1, headword))
            placed.sort()
            self._syllabus[scheme_id] = (placed, {word for _, _, word in placed})
        return self._syllabus[scheme_id]

    def words_at_levels(self, scheme_id: str) -> Mapping[int, int]:
        """How many headwords the level scheme puts at each level."""
        return self._file.words_at_levels(scheme_id)

    def merged_ids(self) -> list[EntryId]:
        """The entry IDs merged into other entries (decision 0007): what
        `Vocabulary.follow_merged_entries` checks at start."""
        return [EntryId(old) for old in self._file.merged_ids()]

    def is_word(self, text: str) -> bool:
        return text in self._split_data()

    def split(self, text: str) -> list[tuple[int, int]]:
        """The word split: [(start, end)] covering `text`, each run of Chinese
        characters cut into dictionary words - as few as possible, so whole
        phrases and chengyu stay together; among equally few, the most
        evenly sized (研究/生命/起源, not 研究生/命/起源), then the commoner
        words (是/非常, not 是非/常; 这个/人, not 这/个人 - by the entries'
        frequency ranks), then the longest first. Everything else (Latin,
        digits, punctuation) is one span per run, not looked up.

        Project 039 (2026-11-05) measured the split on 60 FLEURS sentences:
        every wrong cut that made a non-word (很|多情|况, 中看|到, 会面|临刑|事)
        was a tie on the first two rules, and the frequency rule fixes
        them all. The server splits the same way for word links, with the
        same ranks, so a link's underline matches the hover highlight.

        **A phrase of two common words isn't a word** (polyglotic-hq 359,
        decision 0151): CC-CEDICT's 中的 ("to hit the target"), 有了 ("to
        be pregnant") and 到了 have no frequency rank, yet as one word they
        beat 中 + 的 on the first rule, so 生活中的 read "to hit the
        target". A form without a rank that is two words each among the
        `COMMON_PARTS` commonest is left to its words - unless it's a name,
        an idiom or a word HSK lists (有的, "some")."""
        spans: list[tuple[int, int]] = []
        i, n = 0, len(text)
        while i < n:
            j = i
            if is_han(text[i]):
                while j < n and is_han(text[j]):
                    j += 1
                spans += [(i + a, i + b) for a, b in self._split_run(text[i:j])]
            else:
                while j < n and not is_han(text[j]):
                    j += 1
                spans.append((i, j))
            i = j
        return spans

    def _split_run(self, run: str) -> list[tuple[int, int]]:
        words = self._split_data()  # a form -> its commonness
        simplified = self.simplified(run)  # a converted line splits as before (375)
        n = len(run)
        # best[i]: (words, sum of squared lengths, -commonness, previous cut)
        # for run[:i]; commonness is the words' summed _commonness
        best: list[tuple[int, int, float, int] | None] = [(0, 0, 0.0, -1)] + [None] * n
        for end in range(1, n + 1):
            for start in range(max(0, end - MAX_WORD), end):
                before = best[start]
                word = run[start:end]
                if word not in words:
                    word = simplified[start:end]
                if before is None or (
                    end - start > 1
                    and (word not in words or self._is_phrase(word, words))
                ):
                    continue
                candidate = (
                    before[0] + 1,
                    before[1] + (end - start) ** 2,
                    before[2] - words.get(word, 0.0),
                    start,
                )
                current = best[end]
                # <=: on a tie the later start wins - the longer earlier word
                if current is None or candidate[:3] <= current[:3]:
                    best[end] = candidate
        cuts = []
        end = n
        while end > 0:
            step = best[end]
            assert step is not None  # every single character is a step
            cuts.append((step[3], end))
            end = step[3]
        return cuts[::-1]

    def _is_phrase(self, form: str, words: Mapping[str, float]) -> bool:
        """Whether the dictionary form `form` is a phrase the split leaves
        for its words: unranked (`words`: the split's commonness), two
        common words (`_two_common_words`), and not a name, an idiom or a
        word a syllabus lists (有的, HSK 1). Asked of the file once a form."""
        if words.get(form, 0.0) or not _two_common_words(form, words):
            return False
        found = self._left_to_words.get(form)
        if found is None:
            found = not any(
                _is_name(r) or r.levels or any("(idiom)" in m for m in r.meanings)
                for r in self._file.records(form)
            )
            self._left_to_words[form] = found
        return found

    def words_in(self, text: str, scheme_id: str) -> list[WordInLine]:
        """The dictionary words in `text`, by the word split, each with the
        facts Learning needs for a learner in `scheme_id` - for highlights
        and exposures. A word counts for its everyday reading's entry (还
        for hái). Characters the dictionary hasn't got are left out. The
        pieces of a foreign name it hasn't got count as a name
        (`names_spelt_by_sound`: 杜|瓦|尔)."""
        found = []
        for start, end in self.split(text):
            word = text[start:end]
            if not has_han(word):
                continue
            entries = self.lookup(word)
            if entries:
                found.append(WordInLine(start, end, entries[0].facts(scheme_id)))
        return names_spelt_by_sound(text, found)

    def word_at(self, text: str, index: int) -> tuple[int, int] | None:
        """(start, end) of the dictionary word the character at `index`
        belongs to - None for anything but a Chinese character."""
        if not (0 <= index < len(text)) or not is_han(text[index]):
            return None
        for start, end in self.split(text):
            if start <= index < end:
                return start, end
        return None

    def parts(self, word: str) -> list[str]:
        """The shorter dictionary words inside `word` (游戏 in 打游戏),
        longest first - each once, in order of where they start. Never a
        piece cut out of a name spelt by sound: 萨斯 ("SARS") isn't inside
        德克萨斯 ("Texas") - though 上海 is inside 上海话, and 北京 and 大学
        inside 北京大学 (`_spelt_by_sound`; polyglotic-hq 350)."""
        words = self._split_data()
        found: list[tuple[str, int]] = []
        for length in range(len(word) - 1, 1, -1):
            for start in range(len(word) - length + 1):
                part = word[start : start + length]
                if part in words and all(part != seen for seen, _ in found):
                    found.append((part, start))
        spelt = self._spelt_by_sound(word, 0)
        for part, start in found:
            spelt += self._spelt_by_sound(part, start)
        return [
            part
            for part, start in found
            if not any(_cuts(start, start + len(part), span) for span in spelt)
        ]

    def _spelt_by_sound(self, word: str, at: int) -> list[tuple[int, int]]:
        """Where `word` - found at `at` - has a name spelt by sound in it:
        each unit of a name (CC-CEDICT capitalises a unit's first syllable:
        "Dé kè sà sī", "Běi jīng Dà xué") made only of SOUND_CHARACTERS, as
        (start, end) from `at`. None if the entry a lookup shows first isn't
        a name."""
        entries = self.lookup(word)
        if not entries or not entries[0].is_name:
            return []
        syllables = entries[0].reading.split()
        if len(syllables) != len(word):
            return []
        starts = [n for n, s in enumerate(syllables) if s[:1].isupper()]
        units = zip(starts, [*starts[1:], len(word)], strict=True)
        return [
            (at + start, at + end)
            for start, end in units
            if end - start > 2 and all(c in SOUND_CHARACTERS for c in word[start:end])
        ]

    def named_by_sound(
        self, text: str, said: Iterable[tuple[int, int, str]]
    ) -> set[tuple[int, int]]:
        """The words of `text` its translation writes by their sound, as a
        name: of each (start, end, what the translation says for that word -
        its word link's words), those whose translation, capitalised, spells
        the word's own pinyin, tones and spaces aside (Wanli for 万里 of
        黄万里, Nai for 乃 of 张乃, Lifan for 立凡 of 张立凡). A word translated
        by its meaning isn't one (党, "Party"; 时代, "Era"; 空军, "Air
        Force"), nor one not capitalised (元, "yuan"). Polyglotic-hq 496:
        every word it found in 491's 282 live clauses was a name or a
        place."""
        found: set[tuple[int, int]] = set()
        for start, end, meant in said:
            word = text[start:end]
            if has_han(word) and self._spelt(word, meant):
                found.add((start, end))
        return found

    def _spelt(self, word: str, meant: str) -> bool:
        """Whether `meant` - a translation's words - holds, from a capitalised
        word on, `word`'s pinyin: one of each character's readings, run
        together without tones (Zhang Nai holds 乃's nai)."""
        tokens = re.findall(r"[A-Za-z]+", _unaccented(meant))
        if not tokens:
            return False
        sounds = {""}
        for char in word:
            each = self._sounds(char)
            sounds = {a + b for a in sounds for b in each}
            if not sounds or len(sounds) > SPELLINGS_MOST:
                sounds = set()
                break
        sounds |= self._sounds(word)  # the word's own readings, as a whole
        for first in range(len(tokens)):
            if not tokens[first][:1].isupper():
                continue
            joined = ""
            for token in tokens[first:]:
                joined += token.lower()
                if joined in sounds:
                    return True
                if len(joined) > 6 * len(word):
                    break
        return False

    def _sounds(self, form: str) -> set[str]:
        """Every reading the dictionary gives `form` (a character, or a word
        as a whole), run together without its tones (ü as u or v, as
        translations write it: Lü, Lu, Lv)."""
        found = self._form_sounds.get(form)
        if found is None:
            found = set()
            for record in self._file.records(form):
                syllables = record.reading.split()
                if len(syllables) != len(form):
                    continue
                bare = re.sub(r"[^a-z:]", "", record.reading.lower())
                found |= {bare.replace("u:", "u"), bare.replace("u:", "v")}
            found.discard("")
            if len(self._form_sounds) >= SOUNDS_KEPT:
                self._form_sounds.clear()
            self._form_sounds[form] = found
        return found

    def pinyin_of(self, text: str) -> str:
        """Best-guess pinyin for any Chinese text: each word's everyday
        reading - for a phrase the dictionary doesn't have as a whole."""
        out = []
        for start, end in self.split(text):
            part = text[start:end]
            if not has_han(part):
                continue
            entries = self.lookup(part)
            out.append(entries[0].reading if entries else "?" * len(part))
        return " ".join(out)

    def readings(self, text: str) -> list[Reading]:
        """Pinyin for a reading line over `text`, a syllable over each
        Chinese character (polyglotic-hq 364 and 369): each word of the word
        split read as its everyday entry reads it - so a character with
        several readings is read by the word it is in (银行 háng, 行动
        xíng; 长大 zhǎng, 很长 cháng) - a character alone by
        `LONE_READINGS` and `_alone`'s rules, and a word the dictionary
        lacks, or whose entry doesn't give each character a syllable,
        character by character. Citation tones, as a dictionary writes
        them: 一 and 不 keep their own (yī gè, bù shì). Nothing over what
        isn't a Chinese character, or one the dictionary hasn't got."""
        found: list[Reading] = []
        spans = self.split(text)
        for at, (start, end) in enumerate(spans):
            word = text[start:end]
            if not has_han(word):
                continue
            syllables = self._syllables(word)
            if syllables is None:
                syllables = [
                    (self._syllables(char) or [""])[0] if is_han(char) else ""
                    for char in word
                ]
            elif len(word) == 1:
                syllables = [_alone(text, spans, at, syllables[0])]
            last = max((n for n, s in enumerate(syllables) if s), default=-1)
            for n, syllable in enumerate(syllables):
                if syllable:
                    found.append(Reading(start + n, start + n + 1, syllable, n == last))
        return found

    def _syllables(self, word: str) -> list[str] | None:
        """`word`'s everyday reading, a syllable a character - None if
        the dictionary lacks it or its reading doesn't go character by
        character (a word with Latin letters or a middle dot in it). The
        first of its entries (`everyday_first`'s order: 结果 jié guǒ,
        "result", before jiē guǒ, "to bear fruit"), a name's or a "variant
        of" only where it has no other. Kept: a caption's words come again
        and again."""
        if word in self._read:
            return self._read[word]
        entries = [e for e in self.lookup(word) if len(e.reading.split()) == len(word)]
        syllables = None
        if entries:
            everyday = [e for e in entries if not (e.is_name or e.variant_only)]
            syllables = (everyday or entries)[0].reading.lower().split()
            if word in LONE_READINGS:
                syllables = [LONE_READINGS[word]]
            syllables = WORD_READINGS.get(word, syllables)
        if len(self._read) >= READINGS_KEPT:
            self._read.clear()
        self._read[word] = syllables
        return syllables

    def reverse_lookup(self, query: str, limit: int = 8) -> list[DictionaryEntry]:
        """Chinese words for an English word or phrase, from CC-CEDICT's
        meanings: a meaning that's exactly the phrase first ("game" - 游戏),
        then ones starting or ending with it, then containing it, then with
        all its words; everyday words before names; then the commonest
        (累 before 骀 for "tired"), favouring a word's main meaning over a
        side one; then the phrase as given before a stemmed form of it."""
        text = query.lower().replace("’", "'")
        text = re.sub(r"n't\b", " not", text)
        text = re.sub(
            r"'(re|m|s|ll|ve|d)\b", lambda m: _CONTRACTIONS.get(m.group(1), ""), text
        )
        words = re.findall(r"[a-z]+", text)
        content = [w for w in words if w not in _STOP] or words
        if not content:
            return []
        found: dict[str, DictionaryEntry] | None = None
        for word in content:
            entries = {
                r.entry_id: entry_from_record(r)
                for form in _stems(word)
                for r in self._file.records_by_meaning(form, REVERSE_CANDIDATES)
            }
            found = (
                entries
                if found is None
                else {k: e for k, e in found.items() if k in entries}
            )
        phrases = self._phrases(words, content)
        ranked = []
        for e in (found or {}).values():
            best = self._best_match(e, phrases, content)
            if best is not None:
                # How common, less a little for each meaning before the
                # match: 支持 (to support, its 2nd) still before 赡 (to
                # support, its 1st). The rank is the word's, so not an
                # obscure reading's - not 那 nuó's (archaic: beautiful).
                obscure = e.meanings[0].startswith(_OBSCURE) if e.meanings else False
                common = (
                    _commonness(None if obscure else e.frequency_rank) - 1.5 * best[2]
                )
                key = (best[0], e.is_name, -common, best[1], len(e.headword))
                ranked.append((key, e))
        ranked.sort(key=lambda r: r[0])
        return [e for _, e in ranked[:limit]]

    @staticmethod
    def _phrases(words: Sequence[str], content: Sequence[str]) -> dict[str, bool]:
        """The phrase, and without what it starts with before its first real
        word ("I don't know" -> "not know"), each also with its words
        stemmed: phrase -> whether it was stemmed."""
        first = words.index(content[0])
        phrases: dict[str, bool] = {}
        for start in (0, first):
            tail = words[start:]
            options = [_stems(w) if w in content else [w] for w in tail][:6]
            for variant in itertools.islice(itertools.product(*options), 64):
                phrase = _plain(" ".join(variant))
                stemmed = any(
                    form != word for form, word in zip(variant, tail, strict=False)
                )
                if phrase and (phrase not in phrases or not stemmed):
                    phrases[phrase] = stemmed
        return phrases

    @staticmethod
    def _best_match(
        entry: DictionaryEntry, phrases: dict[str, bool], content: Sequence[str]
    ) -> tuple[int, bool, int] | None:
        """(how well, stemmed, which meaning) of the best match, or None."""
        best: tuple[int, bool, int] | None = None
        # each sense on its own - a meaning is often several: "safe; secure"
        for position, meaning in enumerate(entry.meanings):
            for sense in meaning.split(";"):
                plain = _plain(sense)
                if not plain:
                    continue
                for phrase, stemmed in phrases.items():
                    if plain == phrase:
                        score = 0
                    elif plain.startswith(phrase + " ") or plain.endswith(" " + phrase):
                        score = 1
                    elif f" {phrase} " in f" {plain} ":
                        score = 2
                    elif all(
                        any(f" {form} " in f" {plain} " for form in _stems(w))
                        for w in content
                    ):
                        score = 3
                    else:
                        continue
                    key = (score, stemmed, position)
                    best = key if best is None or key < best else best
        return best
