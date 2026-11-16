"""Writes the desktop's rules as shared test cases (`docs/rule-cases/`), for any later port to pass.

polyglotic-hq project 051 (from project 050: mobile kept open). The
timing rules, the known line, highlights, the Chinese word split and the
caption display rules are written in Python here; a phone app (project
050 recommends Kotlin Multiplatform) would write them again. These JSON
files say what they must answer, as polyglotic-server's protocol examples
say what each message looks like: every input below comes from this
repo's tests of the rule (`tests/test_timing.py`,
`tests/learning/test_levels.py`, `tests/learning/test_highlights.py`,
`tests/lexicon/test_chinese.py`, `tests/test_caption_display.py`), and
every expected answer is what the rule gives today.
`tests/test_rule_cases.py` replays the files against this app's rules,
reading only the JSON, as a port would.

    uv run python -m tools.rule_cases write   # after changing a rule on purpose
    uv run python -m tools.rule_cases check   # are the files what this writes?

`docs/rule-cases/README.md` says how to read each file.
"""

import argparse
import dataclasses
import itertools
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from polyglotic_desktop.core.learning.highlights import caption_cap, unfamiliar_words
from polyglotic_desktop.core.learning.levels import (
    DEFAULT_WINDOW,
    UNLIMITED,
    WORDS,
    KnownLine,
    WindowSize,
    place,
)
from polyglotic_desktop.core.learning.statuses import estimated_status
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import Clause, Language, WordLink
from polyglotic_desktop.core.listening.display import (
    LIVE_TRAIL,
    DisplayOptions,
    LinkDetail,
    Placed,
    WordLinks,
    caption_rows,
    first_rewritten,
    following_top,
    numbered_links,
)
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SEC,
    BreathCut,
    CaptionId,
    CaptionMode,
    CaptionTiming,
    LiveSchedule,
    TimingRules,
    TranscriptionRequest,
    WithdrawCaption,
)
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level, WordInLine
from polyglotic_desktop.ports.capture import SourceCategory

REPO = Path(__file__).resolve().parents[1]
FOLDER = REPO / "docs" / "rule-cases"
T0 = 1000.0  # the timing cases' clock at the start of each stream
DECIMALS = 6


def _round(value: float) -> float:
    return round(value, DECIMALS)


# -- the known line and the learning window ------------------------------------------------


def _placed(level: int | None, level_words: int | None, rank: int | None) -> EntryFacts:
    return EntryFacts(EntryId("test:word"), level, rank, False, level_words)


def levels() -> dict[str, Any]:
    lines: list[tuple[KnownLine, WindowSize | None]] = [
        (KnownLine.picked(Level("hsk-2025", 0)), None),
        (KnownLine.picked(Level("hsk-2025", 2)), None),
        (KnownLine.picked(Level("hsk-2025", 4)), 100),  # a level's window: the next
        (KnownLine.picked(Level("en-frequency", 3)), None),
        (KnownLine.words(0), None),
        (KnownLine.words(1000), None),
        (KnownLine.words(1000), 500),
        (KnownLine.words(3000), 2000),
        (KnownLine.words(3000), 3000),  # a size of the learner's own (0144)
        (KnownLine.words(3000), UNLIMITED),  # no end: every word past the line
        (KnownLine.picked(Level("hsk-2025", 4)), UNLIMITED),  # every level above
    ]
    hsk = (300, 500, 1000, 2000, 3600, 5400, 11000)
    words = [
        *(
            _placed(n, size, rank)
            for n, size in enumerate(hsk, 1)
            for rank in (40, 8000)
        ),
        *(
            _placed(None, None, rank)
            for rank in (1, 1000, 1001, 1500, 3000, 3001, 5000)
        ),
        _placed(3, None, 2500),  # an English band: its rank places it
        _placed(None, None, None),  # no rank, no level: rarer than any line
    ]
    cases = []
    for line, size in lines:
        window = line.window(size)
        cases.append(
            {
                "scale": line.scale,
                "known": line.known,
                "stored": {"scheme": line.scale, "midpoint": line.midpoint},
                "window_size": UNLIMITED.value if size is UNLIMITED else size,
                "window_last": window.last,
                "words": [
                    {
                        "level": w.level,
                        "level_words": w.level_words,
                        "rank": w.frequency_rank,
                        "place": place(w),
                        "known": line.knows(w),
                        "reached": window.reaches(w),
                        "in_window": window.holds(w),
                    }
                    for w in words
                ],
            }
        )
    return {
        "rule": "The known line and the learning window: known, learning or rarer",
        "code": "src/polyglotic_desktop/core/learning/levels.py",
        "constants": {"words": WORDS, "default_window": DEFAULT_WINDOW},
        "cases": cases,
    }


# -- highlights ------------------------------------------------------------------------


def _facts(
    name: str, level: int | None = 1, rank: int | None = 100, is_name: bool = False
) -> EntryFacts:
    """As tests/learning/fakes.py's `facts`."""
    return EntryFacts(EntryId(f"test:{name}"), level, rank, is_name)


def _known(n: int) -> list[EntryFacts]:
    return [_facts(f"known{i}", level=1) for i in range(n)]


def _heard_from(heard: dict[str, int]) -> Callable[[EntryId], int]:
    return lambda entry_id: heard.get(entry_id.removeprefix("test:"), 0)


def highlights() -> dict[str, Any]:
    by_level = KnownLine.picked(Level("hsk-2025", 2))
    in_words = KnownLine.words(1000)
    a, b, c = (_facts(n, level=3, rank=r) for n, r in (("a", 1), ("b", 2), ("c", 3)))
    within_reach = [
        *_known(30),
        _facts("next-band", level=3),
        _facts("too-rare", level=5),
        _facts("off-list", level=None),
        _facts("Zhang", level=3, is_name=True),
    ]
    ranked = [
        *_known(20),
        _facts("rarer", level=3, rank=4000),
        _facts("commoner", level=3, rank=900),
        _facts("heard-often", level=3, rank=8000),
    ]
    by_rank = [
        *_known(30),
        _facts("in-window", level=None, rank=1400),
        _facts("window-end", level=None, rank=2000),
        _facts("rarer", level=None, rank=2001),
        _facts("no-rank", level=None, rank=None),
        _facts("Zhang", level=None, rank=1200, is_name=True),
    ]
    Line = list[EntryFacts]
    inputs: list[tuple[str, KnownLine, list[Line], dict[str, int], bool]] = [
        (
            "only new words the window reaches, never names",
            by_level,
            [within_reach],
            {},
            True,
        ),
        (
            "a level's every new word: the rarer too, no names",
            by_level,
            [within_reach],
            {},
            False,
        ),
        ("the commonest wins the one place", by_level, [ranked], {}, True),
        ("the most heard wins it", by_level, [ranked], {"heard-often": 7}, True),
        (
            "at most two a line, each word once",
            by_level,
            [[*_known(40), a, b, c], [*_known(40), a, c]],
            {},
            True,
        ),
        ("in words: a few of the window's", in_words, [by_rank], {}, True),
        (
            "in words: every word of the window, never a rarer one",
            in_words,
            [by_rank],
            {},
            False,
        ),
    ]
    cases = []
    for name, curve, lines, heard, common_only in inputs:
        words = [
            [WordInLine(i * 2, i * 2 + 2, e) for i, e in enumerate(line)]
            for line in lines
        ]
        shown = unfamiliar_words(
            words,
            lambda f, line=curve: estimated_status(f, line),  # type: ignore[misc]
            curve.window(),
            _heard_from(heard),
            common_only,
        )
        cases.append(
            {
                "name": name,
                "scale": curve.scale,
                "known": curve.known,
                "common_only": common_only,
                "heard": heard,
                "lines": [
                    [
                        {
                            "word": w.entry.entry_id.removeprefix("test:"),
                            "start": w.start,
                            "end": w.end,
                            "level": w.entry.level,
                            "rank": w.entry.frequency_rank,
                            "name": w.entry.is_name,
                            "status": estimated_status(w.entry, curve).value,
                        }
                        for w in line
                    ]
                    for line in words
                ],
                "shown": [
                    [w.entry.entry_id.removeprefix("test:") for w in line]
                    for line in shown
                ],
            }
        )
    return {
        "rule": "Unfamiliar words a finished caption shows: the learning window's",
        "code": "src/polyglotic_desktop/core/learning/highlights.py",
        "caption_cap": [
            {"words": n, "cap": caption_cap(n)} for n in (1, 10, 29, 30, 50, 100)
        ],
        "cases": cases,
    }


# -- the Chinese word split ------------------------------------------------------------


def word_split() -> dict[str, Any]:
    from tests.lexicon.sample import (  # the tests' CC-CEDICT samples
        chinese_sample,
        phrases_sample,
    )

    ties = """\
是 是 [shi4] /is; are; am; yes; to be/
非 非 [fei1] /to not be; not; wrong/
常 常 [chang2] /always; ever; often/
是非 是非 [shi4 fei1] /right and wrong; quarrel/
非常 非常 [fei1 chang2] /very; very much; unusual/
簡單 简单 [jian3 dan1] /simple/
的 的 [de5] /of; ~'s (possessive particle)/
不 不 [bu4] /(negative prefix); not; no/
公 公 [gong1] /public; collectively owned/
平 平 [ping2] /flat; level; equal/
不公 不公 [bu4 gong1] /unjust; unfair/
公平 公平 [gong1 ping2] /fair; impartial/
"""
    tie_ranks = {
        "是": 3,
        "非常": 120,
        "是非": 9000,
        "常": 400,
        "不": 5,
        "公平": 900,
        "不公": 20000,
    }
    dictionaries = [
        (
            chinese_sample(frequency_ranks={"人": 10, "游戏": 500, "打游戏": 40000}),
            [
                "他画蛇添足了",
                "研究生命起源",
                "这个人",
                "我们一起打游戏OK吧！",
                "用電腦",
            ],
        ),
        (chinese_sample(ties, frequency_ranks=tie_ranks), ["是非常简单的", "不公平"]),
        (chinese_sample(ties), ["不公平"]),
        (  # a phrase of two common words (polyglotic-hq 359, decision 0151)
            phrases_sample(),
            ["生活中的人", "有了人", "有的人", "去马里", "自由自在", "沧龙"],
        ),
    ]
    cases = []
    for file, texts in dictionaries:
        split = ChineseDictionary(file)
        cases.append(
            {
                "headwords": sorted(file.headwords()),
                "frequency_ranks": dict(sorted(file.frequency_ranks().items())),
                "kept_whole": sorted(
                    form
                    for form in file.headwords()
                    if any(
                        r.reading[:1].isupper()
                        or r.levels
                        or any("(idiom)" in m for m in r.meanings)
                        for r in file.records(form)
                    )
                ),
                "splits": [
                    {"text": t, "words": [t[a:b] for a, b in split.split(t)]}
                    for t in texts
                ],
            }
        )
    return {
        "rule": "Splitting a line of Chinese into dictionary words",
        "code": "src/polyglotic_desktop/core/lexicon/chinese.py (ChineseDictionary.split)",
        "cases": cases,
    }


# -- caption display rules -------------------------------------------------------------


def _clause(
    original: str,
    translations: dict[str, str] | None = None,
    links: dict[str, list[tuple[int, int, int, int, bool, float]]] | None = None,
) -> dict[str, Any]:
    return {
        "original": original,
        "translations": translations or {},
        "links": {
            lang: [
                {"original": [a, b], "translation": [c, d], "key": k, "confidence": s}
                for a, b, c, d, k, s in found
            ]
            for lang, found in (links or {}).items()
        },
    }


def caption_from(data: dict[str, Any]) -> Caption:
    from datetime import UTC, datetime

    now = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    clauses = tuple(
        Clause(
            c["original"],
            {Language(k): v for k, v in c["translations"].items()},
            {
                Language(k): tuple(
                    WordLink(
                        tuple(link["original"]),
                        tuple(link["translation"]),
                        link["key"],
                        link["confidence"],
                    )
                    for link in found
                )
                for k, found in c["links"].items()
            },
        )
        for c in data["clauses"]
    )
    language = Language(data["language"])
    return Caption(
        1,
        CaptionId("a"),
        SourceId("app"),
        False,
        data["live"],
        clauses,
        language,
        (language,),
        now,
        now,
    )


def options_from(data: dict[str, Any]) -> DisplayOptions:
    return DisplayOptions(
        show_original=data["show_original"],
        word_links=WordLinks(data["word_links"]),
        link_detail=LinkDetail(data["link_detail"]),
        max_links=data["max_links"],
    )


def _row_cases() -> list[dict[str, Any]]:
    default = {
        "show_original": True,
        "word_links": "off",
        "link_detail": "most",
        "max_links": None,
    }
    colours = default | {"word_links": "colours"}
    hello = _clause("你好，", {"en": "Hello,"}, {"en": [(0, 2, 0, 5, True, 0.9)]})
    today = _clause("今天", {"en": "today"}, {"en": [(0, 2, 0, 5, True, 0.9)]})
    inputs: list[tuple[str, dict[str, Any], str, str | None, dict[str, Any]]] = [
        (
            "each clause: what was said, then its translation",
            {
                "clauses": [
                    _clause("你好，", {"en": "Hello,"}),
                    _clause("今天。", {"en": "today."}),
                ],
                "live": False,
                "language": "zh",
            },
            "en",
            None,
            default,
        ),
        (
            "hiding originals never leaves a clause without a row",
            {
                "clauses": [_clause("你好，", {"en": "Hello,"}), _clause("嗯")],
                "live": False,
                "language": "zh",
            },
            "en",
            None,
            default | {"show_original": False},
        ),
        (
            "a clause already in the target, into the second language",
            {
                "clauses": [_clause("See you tomorrow.", {"zh": "明天见。"})],
                "live": False,
                "language": "en",
            },
            "en",
            "zh",
            default,
        ),
        (
            "no second language: the original alone",
            {
                "clauses": [_clause("See you tomorrow.", {"zh": "明天见。"})],
                "live": False,
                "language": "en",
            },
            "en",
            None,
            default,
        ),
        (
            "a live caption's last row trails off",
            {
                "clauses": [_clause("你好，", {"en": "Hello,"}), _clause("今天")],
                "live": True,
                "language": "zh",
            },
            "en",
            None,
            default,
        ),
        (
            "word links on settled clauses only",
            {"clauses": [hello, today], "live": True, "language": "zh"},
            "en",
            None,
            colours,
        ),
        (
            "word links once finished",
            {"clauses": [hello, today], "live": False, "language": "zh"},
            "en",
            None,
            colours,
        ),
        (
            "no links with the original hidden",
            {"clauses": [hello], "live": False, "language": "zh"},
            "en",
            None,
            default | {"show_original": False, "word_links": "arrows"},
        ),
        (
            "second-language rows use the second language's links",
            {
                "clauses": [
                    _clause("Good", {"zh": "好"}, {"zh": [(0, 4, 0, 1, True, 0.9)]})
                ],
                "live": False,
                "language": "en",
            },
            "en",
            "zh",
            colours,
        ),
    ]
    cases = []
    for name, caption, target, second, options in inputs:
        rows = caption_rows(
            caption_from(caption),
            Language(target),
            Language(second) if second else None,
            options_from(options),
        )
        cases.append(
            {
                "name": name,
                "caption": caption,
                "target": target,
                "second": second,
                "options": options,
                "rows": [
                    {
                        "text": r.text,
                        "kind": r.kind.value,
                        "language": r.language,
                        "clause": r.clause,
                        "starts_clause": r.starts_clause,
                        "links": [[w.start, w.end, w.link] for w in r.links],
                    }
                    for r in rows
                ],
            }
        )
    return cases


def _link_cases() -> list[dict[str, Any]]:
    inputs: list[
        tuple[str, list[tuple[int, int, int, int, bool, float]], str, Any, Any, Any]
    ] = [
        (
            "one link per counterpart, numbered in reading order",
            [
                (5, 7, 0, 5, True, 0.9),
                (0, 2, 0, 5, True, 0.9),
                (3, 5, 10, 17, True, 0.9),
            ],
            "most",
            None,
            None,
            None,
        ),
        (
            "key words leave out minor links",
            [(0, 1, 0, 1, False, 0.9), (2, 4, 3, 8, True, 0.9)],
            "key",
            None,
            None,
            None,
        ),
        (
            "a cap keeps the surest key links first",
            [
                (0, 1, 0, 1, False, 0.99),
                (2, 3, 2, 3, True, 0.5),
                (4, 5, 4, 5, True, 0.8),
            ],
            "most",
            2,
            None,
            None,
        ),
        (
            "links outside the text are dropped",
            [(0, 2, 0, 5, True, 0.9), (0, 9, 0, 5, True, 0.9), (1, 1, 0, 5, True, 0.9)],
            "most",
            None,
            4,
            5,
        ),
    ]
    cases = []
    for name, found, detail, cap, original_length, translation_length in inputs:
        links = [WordLink((a, b), (c, d), k, s) for a, b, c, d, k, s in found]
        original, translation = numbered_links(
            links, LinkDetail(detail), cap, original_length, translation_length
        )
        cases.append(
            {
                "name": name,
                "links": [
                    {
                        "original": [a, b],
                        "translation": [c, d],
                        "key": k,
                        "confidence": s,
                    }
                    for a, b, c, d, k, s in found
                ],
                "detail": detail,
                "cap": cap,
                "original_length": original_length,
                "translation_length": translation_length,
                "original": [[w.start, w.end, w.link] for w in original],
                "translation": [[w.start, w.end, w.link] for w in translation],
            }
        )
    return cases


def _layout_cases() -> list[dict[str, Any]]:
    gap = 10.0

    def placed(*heights: float, bottom: float = 300.0) -> list[Placed]:
        top = bottom - (sum(heights) + gap * (len(heights) - 1))
        found = []
        for height in heights:
            found.append(Placed(height, top))
            top += height + gap
        return found

    a, b, c = placed(40, 60, 50)
    a2, b2 = placed(40, 60, bottom=280)
    a3, b3 = placed(40, 60)
    inputs: list[tuple[str, list[Placed], bool, float, bool]] = [
        ("arriving captions settle at the bottom", [Placed(40, None), Placed(60, None)], False, 0, True),
        ("nothing to place", [], False, 0, False),
        ("a shrinking caption moves none down", [a, Placed(30, b.top), Placed(50, c.top)], False, 0, False),
        ("growth uses the space left at the bottom first", [a2, Placed(75, b2.top)], False, 0, False),
        ("growth past it pushes the stack up", [a2, Placed(90, b2.top)], False, 0, False),
        ("a live caption that has to push leaves headroom", [a3, Placed(90, b3.top)], True, 64, False),
        ("with room to spare it doesn't push", [a3, b3], True, 64, False),
        ("a new caption pushes the stack up", [a3, b3, Placed(50, None)], False, 0, False),
    ]  # fmt: skip
    return [
        {
            "name": name,
            "items": [{"height": i.height, "top": i.top} for i in items],
            "canvas_height": 300.0,
            "gap": gap,
            "last_is_live": live,
            "headroom": headroom,
            "reanchor": reanchor,
            "top": _round(following_top(items, 300.0, gap, live, headroom, reanchor)),
        }
        for name, items, live, headroom, reanchor in inputs
    ]


def display() -> dict[str, Any]:
    rewritten = [
        (["你好，", "今天" + LIVE_TRAIL], ["你好，", "今天天气"]),
        (["一"], ["一", "二"]),
        (["一", "二", "三"], ["一", "贰", "三"]),
        (["一", "二", "三"], ["一二", "二", "三"]),
        (["一", "二", "三"], ["一", "二"]),
    ]
    return {
        "rule": "Caption display: clause rows, word links drawn, the first rewritten row, the one-way layout",
        "code": "src/polyglotic_desktop/core/listening/display.py",
        "live_trail": LIVE_TRAIL,
        "caption_rows": _row_cases(),
        "numbered_links": _link_cases(),
        "first_rewritten": [
            {"old": old, "new": new, "first": first_rewritten(old, new)}
            for old, new in rewritten
        ],
        "following_top": _layout_cases(),
    }


# -- the live-update timing rules ------------------------------------------------------


def _frames(pattern: Sequence[tuple[float, bool]]) -> list[tuple[float, bool]]:
    spans, t = [], T0
    for seconds, speaking in pattern:
        spans.append((t, t + seconds, speaking))
        t += seconds
    out = []
    for i in range(int((t - T0) / FRAME_SEC)):
        end = T0 + (i + 1) * FRAME_SEC
        middle = end - FRAME_SEC / 2
        out.append((end, any(a <= middle < b and s for a, b, s in spans)))
    return out


def _rules_json(rules: TimingRules) -> dict[str, Any]:
    found = dataclasses.asdict(rules)
    found["schedule"] = rules.schedule.value
    return found


def _timing_case(
    name: str,
    streams: dict[str, tuple[str, list[tuple[float, bool]]]],
    interval: float | None,
    rules: TimingRules,
    pace_hint: float | None = None,
) -> dict[str, Any]:
    ids = (CaptionId(f"c{i}") for i in itertools.count(1))
    timing = CaptionTiming(interval, lambda: next(ids), rules)
    timing.pace_hint = pace_hint
    for source_id, (category, _) in streams.items():
        timing.add_source(Source(SourceId(source_id), SourceCategory(category)))
    merged = sorted(
        (end, source_id, speech)
        for source_id, (_, pattern) in streams.items()
        for end, speech in _frames(pattern)
    )
    decisions: list[dict[str, Any]] = []
    for end, source_id, speech in merged:
        for decision in timing.frame(SourceId(source_id), end, speech):
            if isinstance(decision, WithdrawCaption):
                decisions.append(
                    {
                        "withdraw": decision.caption_id,
                        "source": decision.source.id,
                        "reason": decision.reason.value,
                    }
                )
                continue
            assert isinstance(decision, TranscriptionRequest)
            decisions.append(
                {
                    "caption": decision.caption_id,
                    "kind": decision.kind.value,
                    "source": decision.source.id,
                    "start": _round(decision.speech_start - T0),
                    "end": _round(decision.speech_end - T0),
                    "section": decision.section,
                    "replaces": list(decision.replaces),
                    "at": _round(end - T0),
                }
            )
    return {
        "name": name,
        "live_update_interval": interval,
        "pace_hint": pace_hint,
        "rules": _rules_json(rules),
        "sources": [
            {
                "id": source_id,
                "category": category,
                "pattern": [list(p) for p in pattern],
            }
            for source_id, (category, pattern) in streams.items()
        ],
        "decisions": decisions,
    }


def timing() -> dict[str, Any]:
    poc = TimingRules(lead_in=0.0)  # the tests' arithmetic: no lead-in

    def rules(**changes: Any) -> TimingRules:
        return dataclasses.replace(poc, **changes)

    app, mic = "source-1", "source-mic"
    cases = [
        _timing_case("short speech, one finished caption", {mic: ("mic", [(0.5, False), (3.0, True), (1.5, False)])}, None, poc),
        _timing_case("long speech: live updates, then the whole finished", {app: ("video", [(0.5, False), (9.0, True), (1.5, False)])}, 1.5, poc),
        _timing_case("very long speech split at 20s", {app: ("video", [(0.5, False), (25.0, True), (1.5, False)])}, None, poc),
        _timing_case("back-to-back speech joined", {mic: ("mic", [(0.5, False), (2.0, True), (1.2, False), (2.0, True), (1.5, False)])}, None, poc),
        _timing_case("a long pause isn't joined", {mic: ("mic", [(0.5, False), (2.0, True), (3.0, False), (2.0, True), (1.5, False)])}, None, poc),
        _timing_case("a blip is ignored", {mic: ("mic", [(0.5, False), (0.3, True), (1.5, False)])}, None, poc),
        _timing_case("three back-to-back stretches joined", {app: ("video", [(0.5, False), (2.0, True), (1.0, False), (2.0, True), (1.0, False), (1.5, True), (1.5, False)])}, None, poc),
        _timing_case(
            "no join across another source's caption or a long gap",
            {
                app: ("video", [(0.5, False), (1.5, True), (1.2, False), (1.3, True), (2.5, False), (1.5, True), (1.5, False)]),
                mic: ("mic", [(2.2, False), (0.8, True), (5.0, False)]),
            },
            None,
            poc,
        ),
        _timing_case("a joined caption replaces the live one", {app: ("video", [(2.0, False), (1.2, True), (1.0, False), (7.5, True), (1.0, False)])}, 1.5, poc),
        _timing_case("live updates paced by the server's hint", {app: ("video", [(0.5, False), (9.0, True), (1.5, False)])}, 0.5, poc, pace_hint=3.0),
        _timing_case("growing: at 1.5, 3 and 6s into each section", {app: ("video", [(0.5, False), (14.0, True), (1.5, False)])}, 1.5, rules(schedule=LiveSchedule.GROWING)),
        _timing_case("glimpse: one live update, then the finished caption", {app: ("video", [(0.5, False), (9.0, True), (1.5, False)])}, 1.5, rules(schedule=LiveSchedule.GLIMPSE)),
        _timing_case("a 0.5s hangover ends a caption at a 0.6s pause", {mic: ("mic", [(0.5, False), (3.0, True), (0.6, False), (2.0, True), (1.5, False)])}, None, rules(silence_hangover=0.5)),
        _timing_case(
            "a breath cut at the first short pause after 4s",
            {app: ("video", [(0.5, False), (2.0, True), (0.4, False), (3.0, True), (0.4, False), (2.0, True), (1.5, False)])},
            None,
            rules(breath_cut=BreathCut(after=4.0, pause=0.3, limit=8.0)),
        ),
        _timing_case("a breath cut's limit splits nonstop speech", {app: ("video", [(0.5, False), (19.0, True), (1.5, False)])}, None, rules(breath_cut=BreathCut())),
        _timing_case(
            "a turn cut finishes the quiet source when another starts",
            {app: ("video", [(0.5, False), (3.0, True), (5.0, False)]), mic: ("mic", [(3.9, False), (2.0, True), (2.6, False)])},
            None,
            rules(turn_cut=0.3),
        ),
        _timing_case("joins turned off", {mic: ("mic", [(0.5, False), (2.0, True), (1.2, False), (2.0, True), (1.5, False)])}, None, rules(join_gap=0.0)),
        _timing_case("joins only to repair a fragment", {app: ("video", [(0.5, False), (3.0, True), (1.0, False), (2.0, True), (1.5, False)])}, None, rules(join_only_under=2.0)),
        _timing_case("the default rules: a lead-in before the first speech", {app: ("video", [(1.0, False), (3.0, True), (1.5, False)])}, 1.5, TimingRules()),
        # the caption modes the app offers (project 064): each mode's rules and interval
        _timing_case("Steady: once, finished, at a 0.6s pause or a breath; joins only onto fragments", {app: ("video", [(0.5, False), (4.5, True), (0.4, False), (3.0, True), (0.7, False), (1.2, True), (1.0, False), (1.5, True), (1.5, False)])}, CaptionMode.STEADY.live_update_interval(1.5), CaptionMode.STEADY.rules),
        _timing_case("Quick preview: live updates 1.5 and 3s in, cut at 6s, then the finished caption", {app: ("video", [(0.5, False), (7.0, True), (1.0, False), (1.0, True), (1.5, False)])}, CaptionMode.PREVIEW.live_update_interval(1.5), CaptionMode.PREVIEW.rules),
        _timing_case("Live updates: every 1.5s, finished at a 0.8s pause, joins only onto fragments", {app: ("video", [(0.5, False), (4.0, True), (1.2, False), (1.2, True), (1.2, False), (1.5, True), (1.5, False)])}, CaptionMode.LIVE.live_update_interval(1.5), CaptionMode.LIVE.rules),
    ]  # fmt: skip
    return {
        "rule": "The live-update timing rules (protocol v1: the app decides)",
        "code": "src/polyglotic_desktop/core/listening/timing.py",
        "t0": T0,
        "frame_seconds": FRAME_SEC,
        "cases": cases,
    }


# -- writing and checking --------------------------------------------------------------

BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "timing.json": timing,
    "levels.json": levels,
    "highlights.json": highlights,
    "word-split.json": word_split,
    "display.json": display,
}


def text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.rule_cases")
    parser.add_argument("action", choices=["write", "check"])
    args = parser.parse_args(argv)
    stale = []
    for name, build in BUILDERS.items():
        path = FOLDER / name
        wanted = text(build())
        if args.action == "write":
            FOLDER.mkdir(parents=True, exist_ok=True)
            path.write_text(wanted, encoding="utf-8", newline="\n")
        elif not path.is_file() or path.read_text(encoding="utf-8") != wanted:
            stale.append(name)
    for name in stale:
        print(
            f"{name}: not what the rules give now - `write` after a deliberate change"
        )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
