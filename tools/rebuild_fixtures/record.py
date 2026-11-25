"""Record protocol-v1 streams as plain caption-model view states.

Run ``uv run python -m tools.rebuild_fixtures.record`` from the repository root.
The streams below are deliberately small, public/made-up test utterances; never
add captured user speech here.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.listening.caption_model import CaptionModel, caption_model
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.history import CaptionHistory

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "fixtures" / "rebuild"
START = datetime(2026, 11, 24, tzinfo=UTC)


@dataclass(frozen=True)
class Spec:
    name: str
    covers: tuple[str, ...]
    target: str | None
    mode: str
    max_lines: int
    events: tuple[tuple[float, dict[str, Any]], ...]
    readings: dict[str, str] | None = None


def link(
    original: tuple[int, int],
    translation: tuple[int, int],
    *,
    key: bool = True,
    confidence: float = 0.9,
    original_pos: str | None = None,
    translation_pos: str | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "original": list(original),
        "translation": list(translation),
        "key": key,
        "confidence": confidence,
    }
    if original_pos is not None:
        value["original_pos"] = original_pos
    if translation_pos is not None:
        value["translation_pos"] = translation_pos
    return value


def clause(
    original: str,
    translation: str | None = None,
    *,
    target: str = "en",
    links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"original": original}
    if translation is not None:
        value["translations"] = {target: translation}
    if links:
        value["links"] = {target: links}
    return value


def message(
    cid: str,
    kind: str,
    language: str,
    clauses: list[dict[str, Any]],
    *,
    source: str = "speaker-a",
) -> dict[str, Any]:
    return {
        "type": "caption_update",
        "caption_id": cid,
        "source_id": source,
        "kind": kind,
        "language": language,
        "languages_heard": [language],
        "clauses": clauses,
        "replaces": [],
    }


ZH_LINKS = [
    link((0, 2), (0, 5), original_pos="pronoun", translation_pos="pronoun"),
    link((3, 5), (22, 27), original_pos="noun", translation_pos="noun"),
]
EN_LINKS = [
    link((0, 5), (0, 2), original_pos="pronoun", translation_pos="pronoun"),
    link((17, 22), (3, 5), original_pos="noun", translation_pos="noun"),
]


def specs() -> tuple[Spec, ...]:
    zh = clause(
        "你好，今天天气很好。", "Hello, the weather is nice today.", links=ZH_LINKS
    )
    en = clause("Hello, nice weather.", "你好，天气很好。", target="zh", links=EN_LINKS)
    ja = clause(
        "明日は学校へ行きます。",
        "I will go to school tomorrow.",
        links=[link((0, 2), (20, 28)), link((3, 5), (13, 19))],
    )
    return (
        Spec(
            "mandarin_to_english",
            ("B-D1",),
            "en",
            "everyday-instant",
            3,
            ((0, message("zh1", "finished", "zh", [zh])),),
        ),
        Spec(
            "english_to_mandarin",
            ("B-D1",),
            "zh",
            "steady",
            3,
            ((0, message("en1", "finished", "en", [en])),),
        ),
        Spec(
            "japanese_readings",
            ("B-D1", "B-D4"),
            "en",
            "steady",
            3,
            ((0, message("ja1", "finished", "ja", [ja])),),
            {"明": "あ", "日": "した", "学": "がく", "校": "こう", "行": "い"},
        ),
        Spec(
            "word_link_classes",
            ("B-D3",),
            "en",
            "everyday-instant",
            3,
            ((0, message("pos1", "finished", "zh", [zh])),),
        ),
        Spec(
            "word_link_class_unavailable",
            ("B-D3",),
            "en",
            "steady",
            3,
            (
                (
                    0,
                    message(
                        "pos2",
                        "finished",
                        "zh",
                        [
                            clause(
                                "猫睡觉。",
                                "The cat sleeps.",
                                links=[link((0, 1), (4, 7))],
                            )
                        ],
                    ),
                ),
            ),
        ),
        Spec(
            "live_supersedes_words",
            ("B-L1",),
            "en",
            "everyday-instant",
            3,
            (
                (
                    0,
                    message(
                        "live1", "live", "en", [clause("I like", "我喜欢", target="zh")]
                    ),
                ),
                (
                    0.8,
                    message(
                        "live1",
                        "live",
                        "en",
                        [clause("I love it", "我很喜欢", target="zh")],
                    ),
                ),
            ),
        ),
        Spec(
            "finished_replaces_live",
            ("B-L1", "B-F1"),
            "en",
            "steady",
            3,
            (
                (0, message("finish1", "live", "zh", [clause("早上", "Morning")])),
                (
                    1.1,
                    message(
                        "finish1",
                        "finished",
                        "zh",
                        [clause("早上好。", "Good morning.")],
                    ),
                ),
            ),
        ),
        Spec(
            "late_translation",
            ("B-T1",),
            "en",
            "everyday-instant",
            3,
            (
                (0, message("late1", "live", "zh", [clause("谢谢。")])),
                (0.7, message("late1", "live", "zh", [clause("谢谢。", "Thank you.")])),
            ),
        ),
        Spec(
            "two_speakers",
            ("B-S1",),
            "en",
            "steady",
            3,
            (
                (
                    0,
                    message(
                        "sp1",
                        "finished",
                        "zh",
                        [clause("你好。", "Hello.")],
                        source="speaker-a",
                    ),
                ),
                (
                    0.4,
                    message(
                        "sp2",
                        "finished",
                        "en",
                        [clause("Hi there.", "你好。", target="zh")],
                        source="speaker-b",
                    ),
                ),
            ),
        ),
        Spec(
            "language_switch",
            ("B-G1",),
            "en",
            "steady",
            3,
            (
                (0, message("lang1", "finished", "zh", [clause("再见。", "Goodbye.")])),
                (
                    0.5,
                    message(
                        "lang2",
                        "finished",
                        "en",
                        [clause("See you.", "回头见。", target="zh")],
                    ),
                ),
            ),
        ),
        Spec(
            "video_instant_one_line",
            ("B-V1",),
            "en",
            "video-instant",
            1,
            (
                (
                    0,
                    message(
                        "vi1", "finished", "zh", [clause("第一行。", "First line.")]
                    ),
                ),
                (
                    0.5,
                    message(
                        "vi2", "finished", "zh", [clause("第二行。", "Second line.")]
                    ),
                ),
            ),
        ),
        Spec(
            "video_scrolling_three_lines",
            ("B-V2",),
            "en",
            "video-scrolling",
            3,
            (
                (0, message("vs1", "finished", "zh", [clause("一。", "One.")])),
                (0.5, message("vs2", "finished", "zh", [clause("二。", "Two.")])),
                (0.5, message("vs3", "finished", "zh", [clause("三。", "Three.")])),
                (0.5, message("vs4", "finished", "zh", [clause("四。", "Four.")])),
            ),
        ),
    )


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def _words(
    model: CaptionModel, clause_number: int, readings: dict[str, str]
) -> list[dict[str, Any]]:
    clause = model.clauses[clause_number]
    found = []
    for start, end, after in clause.original_units:
        text = clause.original[start:end]
        found.append(
            {
                "span": [start, end],
                "after": after,
                "text": text,
                "reading": "".join(readings.get(char, "") for char in text) or None,
            }
        )
    return found


def _state(
    history: CaptionHistory,
    target: Language | None,
    max_lines: int,
    readings: dict[str, str],
) -> dict[str, Any]:
    models = [caption_model(caption, target) for caption in history.captions][
        -max_lines:
    ]
    lines = []
    for model in models:
        clauses = []
        for number, item in enumerate(model.clauses):
            links = [link for link in model.links if link.original[0].clause == number]
            clauses.append(
                {
                    "original": item.original,
                    "translation": item.translation,
                    "translation_language": item.language,
                    "settled": item.settled,
                    "tokens": _words(model, number, readings),
                    "links": [
                        {
                            "number": value.number,
                            "key": value.key,
                            "confidence": value.confidence,
                            "original": [
                                [word.start, word.end] for word in value.original
                            ],
                            "translation": [
                                [word.start, word.end] for word in value.translation
                            ],
                            "original_classes": [word.pos for word in value.original],
                            "translation_classes": [
                                word.pos for word in value.translation
                            ],
                        }
                        for value in links
                    ],
                }
            )
        lines.append(
            {
                "key": model.key,
                "caption_id": model.caption_id,
                "source_id": model.source,
                "language": model.language,
                "final": not model.live,
                "clauses": clauses,
            }
        )
    return {"lines": lines}


def record(spec: Spec) -> dict[str, Any]:
    clock = Clock()
    history = CaptionHistory(clock=clock)
    checkpoints = []
    elapsed = 0.0
    events = []
    target = Language(spec.target) if spec.target else None
    for delay, raw in spec.events:
        elapsed += delay
        clock.now = START + timedelta(seconds=elapsed)
        decoded = protocol.decode(json.dumps(raw))
        if not isinstance(decoded, protocol.CaptionUpdate):
            raise TypeError(f"{spec.name}: not a caption_update")
        history.apply(listening.caption_update(decoded))
        events.append({"at_seconds": elapsed, "message": raw})
        checkpoints.append(
            {
                "at_seconds": elapsed,
                "state": _state(history, target, spec.max_lines, spec.readings or {}),
            }
        )
    return {
        "schema_version": 1,
        "name": spec.name,
        "covers": list(spec.covers),
        "view": {"mode": spec.mode, "target": spec.target, "max_lines": spec.max_lines},
        "events": events,
        "checkpoints": checkpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail instead of rewriting stale fixtures"
    )
    args = parser.parse_args()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    stale = []
    for spec in specs():
        path = FIXTURES / f"{spec.name}.json"
        text = json.dumps(record(spec), ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8")
    if stale:
        raise SystemExit("stale rebuild fixtures: " + ", ".join(stale))


if __name__ == "__main__":
    main()
