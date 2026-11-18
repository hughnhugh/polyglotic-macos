"""Saved sentences searched at 5,000 and 50,000 (polyglotic-hq 459; the
user, 2026-11-14: "probably <100ms search in a very large bank ... Maybe
just target 5000").

Made-up sentences, never a learner's: Mandarin of 6 to 40 characters drawn
on a Zipf curve over 3,500 common characters, each with an English
translation of 4 to 25 words drawn on a Zipf curve over 5,000 made-up
words; a word filter of a saved word now and then. The queries are like a
learner's: 1 to 6 characters of Mandarin, 1 to 4 English words, or both.

It measures, at each size:
- **a search** (`Vocabulary.find_sentences`): the median, 95th percentile
  and slowest of `--queries` queries, and the empty query (every
  sentence, newest first: what the section shows first);
- **the start:** the learning file's `load`, which leaves saved sentences
  out (`start_load_ms`, with every sentence in the file); **the first
  look:** reading them (`SqliteLearningStore.saved_sentences`) and the
  first search preparing their text (`SentenceSearch`) - once a run,
  when Words' Sentences are first opened or a sentence first saved;
- **memory:** what the prepared sentences hold (`tracemalloc`), and the
  file's size.

    uv run python -m tools.bench_sentences --sizes 5000 50000 --queries 300

Single-threaded; it runs a few seconds at 50,000 (most of it making the
file).
"""

import argparse
import random
import statistics
import tempfile
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.core.learning.sentences import (
    SavedSentence,
    SentenceLink,
    SentencePart,
    SentenceSearch,
)
from polyglotic_desktop.core.learning.vocabulary import Vocabulary, _stored_sentence

COMMON = 3500
WORDS = 5000


def _zipf(rng: random.Random, n: int) -> int:
    """An index in [0, n) on a Zipf curve (s = 1): the commonest most."""
    return min(int(n ** rng.random()) - 1, n - 1)


def _chars(rng: random.Random, count: int) -> str:
    return "".join(chr(0x4E00 + _zipf(rng, COMMON) * 5) for _ in range(count))


def _words(rng: random.Random, count: int) -> str:
    return " ".join(f"w{_zipf(rng, WORDS)}x" for _ in range(count))


def _sentence(rng: random.Random, n: int, at: datetime) -> SavedSentence:
    parts = []
    for _ in range(rng.choice((1, 1, 1, 2, 3))):
        original = _chars(rng, rng.randint(6, 25))
        translation = _words(rng, rng.randint(4, 15))
        links = tuple(
            SentenceLink((k, k + 2), (k * 3, k * 3 + 4)) for k in range(0, 6, 2)
        )
        parts.append(SentencePart(original, translation, links, "Discord"))
    return SavedSentence(
        f"{n:08x}",
        "".join(p.original for p in parts),
        " ".join(p.translation for p in parts),
        tuple(parts),
        rng.choice(("saved", "tricky")),
        at + timedelta(seconds=n),
        "en",
    )


def _query(rng: random.Random) -> str:
    kind = rng.random()
    if kind < 0.4:
        return _chars(rng, rng.randint(1, 6))
    if kind < 0.8:
        return _words(rng, rng.randint(1, 4))
    return _chars(rng, rng.randint(1, 3)) + " " + _words(rng, rng.randint(1, 2))


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


def measure(size: int, queries: int, folder: Path) -> dict[str, object]:
    rng = random.Random(459 + size)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    sentences = [_sentence(rng, n, at) for n in range(size)]
    path = folder / f"learning-{size}.sqlite"
    store = SqliteLearningStore(path)
    for name in ("saved", "tricky"):
        store._db.execute(
            "INSERT OR IGNORE INTO categories VALUES (?, ?, '#ffffff', 0)",
            (name, name),
        )
    store._db.execute("BEGIN")  # one transaction: only making the file
    for sentence in sentences:
        store._db.execute(
            "INSERT INTO saved_sentences VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sentence.id,
                sentence.original,
                sentence.translation,
                sqlite_parts(sentence),
                "en",
                sentence.category_id,
                sentence.saved_at.isoformat(),
            ),
        )
    store._db.execute("COMMIT")
    store.close()

    store = SqliteLearningStore(path)
    started = time.perf_counter()
    store.load()
    start_load = time.perf_counter() - started
    vocabulary = Vocabulary(store, lambda entry_id, scheme: None, "hsk-2025")
    started = time.perf_counter()
    read = store.saved_sentences()
    first_read = time.perf_counter() - started
    sentences = vocabulary.sentences  # read: what a first look reads
    started = time.perf_counter()
    vocabulary.find_sentences("x")  # the first search prepares their text
    prepared = time.perf_counter() - started
    tracemalloc.start()
    search = SentenceSearch(sentences)
    before, _ = tracemalloc.get_traced_memory()
    search.search("x")
    held = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()

    times = []
    found = []
    for _ in range(queries):
        query = _query(rng)
        category: str | None = rng.choice((None, None, "saved"))
        started = time.perf_counter()
        hits = vocabulary.find_sentences(query, category)
        times.append(time.perf_counter() - started)
        found.append(len(hits))
    started = time.perf_counter()
    vocabulary.find_sentences()
    every = time.perf_counter() - started
    store.close()
    times.sort()
    return {
        "sentences": size,
        "search_ms_median": _ms(statistics.median(times)),
        "search_ms_p95": _ms(times[int(len(times) * 0.95) - 1]),
        "search_ms_slowest": _ms(times[-1]),
        "every_sentence_ms": _ms(every),
        "found_median": statistics.median(found),
        "start_load_ms": _ms(start_load),
        "first_read_ms": _ms(first_read),
        "first_search_prepares_ms": _ms(prepared),
        "prepared_mb": round(held / 1e6, 2),
        "search_len": len(search),
        "file_mb": round(path.stat().st_size / 1e6, 2),
        "read": len(read),
    }


def sqlite_parts(sentence: SavedSentence) -> str:
    from polyglotic_desktop.adapters.sqlite_learning import _parts_json

    return _parts_json(_stored_sentence(sentence).parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[5000, 50000])
    parser.add_argument("--queries", type=int, default=300)
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix="459-sentences-"))
    for size in args.sizes:
        print(measure(size, args.queries, folder))
        (folder / f"learning-{size}.sqlite").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
