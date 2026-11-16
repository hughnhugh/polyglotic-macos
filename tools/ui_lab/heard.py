"""Words' "What you've heard" with real-looking numbers (polyglotic-hq
project 163): three made-up learners on a made-up dictionary as big as the
bands - a new learner, a month in, a heavy learner.

The dictionary: 12,000 three-character words of 24 common characters, each
with a frequency rank (1 to 12,000, in order) and an HSK 2025 level by
rank (the syllabus's cumulative sizes: 300, 500, 1,000, 2,000, 3,600,
5,400, 11,000). What the learner heard is drawn from a Zipf curve over the
ranks (exponent `ZIPF`), `TOKENS_PER_MIN` dictionary words a minute of
listening, a finished caption every `CAPTION_EVERY_SEC` - a model, not a
measurement: no real counts exist yet (155, 3.3: our own opt-in counts can
give the Mandarin curve later). The weeks before are written to the store
as the counts they'd have left; the last 7 days are counted as captions
finish, through `Vocabulary`, so coverage and listening come from the real
counting. Seeded: the same numbers every run.
"""

import itertools
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.learning.vocabulary import FactsLookup, Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    Level,
    WordInLine,
    WordStatus,
)
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.learning import (
    StoredCoverage,
    StoredExposures,
    StoredListening,
    StoredSavedWord,
)
from polyglotic_desktop.ui.learning import LearningTools

CHARACTERS = {
    "天": ("tian1", "sky"), "山": ("shan1", "mountain"), "水": ("shui3", "water"),
    "火": ("huo3", "fire"), "木": ("mu4", "wood"), "花": ("hua1", "flower"),
    "草": ("cao3", "grass"), "风": ("feng1", "wind"), "雨": ("yu3", "rain"),
    "云": ("yun2", "cloud"), "月": ("yue4", "moon"), "日": ("ri4", "sun"),
    "星": ("xing1", "star"), "石": ("shi2", "stone"), "田": ("tian2", "field"),
    "河": ("he2", "river"), "海": ("hai3", "sea"), "林": ("lin2", "forest"),
    "鸟": ("niao3", "bird"), "鱼": ("yu2", "fish"), "马": ("ma3", "horse"),
    "牛": ("niu2", "ox"), "羊": ("yang2", "sheep"), "虫": ("chong2", "insect"),
}  # fmt: skip
WORDS = 12_000
HSK_SIZES = (300, 500, 1000, 2000, 3600, 5400, 11000)
"""HSK 2025's cumulative word counts by level (`core.lexicon.entries`)."""
ZIPF = 1.15
TOKENS_PER_MIN = 100
"""Dictionary words a minute of listening (speech about 60 % of the time,
about 3 words a second of it) - a guess."""
CAPTION_EVERY_SEC = 5
TODAY = datetime(2026, 11, 7, 21, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Learner:
    """A made-up learner: the HSK level picked, listening before the last
    7 days (hours, over `weeks`) and in them, words put in the deck and
    marked known by hand."""

    level: int
    hours_before: float
    weeks: int
    hours_this_week: float
    deck: int
    known_by_hand: int


NEW_LEARNER = Learner(1, 1.0, 1, 2.2, 6, 4)
MONTH_IN = Learner(3, 18.0, 3, 6.5, 60, 40)
HEAVY = Learner(5, 290.0, 40, 21.0, 300, 400)


def dictionary(size: int = WORDS) -> ChineseDictionary:
    """The made-up dictionary: `size` words - three characters long, then
    (past 12,144) four - the first `WORDS` the same whatever the size."""
    records, forms = [], {}
    words = (
        "".join(w)
        for w in itertools.chain(
            itertools.permutations(CHARACTERS, 3), itertools.permutations(CHARACTERS, 4)
        )
    )
    for rank, word in enumerate(itertools.islice(words, size), 1):
        parts = [CHARACTERS[c] for c in word]
        level = next((n for n, size in enumerate(HSK_SIZES, 1) if rank <= size), None)
        entry_id = f"lab:{rank}"
        records.append(
            EntryRecord(
                entry_id=entry_id,
                headword=word,
                traditional=word,
                reading=" ".join(p for p, _ in parts),
                meanings=(" ".join(m for _, m in parts),),
                frequency_rank=rank,
                levels=(("hsk-2025", level),) if level else (),
            )
        )
        forms[word] = [entry_id]
    found = ChineseDictionary(FakeDictionaryFile(records, forms))
    found.prepare()
    return found


def _draw(rng: random.Random, count: int) -> list[int]:
    weights = [1 / rank**ZIPF for rank in range(1, WORDS + 1)]
    return rng.choices(range(1, WORDS + 1), cum_weights=_cumulative(weights), k=count)


def _cumulative(weights: list[float]) -> list[float]:
    return list(itertools.accumulate(weights))


def learner_tools(
    learner: Learner, zh: ChineseDictionary | None = None
) -> LearningTools:
    """The learning tools of `learner` as of `TODAY`."""
    rng = random.Random(163)
    zh = zh or dictionary()

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return zh.facts(entry_id, scheme)

    store = MemoryLearningStore()
    week_start = TODAY - timedelta(days=6, hours=TODAY.hour)
    tokens = _draw(rng, int(learner.hours_before * 60 * TOKENS_PER_MIN))
    for rank, heard in Counter(tokens).items():
        entry_id = f"lab:{rank}"
        store.exposures[entry_id] = StoredExposures(entry_id, heard, 0, 0)
    days = learner.weeks * 7
    for n in range(days):  # the hours before, a day at a time, every other day
        if n % 2:
            continue
        day = (week_start - timedelta(days=days - n)).date()
        seconds = learner.hours_before * 3600 / max(1, (days + 1) // 2)
        store.add_listening([StoredListening(day, "video", seconds)])
    clock = Clock(week_start)
    vocabulary = Vocabulary(store, facts, "hsk-2025", clock)
    vocabulary.set_level(Level("hsk-2025", learner.level))
    heard_new = [
        EntryId(f"lab:{rank}")
        for rank, _ in Counter(tokens).most_common()
        if vocabulary.status_of_entry(EntryId(f"lab:{rank}")).status is WordStatus.NEW
    ]
    for entry_id in heard_new[: learner.deck]:
        vocabulary.set_status(entry_id, WordStatus.LEARNING)
    for entry_id in heard_new[learner.deck : learner.deck + learner.known_by_hand]:
        vocabulary.set_status(entry_id, WordStatus.KNOWN)
    _this_week(vocabulary, clock, learner.hours_this_week, rng, facts)
    return LearningTools(vocabulary, zh)


def _this_week(
    vocabulary: Vocabulary,
    clock: Clock,
    hours: float,
    rng: random.Random,
    facts: FactsLookup,
) -> None:
    """The last 7 days' listening, counted as captions finish: on 5 of the 7
    days, in evening sessions, a game and videos."""
    per_caption = TOKENS_PER_MIN * CAPTION_EVERY_SEC // 60
    captions = int(hours * 3600 / CAPTION_EVERY_SEC)
    days = [0, 1, 3, 4, 6]
    ranks = _draw(rng, captions * per_caption)
    for index in range(captions):
        day = days[index * len(days) // captions]
        start = TODAY - timedelta(days=6 - day, hours=TODAY.hour - 19)
        clock.now = max(clock.now, start)
        line = ranks[index * per_caption : (index + 1) * per_caption]
        words = []
        for rank in line:
            found = facts(EntryId(f"lab:{rank}"), "hsk-2025")
            if found is not None:
                words.append(WordInLine(0, 3, found))
        vocabulary.caption_finished(f"week.{index}", words, False)
        vocabulary.listened("game" if day in (1, 4) else "video")
        clock.advance(seconds=CAPTION_EVERY_SEC)
    clock.now = TODAY


def met_dictionary(met: int) -> ChineseDictionary:
    """A made-up dictionary big enough for a learner who met `met` words."""
    return dictionary(max(WORDS, met + met // 4))


def met_learner_tools(met: int, zh: ChineseDictionary | None = None) -> LearningTools:
    """A learner who has met exactly `met` words (polyglotic-hq project 212):
    the commonest 80 % by rank, the rest rarer words, each heard on a Zipf
    curve; HSK 5 picked; a deck, words known by hand and saved words in
    proportion; a week of coverage and listening - written to the store,
    then read by a new `Vocabulary` as at the app's start, nothing about
    the words read from the dictionary yet. Seeded: the same every run."""
    zh = zh or met_dictionary(met)
    rng = random.Random(212)
    size = max(WORDS, met + met // 4)
    common = int(met * 0.8)
    ranks = [
        *range(1, common + 1),
        *rng.sample(range(common + 1, size + 1), met - common),
    ]
    store = MemoryLearningStore()
    today = TODAY.date()
    for rank in ranks:
        entry_id = f"lab:{rank}"
        heard = max(1, round(20 * met / rank**ZIPF))
        first = today - timedelta(days=rng.randrange(26 * 7))  # met evenly
        store.exposures[entry_id] = StoredExposures(entry_id, heard, 0, 0, first)
    for n in range(7):  # 5 of the last 7 days: about 2 hours each
        if n in (2, 5):
            continue
        day = today - timedelta(days=n)
        store.add_coverage([StoredCoverage(day, 10_400, 300, 1_300)])
        store.add_listening([StoredListening(day, "video", 7_200.0)])

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        return zh.facts(entry_id, scheme)

    clock = Clock(TODAY)
    setting_up = Vocabulary(store, facts, "hsk-2025", clock)
    setting_up.set_level(Level("hsk-2025", 5))
    new = [
        EntryId(f"lab:{rank}")
        for rank in ranks
        if setting_up.status_of_entry(EntryId(f"lab:{rank}")).status is WordStatus.NEW
    ]
    deck, by_hand, saved = met // 40, met // 25, met // 50
    for entry_id in new[:deck]:
        setting_up.set_status(entry_id, WordStatus.LEARNING)
    for entry_id in new[deck : deck + by_hand]:
        setting_up.set_status(entry_id, WordStatus.KNOWN)
    category = setting_up.categories[0].id
    for entry_id in new[deck + by_hand : deck + by_hand + saved]:
        entry = zh.entry(entry_id)
        assert entry is not None
        store.save_word(
            StoredSavedWord(
                entry_id, entry.headword, entry.traditional, entry.reading,
                entry.meanings[0], category, entry.headword, "", TODAY,
            )
        )  # fmt: skip
    return LearningTools(Vocabulary(store, facts, "hsk-2025", clock), zh)


def numbers(learner: Learner) -> dict[str, object]:
    """What Words shows for `learner` - for the report."""
    tools = learner_tools(learner)
    vocabulary = tools.vocabulary
    met = vocabulary.met_words()
    coverage = vocabulary.coverage()
    return {
        "met": len(met),
        "coverage": round(coverage.share or 0, 3),
        "tokens_7_days": coverage.tokens,
        "one_new_in": coverage.one_new_in,
        "listening_h": round(vocabulary.listening() / 3600, 1),
        "listening_7_days_h": round(vocabulary.listening(7) / 3600, 1),
        "day": date(2026, 11, 7).isoformat(),
    }
