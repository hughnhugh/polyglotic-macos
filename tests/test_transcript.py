"""The transcript written out as text, SRT and CSV - finished captions
only, in the caption history's order. Made-up text only."""

import csv
import io
from datetime import UTC, datetime, timedelta, timezone

from polyglotic_desktop.core.listening.captions import Clause, Language
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.core.listening.transcript import (
    as_csv,
    as_srt,
    as_text,
    translation_text,
)

EN = Language("en")
ZH = Language("zh")
START = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)


def caption(
    n: int,
    *clauses: Clause,
    at: float,
    took: float = 2.0,
    live: bool = False,
    you: bool = False,
    language: str = "zh",
) -> Caption:
    return Caption(
        n,
        CaptionId(str(n)),
        SourceId("mic" if you else "app"),
        you,
        live,
        clauses,
        Language(language),
        (Language(language),),
        START + timedelta(seconds=at),
        START + timedelta(seconds=at + took),
    )


CAPTIONS = [
    caption(
        1, Clause("你好，", {EN: "Hello,"}), Clause("今天。", {EN: "today."}), at=1.0
    ),
    caption(
        2,
        Clause("Sounds good.", {ZH: "不错。"}),
        at=4.0,
        took=0.5,
        you=True,
        language="en",
    ),
    caption(3, Clause("还在说"), at=6.0, live=True),
]


def test_text_has_each_finished_caption_with_its_translations() -> None:
    text = as_text(CAPTIONS, [EN, ZH], {"en": "English", "zh": "Chinese"}, you="You")
    assert text == (
        "[09:00:01] 你好，今天。\n"
        "    English: Hello, today.\n"
        "\n"
        "[09:00:04] You: Sounds good.\n"
        "    Chinese: 不错。\n"
    )
    assert as_text([], [EN]) == ""


def test_srt_cues_are_timed_from_the_session_start() -> None:
    assert as_srt(CAPTIONS, [EN], START) == (
        "1\n"
        "00:00:01,000 --> 00:00:03,000\n"
        "你好，今天。\n"
        "Hello, today.\n"
        "\n"
        "2\n"
        "00:00:04,000 --> 00:00:05,500\n"
        "Sounds good.\n"
    )


def test_an_srt_cue_never_runs_into_the_next() -> None:
    close = [
        caption(1, Clause("一。"), at=0.0, took=5.0),
        caption(2, Clause("二。"), at=3.0, took=1.0),
    ]
    srt = as_srt(close, [], START)
    assert "00:00:00,000 --> 00:00:03,000" in srt
    assert "00:00:03,000 --> 00:00:04,500" in srt


def test_csv_has_a_row_per_finished_caption_and_a_column_per_language() -> None:
    rows = list(csv.reader(io.StringIO(as_csv(CAPTIONS, [EN, ZH]))))
    assert rows == [
        ["time", "you", "source", "language", "original", "en", "zh"],
        [
            "2026-11-04T09:00:01+00:00",
            "no",
            "",
            "zh",
            "你好，今天。",
            "Hello, today.",
            "",
        ],
        ["2026-11-04T09:00:04+00:00", "yes", "", "en", "Sounds good.", "", "不错。"],
    ]


def test_text_and_csv_name_each_source_in_the_time_zone_given() -> None:
    """As the transcript shows them (project 062): several apps at once
    are told apart, and the times are the PC's, not UTC."""
    sydney = timezone(timedelta(hours=11))
    sources = {SourceId("app"): "Discord", SourceId("mic"): "Me"}
    text = as_text(CAPTIONS, [EN], {"en": "English"}, "You", sydney, sources)
    assert text == (
        "[20:00:01] Discord: 你好，今天。\n"
        "    English: Hello, today.\n"
        "\n"
        "[20:00:04] Me: Sounds good.\n"
    )
    # a source not named: no name, but the user's own are still "You"
    text = as_text(CAPTIONS, [], zone=sydney, sources={})
    assert text.splitlines()[0] == "[20:00:01] 你好，今天。"
    assert text.splitlines()[2] == "[20:00:04] You: Sounds good."
    rows = list(csv.reader(io.StringIO(as_csv(CAPTIONS, [EN], sydney, sources))))
    assert rows[1][:3] == ["2026-11-04T20:00:01+11:00", "no", "Discord"]
    assert rows[2][:3] == ["2026-11-04T20:00:04+11:00", "yes", "Me"]


def test_a_captions_translation_alone_one_language_a_line() -> None:
    """The transcript's "Copy the translation" (polyglotic-hq 333): only
    the languages it was translated into, without their names."""
    first, second, untranslated = CAPTIONS
    assert translation_text(first, [EN, ZH]) == "Hello, today."
    assert translation_text(second, [EN, ZH]) == "不错。"
    both = caption(4, Clause("Bonjour.", {EN: "Hello.", ZH: "你好。"}), at=9.0)
    assert translation_text(both, [EN, ZH]) == "Hello.\n你好。"
    assert translation_text(untranslated, [EN]) == ""
    assert translation_text(first, []) == ""  # Original only


# polyglotic-hq 432: in a window into English with Chinese its second
# language, an English caption's Chinese line comes under the window's
# language, English (protocol.md's `second_languages`) - it was saved and
# copied in the English column, and the Chinese column was empty.
SECONDS = {EN: ZH}
SECOND_LINE = [
    caption(
        1, Clause("你好，", {EN: "Hello,"}), Clause("今天。", {EN: "today."}), at=1.0
    ),
    caption(2, Clause("See you.", {EN: "明天见。"}), at=4.0, language="en"),
]


def test_a_second_language_line_is_saved_under_its_own_language() -> None:
    rows = list(csv.reader(io.StringIO(as_csv(SECOND_LINE, [EN, ZH], seconds=SECONDS))))
    assert [row[3:] for row in rows] == [
        ["language", "original", "en", "zh"],
        ["zh", "你好，今天。", "Hello, today.", ""],
        ["en", "See you.", "", "明天见。"],
    ]
    names = {"en": "English", "zh": "Chinese"}
    text = as_text(SECOND_LINE, [EN, ZH], names, seconds=SECONDS)
    assert "    Chinese: 明天见。" in text
    assert "English: 明天见" not in text
    assert "    English: Hello, today." in text


def test_a_second_language_line_is_copied_and_cued_as_the_window_shows_it() -> None:
    first, second = SECOND_LINE
    assert translation_text(second, [EN, ZH], SECONDS) == "明天见。"
    assert translation_text(first, [EN, ZH], SECONDS) == "Hello, today."
    srt = as_srt(SECOND_LINE, [EN, ZH], START, SECONDS)
    assert "See you.\n明天见。" in srt and "你好，今天。\nHello, today." in srt


def test_a_line_already_in_its_key_stays_there() -> None:
    """Only a caption said in the window's language has its line written in
    the second; one said in another language is in the window's."""
    heard_en = caption(1, Clause("Hi.", {ZH: "嗨。"}), at=1.0, language="en")
    rows = list(csv.reader(io.StringIO(as_csv([heard_en], [ZH, EN], seconds={ZH: EN}))))
    assert rows[1][5:] == ["嗨。", ""]
