"""Steady's card stack (views.cards; polyglotic-hq 552, decision 0260): the
user's complaints as rules - a shown word never changes card or place, a
translation moves nothing, the stack never comes back down."""

import math
from dataclasses import replace
from itertools import pairwise

import pytest

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    SpeechTimes,
    WordLink,
)
from polyglotic_desktop.core.listening.continuations import CaptionGroups
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.playout import each_character
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui_next.views.cards import (
    COMING_SEC,
    DEPTH_SCALES,
    DEPTH_SEC,
    FAR_INK,
    FIT,
    GLIDE_FASTEST,
    GONE_AT,
    NEW_CARD_AFTER_SEC,
    Deck,
    Depth,
    Glide,
    depth_alpha,
    depth_scale,
    drum,
    drum_room,
    ease,
    pieces,
)

APP = SourceId("app")
EN, ZH = Language("en"), Language("zh")
WIDTH = 200.0


def wide(text: str, translation: bool) -> float:
    """10 px a character, whichever side."""
    return 10.0 * len(text)


def deck(width: float = WIDTH) -> Deck:
    return Deck(width / FIT, wide, each_character, likely=1.0)


def live(text: str, caption: str = "a", translation: str = "") -> CaptionUpdate:
    clause = Clause(text, {ZH: translation} if translation else {})
    return CaptionUpdate(
        CaptionId(caption), APP, CaptionKind.LIVE, clauses=(clause,),
        language=EN, established=len(text),
    )  # fmt: skip


def finished(
    text: str,
    translation: str = "",
    caption: str = "a",
    links: tuple[WordLink, ...] = (),
) -> CaptionUpdate:
    clause = Clause(
        text, {ZH: translation} if translation else {}, {ZH: links} if links else {}
    )
    return CaptionUpdate(
        CaptionId(caption), APP, CaptionKind.FINISHED, clauses=(clause,), language=EN
    )


class Table:
    """The cards as a window's view would hold them: each card's latest
    update, by its caption id."""

    def __init__(self, cards: Deck) -> None:
        self.deck = cards
        self.cards: dict[CaptionId, CaptionUpdate] = {}

    def show(self, update: CaptionUpdate, now: float = 0.0) -> None:
        for card in self.deck.show(update, now):
            if card.kind is CaptionKind.WITHDRAWN:
                del self.cards[card.caption_id]
            else:
                self.cards[card.caption_id] = card

    def said(self) -> list[str]:
        return [
            " ".join(c.original for c in card.clauses) for card in self.cards.values()
        ]

    def translated(self) -> list[str]:
        return [
            " ".join(c.translations.get(ZH, "") for c in card.clauses).strip()
            for card in self.cards.values()
        ]


def test_text_is_cut_into_words_that_keep_their_punctuation() -> None:
    assert pieces("So, my dad.", each_character) == [
        ("So,", True),
        ("my", True),
        ("dad.", False),
    ]
    assert pieces("我的dad。", each_character) == [
        ("我", False),
        ("的", False),
        ("dad。", False),
    ]


def test_a_word_that_does_not_fit_starts_the_next_card() -> None:
    table = Table(deck())
    table.show(live("one two three four five six seven"))
    assert table.said() == ["one two three four", "five six seven"]
    assert all(wide(text, False) <= WIDTH for text in table.said())


def test_words_keep_their_card_as_the_caption_grows() -> None:
    table = Table(deck())
    text = "one two three four five six seven eight nine ten"
    words = text.split()
    before: list[str] = []
    for n in range(1, len(words) + 1):
        table.show(live(" ".join(words[:n])))
        now = table.said()
        # every card but the last is as it was; the last only grew
        assert now[: len(before) - 1] == before[:-1] if before else True
        if before and len(now) == len(before):
            assert now[-1].startswith(before[-1])
        before = now


def test_a_translation_moves_no_word_and_adds_no_card() -> None:
    table = Table(deck())
    table.show(live("one two three four five six"))
    before = table.said()
    table.show(finished("one two three four five six", "一二三四五六"))
    assert table.said() == before
    assert "".join(table.translated()) == "一二三四五六"


def test_a_supplied_translation_counts_toward_the_next_words_room() -> None:
    table = Table(deck())
    table.show(finished("a", "a full line here"))
    table.show(live("one two", caption="b"), now=0.1)
    assert table.said() == ["a one", "two"]
    assert table.translated()[0] == "a full line here"


def test_a_translation_is_never_cut_short() -> None:
    # 553's review: "can be as wide..." lost "as six miles" - text is never
    # dropped; a card too small for its translation takes a second line
    table = Table(deck())
    meant = "a translation that is much too long to fit one card of this width"
    table.show(live("one two three"))
    table.show(finished("one two three", meant))
    (line,) = table.translated()
    assert line == meant
    assert table.deck.counts.cut_short == 1  # counted: a card with a second line


def test_a_translation_that_grows_moves_no_shown_word_to_another_card() -> None:
    # 553's review: "...mammals cannot / travel long distances" became
    # "...mammals cannot travel long / distances" as the caption went on
    table = Table(deck())
    one = Clause(
        "one two three four five six,", {ZH: "uno dos tres cuatro cinco seis,"}
    )
    two = Clause("seven eight nine ten eleven", {ZH: "siete ocho nueve diez once"})
    first = CaptionUpdate(
        CaptionId("a"), APP, CaptionKind.LIVE,
        clauses=(one, Clause("seven")), language=EN,
        established=len(one.original) + 6,
    )  # fmt: skip
    table.show(first)
    shown = table.translated()
    assert " ".join(shown).split() == one.translations[ZH].split()
    table.show(
        CaptionUpdate(
            CaptionId("a"), APP, CaptionKind.FINISHED, clauses=(one, two), language=EN
        )
    )
    after = table.translated()
    for was, now in zip(shown[:-1], after, strict=False):
        assert now == was  # every card but the last cut keeps its share
    assert after[len(shown) - 1].startswith(shown[-1])  # and that one only grows
    assert (
        " ".join(after).split()
        == (one.translations[ZH] + " " + two.translations[ZH]).split()
    )


def test_a_translation_is_cut_where_its_card_is_and_runs_on() -> None:
    table = Table(deck())
    said = "one two three four five six seven"
    table.show(live(said))
    table.show(finished(said, "uno dos tres cuatro cinco seis siete"))
    first, second = table.translated()
    assert f"{first} {second}" == "uno dos tres cuatro cinco seis siete"
    assert wide(first, True) <= WIDTH and wide(second, True) <= WIDTH


def test_a_translation_is_cut_where_no_word_link_crosses() -> None:
    # the first card's words are one short word of the translation: by
    # length alone the cut would fall in the middle
    table = Table(deck())
    said = "one two three four five six seven"
    links = (
        WordLink((0, 18), (0, 2), True, 1.0),  # the first card's words: "aa"
        WordLink((19, 23), (3, 5), True, 1.0),  # "five": "bb"
        WordLink((24, 33), (6, 14), True, 1.0),  # "six seven": "cc dd ee"
    )
    table.show(live(said))
    table.show(finished(said, "aa bb cc dd ee", links=links))
    assert table.translated() == ["aa", "bb cc dd ee"]


def test_word_links_are_kept_within_a_card() -> None:
    table = Table(deck())
    said = "one two three four five six seven"
    links = (
        WordLink((4, 7), (4, 7), True, 1.0),
        WordLink((19, 23), (20, 25), True, 0.9),
    )
    table.show(live(said))
    table.show(finished(said, "uno dos tres cuatro cinco seis siete", links=links))
    first, second = table.cards.values()
    (link,) = first.clauses[0].links[ZH]
    assert first.clauses[0].original[slice(*link.original)] == "two"
    assert first.clauses[0].translations[ZH][slice(*link.translation)] == "dos"
    (link,) = second.clauses[0].links[ZH]
    assert second.clauses[0].original[slice(*link.original)] == "five"
    assert second.clauses[0].translations[ZH][slice(*link.translation)] == "cinco"


def test_a_changed_word_that_fits_is_changed_where_it_is() -> None:
    table = Table(deck())
    table.show(live("one two three"))
    table.show(live("one too three"))
    assert table.said() == ["one too three"]
    assert table.deck.counts.in_place == 1


def test_a_change_that_would_move_shown_words_waits_for_the_finish() -> None:
    table = Table(deck())
    table.show(live("one two three four"))
    table.show(live("well one two three four"))  # a word put in front
    assert table.said() == ["one two three four"]
    assert table.deck.counts.waited > 0
    table.show(finished("well one two three four"))
    assert " ".join(table.said()).split() == ["well", "one", "two", "three", "four"]
    assert table.deck.counts.settles == 1


def test_lighting_words_already_on_cards_preserves_their_places() -> None:
    table = Table(deck(100.0))
    update = live("one two three four five six seven")
    table.show(replace(update, established=0))
    placed = {
        table.deck.card_id(card): " ".join(word.text for _, word in card.words)
        for card in table.deck.cards
    }
    assert len(placed) > 1
    assert len(table.cards) == 1  # only the first waiting line is in view
    for count in (3, 7, 13, 18, 23, 27, len(update.clauses[0].original)):
        table.show(replace(update, established=count))
        assert all(
            placed[key] == card.clauses[0].original for key, card in table.cards.items()
        )
    assert set(table.cards) == set(placed)
    assert table.deck.counts.cards == len(placed)


def test_lighting_a_word_updates_only_its_card() -> None:
    cards = deck(100.0)
    update = live("one two three four five six seven")
    (first,) = cards.show(replace(update, established=0), 0.0)
    assert len(cards.cards) > 1
    (lit,) = cards.show(replace(update, established=3), 0.5)
    assert (lit.caption_id, lit.established) == (first.caption_id, 3)


def test_the_next_card_is_made_a_word_ahead() -> None:
    cards = deck()
    table = Table(cards)
    cards.hear(live("one two three four five"))  # the server's text, unseen
    table.show(live("one two three"))
    assert not cards.room
    table.show(live("one two three four"))  # "five" won't fit: its card is made
    assert cards.room
    assert table.said() == ["one two three four"]
    table.show(live("one two three four five"))
    assert not cards.room
    assert table.said() == ["one two three four", "five"]


def test_a_translated_karaoke_line_shows_the_pair_before_its_first_word_lights() -> (
    None
):
    table = Table(deck())
    table.show(replace(live("one two", translation="un deux"), established=0))
    assert table.translated() == ["un deux"]
    assert next(iter(table.cards.values())).established == 0


def test_words_ahead_are_not_established_and_may_change() -> None:
    table = Table(deck())
    ahead = CaptionUpdate(
        CaptionId("a"), APP, CaptionKind.LIVE, clauses=(Clause("one two three"),),
        language=EN, established=3,
    )  # fmt: skip
    table.show(ahead)
    (card,) = table.cards.values()
    assert card.established == 3
    table.show(live("one too many"))  # the words ahead were others
    assert table.said() == ["one too many"]
    assert table.deck.counts.waited == 0


def test_a_caption_after_a_pause_starts_a_card() -> None:
    table = Table(deck())
    table.show(finished("one two", "uno dos"))
    table.show(live("three", caption="b"), now=NEW_CARD_AFTER_SEC.value + 0.1)
    assert table.said() == ["one two", "three"]
    assert table.translated() == ["uno dos", ""]


def test_re_spoken_cards_keep_the_mark_separate_from_the_speaker() -> None:
    table = Table(deck())
    table.show(finished("one"))
    table.show(replace(finished("two", caption="b"), respoken=True), now=0.3)
    table.show(finished("three", caption="c"), now=0.6)
    assert table.said() == ["one", "two", "three"]
    assert [card.respoken for card in table.cards.values()] == [False, True, False]


def test_a_short_caption_carries_on_on_the_front_card() -> None:
    # 553's third recording: 35 of 61 Mandarin lines were pushed within
    # 1.5 s of being written - every short clause started a card and
    # pushed the one before. A caption that follows at once and fits
    # carries on where the last one ended; its translation follows too.
    table = Table(deck())
    table.show(finished("one two", "uno dos"))
    table.show(finished("three", "tres", caption="b"), now=1.0)
    assert table.said() == ["one two three"]
    assert table.translated() == ["uno dos tres"]


def spoken(
    text: str, translation: str, caption: str, start: float, end: float
) -> CaptionUpdate:
    """A finished caption of speech said from `start` to `end`."""
    return replace(
        finished(text, translation, caption),
        language=ZH,
        times=SpeechTimes(start, end, end + 0.1, end + 0.5),
    )


def test_a_sentence_said_slowly_is_one_line_not_a_card_a_word() -> None:
    # the user, 2026-11-21 (a Mandarin eating video): "consecutive lines
    # get made for single words in a sentence" - 這個 / 面 / 的 / 那個 /
    # 麵條, each its own card down the window's left edge. The server
    # finishes each fragment on its own after a pause of 2-4 s (583's
    # recording: median 6 characters, median pause 2.7 s)
    table = Table(deck(width=400.0))
    said = (("這個", "at this"), ("面", "noodle,"), ("的", "of"), ("那個", "um"))
    at = 0.0
    for n, (text, meant) in enumerate(said):
        table.show(spoken(text, meant, f"w{n}", at, at + 0.5), now=at + 1.5)
        at += 3.5  # a 3 s pause between words
    assert table.said() == ["這個 面 的 那個"]
    assert table.translated() == ["at this noodle, of um"]


def test_a_long_pause_or_another_language_starts_a_card() -> None:
    table = Table(deck(width=400.0))
    table.show(spoken("這個", "this", "a", 0.0, 0.5), now=1.5)
    table.show(
        spoken("面", "noodle", "b", 0.5 + NEW_CARD_AFTER_SEC.value + 0.5, 6.5), now=7.5
    )
    english = replace(
        spoken("yes", "是", "c", 7.0, 7.5), language=EN, languages_heard=(EN,)
    )
    table.show(english, now=8.5)
    assert table.said() == ["這個", "面", "yes"]


@pytest.mark.parametrize(
    "withdraw_later", [False, True], ids=["join", "withdraw-then-join"]
)
def test_a_refinished_caption_has_one_translation_on_a_shared_card(
    withdraw_later: bool,
) -> None:
    table = Table(deck(width=900.0))
    meant = "我們找到了新的地圖"
    link = WordLink((17, 20), (7, 9), True, 1.0)
    first = finished("We found", "找到了")
    aside = finished("Yes.", "對。", caption="aside")
    later = live("the new", caption="b")
    joined = replace(
        finished("We found the new map.", meant, links=(link,)),
        replaces=(later.caption_id,),
    )
    # The join was requested before the aside. Its answer arrives after
    # the aside has shared the card, with a last word still to add.
    updates = [first, later]
    if withdraw_later:
        updates.append(CaptionUpdate(later.caption_id, APP, CaptionKind.WITHDRAWN))
    for n, update in enumerate([*updates, aside, joined, joined]):
        table.deck.hear(update, n * 0.4)
        table.show(update, now=n * 0.4)
    (card,) = table.cards.values()
    assert sum(c.translations.get(ZH, "").count(meant) for c in card.clauses) == 1
    phrase, answer = card.clauses
    assert phrase.original == joined.clauses[0].original
    assert phrase.links[ZH] == (link,)
    assert (answer.original, answer.translations[ZH]) == ("Yes.", "對。")


def test_a_joined_caption_keeps_its_captions_places() -> None:
    table = Table(deck())
    table.show(finished("one two", "uno dos"))
    table.show(finished("three four", "tres cuatro", caption="b"), now=9.0)
    before = table.said()
    joined = CaptionUpdate(
        CaptionId("c"), APP, CaptionKind.FINISHED,
        clauses=(Clause("one two three four", {ZH: "uno dos tres cuatro"}),),
        language=EN, replaces=(CaptionId("a"), CaptionId("b")),
    )  # fmt: skip
    table.show(joined)
    assert table.said() == before  # no word left its card, none shown twice
    assert table.translated() == ["uno dos", "tres cuatro"]


def test_a_translation_is_never_cut_inside_a_word() -> None:
    table = Table(deck())
    said = "one two three four five six seven"
    meant = "extraordinarily longwinded translations everywhere"
    table.show(live(said))
    table.show(finished(said, meant))
    words = set(meant.split())
    for line in table.translated():
        assert set(line.split()) <= words
    assert " ".join(table.translated()).split() == meant.split()


def test_a_captions_clauses_are_one_text_on_its_cards() -> None:
    table = Table(deck())
    update = CaptionUpdate(
        CaptionId("a"), APP, CaptionKind.FINISHED,
        clauses=(
            Clause("one two three.", {ZH: "uno dos tres."}),
            Clause("four five six seven", {ZH: "cuatro cinco seis siete"}),
        ),
        language=EN,
    )  # fmt: skip
    table.show(update)
    assert table.said() == ["one two three. four", "five six seven"]
    assert all(len(card.clauses) == 1 for card in table.cards.values())
    assert " ".join(table.translated()) == "uno dos tres. cuatro cinco seis siete"
    assert all(wide(line, True) <= WIDTH for line in table.translated())


def test_a_withdrawn_captions_cards_go() -> None:
    table = Table(deck())
    table.show(live("one two three four five six"))
    table.show(CaptionUpdate(CaptionId("a"), APP, CaptionKind.WITHDRAWN))
    assert table.said() == []


def test_a_card_is_finished_once_closed_and_its_captions_are() -> None:
    table = Table(deck())
    table.show(finished("one two three four five six"))
    first, second = table.cards.values()
    assert first.kind is CaptionKind.FINISHED
    assert second.kind is CaptionKind.LIVE  # the next caption may carry on in it


# -- the one motion -----------------------------------------------------------------------


def test_a_glide_starts_gently_and_never_comes_back() -> None:
    glide = Glide()
    glide.push(0.0, 80.0)
    last, steps = 80.0, []
    for frame in range(1, 121):
        px = glide.to(frame / 60)
        assert 0.0 <= px <= last + 1e-9  # only ever towards its place
        steps.append(last - px)
        last = px
    assert steps[0] < max(steps) / 3  # from rest, not at full speed
    assert max(steps) < 6.0  # under 6 px in a 60 Hz frame for a card's height
    assert not glide.moving(3.0)


def test_a_push_mid_glide_keeps_its_speed() -> None:
    glide = Glide()
    glide.push(0.0, 80.0)
    before = glide.to(0.1) - glide.to(0.1 + 1 / 60)
    glide.push(0.1 + 1 / 60, 80.0)
    after = glide.to(0.1 + 1 / 60) - glide.to(0.1 + 2 / 60)
    assert abs(after - before) < 1.5  # no jolt: one glide


@pytest.mark.parametrize("pitch", [92.0, -92.0])
def test_a_run_of_cards_keeps_the_glides_existing_speed_limit(pitch: float) -> None:
    glide = Glide()
    for frame in range(90):
        now = frame / 60
        if frame % 5 == 0:
            glide.push(now, pitch, most=3 * abs(pitch))
        before = glide.to(now)
        after = glide.to((frame + 1) / 60)
        assert abs(after - before) <= GLIDE_FASTEST.value / 60 + 1e-6


def test_a_glide_takes_about_half_a_second_and_is_at_rest_within_one() -> None:
    # "slow and smooth" (the user, 2026-11-20): 553 measured 0.3 s
    glide = Glide()
    glide.push(0.0, 80.0)
    assert glide.to(0.25) > 20.0  # still on its way at a quarter second
    assert glide.to(0.6) < 8.0
    assert not glide.moving(1.0)


def test_a_glide_scrolled_back_comes_down_to_its_place() -> None:
    glide = Glide()
    glide.push(0.0, -80.0, most=60.0)
    last = glide.to(0.0)
    assert last == -60.0  # never from further than `most`, either way
    for frame in range(1, 121):
        px = glide.to(frame / 60)
        assert last - 1e-9 <= px <= 0.0  # only ever towards its place
        last = px
    assert last == 0.0


def test_a_deck_put_away_leaves_its_finished_cards_as_they_stand() -> None:
    table = Table(deck())
    table.show(finished("one two three four five", "uno dos tres cuatro cinco"))
    table.show(live("six seven", caption="b"), now=9.0)
    before = table.said()
    for card in table.deck.finish():
        if card.kind is CaptionKind.WITHDRAWN:
            del table.cards[card.caption_id]
        else:
            table.cards[card.caption_id] = card
    assert table.said() == before[:-1]  # the caption still being said goes
    assert all(card.kind is CaptionKind.FINISHED for card in table.cards.values())


def test_a_glide_is_never_fast_however_far_it_goes() -> None:
    # 553: the page rose 86 px in a tenth of a second
    for far in (70.0, 140.0, 210.0):
        glide = Glide()
        glide.push(0.0, far)
        last = far
        for frame in range(1, 600):
            px = glide.to(frame / 60)
            assert last - px <= GLIDE_FASTEST.value / 60 + 1e-6
            last = px
        assert last == 0.0


def test_a_card_is_seen_coming_before_the_playout_shows_it() -> None:
    table = Table(deck())
    assert not table.deck.coming()
    table.show(live("one two three"))
    assert not table.deck.coming()  # nothing more is said
    table.deck.hear(live("one two three four"))
    assert not table.deck.coming()  # it fits the front card
    table.deck.hear(live("one two three four five six"))
    assert table.deck.coming()  # more than the front card holds: a card is coming
    table.show(finished("one two three four five six"))
    assert not table.deck.coming()  # shown: no longer ahead
    table.deck.hear(live("seven", caption="b"), now=10.0)
    assert table.deck.coming(10.5)  # a caption not begun: it starts a card
    assert not table.deck.coming(10.0 + COMING_SEC + 1.0)  # never shown: not coming
    table.deck.hear(CaptionUpdate(CaptionId("b"), APP, CaptionKind.WITHDRAWN), now=11.0)
    assert not table.deck.coming(11.0)


# -- the drum -----------------------------------------------------------------------------


def test_cards_at_the_foot_are_flat() -> None:
    assert drum(300.0, 60.0, 400.0) == (300.0, 1.0, 1.0)


def test_cards_turn_away_in_order_and_are_gone_before_the_top() -> None:
    view, tall = 400.0, 60.0
    room = drum_room(view)
    tops, inks, feet = [], [], []
    top = 400.0 - tall
    while top > -room - tall:
        at, squash, ink = drum(top, tall, view)
        if ink > 0.0:
            tops.append(at)
            feet.append(at + tall * squash)
            inks.append(ink)
            assert at >= 0.0
        top -= tall
    assert tops == sorted(tops, reverse=True)
    assert inks == sorted(inks, reverse=True)
    # a card's foot is on the top of the card under it: no holes, no overlap
    for foot, under in zip(feet[1:], tops[:-1], strict=True):
        assert math.isclose(foot, under, abs_tol=0.01)
    assert drum(-room - tall, tall, view)[2] == 0.0  # past the far end: gone
    assert min(inks) >= FAR_INK.value  # never an empty band where cards are
    assert math.pi / 2 > GONE_AT  # gone before it is edge on


def test_a_change_that_would_move_the_words_after_it_waits() -> None:
    table = Table(deck())
    table.show(live("one two three"))
    table.show(live("one twelve three"))  # wider: "three" would move
    assert table.said() == ["one two three"]
    assert table.deck.counts.waited == 1
    table.show(live("one two thirteen"))  # the last word: nothing after it
    assert table.said() == ["one two thirteen"]


def test_a_cards_language_is_as_first_shown() -> None:
    table = Table(deck())
    table.show(live("one two"))
    late = CaptionUpdate(
        CaptionId("a"), APP, CaptionKind.LIVE, clauses=(Clause("one two three"),),
        language=Language("de"), established=13,
    )  # fmt: skip
    table.show(late)  # the server names another language: no label comes or goes
    (card,) = table.cards.values()
    assert card.language == EN


def test_a_step_back_in_depth_is_eased_and_never_jumps() -> None:
    depth = Depth()
    depth.came(0.0)
    path = [depth.behind(t / 100) for t in range(40)]
    assert path[0] == 1.0 and path[-1] == 0.0  # one step, done in DEPTH_SEC
    steps = [a - b for a, b in pairwise(path)]
    assert all(step >= 0.0 for step in steps)  # always back, never forth
    assert max(steps) < 0.12  # gentle: a tenth of a step in 10 ms at most
    depth.came(1.0)
    depth.came(1.0)  # two cards at once: two steps, from where it stood
    assert depth.behind(1.0) == 2.0
    depth.came(1.1)  # and no more than two at a time
    assert depth.behind(1.1) <= 2.0
    assert depth_scale(0.0) == 1.0 and depth_scale(-0.5) == 1.0
    assert (
        depth_scale(1.0) == DEPTH_SCALES.value[1]
        and depth_scale(2.0) == DEPTH_SCALES.value[2]
    )
    assert depth_scale(3.0) < DEPTH_SCALES.value[2]  # leaving: smaller still
    assert depth_alpha(-0.25, 3) == 0.75 and depth_alpha(2.5, 3) == 0.5
    assert depth_alpha(3.0, 3) == 0.0
    assert ease(0.5) == 0.5 and ease(0.0) == 0.0 and ease(1.0) == 1.0
    assert DEPTH_SEC.value == 0.3


def test_a_join_onto_the_caption_before_keeps_the_words_in_order() -> None:
    # 583's replay of paused Mandarin: the app joins speech after a short
    # pause onto the caption before it, as that caption, replacing the
    # later one's live caption. Its words were taken first, so on a shared
    # line the sentence came out "因为远离大陆，乱。哺乳".
    table = Table(deck(width=400.0))
    table.show(spoken("或走向混乱。", "or to chaos.", "x", 0.0, 1.0), now=1.5)
    table.show(spoken("因为远离大陆。", "because far.", "a", 2.5, 3.0), now=3.5)
    later = replace(live("哺乳动物无法长途", caption="b"), language=ZH)
    table.show(later, now=5.5)
    joined = replace(
        spoken(
            "因为远离大陆，哺乳动物无法长途。", "because far, mammals.", "a", 2.5, 5.2
        ),
        replaces=(CaptionId("b"),),
    )
    table.show(joined, now=7.0)
    said = "".join(table.said()).replace(" ", "")
    assert said == "或走向混乱。因为远离大陆，哺乳动物无法长途。"


def test_the_cards_in_depth_step_by_what_is_drawn() -> None:
    # 583's Video film, 36.47 s: a card dealt again was held back, the
    # stack lost its front card and dropped 204 px, then climbed back
    assert Depth.moved([16, 15, 14], [17, 16, 15, 14]) == 1  # one came
    assert Depth.moved([16, 15, 14], [18, 15, 14]) == 0  # dealt again in place
    assert Depth.moved([16, 15, 14], [15, 14, 13]) == -1  # the front one went
    depth = Depth()
    depth.shift(0.0, -1, 80.0)  # forward, eased, never faster than a glide
    path = [depth.behind(t / 100) for t in range(80)]
    assert path[0] == -1.0 and path[-1] == 0.0
    assert (
        max(abs(a - b) for a, b in pairwise(path)) * 100 * 80 <= GLIDE_FASTEST.value + 1
    )


def test_folding_a_live_continuation_keeps_words_on_their_original_cards() -> None:
    history = CaptionHistory()
    groups = CaptionGroups(history, lambda cid: None)
    table = Table(deck(width=100))

    def apply(update: CaptionUpdate) -> None:
        for shown in groups.project(update):
            history.apply(shown)
            table.deck.hear(shown)
            table.show(shown)

    def positions() -> dict[str, tuple[int, float]]:
        places = {}
        for card in table.deck.cards:
            x = 0.0
            for _, word in card.words:
                places[word.text.rstrip(".")] = (card.number, x)
                x += word.width + (wide(" ", False) if word.space else 0.0)
        return places

    apply(finished("red green.", "old"))
    apply(live("blue gold", caption="b"))
    before = positions()
    assert len({card for card, _ in before.values()}) > 1
    combined = replace(
        finished("red green blue gold.", "new", "b"), continues=CaptionId("a")
    )
    apply(combined)
    apply(
        replace(
            combined, clauses=(Clause("red green blue gold again.", {ZH: "revised"}),)
        )
    )
    assert all(positions()[word] == at for word, at in before.items())
    assert " ".join(table.said()) == "red green blue gold again."
    assert " ".join(table.translated()).strip() == "revised"
