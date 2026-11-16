"""A looked-up word's counterpart (polyglotic-hq 328, `display.counterpart`):
the words of the other row of its clause that the clause's word links join
it to - one word, several, none, a paraphrase, right-to-left text, a link
to punctuation; every link whether drawn or not; a word in the
translation row; finished captions only. Made-up text only."""

from datetime import UTC, datetime

from polyglotic_desktop.core.listening.captions import Clause, Language, WordLink
from polyglotic_desktop.core.listening.display import (
    COUNTERPART_GAP,
    Counterpart,
    DisplayOptions,
    LinkDetail,
    RowKind,
    WordLinks,
    caption_rows,
    counterpart,
)
from polyglotic_desktop.core.listening.history import Caption
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId

EN, ZH, VI, AR = Language("en"), Language("zh"), Language("vi"), Language("ar")
NOW = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
COLOURS = DisplayOptions(word_links=WordLinks.COLOURS)


def link(
    original: str, said: str, translation: str, meant: str, key: bool = True
) -> WordLink:
    """A link between `said`'s first place in `original` and `meant`'s in
    `translation`."""
    a, c = original.index(said), translation.index(meant)
    return WordLink((a, a + len(said)), (c, c + len(meant)), key, 0.9)


def clause(
    original: str,
    translation: str,
    pairs: tuple[tuple[str, str], ...],
    into: Language = EN,
    minor: tuple[tuple[str, str], ...] = (),
) -> Clause:
    links = tuple(link(original, s, translation, m) for s, m in pairs) + tuple(
        link(original, s, translation, m, key=False) for s, m in minor
    )
    return Clause(original, {into: translation}, {into: links})


def caption(*clauses: Clause, language: str = "zh", live: bool = False) -> Caption:
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


def look_up(
    shown: Caption,
    word: str,
    target: Language = EN,
    row: int = 0,
    options: DisplayOptions = COLOURS,
    second: Language | None = None,
) -> Counterpart | None:
    """`word` looked up in row `row` of `shown` as a window into `target`
    shows it."""
    rows = caption_rows(shown, target, second, options)
    at = rows[row].text.index(word)
    return counterpart(shown, rows, row, (at, at + len(word)))


COMPUTER = clause(
    "我的电脑又卡了，",
    "My computer froze again,",
    (("电脑", "computer"), ("卡", "froze"), ("又", "again")),
)


def test_one_word() -> None:
    assert look_up(caption(COMPUTER), "电脑") == Counterpart("computer", EN)
    bank = clause(
        "I went to the bank yesterday.",
        "Hôm qua tôi đã đến ngân hàng.",
        (("bank", "ngân hàng"), ("went", "đã đến")),
        into=VI,
    )
    found = look_up(caption(bank, language="en"), "bank", target=VI)
    assert found == Counterpart("ngân hàng", VI)


def test_several_words_in_the_translations_order() -> None:
    """A word linked to two places: both, in the translation's order -
    joined where only spaces lie between, else with a gap."""
    turn_off = Clause(
        "把灯关掉",
        {EN: "Turn the light off"},
        {
            EN: (
                WordLink((2, 4), (15, 18), True, 0.9),  # 关掉 -> off
                WordLink((2, 4), (0, 4), True, 0.9),  # 关掉 -> Turn
                WordLink((1, 2), (9, 14), True, 0.9),  # 灯 -> light
            )
        },
    )
    found = look_up(caption(turn_off), "关掉")
    assert found is not None and found.words == f"Turn{COUNTERPART_GAP}off"
    play = Clause(
        "打游戏",
        {EN: "play games"},
        {
            EN: (
                WordLink((0, 3), (5, 10), True, 0.9),  # games
                WordLink((0, 3), (0, 4), True, 0.9),  # play
            )
        },
    )
    found = look_up(caption(play), "打游戏")
    assert found is not None and found.words == "play games"


def test_a_phrase_dragged_across_takes_every_word_it_holds() -> None:
    found = look_up(caption(COMPUTER), "电脑又卡")
    assert found is not None
    assert found.words == "computer froze again"


def test_none_no_link_no_line() -> None:
    """A particle, a word the translation dropped: no counterpart at all -
    never an empty one."""
    assert look_up(caption(COMPUTER), "了") is None
    assert look_up(caption(COMPUTER), "我的") is None


def test_a_paraphrase_is_its_whole_span() -> None:
    cornered = clause(
        "他已经走投无路了。",
        "He had nowhere left to turn.",
        (("走投无路", "had nowhere left to turn"),),
    )
    found = look_up(caption(cornered), "走投无路")
    assert found == Counterpart("had nowhere left to turn", EN)


def test_right_to_left_text_keeps_its_own_order() -> None:
    """Arabic both ways: the pieces in the text's own (logical) order -
    the card's layout draws them right to left."""
    into_arabic = clause(
        "我很喜欢这本书",
        "أنا أحب هذا الكتاب كثيرا",
        (("书", "الكتاب"), ("喜欢", "أحب")),
        into=AR,
    )
    assert look_up(caption(into_arabic), "书", target=AR) == Counterpart("الكتاب", AR)
    two = Clause(
        "我很喜欢这本书",
        {AR: "أنا أحب هذا الكتاب كثيرا"},
        {
            AR: (
                WordLink((1, 4), (19, 24), True, 0.9),  # 很喜欢 -> كثيرا
                WordLink((1, 4), (4, 7), True, 0.9),  # 很喜欢 -> أحب
            )
        },
    )
    found = look_up(caption(two), "很喜欢", target=AR)
    assert found is not None and found.words == f"أحب{COUNTERPART_GAP}كثيرا"
    from_arabic = clause("أنا أحب الكتب", "I love books", (("الكتب", "books"),))
    found = look_up(caption(from_arabic, language="ar"), "الكتب")
    assert found == Counterpart("books", EN)


def test_a_link_to_punctuation_says_nothing_and_ends_are_trimmed() -> None:
    commas = Clause(
        "我的电脑，又卡了",
        {EN: "My computer, again, froze"},
        {
            EN: (
                WordLink((4, 5), (11, 12), False, 0.4),  # ， -> ,
                WordLink((2, 4), (3, 12), True, 0.9),  # 电脑 -> "computer,"
                WordLink((5, 6), (12, 19), True, 0.9),  # 又 -> " again,"
            )
        },
    )
    assert look_up(caption(commas), "，") is None
    assert look_up(caption(commas), "电脑") == Counterpart("computer", EN)
    assert look_up(caption(commas), "又") == Counterpart("again", EN)


def test_every_link_counts_drawn_or_not() -> None:
    """Links off, key words only, a cap: what's drawn changes, not the
    counterpart (323 thins the drawn links by what the learner knows)."""
    mine = clause(
        "这是我的电脑",
        "This is my computer",
        (("电脑", "computer"),),
        minor=(("我的", "my"),),
    )
    off = DisplayOptions(word_links=WordLinks.OFF)
    key = DisplayOptions(word_links=WordLinks.COLOURS, link_detail=LinkDetail.KEY)
    capped = DisplayOptions(word_links=WordLinks.COLOURS, max_links=0)
    for options in (off, key, capped):
        assert look_up(caption(mine), "我的", options=options) == Counterpart("my", EN)
        assert look_up(caption(mine), "电脑", options=options) == Counterpart(
            "computer", EN
        )


def test_a_word_in_the_translation_row_gets_what_was_said() -> None:
    """A learner of the translation's language (an English learner hearing
    Chinese): the words of the original its links join it to, in the
    caption's language - shown even when the original row is hidden."""
    shown = caption(COMPUTER)
    rows = caption_rows(shown, EN, None, DisplayOptions())
    assert [r.kind for r in rows] == [RowKind.ORIGINAL, RowKind.TRANSLATION]
    assert look_up(shown, "froze", row=1) == Counterpart("卡", ZH)
    hidden = DisplayOptions(show_original=False)
    assert look_up(shown, "computer", options=hidden) == Counterpart("电脑", ZH)


def test_the_translation_shown_is_the_one_used() -> None:
    """A caption translated into two languages (my speech in two windows):
    each window's card says the counterpart in its own translation; a
    clause already in the window's language, in its second language."""
    both = Clause(
        "我的电脑又卡了，",
        {EN: "My computer froze again,", VI: "Máy tính của tôi lại bị treo,"},
        {
            EN: (WordLink((2, 4), (3, 11), True, 0.9),),
            VI: (WordLink((2, 4), (0, 8), True, 0.9),),
        },
    )
    assert look_up(caption(both), "电脑", target=EN) == Counterpart("computer", EN)
    assert look_up(caption(both), "电脑", target=VI) == Counterpart("Máy tính", VI)
    already = clause(
        "I like it", "我喜欢", (("like", "喜欢"),), into=ZH
    )  # the mic, already in the window's English: its second, Chinese
    found = look_up(caption(already, language="en"), "like", target=EN, second=ZH)
    assert found == Counterpart("喜欢", ZH)
    kept = clause("I like it", "我喜欢", (("like", "喜欢"),), into=EN)
    # as the server keeps it: under the target (polyglotic-hq 427)
    found = look_up(caption(kept, language="en"), "like", target=EN, second=ZH)
    assert found == Counterpart("喜欢", ZH)
    back = look_up(caption(kept, language="en"), "喜欢", EN, 1, second=ZH)
    assert back == Counterpart("like", EN)


def test_only_on_a_finished_caption() -> None:
    """A caption still being spoken can change under an open card: no
    counterpart until it's finished - the marks' rule."""
    live = caption(COMPUTER, COMPUTER, live=True)
    rows = caption_rows(live, EN, None, DisplayOptions())
    assert counterpart(live, rows, 0, (2, 4)) is None  # an earlier clause too
    assert counterpart(live, rows, 2, (2, 4)) is None


def test_no_translation_row_no_counterpart() -> None:
    """Captions only (no translation shown), a row out of range, a span
    out of the text: nothing."""
    shown = caption(COMPUTER)
    alone = caption_rows(shown, Language(""), None, DisplayOptions())
    assert counterpart(shown, alone, 0, (2, 4)) is None
    rows = caption_rows(shown, EN, None, DisplayOptions())
    assert counterpart(shown, rows, 5, (2, 4)) is None
    assert counterpart(shown, rows, 0, (40, 42)) is None
