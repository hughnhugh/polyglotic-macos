"""Caption display rules, out of Qt: clause rows, the second-language
rule, which word links are drawn, the first rewritten row, and the
one-way layout. Made-up text only."""

from datetime import UTC, datetime

from polyglotic_desktop.core.listening.captions import Clause, Language, WordLink
from polyglotic_desktop.core.listening.display import (
    LIVE_TRAIL,
    MARK_WAIT_SEC,
    CaptionRow,
    DisplayOptions,
    LinkDetail,
    LinkedWords,
    ListeningMark,
    Placed,
    RowKind,
    WordLinks,
    caption_rows,
    clause_versions,
    first_rewritten,
    following_top,
    numbered_links,
    stack_height,
)
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

EN = Language("en")
ZH = Language("zh")
FR = Language("fr")
NOW = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
COLOURS = DisplayOptions(word_links=WordLinks.COLOURS)


def caption(*clauses: Clause, live: bool = False, language: str = "zh") -> Caption:
    return Caption(
        1,
        CaptionId("a"),
        SourceId("app"),
        False,
        live,
        clauses,
        Language(language),
        (Language(language),),
        NOW,
        NOW,
    )


def link(
    a: int, b: int, c: int, d: int, key: bool = True, sure: float = 0.9
) -> WordLink:
    return WordLink((a, b), (c, d), key, sure)


def texts(rows: list[CaptionRow]) -> list[tuple[str, RowKind]]:
    return [(r.text, r.kind) for r in rows]


def test_each_clause_shows_what_was_said_then_its_translation() -> None:
    rows = caption_rows(
        caption(Clause("你好，", {EN: "Hello,"}), Clause("今天。", {EN: "today."})),
        EN,
        None,
        DisplayOptions(),
    )
    assert texts(rows) == [
        ("你好，", RowKind.ORIGINAL),
        ("Hello,", RowKind.TRANSLATION),
        ("今天。", RowKind.ORIGINAL),
        ("today.", RowKind.TRANSLATION),
    ]
    assert [r.starts_clause for r in rows] == [True, False, True, False]
    assert [r.clause for r in rows] == [0, 0, 1, 1]
    assert [r.language for r in rows] == [ZH, EN, ZH, EN]


def test_hiding_originals_leaves_the_translation_but_never_a_clause_without_one() -> (
    None
):
    rows = caption_rows(
        caption(Clause("你好，", {EN: "Hello,"}), Clause("嗯")),
        EN,
        None,
        DisplayOptions(show_original=False),
    )
    assert texts(rows) == [("Hello,", RowKind.TRANSLATION), ("嗯", RowKind.ORIGINAL)]
    assert all(r.starts_clause for r in rows)


def test_a_clause_already_in_the_target_is_translated_into_the_second_language() -> (
    None
):
    said = caption(Clause("See you tomorrow.", {ZH: "明天见。"}), language="en")
    rows = caption_rows(said, EN, ZH, DisplayOptions())
    assert texts(rows) == [
        ("See you tomorrow.", RowKind.ORIGINAL),
        ("明天见。", RowKind.TRANSLATION),
    ]
    assert rows[1].language == ZH
    assert texts(caption_rows(said, EN, None, DisplayOptions())) == [
        ("See you tomorrow.", RowKind.ORIGINAL)
    ]
    assert texts(caption_rows(said, EN, EN, DisplayOptions())) == [
        ("See you tomorrow.", RowKind.ORIGINAL)
    ]


def test_a_second_language_line_kept_under_the_target_is_in_the_second() -> None:
    """The server keeps a caption's line in the target's second language
    under the target ({"en": "明天见。"}: English heard, English the target,
    Chinese its second - its `target_language`): the row is in Chinese, for
    its font and pinyin, and its links are the target's (polyglotic-hq 427:
    the user's preview 2, "translation lines still don't have
    pinyin/zhuyin" - the row said English)."""
    said = caption(
        Clause("See you tomorrow.", {EN: "明天见。"}, {EN: (link(4, 7, 0, 1),)}),
        language="en",
    )
    rows = caption_rows(said, EN, ZH, COLOURS)
    assert texts(rows) == [
        ("See you tomorrow.", RowKind.ORIGINAL),
        ("明天见。", RowKind.TRANSLATION),
    ]
    assert (rows[1].language, rows[1].target) == (ZH, EN)
    assert rows[0].links == (LinkedWords(4, 7, 0),)
    assert rows[1].links == (LinkedWords(0, 1, 0),)
    # a caption in another language: its line under the target is the target's
    heard = caption(Clause("明天见。", {EN: "See you tomorrow."}), language="zh")
    assert caption_rows(heard, EN, ZH, COLOURS)[1].language == EN
    # no second language: the target's own (a mixed line rewritten in it)
    assert caption_rows(said, EN, None, COLOURS)[1].language == EN


def test_a_live_captions_last_row_trails_off() -> None:
    rows = caption_rows(
        caption(Clause("你好，", {EN: "Hello,"}), Clause("今天"), live=True),
        EN,
        None,
        DisplayOptions(),
    )
    assert rows[-1].text == "今天" + LIVE_TRAIL
    assert rows[1].text == "Hello,"


def test_word_links_are_drawn_on_settled_clauses_only() -> None:
    first = Clause("你好，", {EN: "Hello,"}, {EN: (link(0, 2, 0, 5),)})
    last = Clause("今天", {EN: "today"}, {EN: (link(0, 2, 0, 5),)})
    rows = caption_rows(caption(first, last, live=True), EN, None, COLOURS)
    assert rows[0].links == (LinkedWords(0, 2, 0),)
    assert rows[1].links == (LinkedWords(0, 5, 0),)
    assert rows[2].links == () and rows[3].links == ()
    finished = caption_rows(caption(first, last), EN, None, COLOURS)
    assert finished[3].links == (LinkedWords(0, 5, 1),)  # the caption's second


def test_links_are_numbered_across_the_caption_not_from_0_in_each_clause() -> None:
    """Numbered from 0 in each clause, two clauses on one line of a
    caption that fills the width shared a colour: 我们 and 好不好 both
    orange (polyglotic-hq 340's fault 1)."""
    first = Clause(
        "我们周末去，", {EN: "We go at the weekend,"},
        {EN: (link(0, 2, 0, 2), link(2, 4, 13, 20))},
    )  # fmt: skip
    plain = Clause("嗯，", {EN: "mm,"})
    last = Clause("好不好？", {EN: "okay?"}, {EN: (link(0, 3, 0, 4),)})
    rows = caption_rows(caption(first, plain, last), EN, None, COLOURS)
    numbers = [[words.link for words in row.links] for row in rows]
    assert numbers == [[0, 1], [0, 1], [], [], [2], [2]]
    # a clause that comes later renumbers none before it
    shorter = caption_rows(caption(first, plain), EN, None, COLOURS)
    assert [row.links for row in shorter] == [row.links for row in rows[:4]]


def test_the_cap_is_still_each_clauses_own() -> None:
    both = (link(0, 1, 0, 1), link(1, 2, 2, 3))
    first = Clause("ab", {EN: "a b"}, {EN: both})
    last = Clause("cd", {EN: "c d"}, {EN: both})
    capped = DisplayOptions(word_links=WordLinks.COLOURS, max_links=1)
    rows = caption_rows(caption(first, last), EN, None, capped)
    assert [[words.link for words in row.links] for row in rows] == [[0], [0], [1], [1]]


def test_word_links_need_the_original_shown_and_links_on() -> None:
    clause = Clause("你好", {EN: "Hello"}, {EN: (link(0, 2, 0, 5),)})
    for options in (
        DisplayOptions(),
        DisplayOptions(show_original=False, word_links=WordLinks.ARROWS),
    ):
        assert all(
            r.links == () for r in caption_rows(caption(clause), EN, None, options)
        )


def test_second_language_rows_use_the_second_languages_links() -> None:
    clause = Clause("Good", {ZH: "好"}, {ZH: (link(0, 4, 0, 1),)})
    rows = caption_rows(caption(clause, language="en"), EN, ZH, COLOURS)
    assert rows[0].links == (LinkedWords(0, 4, 0),)
    assert rows[1].links == (LinkedWords(0, 1, 0),)


def test_one_link_per_counterpart_numbered_in_reading_order() -> None:
    # 佛印 ... 佛印 both say "Foyin"; 老师 says "teacher"
    links = [link(5, 7, 0, 5), link(0, 2, 0, 5), link(3, 5, 10, 17)]
    original, translation = numbered_links(links, LinkDetail.MOST)
    assert original == (
        LinkedWords(0, 2, 0),
        LinkedWords(3, 5, 1),
        LinkedWords(5, 7, 0),
    )
    assert translation == (LinkedWords(0, 5, 0), LinkedWords(10, 17, 1))


def test_key_words_leaves_out_minor_links() -> None:
    links = [link(0, 1, 0, 1, key=False), link(2, 4, 3, 8)]
    original, translation = numbered_links(links, LinkDetail.KEY)
    assert original == (LinkedWords(2, 4, 0),)
    assert translation == (LinkedWords(3, 8, 0),)


def test_a_cap_keeps_the_surest_key_links_first() -> None:
    links = [
        link(0, 1, 0, 1, key=False, sure=0.99),
        link(2, 3, 2, 3, sure=0.5),
        link(4, 5, 4, 5, sure=0.8),
    ]
    original, _ = numbered_links(links, LinkDetail.MOST, cap=2)
    assert [(w.start, w.link) for w in original] == [(2, 0), (4, 1)]


def test_links_outside_the_text_are_dropped() -> None:
    links = [link(0, 2, 0, 5), link(0, 9, 0, 5), link(1, 1, 0, 5)]
    original, _ = numbered_links(links, LinkDetail.MOST, None, 4, 5)
    assert original == (LinkedWords(0, 2, 0),)


def test_a_clauses_versions_for_a_lookup_context() -> None:
    shown = caption(Clause("你好", {EN: "Hello", FR: ""}))
    assert clause_versions(shown, 0) == {"zh": "你好", "en": "Hello"}


# -- the first rewritten row ---------------------------------------------------------------


def test_nothing_rewritten_when_the_last_row_only_grows() -> None:
    assert (
        first_rewritten(["你好，", "今天" + LIVE_TRAIL], ["你好，", "今天天气"]) is None
    )
    assert first_rewritten(["一"], ["一", "二"]) is None


def test_the_first_row_that_changed_is_where_the_crossfade_starts() -> None:
    assert first_rewritten(["一", "二", "三"], ["一", "贰", "三"]) == 1
    # an earlier row only growing is a rewrite: it isn't the last
    assert first_rewritten(["一", "二", "三"], ["一二", "二", "三"]) == 0


def test_rows_gone_from_the_end_crossfade_from_there() -> None:
    assert first_rewritten(["一", "二", "三"], ["一", "二"]) == 2


# -- the one-way layout --------------------------------------------------------------------

GAP = 10.0


def placed(*heights: float, bottom: float = 300.0) -> list[Placed]:
    """Captions stacked to end at `bottom`."""
    top = bottom - stack_height([Placed(h, None) for h in heights], GAP)
    found = []
    for height in heights:
        found.append(Placed(height, top))
        top += height + GAP
    return found


def test_arriving_captions_settle_at_the_bottom() -> None:
    items = [Placed(40, None), Placed(60, None)]
    assert following_top(items, 300, GAP, False, 0, reanchor=True) == 300 - 110
    assert following_top([], 300, GAP, False, 0, reanchor=False) == 300


def test_a_shrinking_caption_moves_none_down_and_leaves_space_at_the_bottom() -> None:
    a, b, c = placed(40, 60, 50)
    shrunk = [a, Placed(30, b.top), Placed(50, c.top)]
    top = following_top(shrunk, 300, GAP, False, 0, reanchor=False)
    assert top == a.top  # the one above stays; the one below moves up
    assert top + stack_height(shrunk, GAP) < 300


def test_growth_uses_the_space_left_at_the_bottom_first() -> None:
    a, b = placed(40, 60, bottom=280)  # 20px free below
    grown = [a, Placed(75, b.top)]
    assert following_top(grown, 300, GAP, False, 0, reanchor=False) == a.top
    pushed = [a, Placed(90, b.top)]
    assert following_top(pushed, 300, GAP, False, 0, reanchor=False) == 300 - 140


def test_a_live_caption_that_has_to_push_leaves_headroom() -> None:
    a, b = placed(40, 60)
    grown = [a, Placed(90, b.top)]
    bottom = 300 - stack_height(grown, GAP)
    assert following_top(grown, 300, GAP, True, 64, reanchor=False) == bottom - 64
    # with room to spare it doesn't push at all
    assert following_top([a, b], 300, GAP, True, 64, reanchor=False) == a.top


def test_a_new_caption_pushes_the_stack_up() -> None:
    a, b = placed(40, 60)
    items = [a, b, Placed(50, None)]
    assert following_top(items, 300, GAP, False, 0, reanchor=False) == 300 - 170


# -- Quick preview's line and the listening mark (project 064) -----------------


def test_quick_previews_line_shows_its_translation_without_word_links() -> None:
    """With the preview on, a live caption is provisional: what was said,
    with its translation under it, trailing off (polyglotic-hq 268,
    DECISIONS.md #101) - but no word links, even on a settled clause
    (049's wireframes, 3.2); its finished caption is shown as any other."""
    preview = DisplayOptions(word_links=WordLinks.COLOURS, preview=True)
    said = Clause(
        "这个游戏的画面", {EN: "This game's graphics"}, {EN: (link(0, 2, 0, 4),)}
    )
    rows = caption_rows(caption(said, live=True), EN, None, preview)
    assert texts(rows) == [
        ("这个游戏的画面", RowKind.ORIGINAL),
        ("This game's graphics" + LIVE_TRAIL, RowKind.TRANSLATION),
    ]
    two = caption_rows(caption(said, said, live=True), EN, None, preview)
    assert [r.links for r in two] == [()] * 4
    # before its translation arrives (or none asked for): what was said
    bare = Clause("这个游戏的画面")
    assert texts(caption_rows(caption(bare, live=True), EN, None, preview)) == [
        ("这个游戏的画面" + LIVE_TRAIL, RowKind.ORIGINAL)
    ]
    hidden = DisplayOptions(show_original=False, preview=True)
    assert texts(caption_rows(caption(said, live=True), EN, None, hidden)) == [
        ("This game's graphics" + LIVE_TRAIL, RowKind.TRANSLATION)
    ]
    done = caption_rows(caption(said), EN, None, preview)
    assert [r.kind for r in done] == [RowKind.ORIGINAL, RowKind.TRANSLATION]
    live_updates = caption_rows(caption(said, live=True), EN, None, DisplayOptions())
    assert [r.kind for r in live_updates] == [RowKind.ORIGINAL, RowKind.TRANSLATION]


APP_ID, MIC_ID = SourceId("app"), SourceId("mic")


def test_the_listening_mark_shows_from_speech_until_its_caption() -> None:
    mark = ListeningMark()
    assert not mark.showing(0.0)
    mark.heard({APP_ID}, 1.0)
    assert mark.showing(1.0)
    mark.heard(set(), 4.0)  # the speech stopped (its pause passed)
    assert mark.showing(4.5)  # its caption is on its way
    mark.captioned(MIC_ID, 4.6)  # another source's: not this one
    assert mark.showing(4.6)
    mark.captioned(APP_ID, 4.8)
    assert not mark.showing(4.8)


def test_the_listening_mark_stays_through_a_breath_cut() -> None:
    """A caption arriving while the speech goes on (a breath cut's first
    piece) doesn't hide the mark: more is being heard."""
    mark = ListeningMark()
    mark.heard({APP_ID}, 1.0)
    mark.captioned(APP_ID, 5.5)
    mark.heard({APP_ID}, 5.6)
    assert mark.showing(5.6)
    mark.heard(set(), 8.0)
    assert mark.showing(8.1)
    mark.captioned(APP_ID, 8.6)
    assert not mark.showing(8.6)


def test_the_listening_mark_gives_up_when_no_caption_comes() -> None:
    """Too short to send, mic bleed, or lost: gone MARK_WAIT_SEC after the
    speech stopped."""
    mark = ListeningMark()
    mark.heard({MIC_ID}, 1.0)
    mark.heard(set(), 2.0)
    assert mark.showing(2.0 + MARK_WAIT_SEC)
    assert not mark.showing(2.1 + MARK_WAIT_SEC)


def test_a_caption_back_before_the_stop_was_seen_hides_the_mark_at_once() -> None:
    """The caption can arrive between two looks at who's speaking: the
    speech stopped and was answered before the mark noticed - it goes
    when the stop is seen, not MARK_WAIT_SEC later."""
    mark = ListeningMark()
    mark.heard({APP_ID}, 1.0)
    mark.heard({APP_ID}, 3.0)
    mark.captioned(APP_ID, 3.05)
    mark.heard(set(), 3.1)
    assert not mark.showing(3.1)


def test_speech_under_way_is_speaking_until_it_is_seen_to_stop() -> None:
    """A caption window's arrival slides quicker while speech goes on
    (polyglotic-hq 267): speaking from the first word until the speech
    stops, through a caption that arrives meanwhile (a breath cut)."""
    mark = ListeningMark()
    assert not mark.speaking()
    mark.heard({APP_ID}, 1.0)
    assert mark.speaking()
    mark.captioned(APP_ID, 2.0)  # a breath cut's first piece: still talking
    mark.heard({APP_ID}, 2.5)
    assert mark.speaking()
    mark.heard(set(), 3.0)  # stopped: its caption on its way
    assert mark.showing(3.0) and not mark.speaking()
