"""`tools/learner_start.py`: the made-up learner and a start timed to its
window, which CI's start gate runs on the real CC-CEDICT
(`tests/ui/test_start_with_a_big_learner.py`) - here on small made-up
dictionaries, so they're tested on every run."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from tests.ui.test_check_install import sample_dictionaries
from tools.learner_start import (
    longest_busy,
    made_up_learner,
    returning_learner,
    timed_start,
)

from polyglotic_desktop.adapters.json_settings import JsonSettingsStore
from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
from polyglotic_desktop.adapters.sqlite_outbox import open_outbox
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.consent import agreement_needed
from polyglotic_desktop.ui.settings import Settings


def ranked_dictionary(path: Path, entries: int) -> Path:
    """A made-up CC-CEDICT of `entries` entries, ranked in order, none on
    an HSK list (so every one is new to an HSK 4 learner)."""
    records = [
        EntryRecord(
            f"cedict:{n:04d}",
            chr(0x4E00 + n),
            chr(0x4E00 + n),
            "yi1",
            (f"meaning {n}",),
            frequency_rank=n,
        )
        for n in range(1, entries + 1)
    ]
    forms = {r.headword: [r.entry_id] for r in records}
    write_dictionary(path, {"dictionary": "cedict"}, records, forms)
    return path


def test_the_made_up_learner_has_met_the_commonest_words(tmp_path: Path) -> None:
    cedict = ranked_dictionary(tmp_path / "cedict.sqlite", 300)
    learning = tmp_path / "learning.sqlite"

    made_up_learner(cedict, 200, learning)

    db = sqlite3.connect(learning)
    try:
        heard = dict(db.execute("SELECT entry_id, heard FROM exposures"))
        by_hand = [s for (s,) in db.execute("SELECT status FROM statuses")]
        saved = db.execute("SELECT count(*) FROM saved_words").fetchone()[0]
    finally:
        db.close()
    assert len(heard) == 200  # the commonest 200 of 300
    assert heard["cedict:0001"] == 4000  # 20 * 200 / 1 ** 1.15
    assert heard["cedict:0200"] == 9  # 20 * 200 / 200 ** 1.15, rounded
    assert "cedict:0201" not in heard
    assert by_hand.count("learning") == 200 // 40
    assert by_hand.count("known") == 200 // 25
    assert saved == 200 // 50


def test_a_dictionary_with_too_few_words_is_refused(tmp_path: Path) -> None:
    """A learner of 30,000 words on the tests' sample would quietly be a
    small one."""
    cedict = ranked_dictionary(tmp_path / "cedict.sqlite", 10)

    with pytest.raises(ValueError, match="10 entries"):
        made_up_learner(cedict, 11, tmp_path / "learning.sqlite")


def test_a_returning_learner_is_asked_nothing(tmp_path: Path) -> None:
    learning = tmp_path / "learning.sqlite"
    made_up_learner(ranked_dictionary(tmp_path / "cedict.sqlite", 50), 50, learning)

    data = returning_learner(tmp_path / "data", learning)

    outbox = open_outbox(data / "outbox.sqlite")
    try:
        assert not agreement_needed(outbox.consent())
    finally:
        outbox.close()
    store = JsonSettingsStore(data / "settings.json")
    try:
        assert Settings(store).value.learning == "zh"  # the first run's isn't asked
    finally:
        store.close()
    assert (data / "learning.sqlite").read_bytes() == learning.read_bytes()


def test_a_pack_learner_learns_the_packs_language_too(tmp_path: Path) -> None:
    """436's start: Chinese, with a pack language beside it (decision 0175)."""
    learning = tmp_path / "learning.sqlite"
    made_up_learner(ranked_dictionary(tmp_path / "cedict.sqlite", 5), 5, learning)

    data = returning_learner(tmp_path / "data", learning, pack_language="es")

    store = JsonSettingsStore(data / "settings.json")
    try:
        languages = Settings(store).value.learning_languages
    finally:
        store.close()
    assert (languages.main, languages.also) == ("zh", ("es",))


def test_the_longest_stretch_is_read_from_the_watchdogs_lines_since(
    tmp_path: Path,
) -> None:
    log = tmp_path / "polyglotic.log"
    watchdog = "WARNING polyglotic_desktop.perf.watchdog: interface thread busy"
    log.write_text(
        f"2026-11-17 02:11:15,407 {watchdog} 250 ms in controls.py:__init__"
        " (from main.py:new_interface), of 468 ms in a loop outside Qt's\n"
        "2026-11-17 02:11:16,790 INFO polyglotic_desktop.main: learning data open\n"
        f"2026-11-17 02:11:17,230 {watchdog} 61 ms in words_page.py:_add"
        " (from main.py:open_added)\n"
        f"2026-11-17 02:11:17,530 {watchdog} 87 ms in Qt or a library, outside"
        " the app's code\n",
        encoding="utf-8",
    )

    since = datetime(2026, 11, 17, 2, 11, 16)
    assert longest_busy(log, since) == (
        87.0,
        "Qt or a library, outside the app's code",
    )
    assert longest_busy(log, datetime(2026, 11, 17, 2, 11, 17, 300_000))[0] == 87.0
    assert longest_busy(log, datetime(2026, 11, 17, 2, 12)) == (0.0, "")
    assert longest_busy(tmp_path / "none.log", since) == (0.0, "")


@pytest.mark.windows_only  # the app's own OS adapters
def test_a_start_is_timed_from_main_to_its_window(tmp_path: Path) -> None:
    dictionaries = sample_dictionaries(tmp_path / "dictionaries")
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", 5, learning)

    start = timed_start(returning_learner(tmp_path / "data", learning), dictionaries)

    assert 0 < start.window_ms < 60_000
    assert start.busy is not None and 0.0 <= start.busy <= 1.0  # the rest of the PC

    # where the time went: every part from main()'s call to the paint, with
    # nothing left between them (polyglotic-hq 314)
    assert {"learner", "page_home", "page_settings", "first_paint"} <= set(start.parts)
    assert list(start.parts)[-1] == "first_paint"
    assert abs(sum(start.parts.values()) - start.window_ms) < 5


BESIDE_THE_WINDOW = {
    "imports",  # the connection's and speech libraries: wanted just after it
    "learning-store_0",  # the learning data's reads and saves, in order
    "outbox_0",  # the outbox's writes, in order
    "updates_0",  # the look for an update: a broken start can still update
    "apps-with-sound_0",  # the apps with sound, looked for off the interface
    "interface-watchdog",  # times the interface thread's long stretches
    "fonts-ahead",  # Windows' fonts read, never holding the interpreter (322)
}
"""The threads that may begin before the window's first paint."""


@pytest.mark.windows_only  # the app's own OS adapters
def test_only_what_the_window_needs_runs_beside_its_build(tmp_path: Path) -> None:
    """A thread running Python while the window is built takes the
    interpreter from it by turns: the dictionary's read-ahead, begun before
    the window, made it about 50 ms later at 30,000 words met (361 ms
    against 309, 12 starts each, interleaved, the PC about 35 % busy;
    polyglotic-hq 314). It begins once the window has shown and the
    libraries are in. A new thread at start is added here only if the
    window, or the moment after it, needs it."""
    dictionaries = sample_dictionaries(tmp_path / "dictionaries")
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", 5, learning)

    start = timed_start(returning_learner(tmp_path / "data", learning), dictionaries)

    assert "dictionary" not in start.threads  # the read-ahead's
    assert set(start.threads) <= BESIDE_THE_WINDOW


@pytest.mark.windows_only  # the app's own OS adapters
def test_another_learned_language_opens_after_the_window(tmp_path: Path) -> None:
    """Chinese and English both learned (polyglotic-hq 306): English's
    learning data, its store's thread and its read-ahead begin after the
    first paint (`open_added`), so the window is built beside exactly the
    threads a Chinese learner's is - one learning store, no read-ahead."""
    dictionaries = sample_dictionaries(tmp_path / "dictionaries")
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", 5, learning)
    english = tmp_path / "learning-en.sqlite"
    made_up_learner(dictionaries / "ecdict.sqlite", 1, english)

    start = timed_start(
        returning_learner(tmp_path / "data", learning, english), dictionaries
    )

    assert "dictionary" not in start.threads
    assert set(start.threads) <= BESIDE_THE_WINDOW
    assert start.threads.count("learning-store_0") == 1  # the main language's


@pytest.mark.windows_only  # the app's own OS adapters, and Windows' desktops
def test_a_start_with_real_windows_goes_on_to_its_first_answered_click(
    tmp_path: Path,
) -> None:
    """On a private desktop - nothing reaches a screen - with Qt's `windows`
    platform, past the paint to the event loop's first turn (polyglotic-hq
    322). The offscreen start still ends at its paint."""
    dictionaries = sample_dictionaries(tmp_path / "dictionaries")
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", 5, learning)

    real = timed_start(
        returning_learner(tmp_path / "real", learning), dictionaries, real_windows=True
    )
    offscreen = timed_start(returning_learner(tmp_path / "off", learning), dictionaries)

    assert 0 < real.window_ms < 60_000
    assert real.answers_ms is not None and 0 <= real.answers_ms < 60_000
    assert list(real.parts)[-1] == "first_paint"
    assert abs(sum(real.parts.values()) - real.window_ms) < 5
    assert set(real.threads) <= BESIDE_THE_WINDOW
    assert offscreen.answers_ms is None
    # Windows' fonts are read beside the start's other work, on a thread of
    # their own - only with real windows: offscreen has none to read
    # (polyglotic-hq 322, decision 0112)
    assert "fonts-ahead" in real.threads
    assert "fonts-ahead" not in offscreen.threads
    # and waited for once the learner's data is read, before any page
    for start in (real, offscreen):
        parts = list(start.parts)
        assert parts.index("learner") < parts.index("fonts") < parts.index("app")
        # Windows' first-time work for a first window comes in that wait
        # (decision 0113)
        assert parts.index("learner") < parts.index("first_window")
        assert parts.index("first_window") < parts.index("fonts")
    # a window of Windows' is made only with real windows: offscreen the
    # part is a mark and nothing else
    assert real.parts["first_window"] > 2 > offscreen.parts["first_window"]


@pytest.mark.windows_only  # a batch file stands in for the start
def test_a_start_that_reached_its_window_counts_though_its_ending_hung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One start in about 500 wrote its time and then never ended
    (polyglotic-hq 312): it's stopped at the timeout, and its time counts."""
    from tools import learner_start

    hung = tmp_path / "hung.bat"
    hung.write_bytes(
        b'@echo {"window_ms": 321.0, "busy": 0.2} > "%~6"\r\n'
        b"@ping -n 30 127.0.0.1 > nul\r\n"
    )
    monkeypatch.setattr(learner_start.sys, "executable", str(hung))
    monkeypatch.setattr(learner_start, "CHILD_TIMEOUT_SECONDS", 2)
    data = tmp_path / "data"
    data.mkdir()
    start = learner_start.timed_start(data, tmp_path)
    assert start.window_ms == 321.0 and start.busy == 0.2
