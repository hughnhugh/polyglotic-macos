"""Caption history: live updates replaced in place, finished captions,
joins, withdrawals, stable keys, late updates, the 300 kept, never blank,
settled text. Made-up text only."""

from datetime import UTC, datetime, timedelta

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.history import (
    CaptionHistory,
    join_text,
    keep_translations,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, WithdrawalReason

EN = Language("en")
APP = SourceId("app")
MIC = SourceId("mic")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def clause(original: str, english: str | None = None) -> Clause:
    return Clause(original, {EN: english} if english else {})


def update(
    caption_id: str,
    kind: CaptionKind,
    *clauses: Clause,
    source: SourceId = APP,
    replaces: tuple[str, ...] = (),
) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption_id),
        source,
        kind,
        clauses,
        Language("zh"),
        (Language("zh"),),
        tuple(CaptionId(r) for r in replaces),
    )


def live(caption_id: str, *clauses: Clause, **kw: object) -> CaptionUpdate:
    return update(caption_id, CaptionKind.LIVE, *clauses, **kw)  # type: ignore[arg-type]


def finished(caption_id: str, *clauses: Clause, **kw: object) -> CaptionUpdate:
    return update(caption_id, CaptionKind.FINISHED, *clauses, **kw)  # type: ignore[arg-type]


def withdrawn(caption_id: str) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption_id),
        APP,
        CaptionKind.WITHDRAWN,
        reason=WithdrawalReason.MIC_BLEED,
    )


def originals(history: CaptionHistory) -> list[str]:
    return [c.original for c in history.captions]


def test_live_updates_replace_their_caption_in_place_until_it_finishes() -> None:
    history = CaptionHistory()
    history.apply(live("a", clause("你好")))
    history.apply(live("b", clause("我们")))
    first_key = history.captions[0].key
    history.apply(live("a", clause("你好，今天")))
    history.apply(finished("a", clause("你好，今天天气很好。")))
    assert originals(history) == ["你好，今天天气很好。", "我们"]
    caption = history.captions[0]
    assert caption.key == first_key and not caption.live
    assert history.captions[1].live


def test_every_change_bumps_the_version() -> None:
    history = CaptionHistory()
    history.apply(live("a", clause("你好")))
    history.apply(finished("a", clause("你好。")))
    history.apply(withdrawn("a"))
    assert history.version == 3
    history.apply(withdrawn("nothing"))
    assert history.version == 3


def test_a_joined_caption_takes_the_place_and_key_of_the_earliest() -> None:
    clock = Clock()
    history = CaptionHistory(clock=clock)
    history.apply(finished("a", clause("我去了超市。")))
    started = history.captions[0].started_at
    key = history.captions[0].key
    clock.advance(1.5)
    history.apply(live("b", clause("买了水果")))
    history.apply(live("other", clause("嗯")))
    clock.advance(1)
    joined = history.apply(
        finished("a", clause("我去了超市，"), clause("买了水果。"), replaces=("b",))
    )
    assert originals(history) == ["我去了超市，买了水果。", "嗯"]
    assert joined is not None and joined.key == key and joined.started_at == started
    assert joined.updated_at == clock.now


def test_a_withdrawn_caption_goes_and_late_updates_dont_bring_it_back() -> None:
    history = CaptionHistory()
    history.apply(live("a", clause("Thanks for watching")))
    history.apply(withdrawn("a"))
    assert history.captions == ()
    assert history.apply(live("a", clause("Thanks for watching!"))) is None
    assert history.apply(finished("a", clause("Thanks for watching!"))) is None
    assert history.captions == ()


def test_a_replaced_caption_ignores_its_late_updates() -> None:
    history = CaptionHistory()
    history.apply(finished("a", clause("一")))
    history.apply(live("b", clause("二")))
    history.apply(finished("a", clause("一，"), clause("二。"), replaces=("b",)))
    assert history.apply(live("b", clause("二三"))) is None
    assert originals(history) == ["一，二。"]


def test_a_late_live_update_never_undoes_a_finished_caption() -> None:
    history = CaptionHistory()
    history.apply(finished("a", clause("你好。")))
    assert history.apply(live("a", clause("你"))) is None
    assert originals(history) == ["你好。"] and not history.captions[0].live


def test_a_caption_can_be_finished_again_by_a_join_the_latest_wins() -> None:
    history = CaptionHistory()
    history.apply(finished("a", clause("一。")))
    history.apply(finished("a", clause("一，二。")))
    assert originals(history) == ["一，二。"]


def test_captions_from_your_mic_are_by_you() -> None:
    history = CaptionHistory(your_sources=[MIC])
    history.apply(live("a", clause("hello"), source=MIC))
    history.apply(live("b", clause("你好")))
    assert [c.by_you for c in history.captions] == [True, False]
    assert history.is_yours(MIC) and not history.is_yours(APP)


def test_only_the_last_captions_are_kept() -> None:
    history = CaptionHistory(max_captions=3)
    for n in range(5):
        history.apply(finished(str(n), clause(f"第{n}")))
    assert originals(history) == ["第2", "第3", "第4"]


def test_finished_captions_dropped_off_the_front_are_kept_as_text_if_asked() -> None:
    """polyglotic-hq 137: a transcript lists its last 1,000 lines, but Copy
    all and Save write out the whole session - the captions that dropped
    off, kept as text (no word links: only showing them needs those)."""
    linked = Clause("第0", {EN: "zero"}, {EN: (WordLink((0, 2), (0, 4), True, 0.9),)})
    history = CaptionHistory(max_captions=2, keep_earlier=3)
    history.apply(finished("0", linked))
    history.apply(live("x", clause("还在说")))  # live: never kept as text
    for n in range(1, 5):
        history.apply(finished(str(n), clause(f"第{n}")))
    assert originals(history) == ["第3", "第4"]
    assert [c.original for c in history.earlier] == ["第0", "第1", "第2"]
    assert history.earlier[0].translation(EN) == "zero"
    assert history.earlier[0].clauses[0].links == {}
    history.apply(finished("5", clause("第5")))
    assert [c.original for c in history.earlier] == ["第1", "第2", "第3"]  # at most 3
    assert not CaptionHistory(max_captions=2).earlier.maxlen  # not asked: none kept


def test_keys_are_never_reused() -> None:
    history = CaptionHistory()
    history.apply(live("a", clause("一")))
    history.apply(withdrawn("a"))
    history.apply(live("b", clause("二")))
    history.apply(live("c", clause("三")))
    keys = [c.key for c in history.captions]
    assert len(set(keys)) == 2 and 1 not in keys


# -- never blank ------------------------------------------------------------------------


def test_a_live_update_keeps_the_previous_translation_until_a_new_one_arrives() -> None:
    history = CaptionHistory()
    history.apply(live("a", clause("你好", "Hello")))
    history.apply(live("a", clause("你好，今天"), clause("天气")))
    first = history.captions[0].clauses[0]
    assert first.original == "你好，今天" and first.translations[EN] == "Hello"
    assert EN not in history.captions[0].clauses[1].translations
    history.apply(live("a", clause("你好，今天", "Hello, today")))
    assert history.captions[0].clauses[0].translations[EN] == "Hello, today"


def test_a_finished_caption_keeps_a_translation_only_where_its_clause_is_unchanged() -> (
    None
):
    history = CaptionHistory()
    history.apply(live("a", clause("你好，", "Hello,"), clause("今天", "today")))
    history.apply(finished("a", clause("你好，"), clause("今天天气很好。")))
    kept, rewritten = history.captions[0].clauses
    assert kept.translations[EN] == "Hello,"
    assert EN not in rewritten.translations


def test_a_kept_translation_keeps_its_links_only_if_the_original_is_unchanged() -> None:
    link = WordLink((0, 2), (0, 5), True, 0.9)
    before = (Clause("你好", {EN: "Hello"}, {EN: (link,)}),)
    same = keep_translations(before, (Clause("你好"),), live=True)
    assert same[0].links[EN] == (link,)
    grown = keep_translations(before, (Clause("你好吗"),), live=True)
    assert grown[0].translations[EN] == "Hello" and EN not in grown[0].links


def test_a_new_translation_replaces_the_kept_one() -> None:
    before = (clause("你好", "Hello"),)
    after = keep_translations(before, (clause("你好", "Hi"),), live=True)
    assert after[0].translations[EN] == "Hi"


def test_text_joins_with_spaces_except_next_to_chinese() -> None:
    assert join_text(["Hello,", "how are you?"]) == "Hello, how are you?"
    assert join_text(["你好，", "今天"]) == "你好，今天"
    assert join_text(["我用", "Python", "写的"]) == "我用Python写的"
    assert join_text([" ", "a"]) == "a"


def test_a_caption_reads_as_one_line_in_any_language() -> None:
    history = CaptionHistory()
    caption = history.apply(
        finished("a", clause("你好，", "Hello,"), clause("今天。", "today."))
    )
    assert caption is not None
    assert caption.original == "你好，今天。"
    assert caption.translation(EN) == "Hello, today."
    assert caption.translation(Language("fr")) == "你好，今天。"


# -- settled text (polyglotic-hq 296, decision 0088) ----------------------------


def test_words_shown_for_three_seconds_are_never_rewritten() -> None:
    """The user, 2026-11-13: "We don't need to rewrite words spoken 3
    seconds ago right?" A later hearing rewrote all of a caption - the
    words read seconds ago among them. Now what has stood 3s stays; only
    what comes after it is taken."""
    clock = Clock()
    history = CaptionHistory(clock=clock)
    history.apply(live("a", clause("We walked to this", "我们走到这")))
    clock.advance(1.5)
    # 1.5s on, nothing has stood long enough: the update rewrites it
    history.apply(live("a", clause("We went to this door", "我们去了这扇门")))
    assert originals(history) == ["We went to this door"]
    clock.advance(1.5)
    history.apply(live("a", clause("We went to this door and", "我们去了这扇门然后")))
    clock.advance(1.6)
    # "We went to this" has stood 3.1s, "door" 3.1s, "and" 1.6s
    history.apply(
        finished(
            "a", clause("We want to the store and bought milk.", "我们去商店买了牛奶。")
        )
    )
    caption = history.captions[0]
    assert caption.original == "We went to this door and bought milk."
    assert not caption.live
    assert caption.translation(EN) == "我们去商店买了牛奶。"


def test_a_finished_caption_still_rewrites_what_is_new() -> None:
    clock = Clock()
    history = CaptionHistory(clock=clock)
    history.apply(live("a", clause("我去了超时")))
    clock.advance(2.0)
    history.apply(finished("a", clause("我去了超市。")))
    assert originals(history) == ["我去了超市。"]


def test_how_long_shown_words_may_change_is_the_learners_choice() -> None:
    """The user, 2026-11-14: "changing lines up to 3 seconds in live
    updates is a bit too long anyway, make this a configurable setting.
    After 0s - 3seconds" (polyglotic-hq 309). At 1s, words shown 1.5s ago
    stay - at the 3s it was fixed at, the update rewrote them."""
    for seconds, kept in ((3.0, "We went"), (1.0, "We walked")):
        clock = Clock()
        history = CaptionHistory(clock=clock)
        history.set_settle_after(seconds)
        history.apply(live("a", clause("We walked to this")))
        clock.advance(1.5)
        history.apply(live("a", clause("We went to this door")))
        assert originals(history)[0].startswith(kept), seconds


def test_at_no_seconds_a_shown_word_never_changes() -> None:
    """0: text never changes once shown - an update only adds to it. The
    last word of a live caption may be half said, so it alone is still
    the update's ("th" becomes "this")."""
    clock = Clock()
    history = CaptionHistory(clock=clock)
    history.set_settle_after(0.0)
    history.apply(live("a", clause("We walked to th")))
    history.apply(live("a", clause("We went to this door and")))
    assert originals(history) == ["We walked to this door and"]
    clock.advance(0.2)
    history.apply(finished("a", clause("He wants to the store and bought milk.")))
    assert originals(history) == ["We walked to this door and bought milk."]


def test_the_time_to_settle_stays_between_none_and_three_seconds() -> None:
    history = CaptionHistory()
    assert history.settle_after == 3.0  # as it was (decision 0088)
    history.set_settle_after(-1)
    assert history.settle_after == 0.0
    history.set_settle_after(10)
    assert history.settle_after == 3.0


def test_clauses_above_a_captions_last_two_settle_at_once() -> None:
    """ "After 1-2 lines, lines should settle": only a caption's last two
    clauses may still be rewritten, however new the ones above them."""
    history = CaptionHistory()
    history.apply(
        live(
            "a",
            clause("一二三，", "one two three,"),
            clause("四五六，", "four five six,"),
            clause("七八", "seven eight"),
        )
    )
    history.apply(
        finished(
            "a",
            clause("壹贰叁，", "ONE TWO THREE,"),
            clause("肆伍陆，", "FOUR FIVE SIX,"),
            clause("七八九。", "seven eight nine."),
        )
    )
    caption = history.captions[0]
    assert [c.original for c in caption.clauses] == ["一二三，", "肆伍陆，", "七八九。"]
    assert caption.clauses[0].translations[EN] == "one two three,"
    assert caption.clauses[1].translations[EN] == "FOUR FIVE SIX,"


def test_settled_words_keep_the_links_of_the_words_the_update_shares() -> None:
    """Shown for 3 s, a caption's words stay (decision 0088) - and when the
    finished caption heard one of them differently, the row had no word
    links at all (polyglotic-hq 340: 0 of 3). The links of the words both
    have are the row's; the changed word's goes."""
    clock = Clock()
    history = CaptionHistory(clock=clock)
    said = "Let's go play games together this weekend"
    history.apply(live("a", clause("我们周末一起去打游戏吧", said)))
    clock.advance(4)
    heard = "我们周末一块去打游戏吧，"
    links = tuple(
        WordLink(
            (heard.index(word), heard.index(word) + len(word)),
            (said.index(meant), said.index(meant) + len(meant)),
            True,
            0.9,
        )
        for word, meant in (
            ("周末", "weekend"),
            ("一块", "together"),
            ("打游戏", "play games"),
        )
    )
    history.apply(
        finished(
            "a",
            Clause(heard, {EN: said + ","}, {EN: links}),
            clause("好不好？", "okay?"),
        )
    )
    first = history.captions[0].clauses[0]
    assert first.original.startswith("我们周末一起去打游戏吧")  # the words first shown
    assert first.translations[EN] == said + ","
    kept = {
        (first.original[a:b], first.translations[EN][c:d])
        for (a, b), (c, d) in ((k.original, k.translation) for k in first.links[EN])
    }
    assert kept == {("周末", "weekend"), ("打游戏", "play games")}


def test_a_join_keeps_what_both_captions_had_settled() -> None:
    """A joined caption hears the earlier fragment and the speech after it
    again: the fragment's settled words stay, and the live caption's that
    it replaces."""
    clock = Clock()
    history = CaptionHistory(clock=clock)
    history.apply(finished("a", clause("我去了超时。", "I went overtime.")))
    clock.advance(1.0)
    history.apply(live("b", clause("买了一些", "bought some")))
    clock.advance(3.5)
    history.apply(
        finished(
            "a",
            clause("我去了超市，", "I went to the supermarket,"),
            clause("买了一些水果。", "and bought some fruit."),
            replaces=("b",),
        )
    )
    (caption,) = history.captions
    assert [c.original for c in caption.clauses] == ["我去了超时。", "买了一些水果。"]
    assert caption.clauses[0].translations[EN] == "I went overtime."
    assert caption.clauses[1].translations[EN] == "and bought some fruit."


def test_what_settled_is_forgotten_with_its_caption() -> None:
    clock = Clock()
    history = CaptionHistory(clock=clock, max_captions=2)
    history.apply(live("a", clause("你好")))
    history.apply(withdrawn("a"))
    for n in range(4):
        history.apply(finished(f"c{n}", clause("好。")))
    history.apply(live("b", clause("我们")))
    history.apply(finished("d", clause("好的。"), replaces=("b",)))
    assert set(history._stable) == {c.caption_id for c in history.captions}
    assert set(history._heard) == set(history._stable)


# -- how long a history keeps its captions (polyglotic-hq 334) -----------------------


def test_with_a_time_limit_captions_older_than_it_drop_off_the_front() -> None:
    """A transcript's "the last 3 hours": a caption that first appeared
    longer ago than the limit goes at the next update - into `earlier`,
    as text, so Copy all and Save still have it."""
    clock = Clock()
    history = CaptionHistory(
        clock=clock, max_captions=1_000, keep_for=3600, keep_earlier=10
    )
    history.apply(finished("a", clause("一。")))
    clock.advance(1800)
    history.apply(finished("b", clause("二。")))
    clock.advance(1800)  # "a" is exactly an hour old: kept
    history.apply(finished("c", clause("三。")))
    assert originals(history) == ["一。", "二。", "三。"]
    clock.advance(1)
    history.apply(finished("d", clause("四。")))
    assert originals(history) == ["二。", "三。", "四。"]
    assert [c.original for c in history.earlier] == ["一。"]


def test_the_count_still_holds_under_a_time_limit() -> None:
    clock = Clock()
    history = CaptionHistory(clock=clock, max_captions=3, keep_for=3600)
    for n in range(5):
        history.apply(finished(str(n), clause(f"第{n}")))
    assert originals(history) == ["第2", "第3", "第4"]


def test_a_joined_caption_keeps_its_place_under_a_time_limit() -> None:
    """A join takes the earliest caption's place and when it first
    appeared: under the time limit it goes when that one would have."""
    clock = Clock()
    history = CaptionHistory(clock=clock, keep_for=60)
    history.apply(finished("a", clause("我去了超市。")))
    clock.advance(30)
    history.apply(live("b", clause("买了水果")))
    history.apply(
        finished("a", clause("我去了超市，"), clause("买了水果。"), replaces=("b",))
    )
    assert originals(history) == ["我去了超市。买了水果。"]  # what stood, kept
    clock.advance(31)
    history.apply(finished("c", clause("好。")))
    assert originals(history) == ["好。"]


def test_lowered_limits_drop_captions_at_once_and_raised_ones_take_them_back() -> None:
    """The learner's choice changes what's kept now, not only from the next
    caption: lowered, the oldest go into `earlier`; raised, they come back
    from it, as text (no word links), in their places and with their keys."""
    linked = Clause("第0", {EN: "zero"}, {EN: (WordLink((0, 2), (0, 4), True, 0.9),)})
    clock = Clock()
    history = CaptionHistory(clock=clock, max_captions=10, keep_earlier=10)
    history.apply(finished("0", linked))
    for n in range(1, 5):
        clock.advance(600)
        history.apply(finished(str(n), clause(f"第{n}")))
    keys = [c.key for c in history.captions]
    version = history.version
    history.set_limits(2)
    assert originals(history) == ["第3", "第4"]
    assert [c.original for c in history.earlier] == ["第0", "第1", "第2"]
    assert history.version == version + 1
    history.set_limits(10, keep_for=1500)  # the last 25 minutes: 第2 on
    assert originals(history) == ["第2", "第3", "第4"]
    assert [c.original for c in history.earlier] == ["第0", "第1"]
    history.set_limits(10)
    assert originals(history) == ["第0", "第1", "第2", "第3", "第4"]
    assert [c.key for c in history.captions] == keys
    assert history.captions[0].clauses[0].links == {}  # back as text
    assert not history.earlier
    version = history.version
    history.set_limits(10)
    assert history.version == version  # unchanged: nothing to redraw
    assert history.limits == (10, None)


def test_what_comes_back_is_never_more_than_the_limit() -> None:
    history = CaptionHistory(max_captions=2, keep_earlier=10)
    for n in range(6):
        history.apply(finished(str(n), clause(f"第{n}")))
    history.set_limits(4)
    assert originals(history) == ["第2", "第3", "第4", "第5"]
    assert [c.original for c in history.earlier] == ["第0", "第1"]


def test_settled_text_holds_past_the_old_limit_of_300() -> None:
    """With a long history kept, the rules for settled text work as they
    did within the 300: a caption 3,000 captions in keeps the words it has
    shown 3s, and a join reaches a caption past the old limit's front -
    keeping what both captions it joins had settled."""
    clock = Clock()
    history = CaptionHistory(clock=clock, max_captions=4_000, keep_for=3 * 3600)
    for n in range(3_000):
        clock.advance(3)
        history.apply(finished(f"c{n}", clause(f"第{n}句。")))
    clock.advance(1)
    history.apply(live("a", clause("We went to this door and", "我们去了这扇门然后")))
    clock.advance(3.1)
    history.apply(finished("a", clause("We want to the store and bought milk.")))
    assert history.captions[-1].original == "We went to this door and bought milk."
    assert len(history.captions) == 3_001
    old = history.captions[-400]  # older than the 300 kept before
    clock.advance(1)
    history.apply(
        finished(
            str(old.caption_id),
            clause(old.original),
            clause("又一句。"),
            replaces=(str(history.captions[-399].caption_id),),
        )
    )
    assert len(history.captions) == 3_000
    joined = history.captions[-399]
    assert joined.original == "第2601句。第2602句。"  # both had stood: kept
    assert joined.key == old.key
