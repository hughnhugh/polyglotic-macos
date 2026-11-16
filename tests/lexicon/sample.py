"""A fake `DictionaryFile` for testing Lexicon without a file on disk, and
the proof of concept's sample of real CC-CEDICT lines, assembled the way
the build assembles the real thing."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from tools.dictionaries import cedict
from tools.dictionaries.entry_ids import default_id

from polyglotic_desktop.core.lexicon import chinese
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.ports.dictionary import EntryRecord

CEDICT_SAMPLE = """\
# CC-CEDICT
電腦 电脑 [dian4 nao3] /computer/CL:臺|台[tai2]/
電 电 [dian4] /electric; electricity; electrical/
腦 脑 [nao3] /brain; mind; head/
畫蛇添足 画蛇添足 [hua4 she2 tian1 zu2] /lit. draw legs on a snake (idiom); fig. to ruin the effect by adding sth superfluous/
畫 画 [hua4] /to draw; to paint/picture; painting/
蛇 蛇 [she2] /snake; serpent/
添 添 [tian1] /to add; to increase; to replenish/
足 足 [ju4] /excessive/
足 足 [zu2] /foot; to be sufficient; ample/
足球 足球 [zu2 qiu2] /soccer ball; football/
滿足 满足 [man3 zu2] /to satisfy; to meet (the needs of)/
研究 研究 [yan2 jiu1] /research; study/
研究生 研究生 [yan2 jiu1 sheng1] /graduate student/
生命 生命 [sheng1 ming4] /life (as the characteristic of living beings)/
起源 起源 [qi3 yuan2] /origin/
這個 这个 [zhe4 ge5] /this; this one/
個人 个人 [ge4 ren2] /individual; personal/
這 这 [zhe4] /this; these/
個 个 [ge4] /individual; this; that; size/
人 人 [ren2] /person; people/
打遊戲 打游戏 [da3 you2 xi4] /to play a game/
遊戲 游戏 [you2 xi4] /game/
還 还 [huan2] /to pay back; to return/
還 还 [hai2] /still; still in progress; yet/
還款 还款 [huan2 kuan3] /repayment/
還錢 还钱 [huan2 qian2] /to pay back money/
瞭 了 [liao3] /variant of 了[liao3]/
了 了 [le5] /(completed action marker)/
女 女 [nu:3] /female; woman/
北京 北京 [Bei3 jing1] /Beijing/
"""


class FakeDictionaryFile:
    """Everything a dictionary file holds, in memory."""

    def __init__(
        self,
        records: Sequence[EntryRecord],
        forms: Mapping[str, Sequence[str]],
        meaning_words: Mapping[str, Iterable[str]] | None = None,
        lemmas: Mapping[str, str] | None = None,
        merged: Mapping[str, str] | None = None,
        form_readings: Mapping[str, str] | None = None,
    ) -> None:
        self.by_id = {r.entry_id: r for r in records}
        self.forms = {form: list(ids) for form, ids in forms.items()}
        self.meaning_words = {w: list(ids) for w, ids in (meaning_words or {}).items()}
        self.lemmas = dict(lemmas or {})
        self.merged = dict(merged or {})
        self.form_readings = dict(form_readings or {})

    def headwords(self) -> Iterable[str]:
        return list(self.forms)

    def frequency_ranks(self) -> Mapping[str, int]:
        ranks: dict[str, int] = {}
        for form, ids in self.forms.items():
            ranked = [r for i in ids if (r := self.by_id[i].frequency_rank) is not None]
            if ranked:
                ranks[form] = min(ranked)
        return ranks

    def records(self, word: str) -> Sequence[EntryRecord]:
        return [self.by_id[i] for i in self.forms.get(word, ())]

    def records_by_meaning(
        self, english_word: str, limit: int
    ) -> Sequence[EntryRecord]:
        found = [self.by_id[i] for i in self.meaning_words.get(english_word, ())]
        found.sort(key=lambda r: (r.frequency_rank is None, r.frequency_rank or 0))
        return found[:limit]

    def lemma(self, word: str) -> str | None:
        return self.lemmas.get(word)

    def form_reading(self, word: str) -> str:
        return self.form_readings.get(word, "")

    def record(self, entry_id: str) -> EntryRecord | None:
        return self.by_id.get(self.merged.get(entry_id, entry_id))

    def merged_ids(self) -> Sequence[str]:
        return list(self.merged)

    def words_ranked(self, last: int) -> Sequence[int]:
        ranks = {r.frequency_rank for r in self.by_id.values()}
        return sorted(r for r in ranks if r is not None and r <= last)

    def headwords_ranked(self, after: int, limit: int) -> Sequence[tuple[str, int]]:
        found = [
            (first.headword, first.frequency_rank)
            for first in self._own_first()
            if first.frequency_rank is not None and first.frequency_rank > after
        ]
        return sorted(found, key=lambda pair: pair[1])[:limit]

    def headwords_at_levels(self, scheme: str) -> Sequence[tuple[str, int, int | None]]:
        return [
            (first.headword, level, first.frequency_rank)
            for first in self._own_first()
            if (level := dict(first.levels).get(scheme)) is not None
        ]

    def _own_first(self) -> list[EntryRecord]:
        """The entries that are the first for their own headword."""
        firsts = (self.by_id[ids[0]] for form, ids in self.forms.items() if ids)
        return [r for r in firsts if self.forms[r.headword][0] == r.entry_id]

    def words_at_levels(self, scheme: str) -> Mapping[int, int]:
        headwords: dict[int, set[str]] = {}
        for record in self.by_id.values():
            level = dict(record.levels).get(scheme)
            if level is not None:
                headwords.setdefault(level, set()).add(record.headword)
        return {level: len(found) for level, found in sorted(headwords.items())}


def chinese_sample(
    text: str = CEDICT_SAMPLE, frequency_ranks: Mapping[str, int] | None = None
) -> FakeDictionaryFile:
    """CC-CEDICT lines as a dictionary file: entry IDs, everyday readings
    first, the reverse lookup's index."""
    ranks = frequency_ranks or {}
    records = [
        EntryRecord(
            entry_id=default_id("cedict", line.key),
            headword=line.simplified,
            traditional=line.traditional,
            reading=line.pinyin,
            meanings=line.meanings,
            frequency_rank=ranks.get(line.simplified),
        )
        for line in cedict.parse(text.splitlines())
    ]
    entries = [chinese.entry_from_record(r) for r in records]
    uses = chinese.count_reading_uses(entries)
    by_form: dict[str, list[DictionaryEntry]] = {}
    for e in entries:
        for form in dict.fromkeys((e.headword, e.traditional)):
            by_form.setdefault(form, []).append(e)
    forms = {
        form: [e.entry_id for e in chinese.everyday_first(form, found, uses)]
        for form, found in by_form.items()
    }
    meaning_words: dict[str, list[str]] = {}
    for e in entries:
        for word in chinese.index_words(e):
            meaning_words.setdefault(word, []).append(e.entry_id)
    return FakeDictionaryFile(records, forms, meaning_words)


PHRASES_SAMPLE = """\
中 中 [zhong1] /within; among; in/
的 的 [de5] /of; ~'s (possessive particle)/
中的 中的 [zhong4 di4] /to hit the target; (fig.) to hit the nail on the head/
生活 生活 [sheng1 huo2] /life; to live/
有 有 [you3] /to have; there is/
了 了 [le5] /(completed action marker)/
有了 有了 [you3 le5] /I've got a solution!; to have a bun in the oven (i.e. to be pregnant)/
有的 有的 [you3 de5] /(there are) some (who are...); some (exist)/
人 人 [ren2] /person; people/
馬 马 [ma3] /horse/
裡 里 [li3] /inside/
馬里 马里 [Ma3 li3] /Mali/
自由 自由 [zi4 you2] /freedom; free/
自在 自在 [zi4 zai4] /free; unrestrained/
自由自在 自由自在 [zi4 you2 zi4 zai4] /free and unrestrained (idiom)/
滄 沧 [cang1] /blue-green or azure (of water)/
龍 龙 [long2] /dragon/
滄龍 沧龙 [cang1 long2] /(zoology) mosasaur/
"""
"""Real CC-CEDICT lines (polyglotic-hq 359): unranked phrases of two common
words (中的, 有了) beside unranked words kept whole - a name (马里), an
idiom (自由自在), an HSK word (有的) and one with a rare part (沧龙)."""
PHRASE_RANKS = {
    "的": 1, "有": 5, "了": 6, "中": 17, "人": 20, "里": 50, "生活": 200,
    "马": 600, "自由": 800, "龙": 1500, "自在": 2900, "沧": 21810,
}  # fmt: skip
"""Ranks like jieba's (沧 past the 3,000 commonest)."""


def phrases_sample(ranked: bool = True) -> FakeDictionaryFile:
    """`PHRASES_SAMPLE` as a file, with 有的's HSK level as the build
    attaches it; `ranked`: with `PHRASE_RANKS`."""
    file = chinese_sample(PHRASES_SAMPLE, PHRASE_RANKS if ranked else None)
    for entry_id in file.forms["有的"]:
        record = file.by_id[entry_id]
        file.by_id[entry_id] = replace(record, levels=(("hsk-2025", 1),))
    return file


def english_sample() -> FakeDictionaryFile:
    """A few ECDICT-style entries with frequency ranks and inflections."""
    words = {
        "I": ("pron. 我", 11),
        "she": ("pron. 她", 40),
        "he": ("pron. 他", 30),
        "they": ("pron. 他们", 35),
        "to": ("prep. 到", 5),
        "keep": ("v. 保持", 250),
        "run": ("v. 跑", 202),
        "running": ("n. 赛跑", 3252),
        "brunch": ("n. 早午餐", 15000),
        "leave": ("v. 离开", 300),
        "left": ("a. 左边的", 771),
        "English": ("n. 英语", 900),
        "awkward": ("a. 尴尬的", 2500),
        "ubiquitous": ("a. 无处不在的", 9000),
    }
    records = [
        EntryRecord(f"ecdict:{word}", word, "", "", (meaning,), rank)
        for word, (meaning, rank) in words.items()
    ]
    return FakeDictionaryFile(
        records,
        forms={r.headword: [r.entry_id] for r in records},
        lemmas={"running": "run", "ran": "run", "runs": "run", "left": "leave"},
    )
