"""One app's captions as lines: the new interface's caption window and
transcript view, without Qt."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tests.ui_next.made_up import (
    EN,
    OTHER_APP,
    ZH,
    finished_updates,
    live_update,
    withdrawn,
)

from polyglotic_desktop.core.listening.captions import Clause
from polyglotic_desktop.core.listening.display import DisplayOptions, RowKind
from polyglotic_desktop.core.listening.sources import WHOLE_SYSTEM, SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.views.captions import (
    TEXT_SIZES,
    TRANSCRIPT_LINES,
    CaptionLines,
    Labels,
)


def lines_of(keep: int = TRANSCRIPT_LINES) -> CaptionLines:
    return CaptionLines((APP,), EN, keep=keep)


def test_a_finished_caption_shows_what_was_said_and_its_translation() -> None:
    view = lines_of()
    assert view.apply(finished_updates(1)[0])
    (line,) = view.lines
    kinds = [row.kind for row in line.rows]
    assert kinds == [
        RowKind.ORIGINAL,
        RowKind.TRANSLATION,
        RowKind.ORIGINAL,
        RowKind.TRANSLATION,
    ]
    assert line.rows[1].text == "Let's go play games together this weekend,"
    assert not line.live


def test_other_apps_captions_are_not_shown() -> None:
    view = lines_of()
    revision = view.revision
    assert not view.apply(finished_updates(1, OTHER_APP)[0])
    assert view.lines == ()
    assert view.revision == revision


def test_a_caption_keeps_its_key_from_live_to_finished() -> None:
    view = lines_of()
    view.apply(live_update("app-00000"))
    (live,) = view.lines
    assert live.live and live.rows[-1].text.endswith(" …")
    view.apply(finished_updates(1)[0])
    (done,) = view.lines
    assert done.key == live.key and not done.live


def test_a_withdrawn_caption_goes() -> None:
    view = lines_of()
    for update in finished_updates(3):
        view.apply(update)
    view.apply(withdrawn("app-00001"))
    assert len(view.lines) == 2


def test_a_transcript_keeps_its_last_thousand_lines() -> None:
    view = lines_of()
    for update in finished_updates(TRANSCRIPT_LINES + 20):
        view.apply(update)
    assert len(view.lines) == TRANSCRIPT_LINES
    assert view.lines[0].key == 21  # the first 20 dropped


def test_only_the_changed_caption_is_rebuilt() -> None:
    view = lines_of()
    for update in finished_updates(5):
        view.apply(update)
    before = view.lines
    view.apply(finished_updates(1, start=5)[0])
    assert all(a is b for a, b in zip(before, view.lines[:5], strict=True))


def test_the_language_changes_every_line() -> None:
    view = lines_of()
    for update in finished_updates(2):
        view.apply(update)
    view.set_language(ZH)  # the made-up lines have no Chinese translation
    assert all(row.kind is RowKind.ORIGINAL for line in view.lines for row in line.rows)


def test_quick_previews_line_is_provisional() -> None:
    view = lines_of()
    view.set_options(DisplayOptions(preview=True))
    view.apply(live_update("app-00000"))
    (line,) = view.lines
    assert line.provisional
    # with its translation under it (polyglotic-hq 268, DECISIONS.md #101),
    # but no word links
    assert {row.kind for row in line.rows} == {RowKind.ORIGINAL, RowKind.TRANSLATION}
    assert all(row.links == () for row in line.rows)


def test_the_text_size_changes_no_line_and_stays_in_range() -> None:
    view = lines_of()
    view.apply(finished_updates(1)[0])
    before, revision = view.lines, view.revision
    view.set_text_size(1.3)
    assert view.text_size == 1.3
    assert view.lines is before
    assert view.revision == revision + 1
    view.set_text_size(9)
    assert view.text_size == TEXT_SIZES[1]
    view.set_text_size(0.1)
    assert view.text_size == TEXT_SIZES[0]


def test_the_users_own_speech_shows_beside_the_apps() -> None:
    view = CaptionLines((APP, MIC), EN, keep=TRANSCRIPT_LINES, yours=(MIC,))
    view.apply(finished_updates(1)[0])
    view.apply(finished_updates(1, MIC, start=1)[0])
    view.apply(finished_updates(1, OTHER_APP, start=2)[0])
    assert [(line.source, line.by_you) for line in view.lines] == [
        (APP, False),
        (MIC, True),
    ]


def test_captions_only_shows_each_original_alone() -> None:
    view = CaptionLines((APP,), None, keep=TRANSCRIPT_LINES)
    view.apply(finished_updates(1)[0])
    view.apply(live_update("app-00001"))
    finished, live = view.lines
    assert [row.kind for row in finished.rows] == [RowKind.ORIGINAL] * 2
    assert [row.text for row in finished.rows] == [
        "我们周末一起去打游戏吧，",
        "好不好？",
    ]
    assert live.rows[-1].kind is RowKind.ORIGINAL
    assert live.rows[-1].text.endswith(" …")  # still being spoken


def test_a_translation_can_be_turned_off_and_on() -> None:
    view = lines_of()
    view.apply(finished_updates(1)[0])
    view.set_language(None)
    assert len(view.lines[0].rows) == 2
    view.set_language(EN)
    assert len(view.lines[0].rows) == 4


def test_the_label_above_a_caption_says_its_source_and_the_language_spoken() -> None:
    view = CaptionLines((APP, MIC), EN, keep=10, yours=(MIC,))
    first, second = finished_updates(2)
    view.apply(first)
    view.apply(replace(second, source_id=MIC))
    assert [line.label for line in view.lines] == ["", "You"]  # mine, always
    labels = Labels(
        {APP: SourceLabel("Discord", "#4dd0e1")},
        show_source=True,
        show_language=True,
        spoken=lambda heard: "+".join(str(h) for h in heard),
    )
    view.set_labels(labels)
    app_line = view.lines[0]
    assert app_line.label.startswith("Discord  ") and app_line.label_color == "#4dd0e1"
    assert view.lines[0].caption_id == first.caption_id


def test_caption_panel_labels_use_local_time_and_name_each_source_change() -> None:
    now = datetime(2026, 11, 23, 10, 43, tzinfo=UTC)
    view = CaptionLines(
        (APP, MIC),
        EN,
        keep=10,
        yours=(MIC,),
        clock=lambda: now,
        labels=Labels(
            sources={APP: SourceLabel("System audio", "#4dd0e1")},
            show_source=True,
            show_language=True,
            show_time=True,
            spoken=lambda heard: {EN: "English", ZH: "Chinese"}[heard[0]],
        ),
    )
    actual = []
    for update, source, language, name in zip(
        finished_updates(4),
        (APP, APP, MIC, APP),
        (EN, ZH, ZH, ZH),
        ("System audio", "", "You", "System audio"),
        strict=True,
    ):
        now += timedelta(minutes=2)
        view.apply(
            replace(
                update, source_id=source, language=language, languages_heard=(language,)
            )
        )
        time = now.astimezone().strftime("%H:%M")
        spoken = "English" if language == EN else "Chinese"
        actual.append(" · ".join(part for part in (name, spoken, time) if part))
    assert [(line.label, line.label_color) for line in view.lines] == [
        (label, "") for label in actual
    ]
    view.set_limits(3)
    assert [line.label for line in view.lines] == [
        f"System audio · {actual[1]}",
        *actual[2:],
    ]


def test_a_captions_delay_is_on_its_label_only_when_asked() -> None:
    """polyglotic-hq 271: "a way to measure / display how long each
    translation takes" - on the line above the caption, off by default."""
    import dataclasses
    import time

    from polyglotic_desktop.core.listening.captions import SpeechTimes
    from polyglotic_desktop.core.listening.delays import CaptionDelay
    from polyglotic_desktop.ui_next.views.captions import Labels

    def said(took: CaptionDelay) -> str:
        return f"{took.from_start:.0f}/{took.from_end:.0f}/{took.server}"

    now = time.perf_counter()
    times = SpeechTimes(now - 4.0, now - 1.0, now - 0.6, now - 0.1)
    first, second = finished_updates(2)
    timed = dataclasses.replace(first, times=times, processing_ms=400)

    view = lines_of()
    view.apply(timed)
    assert view.lines[0].label == ""  # not asked: nothing
    view.set_labels(Labels(delay=said))
    assert view.lines[0].label == "4/1/0.4"
    view.apply(second)  # not this session's speech: no delay known
    assert view.lines[1].label == ""
    view.set_labels(Labels(show_language=True, spoken=lambda _: "English", delay=said))
    assert view.lines[0].label == "English  4/1/0.4"


def test_a_views_text_settles_after_the_time_chosen() -> None:
    """polyglotic-hq 309: at 0s a later hearing only adds to what the
    view shows - at 3s (as it was) it rewrote words just shown."""
    said = Clause("We walked to this")
    again = Clause("He went to this door and")

    def shown(seconds: float) -> str:
        view = CaptionLines((APP,), None, keep=10)
        view.set_settle_after(seconds)
        first = replace(live_update("app-00000"), clauses=(said,))
        view.apply(first)
        view.apply(replace(first, clauses=(again,)))
        return view.lines[0].rows[0].text

    assert shown(3.0).startswith("He went to this door and")
    assert shown(0.0).startswith("We walked to this door and")


def test_own_source_is_omitted_while_you_and_other_sources_stay() -> None:
    now = datetime(2026, 11, 25, 5, 17, tzinfo=UTC)
    labels = Labels(
        sources={
            WHOLE_SYSTEM: SourceLabel("Everything the PC plays", "#f5a97f"),
            OTHER_APP: SourceLabel("Zoom", "#a5d66f"),
        },
        own_source=WHOLE_SYSTEM,
        show_source=True,
        show_language=True,
        show_time=True,
        spoken=lambda heard: {EN: "English", ZH: "Chinese"}[heard[0]],
        pace=lambda wpm: f"{wpm} wpm",
    )
    view = CaptionLines(
        (WHOLE_SYSTEM, MIC, OTHER_APP),
        EN,
        keep=10,
        yours=(MIC,),
        clock=lambda: now,
        labels=labels,
    )
    updates = finished_updates(4, WHOLE_SYSTEM)
    for update, source, wpm in zip(
        updates,
        (WHOLE_SYSTEM, MIC, WHOLE_SYSTEM, OTHER_APP),
        (165, 167, 170, 150),
        strict=True,
    ):
        view.apply(
            replace(
                update,
                source_id=source,
                language=EN,
                languages_heard=(EN,),
                pace_wpm=wpm,
            )
        )
    local = now.astimezone().strftime("%H:%M")
    assert [line.label for line in view.lines] == [
        f"English · {local} · 165 wpm",
        f"You · English · {local} · 167 wpm",
        f"English · {local} · 170 wpm",
        f"Zoom · English · {local} · 150 wpm",
    ]

    # Turning caption info off hides every header regardless of source.
    view.set_labels(replace(labels, show_info=False))
    assert [line.label for line in view.lines] == ["", "", "", ""]

    # A mic-only window still keeps "You" on the learner's own speech.
    mic_only = CaptionLines(
        (MIC,),
        EN,
        keep=10,
        yours=(MIC,),
        clock=lambda: now,
        labels=replace(labels, own_source=MIC),
    )
    mic_only.apply(
        replace(
            updates[0], source_id=MIC, language=EN, languages_heard=(EN,), pace_wpm=167
        )
    )
    assert mic_only.lines[0].label == f"You · English · {local} · 167 wpm"
