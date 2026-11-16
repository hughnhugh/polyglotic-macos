"""A transcript's own state, without Qt (`ui_next.views.transcript`):
finished captions only, my speech while its window shows it, Original
only, search, following or scrolled back, what it remembers, and where it
opens."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tests.ui_next.made_up import EN, ZH, finished_updates, live_update

from polyglotic_desktop.core.listening.captions import CaptionKind, Language
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_WINDOW_LINES,
    TRANSCRIPT_LINES,
    TRANSCRIPT_MOST_LINES,
    CaptionLines,
)
from polyglotic_desktop.ui_next.views.placement import Rect, Size
from polyglotic_desktop.ui_next.views.transcript import (
    ASK_FROM_LINES,
    CASCADE,
    DEFAULT_SIZE,
    GAP,
    STORED_KEY,
    StoredTranscripts,
    Transcript,
    TranscriptChoices,
    TranscriptLength,
    beside,
    clear_of,
    match_spans,
    pattern,
    rail_inline,
)

AREA = Rect(0, 0, 1920, 1040)


def filled(count: int = 20, **options: object) -> Transcript:
    found = Transcript(APP, EN, mic=MIC, **options)  # type: ignore[arg-type]
    for update in finished_updates(count):
        found.apply(update)
    return found


def height(line: object) -> float:
    return 40.0


# -- what it collects ----------------------------------------------------------------


def test_only_finished_captions_make_lines() -> None:
    found = filled(3)
    revision = found.revision
    assert not found.apply(live_update("live-1"))  # being spoken: no line
    assert len(found.lines) == 3
    assert found.revision == revision  # nothing to draw again
    finished = replace(live_update("live-1"), kind=CaptionKind.FINISHED)
    assert found.apply(finished)
    assert len(found.lines) == 4


def test_a_caption_window_s_lines_still_show_live_captions() -> None:
    lines = CaptionLines((APP,), EN, keep=150)
    assert lines.apply(live_update("live-1"))
    assert len(lines.lines) == 1 and lines.lines[0].live


def test_my_speech_shows_only_while_its_window_shows_it() -> None:
    found = filled(2)
    mine = finished_updates(1, MIC, start=50)[0]
    assert not found.apply(mine)
    found.set_show_mic(True)
    assert found.apply(finished_updates(1, MIC, start=51)[0])
    assert found.lines[-1].by_you
    found.set_show_mic(False)  # lines already kept stay
    assert not found.apply(finished_updates(1, MIC, start=52)[0])
    assert sum(line.by_you for line in found.lines) == 1


def test_original_only_has_no_translation_rows() -> None:
    found = filled(3)
    found.set_language(None, None)
    kinds = {row.kind for line in found.lines for row in line.rows}
    assert kinds == {RowKind.ORIGINAL}
    assert found.languages() == []


def test_the_languages_copied_are_the_window_s_and_its_second() -> None:
    found = filled(1)
    assert found.languages() == [EN]
    found.set_language(EN, ZH)
    assert found.languages() == [EN, ZH]
    found.set_language(ZH, ZH)
    assert found.languages() == [ZH]


def test_it_keeps_a_thousand_lines() -> None:
    found = filled(TRANSCRIPT_LINES + 30)
    assert len(found.lines) == TRANSCRIPT_LINES
    assert found.lines[0].caption_id == finished_updates(1, start=30)[0].caption_id


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def test_kept_for_three_hours_it_lists_a_lecture_past_a_thousand_lines() -> None:
    """The user's feedback 16 (2026-11-13): "a 3-hour lecture" - a
    caption every 3 s for three hours, 3,600 lines, all listed; an hour
    later the first hour's have gone from the list into Copy all and Save."""
    clock = Clock()
    found = Transcript(APP, EN, clock=clock, length=TranscriptLength.THREE_HOURS)
    for update in finished_updates(3_600):
        clock.now += timedelta(seconds=3)
        found.apply(update)
    assert len(found.lines) == 3_600
    assert found.foot().earlier == 0
    for update in finished_updates(1_200, start=3_600):
        clock.now += timedelta(seconds=3)
        found.apply(update)
    oldest = clock.now - timedelta(hours=3)  # the lines since, to the second
    assert found.lines[0].started_at == oldest and len(found.lines) == 3_601
    assert len(found.captions_kept()) == 4_800  # Save still has them all


def test_the_whole_session_is_listed_up_to_its_most() -> None:
    found = filled(TRANSCRIPT_LINES + 30, length=TranscriptLength.SESSION)
    assert len(found.lines) == TRANSCRIPT_LINES + 30
    assert TranscriptLength.SESSION.limits == (TRANSCRIPT_MOST_LINES, None)
    assert TranscriptLength.THREE_HOURS.limits == (TRANSCRIPT_MOST_LINES, 3 * 3600.0)


def test_the_default_lists_the_newest_thousand_as_before() -> None:
    assert TranscriptLength.NEWEST.limits == (TRANSCRIPT_LINES, None)
    assert filled(5).length is TranscriptLength.NEWEST


def test_a_longer_choice_lists_again_what_the_list_had_dropped() -> None:
    """Chosen mid-lecture: the lines past the newest 1,000 come back to the
    list from Copy all's - and a shorter choice sends them back there."""
    found = filled(TRANSCRIPT_LINES + 30)
    found.search("computer")
    matches = len(found.lines)
    found.set_length(TranscriptLength.SESSION)
    assert len(found.all_lines) == TRANSCRIPT_LINES + 30
    assert len(found.lines) > matches  # the search reaches them too
    assert found.foot().earlier == 0
    assert len(found.captions_kept()) == len(found.lines)
    found.search("")
    found.set_length(TranscriptLength.NEWEST)
    assert len(found.lines) == TRANSCRIPT_LINES
    assert found.foot().earlier == 30
    assert len(found.captions_kept()) == TRANSCRIPT_LINES + 30


def test_a_caption_window_keeps_its_own_lines_whatever_the_transcript_keeps() -> None:
    """The long history lives in the transcript, never in the caption
    window: its lines are its own 150, so a caption there costs what it
    did."""
    window = CaptionLines((APP,), EN, keep=CAPTION_WINDOW_LINES)
    transcript = Transcript(APP, EN, length=TranscriptLength.SESSION)
    for update in finished_updates(2_000):
        window.apply(update)
        transcript.apply(update)
    assert len(window.lines) == CAPTION_WINDOW_LINES
    assert len(transcript.lines) == 2_000


def test_a_long_transcript_needs_saving_until_the_whole_of_it_is_saved() -> None:
    """Quit asks about a transcript of more than 300 lines (the old
    history's) with a line added or changed since its last whole save -
    a save of a search's matches doesn't count."""
    assert not filled(ASK_FROM_LINES).needs_saving()
    found = filled(ASK_FROM_LINES + 1)
    assert found.needs_saving() and found.kept == ASK_FROM_LINES + 1
    found.search("computer")
    found.mark_saved()
    assert found.needs_saving()  # only the matches were written
    found.search("")
    found.mark_saved()
    assert not found.needs_saving()
    found.apply(live_update("still-speaking"))  # no line changes
    assert not found.needs_saving()
    found.apply(finished_updates(1, start=ASK_FROM_LINES + 1)[0])
    assert found.needs_saving()


def test_lines_kept_count_those_past_the_list() -> None:
    found = filled(TRANSCRIPT_LINES + 30)
    assert found.kept == TRANSCRIPT_LINES + 30


def test_a_stored_length_that_isn_t_valid_is_the_default() -> None:
    assert TranscriptLength.from_stored("session") is TranscriptLength.SESSION
    for stored in (None, 3, "forever", ""):
        assert TranscriptLength.from_stored(stored) is TranscriptLength.NEWEST


def test_a_line_says_the_language_spoken_and_whether_it_was_checked() -> None:
    found = filled(2)
    line = found.lines[-1]
    assert line.heard == (Language("zh"),) and not line.checked
    other = finished_updates(1, start=3)[0]
    assert found.use_checked(
        line.caption_id, other.clauses, other.language, other.languages_heard
    )
    assert found.lines[-1].checked


# -- search ----------------------------------------------------------------------------


def test_search_keeps_the_lines_that_match_in_any_row_and_any_case() -> None:
    found = filled(10)  # the made-up conversation's five lines, twice
    found.search("FRUIT")
    assert len(found.lines) == 2
    assert all(
        any("fruit" in row.text.lower() for row in line.rows) for line in found.lines
    )
    found.search("水果")
    assert len(found.lines) == 2
    found.search("")
    assert len(found.lines) == 10


def test_search_takes_its_characters_literally() -> None:
    found = filled(5)
    found.search("a.b")  # not "a, any character, b"
    assert found.lines == ()
    assert pattern("  ") is None


def test_a_new_line_that_matches_shows_while_searching() -> None:
    found = filled(5)
    found.search("fruit")
    revision = found.revision
    found.apply(finished_updates(1, start=6)[0])  # the fruit line again
    assert found.revision != revision
    assert len(found.lines) == 2


def test_a_search_shows_the_newest_match() -> None:
    found = filled(20)
    found.scroll.scroll_by(200, found.lines, height, 300, 10)
    assert not found.scroll.following
    found.search("fruit")
    assert found.scroll.following


def test_match_spans_are_where_the_query_is() -> None:
    search = pattern("ab")
    assert match_spans("xAbyab", search) == [(1, 3), (4, 6)]
    assert match_spans("xyz", search) == []
    assert match_spans("ab", None) == []


def test_the_foot_counts_lines_or_matches() -> None:
    found = filled(10)
    foot = found.foot()
    assert (foot.count, foot.searching, foot.following) == (10, False, True)
    found.search("fruit")
    assert (found.foot().count, found.foot().searching) == (2, True)


def test_scrolled_back_the_foot_counts_the_new_lines() -> None:
    found = filled(20)
    found.foot()  # following: the newest line seen
    found.scroll.scroll_by(200, found.lines, height, 300, 10)
    for update in finished_updates(3, start=40):
        found.apply(update)
    foot = found.foot()
    assert (foot.following, foot.new) == (False, 3)
    found.go_live()
    assert found.foot().following


# -- what it remembers, where it opens ---------------------------------------------------


def test_its_choices_are_stored_and_read_back() -> None:
    stored = StoredTranscripts({"Discord.exe": TranscriptChoices(1.3, True)})
    back = StoredTranscripts.from_stored({STORED_KEY: stored.to_stored()})
    assert back.by_key == {"Discord.exe": TranscriptChoices(1.3, True)}


def test_stored_choices_that_aren_t_valid_are_the_defaults() -> None:
    assert StoredTranscripts.from_stored({}).by_key == {}
    assert StoredTranscripts.from_stored({STORED_KEY: [1]}).by_key == {}
    odd = {STORED_KEY: {"a": {"text_size": 9, "rail_open": "yes"}, "b": None}}
    assert StoredTranscripts.from_stored(odd).by_key == {
        "a": TranscriptChoices(),
        "b": TranscriptChoices(),
    }


def test_it_opens_beside_its_caption_window() -> None:
    window = Rect(300, 700, 800, 260)
    assert beside(window, DEFAULT_SIZE, AREA) == Rect(
        window.right + GAP, AREA.bottom - 520, 720, 520
    )
    on_the_right = Rect(1100, 100, 800, 260)
    assert beside(on_the_right, DEFAULT_SIZE, AREA) == Rect(
        1100 - GAP - 720, 100, 720, 520
    )


def test_with_no_room_at_its_sides_it_opens_above_or_below() -> None:
    bottom_centre = Rect(480, 770, 960, 180)  # a caption window's default
    assert beside(bottom_centre, DEFAULT_SIZE, AREA) == Rect(
        600, 770 - GAP - 520, 720, 520
    )
    top_centre = Rect(480, 10, 960, 180)
    assert beside(top_centre, DEFAULT_SIZE, AREA) == Rect(600, 190 + GAP, 720, 520)


def test_with_no_room_beside_it_opens_centred() -> None:
    tall = Rect(200, 100, 1500, 800)
    assert beside(tall, DEFAULT_SIZE, AREA) == Rect(600, 260, 720, 520)
    assert beside(None, DEFAULT_SIZE, AREA) == Rect(600, 260, 720, 520)
    small = Rect(0, 0, 640, 400)
    assert beside(None, DEFAULT_SIZE, small) == Rect(0, 0, 640, 400)
    assert beside(None, Size(100, 100), small) == Rect(270, 150, 100, 100)


def test_never_exactly_over_another_open_transcript() -> None:
    """polyglotic-hq 184: on a 1280 x 720 screen every transcript opened
    centred - a second exactly over the first."""
    laptop = Rect(0, 0, 1280, 672)
    first = beside(None, DEFAULT_SIZE, laptop)
    assert clear_of(first, [], laptop) == first
    second = clear_of(first, [first], laptop)
    assert (second.x, second.y) == (first.x + CASCADE, first.y + CASCADE)
    third = clear_of(first, [first, second], laptop)
    assert (third.x, third.y) == (first.x + 2 * CASCADE, first.y + 2 * CASCADE)
    assert second.width == first.width and second.height == first.height
    no_room = Rect(0, 0, 720, 520)  # the area is just the transcript's size
    whole = beside(None, DEFAULT_SIZE, no_room)
    assert clear_of(whole, [whole], no_room) == whole


def test_the_rail_is_a_popover_below_700_px() -> None:
    assert rail_inline(700) and not rail_inline(699)
