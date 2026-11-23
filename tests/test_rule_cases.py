"""The desktop's rules against the shared test cases (docs/rule-cases/).

polyglotic-hq project 051 (from project 050: mobile kept open): the
timing rules, the level curve, highlights, the Chinese word split and the
caption display rules, written as JSON cases a later port must pass.
These tests read only the JSON - as a port would - and run this app's
rules on it, so the files and the rules can't drift apart: a rule changed
on purpose means `uv run python -m tools.rule_cases write`, and the diff
shows every answer that changed. `tools/rule_cases.py` says where each
input comes from; docs/rule-cases/README.md how to read the files.
"""

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

from polyglotic_desktop.core.learning.highlights import caption_cap, unfamiliar_words
from polyglotic_desktop.core.learning.levels import (
    DEFAULT_WINDOW,
    UNLIMITED,
    WORDS,
    KnownLine,
    place,
)
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import Language, WordLink
from polyglotic_desktop.core.listening.display import (
    LinkDetail,
    Placed,
    caption_rows,
    first_rewritten,
    following_top,
    numbered_links,
)
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SEC,
    BreathCut,
    CaptionId,
    CaptionTiming,
    LiveSchedule,
    TimingRules,
    TranscriptionRequest,
    WithdrawCaption,
)
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    WordInLine,
    WordStatus,
)
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ports.dictionary import EntryRecord
from tools import rule_cases

FOLDER = Path(__file__).resolve().parents[1] / "docs" / "rule-cases"
CLOSE = 1e-6


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FOLDER / name).read_text(encoding="utf-8"))
    return data


TIMING = load("timing.json")
LEVELS = load("levels.json")
HIGHLIGHTS = load("highlights.json")
SPLIT = load("word-split.json")
DISPLAY = load("display.json")
PLAYOUT = load("playout.json")


def test_the_files_are_what_the_rules_give_now() -> None:
    """Regenerated after every deliberate change (`tools.rule_cases write`)."""
    assert rule_cases.main(["check"]) == 0


def test_every_file_is_described() -> None:
    readme = (FOLDER / "README.md").read_text(encoding="utf-8")
    for name in rule_cases.BUILDERS:
        assert f"`{name}`" in readme, name


# -- timing ----------------------------------------------------------------------------


def frames(pattern: list[list[Any]], t0: float) -> list[tuple[float, bool]]:
    """The README's frame rule: frame i ends at t0 + (i + 1) x frame_seconds
    and is speech if its middle falls in a speaking stretch."""
    spans, t = [], t0
    for seconds, speaking in pattern:
        spans.append((t, t + seconds, speaking))
        t += seconds
    out = []
    for i in range(int((t - t0) / FRAME_SEC)):
        end = t0 + (i + 1) * FRAME_SEC
        middle = end - FRAME_SEC / 2
        out.append((end, any(a <= middle < b and s for a, b, s in spans)))
    return out


def timing_rules(data: dict[str, Any]) -> TimingRules:
    cut = data["breath_cut"]
    return TimingRules(
        schedule=LiveSchedule(data["schedule"]),
        silence_hangover=data["silence_hangover"],
        breath_cut=BreathCut(**cut) if cut else None,
        turn_cut=data["turn_cut"],
        join_gap=data["join_gap"],
        join_only_under=data["join_only_under"],
        lead_in=data["lead_in"],
    )


@pytest.mark.parametrize("case", TIMING["cases"], ids=lambda c: c["name"])
def test_timing(case: dict[str, Any]) -> None:
    t0 = TIMING["t0"]
    assert TIMING["frame_seconds"] == FRAME_SEC
    numbers = iter(range(1, 1000))
    timing = CaptionTiming(
        case["live_update_interval"],
        lambda: CaptionId(f"c{next(numbers)}"),
        timing_rules(case["rules"]),
    )
    timing.pace_hint = case["pace_hint"]
    for source in case["sources"]:
        timing.add_source(
            Source(SourceId(source["id"]), SourceCategory(source["category"]))
        )
    merged = sorted(
        (end, source["id"], speech)
        for source in case["sources"]
        for end, speech in frames(source["pattern"], t0)
    )
    got: list[dict[str, Any]] = []
    for end, source_id, speech in merged:
        for decision in timing.frame(SourceId(source_id), end, speech):
            if isinstance(decision, WithdrawCaption):
                got.append(
                    {
                        "withdraw": decision.caption_id,
                        "source": decision.source.id,
                        "reason": decision.reason.value,
                    }
                )
                continue
            assert isinstance(decision, TranscriptionRequest)
            got.append(
                {
                    "caption": decision.caption_id,
                    "kind": decision.kind.value,
                    "source": decision.source.id,
                    "start": decision.speech_start - t0,
                    "end": decision.speech_end - t0,
                    "section": decision.section,
                    "replaces": list(decision.replaces),
                    "at": end - t0,
                }
            )
    expected = case["decisions"]
    assert len(got) == len(expected)
    for mine, theirs in zip(got, expected, strict=True):
        assert mine.keys() == theirs.keys()
        for key, value in theirs.items():
            if isinstance(value, float):
                assert abs(mine[key] - value) < CLOSE, (key, mine, theirs)
            else:
                assert mine[key] == value, (key, mine, theirs)


# -- the known line and the learning window ------------------------------------------------


@pytest.mark.parametrize(
    "case",
    LEVELS["cases"],
    ids=lambda c: f"{c['scale']}-{c['known']}-{c['window_size']}",
)
def test_known_line(case: dict[str, Any]) -> None:
    assert LEVELS["constants"] == {"words": WORDS, "default_window": DEFAULT_WINDOW}
    line = KnownLine(case["scale"], case["known"])
    stored = case["stored"]
    assert KnownLine.stored(stored["scheme"], stored["midpoint"]) == line
    assert line.midpoint == stored["midpoint"]
    size = case["window_size"]
    window = line.window(UNLIMITED if size == UNLIMITED.value else size)
    assert window.last == case["window_last"]
    for row in case["words"]:
        facts = EntryFacts(
            EntryId("case:word"), row["level"], row["rank"], False, row["level_words"]
        )
        assert place(facts) == row["place"]
        assert line.knows(facts) is row["known"]
        assert window.reaches(facts) is row["reached"]
        assert window.holds(facts) is row["in_window"]


# -- highlights ------------------------------------------------------------------------


def test_caption_cap() -> None:
    for row in HIGHLIGHTS["caption_cap"]:
        assert caption_cap(row["words"]) == row["cap"]


@pytest.mark.parametrize("case", HIGHLIGHTS["cases"], ids=lambda c: c["name"])
def test_highlights(case: dict[str, Any]) -> None:
    statuses: dict[EntryId, WordStatus] = {}
    lines = []
    for line in case["lines"]:
        words = []
        for w in line:
            entry_id = EntryId(f"case:{w['word']}")
            statuses[entry_id] = WordStatus(w["status"])
            facts = EntryFacts(entry_id, w["level"], w["rank"], w["name"])
            words.append(WordInLine(w["start"], w["end"], facts))
        lines.append(words)
    heard: Mapping[str, int] = case["heard"]
    shown = unfamiliar_words(
        lines,
        lambda facts: statuses[facts.entry_id],
        KnownLine(case["scale"], case["known"]).window(),
        lambda entry_id: heard.get(entry_id.removeprefix("case:"), 0),
        case["common_only"],
    )
    assert [
        [w.entry.entry_id.removeprefix("case:") for w in line] for line in shown
    ] == case["shown"]


# -- the Chinese word split ------------------------------------------------------------


class Headwords:
    """All the word split reads from a dictionary file: its headwords
    (both scripts), their frequency ranks, and which are kept whole - a
    name, an idiom or a syllabus's word (decision 0151), here as a name."""

    def __init__(
        self,
        headwords: Iterable[str],
        ranks: Mapping[str, int],
        kept_whole: Iterable[str] = (),
    ) -> None:
        self._headwords = list(headwords)
        self._ranks = dict(ranks)
        self._kept = set(kept_whole)

    def headwords(self) -> Iterable[str]:
        return self._headwords

    def frequency_ranks(self) -> Mapping[str, int]:
        return self._ranks

    def records(self, word: str) -> list[EntryRecord]:
        reading = "Kept" if word in self._kept else "kept"
        return [EntryRecord(word, word, word, reading, ())]


@pytest.mark.parametrize("case", SPLIT["cases"], ids=lambda c: c["splits"][0]["text"])
def test_word_split(case: dict[str, Any]) -> None:
    file = Headwords(case["headwords"], case["frequency_ranks"], case["kept_whole"])
    dictionary = ChineseDictionary(file)  # type: ignore[arg-type]
    for split in case["splits"]:
        text = split["text"]
        assert [text[a:b] for a, b in dictionary.split(text)] == split["words"]


# -- caption display -------------------------------------------------------------------


def word_links(found: list[dict[str, Any]]) -> list[WordLink]:
    return [
        WordLink(
            (link["original"][0], link["original"][1]),
            (link["translation"][0], link["translation"][1]),
            link["key"],
            link["confidence"],
        )
        for link in found
    ]


@pytest.mark.parametrize("case", DISPLAY["caption_rows"], ids=lambda c: c["name"])
def test_caption_rows(case: dict[str, Any]) -> None:
    rows = caption_rows(
        rule_cases.caption_from(case["caption"]),
        Language(case["target"]),
        Language(case["second"]) if case["second"] else None,
        rule_cases.options_from(case["options"]),
    )
    assert [
        {
            "text": r.text,
            "kind": r.kind.value,
            "language": r.language,
            "clause": r.clause,
            "starts_clause": r.starts_clause,
            "links": [[w.start, w.end, w.link] for w in r.links],
        }
        for r in rows
    ] == case["rows"]


@pytest.mark.parametrize("case", DISPLAY["numbered_links"], ids=lambda c: c["name"])
def test_numbered_links(case: dict[str, Any]) -> None:
    original, translation = numbered_links(
        word_links(case["links"]),
        LinkDetail(case["detail"]),
        case["cap"],
        case["original_length"],
        case["translation_length"],
    )
    assert [[w.start, w.end, w.link] for w in original] == case["original"]
    assert [[w.start, w.end, w.link] for w in translation] == case["translation"]


def test_first_rewritten() -> None:
    for case in DISPLAY["first_rewritten"]:
        assert first_rewritten(case["old"], case["new"]) == case["first"], case


@pytest.mark.parametrize("case", DISPLAY["following_top"], ids=lambda c: c["name"])
def test_following_top(case: dict[str, Any]) -> None:
    items = [Placed(i["height"], i["top"]) for i in case["items"]]
    top = following_top(
        items,
        case["canvas_height"],
        case["gap"],
        case["last_is_live"],
        case["headroom"],
        case["reanchor"],
    )
    assert abs(top - case["top"]) < CLOSE


# -- the playout and the two zones (decisions 0245, 0251) ------------------------------


@pytest.mark.parametrize("case", PLAYOUT["tokens"], ids=lambda c: repr(c["text"]))
def test_playout_tokens(case: dict[str, Any]) -> None:
    """Boundaries as tokens: a clause's text as the words played out."""
    tokens = rule_cases.tokens_of(case["text"])
    assert tokens == case["tokens"]
    assert "".join(t["text"] for t in tokens) == case["text"]  # nothing lost


@pytest.mark.parametrize("case", PLAYOUT["cases"], ids=lambda c: c["name"])
def test_playout(case: dict[str, Any]) -> None:
    shown = rule_cases.played_out(
        rule_cases.playout_rules(case["rules"]), case["heard"]
    )
    assert len(shown) == len(case["shown"])
    for got, wanted in zip(shown, case["shown"], strict=True):
        assert got["at"] == pytest.approx(wanted["at"], abs=CLOSE)
        assert {**got, "at": 0} == {**wanted, "at": 0}
    # every case ends with the caption whole, and nothing shown before its time
    heard = case["heard"]
    last = {h["caption"]: "".join(c["original"] for c in h["clauses"]) for h in heard}
    final = {s["caption"]: s["text"] for s in shown}
    newest = heard[-1]["caption"]
    assert final[newest] == last[newest]
    assert all(s["at"] >= heard[0]["at"] for s in shown)


@pytest.mark.parametrize("case", PLAYOUT["zones"], ids=lambda c: c["name"])
def test_zones(case: dict[str, Any]) -> None:
    assert rule_cases.zones_played(case["steps"]) == case["answers"]


def test_the_playouts_constants_are_the_codes() -> None:
    from polyglotic_desktop.core.listening import playout
    from polyglotic_desktop.ui_next.views import zones

    constants = PLAYOUT["constants"]
    assert constants["delay"] == playout.DELAY_SEC
    assert constants["eager_delay"] == playout.EAGER_DELAY_SEC
    assert constants["min_gap"] == playout.MIN_GAP_SEC
    assert constants["pause"] == zones.PAUSE_SEC
    assert constants["live_lines_monologue"] == zones.LIVE_LINES_MONOLOGUE
