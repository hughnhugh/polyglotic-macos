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
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    SpeechTimes,
    WordLink,
    WordTime,
)
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
from polyglotic_desktop.core.listening.playout import (
    DELAY_SEC,
    EAGER_DELAY_SEC,
    ESTIMATE_LATE_SEC,
    MIN_GAP_SEC,
    Ahead,
    Playout,
    PlayoutRules,
    _clause_words,
    each_character,
)
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
from polyglotic_desktop.ui_next.views.zones import (
    CONVERSATION_WITHIN_SEC,
    LIVE_LINES_CONVERSATION,
    LIVE_LINES_MONOLOGUE,
    PAUSE_SEC,
    Zones,
    handed_off,
)

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
        _timing_case("Steady: once, finished, at a 0.6s pause or a breath; joins only onto fragments", {app: ("video", [(0.5, False), (4.5, True), (0.4, False), (3.0, True), (0.7, False), (1.2, True), (1.0, False), (1.5, True), (1.5, False)])}, CaptionMode.WHOLE.live_update_interval(1.5), CaptionMode.WHOLE.rules),
        _timing_case("Quick preview: live updates 1.5 and 3s in, cut at 6s, then the finished caption", {app: ("video", [(0.5, False), (7.0, True), (1.0, False), (1.0, True), (1.5, False)])}, CaptionMode.PREVIEW.live_update_interval(1.5), CaptionMode.PREVIEW.rules),
        _timing_case("Live updates: every 1.5s, finished at a 0.8s pause, joins only onto fragments", {app: ("video", [(0.5, False), (4.0, True), (1.2, False), (1.2, True), (1.2, False), (1.5, True), (1.5, False)])}, CaptionMode.INSTANT.live_update_interval(1.5), CaptionMode.INSTANT.rules),
    ]  # fmt: skip
    return {
        "rule": "The live-update timing rules (protocol v1: the app decides)",
        "code": "src/polyglotic_desktop/core/listening/timing.py",
        "t0": T0,
        "frame_seconds": FRAME_SEC,
        "cases": cases,
    }


# -- the playout (decision 0245) and the two zones (0251) -------------------------------

_INTO = Language("en")


def update_from(data: dict[str, Any]) -> CaptionUpdate:
    """A playout case's `heard` entry as the caption update it stands for."""
    clauses = tuple(
        Clause(
            each["original"],
            {_INTO: each["translation"]} if each.get("translation") else {},
            words=tuple(
                WordTime((w[0], w[1]), w[2], w[3]) for w in each.get("words", ())
            ),
        )
        for each in data["clauses"]
    )
    return CaptionUpdate(
        CaptionId(data["caption"]),
        SourceId(data["source"]),
        CaptionKind(data["kind"]),
        clauses,
        _INTO,
        (_INTO,),
        tuple(CaptionId(c) for c in data.get("replaces", ())),
        times=SpeechTimes(data["start"], data["end"], data["end"], data["at"]),
        established=data.get("established", 0),
    )


def playout_rules(data: dict[str, Any]) -> PlayoutRules:
    return PlayoutRules(
        delay=data["delay"],
        hold_back=data["hold_back"],
        ahead=Ahead(data["ahead"]),
        established_only=data["established_only"],
        translation_after=data["translation_after"],
    )


def played_out(rules: PlayoutRules, heard: list[dict[str, Any]]) -> list[Any]:
    """What a playout shows for `heard`, as the file says it (README)."""
    playout = Playout(rules)
    shown: list[dict[str, Any]] = []

    def note(at: float, updates: Sequence[CaptionUpdate]) -> None:
        for each in updates:
            shown.append(
                {
                    "at": _round(at),
                    "caption": each.caption_id,
                    "kind": each.kind.value,
                    "text": "".join(c.original for c in each.clauses),
                    "established": each.established,
                    "translated": [bool(c.translations) for c in each.clauses],
                }
            )

    def release(until: float | None) -> None:
        while (due := playout.due()) is not None and (until is None or due <= until):
            note(due, playout.release(due))

    for entry in heard:
        release(entry["at"])
        note(entry["at"], playout.heard(update_from(entry), entry["at"]))
    release(None)
    return shown


def _heard(
    caption: str,
    kind: str,
    start: float,
    end: float,
    *clauses: str | tuple[str, str] | dict[str, Any],
    source: str = "app",
    **more: Any,
) -> dict[str, Any]:
    each: list[dict[str, Any]] = []
    for clause in clauses:
        if isinstance(clause, str):
            each.append({"original": clause})
        elif isinstance(clause, tuple):
            each.append({"original": clause[0], "translation": clause[1]})
        else:
            each.append(clause)
    return {
        "at": _round(end + 0.1),
        "caption": caption,
        "source": source,
        "kind": kind,
        "start": start,
        "end": end,
        "clauses": each,
        **more,
    }


def _playout_cases() -> list[dict[str, Any]]:
    default = PlayoutRules()
    eager = PlayoutRules(delay=EAGER_DELAY_SEC, hold_back=0)
    growing = [
        _heard("c1", "live", 10.0, 11.0, "one two three"),
        _heard("c1", "live", 10.0, 12.0, "one two three four five six"),
        _heard("c1", "finished", 10.0, 12.6, ("one two three four five six seven.", "un a sept.")),
    ]  # fmt: skip
    cases: list[tuple[str, PlayoutRules, list[dict[str, Any]]]] = [
        ("the default: words in the speaker's rhythm, a delay behind, the newest held back", default, growing),
        ("the newest word shown too, 1.5 s behind", eager, growing),
        ("a finished caption alone: every word, then the server's own update", default,
         [_heard("c1", "finished", 20.0, 22.0, ("Good morning, everyone.", "Bonjour a tous."))]),
        ("the server's word times are used when it sends them", default,
         [_heard("c1", "finished", 30.0, 33.0, {
             "original": "slow then quick quick",
             "translation": "lent puis vite vite",
             "words": [[0, 4, 30.0, 31.6], [5, 9, 31.8, 32.2], [10, 15, 32.3, 32.6], [16, 21, 32.7, 33.0]],
         })]),
        ("a rewrite of words not yet shown is never seen", default, [
            _heard("c1", "live", 40.0, 41.0, "the whether is"),
            _heard("c1", "live", 40.0, 42.0, "the weather is fine today"),
            _heard("c1", "finished", 40.0, 42.4, "The weather is fine today."),
        ]),
        ("a clause's translation comes with its last word", default,
         [_heard("c1", "finished", 50.0, 53.0, ("One two, ", "Un deux,"), ("three four.", "trois quatre."))]),
        ("Acquisition: each clause's translation 2 s after its last word", dataclasses.replace(default, translation_after=2.0),
         [_heard("c1", "finished", 50.0, 53.0, ("One two, ", "Un deux,"), ("three four.", "trois quatre."))]),
        ("Calm: only the established words while the caption is live", dataclasses.replace(default, established_only=True), [
            _heard("c1", "live", 60.0, 61.0, "one two three", established=4),
            _heard("c1", "live", 60.0, 62.0, "one two three four five", established=14),
            _heard("c1", "finished", 60.0, 62.5, "One two three four five."),
        ]),
        ("words ahead, waiting: the words heard wait faint (text past `established`)", dataclasses.replace(default, ahead=Ahead.WAITING), growing),
        ("words ahead, all: the newest word too", dataclasses.replace(default, ahead=Ahead.ALL), growing),
        ("Chinese: a character at a time, punctuation with the word before", default,
         [_heard("c1", "finished", 70.0, 72.0, ("你好，世界。", "Hello, world."))]),
        ("two sources at once keep their own rhythm", default, [
            _heard("c1", "finished", 80.0, 81.0, "one two three"),
            _heard("m1", "finished", 80.2, 81.2, "yes indeed", source="mic"),
        ]),
        ("a caption that replaces another carries on from the words shown", default, [
            _heard("c1", "live", 90.0, 91.5, "one two three four"),
            _heard("c2", "finished", 90.0, 93.0, "one two three four five six.", replaces=["c1"]),
        ]),
    ]  # fmt: skip
    return [
        {
            "name": name,
            "rules": {
                "delay": rules.delay,
                "hold_back": rules.hold_back,
                "ahead": rules.ahead.value,
                "established_only": rules.established_only,
                "translation_after": rules.translation_after,
            },
            "heard": heard,
            "shown": played_out(rules, heard),
        }
        for name, rules, heard in cases
    ]


def tokens_of(text: str) -> list[dict[str, Any]]:
    return [
        {"text": w.text, "key": w.key, "units": _round(w.units), "start": w.start}
        for w in _clause_words(text, 0, each_character)
    ]


_TOKEN_TEXTS = (
    "one two three",
    "Good morning, everyone.",
    "Well - no; it's a state-of-the-art thing...",
    "\u201cQuoted,\u201d she said.",
    "It cost 3.50 in 2024.",
    "你好，世界。",
    "我用Python写code。",
    "  leading and trailing  ",
    "",
)


def zones_played(steps: list[dict[str, Any]]) -> list[Any]:
    """Each step's answer from a new `Zones` (README)."""
    zones = Zones()
    answers: list[Any] = []
    for step in steps:
        if "heard" in step:
            zones.heard(step["heard"], step["at"])
            answers.append(None)
        elif "live_lines" in step:
            answers.append(zones.live_lines(step["live_lines"]))
        elif "handoff" in step:
            gone = handed_off(
                [(c[0], c[1], c[2]) for c in step["handoff"]],
                step["lines"],
                step["live_lines_shown"],
            )
            zones.settle(gone)
            answers.append({"settled": sorted(zones.settled)})
        else:
            zones.pause(step["pause"])
            answers.append(
                {"settled": sorted(zones.settled), "ended": sorted(zones.ended)}
            )
    return answers


def _zone_cases() -> list[dict[str, Any]]:
    cases: list[tuple[str, list[dict[str, Any]]]] = [
        ("one speaker: three live lines", [
            {"heard": "app", "at": 0.0},
            {"live_lines": 10.0},
        ]),
        ("two speakers within a minute: two live lines; three again once one is quiet", [
            {"heard": "app", "at": 0.0},
            {"heard": "you", "at": 20.0},
            {"live_lines": 30.0},
            {"live_lines": 60.0},
            {"live_lines": 60.5},
            {"heard": "app", "at": 100.0},
            {"live_lines": 100.0},
        ]),
        ("a caption hands off when its last line rolls out of the zone", [
            {"handoff": [[1, 0, False], [2, 1, False], [3, 2, True]], "lines": 3, "live_lines_shown": 3},
            {"handoff": [[1, 0, False], [2, 2, False], [3, 3, True]], "lines": 4, "live_lines_shown": 3},
            {"handoff": [[2, 2, False], [3, 5, True]], "lines": 6, "live_lines_shown": 3},
        ]),
        ("a caption still being spoken never hands off", [
            {"handoff": [[1, 0, True]], "lines": 5, "live_lines_shown": 3},
        ]),
        ("with two live lines a caption hands off a line sooner", [
            {"handoff": [[1, 0, False], [2, 2, True]], "lines": 3, "live_lines_shown": 2},
        ]),
        ("a 5 s pause settles everything, and the next caption starts a paragraph", [
            {"handoff": [[1, 0, False], [2, 1, False]], "lines": 2, "live_lines_shown": 3},
            {"pause": [1, 2]},
            {"pause": []},
        ]),
    ]  # fmt: skip
    return [
        {"name": name, "steps": steps, "answers": zones_played(steps)}
        for name, steps in cases
    ]


def playout() -> dict[str, Any]:
    return {
        "rule": "The paced modes' playout (decision 0245) and the two zones' handoff (0251)",
        "code": [
            "src/polyglotic_desktop/core/listening/playout.py",
            "src/polyglotic_desktop/ui_next/views/zones.py",
        ],
        "constants": {
            "delay": DELAY_SEC,
            "eager_delay": EAGER_DELAY_SEC,
            "min_gap": MIN_GAP_SEC,
            "estimate_late": ESTIMATE_LATE_SEC,
            "live_lines_monologue": LIVE_LINES_MONOLOGUE,
            "live_lines_conversation": LIVE_LINES_CONVERSATION,
            "conversation_within": CONVERSATION_WITHIN_SEC,
            "pause": PAUSE_SEC,
        },
        "tokens": [{"text": t, "tokens": tokens_of(t)} for t in _TOKEN_TEXTS],
        "cases": _playout_cases(),
        "zones": _zone_cases(),
    }


# -- writing and checking --------------------------------------------------------------

BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "timing.json": timing,
    "levels.json": levels,
    "highlights.json": highlights,
    "word-split.json": word_split,
    "display.json": display,
    "playout.json": playout,
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
