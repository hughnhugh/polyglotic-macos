"""Settled text (polyglotic-hq 296, decision 0088): what a caption has shown
for a few seconds doesn't change - its words, its rows and their
translations - and only what comes after is taken from an update. Made-up
text only."""

import random

from polyglotic_desktop.core.listening.captions import Clause, Language, WordLink
from polyglotic_desktop.core.listening.settling import (
    OPEN_CLAUSES,
    Stable,
    settle,
    settled_length,
    shown_text,
)

ZH = Language("zh")


def clause(original: str, translation: str | None = None) -> Clause:
    return Clause(original, {ZH: translation} if translation else {})


def texts(clauses: tuple[Clause, ...]) -> list[tuple[str, str | None]]:
    return [(c.original, c.translations.get(ZH)) for c in clauses]


# -- how long words have stood ---------------------------------------------------

# These two test the marks' logic at a 3 s settle time (the default until
# 810 made it 1 s); the default itself is tested where it's used.
SETTLED = 3.0


def test_words_have_stood_since_they_last_changed() -> None:
    stable = Stable().after("", "I went to the", at=10.0)
    assert stable.stood(12.9, SETTLED) == 0
    assert stable.stood(10.0 + SETTLED, SETTLED) == len("I went to the")
    # the caption grows: what was there has stood as long, the rest is new
    grown = stable.after("I went to the", "I went to the store and", at=11.5)
    assert grown.stood(13.0, SETTLED) == len("I went to the")
    assert grown.stood(14.5, SETTLED) == len("I went to the store and")
    # an update rewrites from "the" on: only what's before it has stood
    rewritten = grown.after("I went to the store and", "I went to this door", at=13.0)
    assert rewritten.stood(13.5, SETTLED) == len("I went to th")
    assert rewritten.stood(16.0, SETTLED) == len("I went to this door")


def test_one_captions_marks_follow_anothers() -> None:
    """A join's text is one caption's after another's: the second's words
    have stood only as long as the first's whole text has."""
    first = Stable().after("", "Hello there.", at=1.0)
    second = Stable().after("", "How are", at=2.0)
    joined = first.then(len("Hello there."), len("Hello there. "), second)
    assert joined.stood(4.5, SETTLED) == len("Hello there.")
    assert joined.stood(5.0, SETTLED) == len("Hello there. How are")
    # the first one changed lately: nothing after it has stood
    changed = first.after("Hello there.", "Hello then.", at=4.0)
    joined = changed.then(len("Hello then."), len("Hello then. "), second)
    assert joined.stood(5.5, SETTLED) == len("Hello the")


def test_never_half_a_word_nor_a_live_captions_last_word() -> None:
    shown = (clause("the government's policy"),)
    assert settled_length(shown, len("the gov"), live=False) == len("the ")
    assert settled_length(shown, len("the government's policy"), live=False) == 23
    # a live caption trails off mid-speech: its last word may be half said
    assert settled_length(shown, 23, live=True) == len("the government's ")
    chinese = (clause("今天天气很好"),)
    assert settled_length(chinese, 3, live=False) == 3
    assert settled_length(chinese, 6, live=True) == 5


def test_clauses_above_the_last_two_are_settled_however_new() -> None:
    """The user: "after 1-2 lines, lines should settle"."""
    assert OPEN_CLAUSES == 2
    shown = (clause("One."), clause("Two."), clause("Three."), clause("Four"))
    assert settled_length(shown, 0, live=True) == len("One. Two. ")
    assert settled_length(shown[:2], 0, live=True) == 0


# -- the rule ------------------------------------------------------------------


def test_nothing_settled_the_update_as_it_is() -> None:
    update = (clause("I went to the store.", "T"),)
    assert settle((clause("I want to this door", "t"),), update, 0) == update
    assert settle((), update, 0) == update


def test_settled_words_stay_and_the_update_carries_on_after_them() -> None:
    """The finished caption hears the start differently: the words shown
    for 3s stay as they were; what comes after them is the update's."""
    shown = (clause("We walked to this door", "t"),)
    update = (clause("We went to the store and bought milk.", "T"),)
    settled = len("We walked to ")
    assert texts(settle(shown, update, settled)) == [
        ("We walked to the store and bought milk.", "T")
    ]
    # the same words again: the update, whole - links and all
    link = WordLink((0, 1), (0, 1), True, 0.9)
    again = (Clause("We walked to the store.", {ZH: "T"}, {ZH: (link,)}),)
    assert settle(shown, again, settled) == again


def test_the_open_clause_grows_and_its_translation_follows() -> None:
    shown = (clause("I went to the store", "我去了"),)
    update = (clause("I went to the store and bought milk.", "我去商店买了牛奶。"),)
    assert settle(shown, update, len("I went to the ")) == update


def test_a_settled_row_keeps_its_words_translation_and_place() -> None:
    shown = (clause("I went to the store.", "我去了商店。"), clause("Then I", "然后我"))
    update = (
        clause("I walked to the shop.", "我走去了商店。"),
        clause("Then I came home.", "然后我回家了。"),
    )
    assert texts(settle(shown, update, len("I went to the store."))) == [
        ("I went to the store.", "我去了商店。"),
        ("Then I came home.", "然后我回家了。"),
    ]


def test_a_settled_row_gets_its_word_links_when_the_update_agrees() -> None:
    link = WordLink((0, 1), (0, 1), True, 0.9)
    shown = (clause("I went to the store.", "我去了商店。"), clause("Then I", "然后我"))
    update = (
        Clause("I went to the store.", {ZH: "我去了商店。"}, {ZH: (link,)}),
        clause("Then I came home.", "然后我回家了。"),
    )
    settled = settle(shown, update, len("I went to the store."))
    assert settled == update and settled[0].links[ZH] == (link,)


def test_a_row_the_update_splits_differently_joins_it() -> None:
    """The finished caption makes one clause of two: the settled words
    stay, but the row and its translation are the update's - a translation
    never says part of the line twice."""
    shown = (
        clause("I went to the store,", "我去了商店，"),
        clause("and then I", "然后我"),
    )
    update = (
        clause("I went to the store and then I came home.", "我去了商店然后回家了。"),
    )
    assert texts(settle(shown, update, len("I went to the store, "))) == [
        ("I went to the store, and then I came home.", "我去了商店然后回家了。")
    ]


def test_settled_words_waiting_for_a_translation_take_the_updates_rows() -> None:
    """Live captions untranslated: the finished caption brings the
    translations, in its own rows, over the settled words."""
    shown = (clause("I want to the store,"), clause("and then I"))
    update = (
        clause("I went to the store,", "我去了商店，"),
        clause("and then I came home.", "然后我回家了。"),
    )
    assert texts(settle(shown, update, len("I want to the store, "))) == [
        ("I want to the store,", "我去了商店，"),
        ("and then I came home.", "然后我回家了。"),
    ]


def test_chinese_is_lined_up_character_by_character() -> None:
    shown = (
        clause("今天天气很好，", "The weather is nice today,"),
        clause("我们去", "we go"),
    )
    update = (
        clause("今天天汽真好，", "Today is really nice,"),
        clause("我们去公园玩。", "let's go to the park."),
    )
    assert texts(settle(shown, update, len("今天天气很好，"))) == [
        ("今天天气很好，", "The weather is nice today,"),
        ("我们去公园玩。", "let's go to the park."),
    ]
    # settled inside a clause: its words stay, its row is the update's
    one = (clause("今天天气很好我们", "x"),)
    assert texts(settle(one, update, 6)) == [
        ("今天天气很好，", "Today is really nice,"),
        ("我们去公园玩。", "let's go to the park."),
    ]


def test_an_update_shorter_than_whats_settled_takes_nothing_away() -> None:
    shown = (clause("I went to the store and then", "t"),)
    update = (clause("I went to the store.", "T"),)
    (settled,) = settle(shown, update, len("I went to the store and then"))
    assert settled.original == "I went to the store and then"
    # every row settled and nothing after them: as shown
    rows = (clause("One.", "一。"), clause("Two.", "二。"))
    assert settle(rows, (clause("One, two.", "一，二。"),), len("One. Two.")) == rows


def test_with_nothing_to_line_up_by_the_place_is_by_the_speechs_length() -> None:
    """Two hearings that share no word: the update carries on as many words
    in as were settled - or, when the speech is known to be twice as long,
    halfway through it."""
    shown = (clause("alpha beta gamma delta", "t"),)
    update = (clause("one two three four five six seven eight", "T"),)
    settled = len("alpha beta gamma delta")
    (by_words,) = settle(shown, update, settled)
    assert by_words.original == "alpha beta gamma delta five six seven eight"
    (by_speech,) = settle(shown, update, settled, grew=4.0)
    assert (
        by_speech.original == "alpha beta gamma delta three four five six seven eight"
    )


def test_settled_words_always_stay_whatever_the_update() -> None:
    """Any two hearings: the result starts with the settled words, exactly
    - none run together where two clauses met - and no clause is empty."""
    rng = random.Random(296)
    vocabulary = [
        "the",
        "a",
        "store",
        "went",
        "walked",
        "I",
        "you",
        "and",
        "then",
        "home",
        "came",
        "milk",
        "bought",
    ]

    def hearing() -> tuple[Clause, ...]:
        return tuple(
            clause(
                " ".join(rng.choices(vocabulary, k=rng.randint(1, 6))),
                rng.choice(["译", None]),
            )
            for _ in range(rng.randint(1, 4))
        )

    for _ in range(500):
        shown, update = hearing(), hearing()
        text = shown_text(shown)
        settled = settled_length(shown, rng.randint(0, len(text)), rng.random() < 0.5)
        result = settle(shown, update, settled)
        kept = text[:settled].split()
        assert shown_text(result).split()[: len(kept)] == kept  # word for word
        assert all(c.original.strip() for c in result)


# -- where two hearings meet (polyglotic-hq 301) ---------------------------------


def settled_after(words: str, update: str) -> str:
    """The text once `update` follows a shown caption whose first `words`
    (written out) are settled: the shown caption is `words` and one more
    word, after the `|`."""
    shown = words.replace("|", "")
    result = settle((clause(shown),), (clause(update),), len(words.split("|")[0]))
    return shown_text(result)


def test_a_word_the_update_lost_before_the_settled_point_costs_no_word_after() -> None:
    """The later hearing misses a word just before the settled point, and
    has a common word a little further on ("the", "it", "a"): that later
    word isn't taken for the settled one - nothing between is left out."""
    assert (
        settled_after(
            "Soon the guards with the dogs entered the |yard",
            "Soon the guards with the dogs entered yard and cornered the men",
        )
        == "Soon the guards with the dogs entered the yard and cornered the men"
    )
    assert (
        settled_after(
            "They pulled it |and", "They pulled and rebuilt it under a new name"
        )
        == "They pulled it and rebuilt it under a new name"
    )
    assert (
        settled_after(
            "With only nine seats left a |day,",
            "With only nine seats left day, a number of people",
        )
        == "With only nine seats left a day, a number of people"
    )
    assert (
        settled_after(
            "and so it grew in |a", "and so it grew a great deal in the south"
        )
        == "and so it grew in a great deal in the south"
    )
    # the same in Chinese, character by character
    assert (
        settled_after("他们分别得了第四、第|五", "他们分别得了第四、五和第六名")
        == "他们分别得了第四、第五和第六名"
    )
    assert (
        settled_after(
            "今天的天气很好，我们去公|园", "今天的天气很好，我们去园玩，公园里"
        )
        == "今天的天气很好，我们去公园玩，公园里"
    )


def test_a_word_the_update_hears_differently_before_the_settled_point() -> None:
    """A settled word heard as another in the update: the settled one
    stays, and the update carries on right after it."""
    assert (
        settled_after(
            "Soon the guards with the |dogs",
            "Soon the guards with zebra dogs came into the yard",
        )
        == "Soon the guards with the dogs came into the yard"
    )


def test_a_last_word_half_said_is_found_in_the_update() -> None:
    """A live caption's last word trails off ("ya", "W"): the update's
    whole word takes its place even when a word before it was lost."""
    assert (
        settled_after(
            "The guards entered the |ya", "The guards entered yard and shut the gate"
        )
        == "The guards entered the yard and shut the gate"
    )
    assert settled_after("他做了一个|W", "他做了一WiFi门") == "他做了一个WiFi门"


def test_a_word_the_update_gained_doubles_nothing() -> None:
    """The later hearing has one word more just before the settled point,
    with everything shown settled: the words after it come once."""
    shown = (clause("We went to the store"),)
    update = (clause("We went to the big store and came home."),)
    result = settle(shown, update, len("We went to the store"))
    assert shown_text(result) == "We went to the store and came home."


SPEECH = (
    "Soon the guards with the dogs entered the yard and cornered the men by the "
    + "wall, and the gate was shut.",
    "She said that the book was on the table in the hall, but it was not in the "
    + "hall, it was in the kitchen.",
    "今天的天气很好，我们去公园玩，公园里的人很多，我们玩得很开心。",
    "第一名是小王，第二名是小李，第三名和第四名是他们的同学。",
)


def test_no_word_is_lost_or_doubled_at_any_seam() -> None:
    """Every place a caption can be settled to, in speech full of repeated
    small words: the later hearing loses, gains or mishears a word one to
    three words before the shown caption's end (itself sometimes cut
    short), and goes on. The result is the settled words, then every word
    of the later hearing that comes after them in the speech - each once."""

    def clauses(words: list[str], gap: str) -> tuple[Clause, ...]:
        rows, row = [], []
        for word in words:
            row.append(word)
            if word[-1] in ",.，。":
                rows.append(clause(gap.join(row)))
                row = []
        return (*rows, clause(gap.join(row))) if row else tuple(rows)

    def letters(words: list[str]) -> list[str]:
        return ["".join(c for c in word if c.isalnum()).casefold() for word in words]

    checked = 0
    for speech in SPEECH:
        cjk = " " not in speech
        gap = "" if cjk else " "
        said = list(speech) if cjk else speech.split()
        for end in range(4, len(said) - 1):
            later = said[: end + 3]
            place = list(range(len(later)))
            hearings = [(said[:end], later, place)]
            if len(said[end - 1]) >= 6:
                hearings.append(([*said[: end - 1], said[end - 1][:-3]], later, place))
            as_shown = tuple(shown for shown, _, _ in hearings)
            for back in (1, 2, 3):
                at = end - back
                lost = (later[:at] + later[at + 1 :], place[:at] + place[at + 1 :])
                filler, other = ("呃", "斑") if cjk else ("uh", "zebra")
                gained = ([*later[:at], filler, *later[at:]], sorted([*place, at]))
                misheard = ([*later[:at], other, *later[at + 1 :]], place)
                for shown in as_shown:
                    hearings += [(shown, *lost), (shown, *gained), (shown, *misheard)]
            for shown, heard, places in hearings:
                old, new = clauses(shown, gap), clauses(heard, gap)
                for kept in range(1, len(shown)):  # the last word never settles
                    settled = len(shown_text(clauses(shown[:kept], gap)))
                    result = shown_text(settle(old, new, settled + (not cjk)))
                    after = [w for w, n in zip(heard, places, strict=True) if n >= kept]
                    got = list(result) if cjk else result.split()
                    assert letters(got) == letters(shown[:kept] + after)
                    checked += 1
    assert checked > 10_000


def test_a_long_caption_is_lined_up_as_a_short_one_is() -> None:
    """Hundreds of words, every seventh heard differently: the update
    carries on at the word after the settled ones."""
    said = [f"word{n}" for n in range(300)]
    again = [w if n % 7 else f"other{n}" for n, w in enumerate(said)]
    shown = (clause(" ".join(said[:200])),)
    update = (clause(" ".join(again)),)
    settled = len(" ".join(said[:150])) + 1
    result = shown_text(settle(shown, update, settled)).split()
    assert result == said[:150] + again[150:]
