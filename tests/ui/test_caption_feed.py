"""The caption feed (`ui.captions.CaptionFeed`), offscreen: caption
updates from any thread applied on the Qt thread, into the history, with
finished captions' exposures counted once - joins included, withdrawals
taken back, the learner's own speech counted apart. Made-up text and the
sample dictionary."""

import threading
from collections.abc import Mapping

import pytest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import FakeDictionaryFile, chinese_sample, english_sample
from tests.ui.fakes import chinese_tools, tools_for

from polyglotic_desktop.core.learning.exposures import in_learned_language
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.timing import CaptionId, WithdrawalReason
from polyglotic_desktop.ui.captions import UNCOUNTED_MOST, CaptionFeed
from polyglotic_desktop.ui.recorded_captions import (
    MIC,
    clause,
    finished,
    live,
    withdrawn,
)


def test_finished_captions_count_exposures_once_joins_included(
    qapp: QApplication,
) -> None:
    tools = chinese_tools()
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)
    computer = tools.lookup("电脑")[0].entry_id
    game = tools.lookup("打游戏")[0].entry_id
    feed.apply(live("a", clause("我的电脑")))
    assert tools.vocabulary.exposures(computer).heard == 0  # live: not counted
    feed.apply(finished("a", clause("我的电脑又卡了，")))
    feed.apply(live("b", clause("打游戏")))
    feed.apply(
        finished("a", clause("我的电脑又卡了，"), clause("打游戏。"), replaces=("b",))
    )
    assert tools.vocabulary.exposures(computer).heard == 1
    assert tools.vocabulary.exposures(game).heard == 1
    feed.apply(withdrawn("a", WithdrawalReason.MIC_BLEED))
    assert tools.vocabulary.exposures(computer).heard == 0
    feed.apply(finished("y", clause("电脑"), source=MIC))
    count = tools.vocabulary.exposures(computer)
    assert count.heard_by_you == 1 and count.heard == 0


def test_updates_from_another_thread_are_applied_on_the_qt_thread(
    qapp: QApplication,
) -> None:
    history = CaptionHistory(your_sources=[MIC])
    feed = CaptionFeed(history, None)
    thread = threading.Thread(
        target=feed.receive, args=(finished("a", clause("你好。")),)
    )
    thread.start()
    thread.join()
    assert history.version == 0  # not yet: queued for the Qt thread
    QApplication.processEvents()
    assert [c.original for c in history.captions] == ["你好。"]


def test_a_dropped_caption_ends_with_what_it_shows_everywhere_updates_go(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 557 (529's B3): a caption whose finished caption won't
    come stayed live for good - provisional in the caption windows, never in
    the transcript or Copy all. `end`, from any thread, ends it on the Qt
    thread as a finished update with what it shows, to the history and to
    every view keeping its own captions (`applied`) - and counts its words
    as heard, like any finished caption. A caption that isn't live is left."""
    tools = chinese_tools()
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)
    computer = tools.lookup("电脑")[0].entry_id
    applied: list[object] = []
    feed.applied.connect(applied.append)
    feed.apply(live("a", clause("我的电脑", "my computer")))
    thread = threading.Thread(target=lambda: feed.end(CaptionId("a")))
    thread.start()
    thread.join()
    qapp.processEvents()
    (caption,) = feed.history.captions
    assert not caption.live and caption.original == "我的电脑"
    ending = applied[-1]
    assert isinstance(ending, CaptionUpdate) and ending.kind is CaptionKind.FINISHED
    assert tools.vocabulary.exposures(computer).heard == 1
    feed.end(CaptionId("a"))  # finished now: nothing more
    feed.end(CaptionId("never shown"))
    qapp.processEvents()
    assert len(applied) == 2 and tools.vocabulary.exposures(computer).heard == 1


def test_a_caption_before_the_dictionary_is_ready_shows_now_and_counts_later(
    qapp: QApplication,
) -> None:
    """The word split's data is read on a thread at start (0.2-0.7 s); a
    caption that arrives first goes into the history at once, and its
    words are counted - and the windows told to mark it - once the data is
    read, never by reading it on the Qt thread (polyglotic-hq 136)."""
    tools = chinese_tools(ready=False)
    history = CaptionHistory(your_sources=[MIC])
    feed = CaptionFeed(history, tools)
    marked: list[bool] = []
    feed.dictionary_ready.connect(lambda: marked.append(True))
    computer = tools.lookup("电脑")[0].entry_id
    feed.apply(finished("a", clause("我的电脑又卡了，")))
    assert [c.original for c in history.captions] == ["我的电脑又卡了，"]
    assert tools.vocabulary.exposures(computer).heard == 0  # not read yet
    assert not tools.ready
    tools.prepare()
    for _ in range(200):  # the reading thread, then the queued signal
        QApplication.processEvents()
        if marked:
            break
        threading.Event().wait(0.01)
    assert tools.ready and marked == [True]
    assert tools.vocabulary.exposures(computer).heard == 1
    feed.apply(finished("b", clause("电脑")))  # ready: counted at once
    assert tools.vocabulary.exposures(computer).heard == 2


class _ReadFailsOnce(FakeDictionaryFile):
    """A dictionary file whose first read of the word split's data fails
    (a disk error, a locked file) and whose next one works."""

    def __init__(self, sample: FakeDictionaryFile) -> None:
        super().__init__(
            list(sample.by_id.values()), sample.forms, sample.meaning_words
        )
        self.failures = 1

    def frequency_ranks(self) -> Mapping[str, int]:
        if self.failures:
            self.failures -= 1
            raise OSError("the dictionary file could not be read")
        return super().frequency_ranks()


def test_a_failed_dictionary_read_still_counts_the_captions_waiting_on_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The start's read on its own thread fails: `dictionary_ready` is
    sent all the same, so the captions waiting on it are counted (the word
    split reads again, here on the Qt thread) instead of hiding for the
    session (polyglotic-hq 142, Low 2). The thread's error still reaches
    the crash handler."""
    failed: list[type[BaseException]] = []
    monkeypatch.setattr(
        threading, "excepthook", lambda args: failed.append(args.exc_type)
    )
    tools = tools_for(
        ChineseDictionary(_ReadFailsOnce(chinese_sample())), "hsk-2025", ready=False
    )
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)
    marked: list[bool] = []
    feed.dictionary_ready.connect(lambda: marked.append(True))
    computer = tools.lookup("电脑")[0].entry_id
    feed.apply(finished("a", clause("我的电脑又卡了，")))
    tools.prepare()
    # Two things to wait for, in no fixed order: the queued signal (the
    # reading thread's `finally`) and the error reaching the hook (after
    # the `finally`, on the reading thread). The Qt thread often handles
    # the signal first - waiting on `marked` alone failed 10 runs in 1000
    # (polyglotic-hq 197).
    for _ in range(200):
        QApplication.processEvents()
        if marked and failed:
            break
        threading.Event().wait(0.01)
    assert marked == [True]
    assert failed == [OSError]
    assert tools.vocabulary.exposures(computer).heard == 1


def test_captions_waiting_on_the_dictionary_are_capped(qapp: QApplication) -> None:
    """Until the word split's data is read, updates wait to be counted -
    at most `UNCOUNTED_MOST` of them, the oldest let go, so a read that
    never finishes can't grow the list for the whole session
    (polyglotic-hq 142, Low 2)."""
    tools = chinese_tools(ready=False)
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)
    for n in range(UNCOUNTED_MOST + 50):
        feed.apply(finished(f"c{n}", clause("电脑。")))
    assert not tools.ready
    assert len(feed._uncounted) == UNCOUNTED_MOST
    assert feed._uncounted[0][0].caption_id == "c50"  # the oldest let go


def test_only_captions_in_the_language_being_learned_count(
    qapp: QApplication,
) -> None:
    """Polyglotic-hq 174: the English dictionary claims 38 % of a Spanish
    line's words (de, el, que - here "he", Spanish for "I have"), so a
    learner of English who heard Spanish was counted English words heard,
    and the week's coverage with them. Only a caption in the language being
    learned counts now - exposures and coverage; a join that turns a
    caption into another language takes back what it counted."""
    tools = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), tools)
    he = tools.lookup("he")[0].entry_id
    vocabulary = tools.vocabulary
    feed.apply(finished("es", clause("Yo he comido."), language=Language("es")))
    assert vocabulary.exposures(he).heard == 0
    assert vocabulary.coverage().tokens == 0
    feed.apply(finished("en", clause("He left."), language=Language("en")))
    assert vocabulary.exposures(he).heard == 1
    assert vocabulary.coverage().tokens == 2  # he, left
    feed.apply(finished("en", clause("He left."), language=Language("es")))
    assert vocabulary.exposures(he).heard == 0 and vocabulary.coverage().tokens == 0


def test_the_language_being_learned_whatever_its_script() -> None:
    assert in_learned_language("zh", "zh") and in_learned_language("zh-hant", "zh")
    assert in_learned_language("en", "en") and in_learned_language("EN-gb", "en")
    assert not in_learned_language("yue", "zh")  # Cantonese isn't Mandarin
    assert not in_learned_language("es", "en")
    assert not in_learned_language(None, "en")  # unknown: not counted


def test_an_update_shown_leaves_a_line_in_the_caption_log_without_its_text(
    qapp: QApplication, caplog: pytest.LogCaptureFixture
) -> None:
    """polyglotic-hq 271: the caption log's last step - how long from the
    speech's start and end until the windows had the caption, and how long
    of that on the interface's thread."""
    import dataclasses
    import logging
    import time

    from polyglotic_desktop.core.listening.captions import SpeechTimes
    from polyglotic_desktop.core.listening.delays import CAPTION_LOG

    caplog.set_level(logging.INFO, logger=CAPTION_LOG)
    feed = CaptionFeed(CaptionHistory(your_sources=[MIC]), None)
    now = time.perf_counter()
    times = SpeechTimes(now - 3.0, now - 1.0, now - 0.5, now - 0.1)
    update = dataclasses.replace(finished("a", clause("你好。")), times=times)
    feed.apply(update)
    feed.apply(finished("b", clause("再见。")))  # not this session's speech: no line
    (shown,) = [r.getMessage() for r in caplog.records if r.name == CAPTION_LOG]
    assert shown.startswith("caption shown id=a kind=finished since_start_ms=3")
    assert "since_end_ms=1" in shown and "interface_ms=1" in shown
    assert "你好" not in shown
    feed.deleteLater()
