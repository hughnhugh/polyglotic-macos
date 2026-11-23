"""How long a card must stay readable (views.dwell; polyglotic-hq 585's
reading rules, provisional on 2026-11-21, built by 583)."""

import pytest

from polyglotic_desktop.ui_next.views.dwell import (
    AFTER_LAST_WORD_SEC,
    READ_LEAST_SEC,
    READ_MOST_SEC,
    READ_START_SEC,
    TRANSLATION_AWAITED_SEC,
    Reading,
    need,
    subtitle_need,
)


def test_a_line_needs_its_characters_at_the_readers_pace() -> None:
    assert need("你好世界我们", 3.25, 10.0) == pytest.approx(
        READ_START_SEC.value + 6 / 3.25
    )
    assert need("one two", 9.0, 17.0) == READ_LEAST_SEC.value  # 0.35 + 6/17: the least
    assert need("x" * 400, 9.0, 17.0) == READ_MOST_SEC.value


def test_subtitle_reading_time_includes_word_spaces_and_complete_long_pages() -> None:
    text = "Read every word. " * 15
    assert subtitle_need(text, 3.25, 10.0, continuing=True) == pytest.approx(
        len(text) / 10.0
    )
    assert subtitle_need(text, 3.25, 10.0) == pytest.approx(
        READ_START_SEC.value + len(text) / 10.0
    )
    assert subtitle_need("\u4e00\u4e8c\u4e09\u3002", 3.25, 10.0) == pytest.approx(
        READ_START_SEC.value + 4 / 3.25
    )


def test_a_card_is_read_once_both_its_sides_are() -> None:
    card = Reading(first=10.0, last=11.0, said="你好世界我们")
    said = 10.0 + need("你好世界我们", 3.25, 10.0)
    # no translation yet: it waits for one, then may go
    assert card.read_by() == pytest.approx(
        max(said, 11.0 + TRANSLATION_AWAITED_SEC.value)
    )
    card.meant, card.landed = "Hello world, we are here together today", 14.0
    assert card.read_by() == pytest.approx(14.0 + need(card.meant, 9.0, 17.0))
    card.awaited, card.meant, card.landed = False, "", None
    assert card.read_by() == pytest.approx(max(said, 11.0 + AFTER_LAST_WORD_SEC.value))


def test_short_captions_sharing_a_card_are_read_as_one_text() -> None:
    one = Reading(first=0.0, last=0.0, said="這個", awaited=False)
    shared = Reading(first=0.0, last=6.0, said="這個 面 的 那個", awaited=False)
    assert shared.read_by() > one.read_by()
    assert shared.read_by() >= 6.0 + AFTER_LAST_WORD_SEC.value
