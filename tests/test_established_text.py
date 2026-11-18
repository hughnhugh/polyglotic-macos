"""Established text (polyglotic-hq 494, decision 0228): a live caption's
start the server says is final, drawn as final; a quiet correction when an
update changes it. Made-up text only."""

import json
from dataclasses import replace

from tests.test_caption_history import Clock, clause, finished, live
from tests.test_protocol import example

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.listening.captions import CaptionUpdate, Language
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    RowKind,
    caption_rows,
)
from polyglotic_desktop.core.listening.established import (
    corrected,
    kept_established,
    per_clause,
    said,
    spans_per_clause,
)
from polyglotic_desktop.core.listening.history import Caption, CaptionHistory

EN = Language("en")


def with_established(update: CaptionUpdate, count: int) -> CaptionUpdate:
    return replace(update, established=count)


# -- the protocol ---------------------------------------------------------------


def test_a_live_update_says_how_much_is_established() -> None:
    message = protocol.decode(
        json.dumps(example("caption_update.live") | {"established": 5})
    )
    assert isinstance(message, protocol.CaptionUpdate)
    assert listening.caption_update(message).established == 5


def test_none_from_a_server_before_it() -> None:
    data = example("caption_update.live")
    data.pop("established", None)
    message = protocol.decode(json.dumps(data))
    assert isinstance(message, protocol.CaptionUpdate)
    assert listening.caption_update(message).established == 0


def test_a_finished_caption_is_final_whatever_it_says() -> None:
    message = protocol.decode(
        json.dumps(example("caption_update.finished") | {"established": 3})
    )
    assert isinstance(message, protocol.CaptionUpdate)
    assert listening.caption_update(message).established == 0


# -- the rules ------------------------------------------------------------------


def test_counted_through_the_clauses_with_nothing_between() -> None:
    clauses = (clause("你好，"), clause("今天天气"))
    assert said(clauses) == "你好，今天天气"
    assert per_clause(clauses, 5) == (3, 2)
    assert per_clause(clauses, 0) == (0, 0)
    assert per_clause(clauses, 99) == (3, 4)
    assert spans_per_clause(clauses, ((2, 5),)) == (((2, 3),), ((0, 2),))


def test_established_text_is_kept_where_the_caption_shows_the_same() -> None:
    heard = (clause("The train leaves at seven"),)
    assert kept_established(heard, 16, heard) == 16
    # settled words kept as first shown: established only as far as they agree,
    # never ending inside a word
    shown = (clause("The trains leave at seven"),)
    assert kept_established(heard, 16, shown) == len("The ")


def test_no_correction_while_an_update_keeps_the_established_words() -> None:
    before = (clause("The train leaves at"),)
    assert corrected(before, 16, (clause("The train leaves at seven"),)) == ()
    assert corrected(before, 0, (clause("Something else"),)) == ()


def test_punctuation_spacing_or_case_alone_isnt_a_correction() -> None:
    # 494's real conversation: the server agrees by words, so a later hearing
    # may write the same words with other marks
    assert corrected((clause("OK，所以"),), 5, (clause("OK, 所以我 come from"),)) == ()
    assert (
        corrected((clause("The train leaves"),), 16, (clause("the train, leaves at"),))
        == ()
    )


def test_a_correction_names_the_words_that_took_their_place() -> None:
    before = (clause("我在细管里"),)
    assert corrected(before, 5, (clause("我在系管里面"),)) == ((2, 3),)
    before = (clause("I want to go to the store"),)
    after = (clause("I want to throw to the store now"),)
    spans = corrected(before, len("I want to go to the"), after)
    assert [said(after)[a:b] for a, b in spans] == ["throw"]


# -- in the caption history -----------------------------------------------------


def test_the_history_keeps_a_live_captions_established_text() -> None:
    history = CaptionHistory(clock=Clock())
    history.apply(live("c1", clause("The train leaves")))
    shown = history.apply(
        with_established(live("c1", clause("The train leaves at seven")), 16)
    )
    assert shown is not None and shown.established == 16 and shown.corrected == ()


def test_a_finished_caption_is_all_final_and_says_what_it_corrected() -> None:
    history = CaptionHistory(clock=Clock())
    history.apply(with_established(live("c1", clause("我在细管里面")), 5))
    done = history.apply(finished("c1", clause("我在系管里面。")))
    assert done is not None and not done.live
    assert done.established == 0
    assert done.corrected == ((2, 3),)


def test_a_finished_caption_that_keeps_the_established_words_corrects_nothing() -> None:
    history = CaptionHistory(clock=Clock())
    history.apply(with_established(live("c1", clause("The train leaves at")), 16))
    done = history.apply(finished("c1", clause("The train leaves at seven.")))
    assert done is not None and done.corrected == ()


def test_a_live_update_that_hears_established_words_again_differently_says_so() -> None:
    history = CaptionHistory(clock=Clock())
    history.apply(with_established(live("c1", clause("我在细管里面")), 5))
    again = history.apply(with_established(live("c1", clause("我在系管里面的")), 2))
    assert again is not None and again.live
    assert again.corrected == ((2, 3),) and again.established == 2


# -- the rows -------------------------------------------------------------------


def _caption(history: CaptionHistory, *updates: CaptionUpdate) -> Caption:
    caption = None
    for each in updates:
        caption = history.apply(each)
    assert caption is not None
    return caption


def test_a_live_captions_rows_say_how_much_is_established() -> None:
    caption = _caption(
        CaptionHistory(clock=Clock()),
        with_established(
            live(
                "c1",
                clause("你好，", "Hello,"),
                clause("今天天气", "today's weather"),
            ),
            5,
        ),
    )
    rows = caption_rows(caption, EN, None, DisplayOptions())
    said_rows = [r for r in rows if r.kind is RowKind.ORIGINAL]
    translated = [r for r in rows if r.kind is RowKind.TRANSLATION]
    assert [r.established for r in said_rows] == [3, 2]
    # a clause established to its end: its translation is final too
    assert [r.established for r in translated] == [len("Hello,"), 0]


def test_a_finished_captions_rows_are_all_final_and_carry_the_correction() -> None:
    history = CaptionHistory(clock=Clock())
    caption = _caption(
        history,
        with_established(live("c1", clause("我在细管里面", "I'm in the tube")), 5),
        finished("c1", clause("我在系管里面。", "I'm in the pipe.")),
    )
    rows = caption_rows(caption, EN, None, DisplayOptions())
    assert all(r.established is None for r in rows)
    assert [r.corrected for r in rows] == [((2, 3),), ()]


def test_a_live_caption_from_a_server_before_it_looks_as_it_did() -> None:
    caption = _caption(CaptionHistory(clock=Clock()), live("c1", clause("你好")))
    assert caption.established == 0
    rows = caption_rows(caption, EN, None, DisplayOptions())
    assert [r.established for r in rows] == [0]
