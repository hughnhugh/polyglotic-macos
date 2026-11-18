"""The conversation's words (polyglotic-hq 485, 491; decision 0227): each
source's window of finished captions, its updates, what it offers our
curriculum (stretch words, then theme words; never everyday talk, names
or numbers; nothing said once), look-alikes and the theme's name."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from polyglotic_desktop.core.learning.theme import (
    EVERY,
    STRETCH_IN,
    WINDOW,
    Chosen,
    ConversationThemes,
    SourceWindow,
    Word,
    everyday,
    known_by_speech,
    look_alike,
    offered,
    theme_name,
)
from polyglotic_desktop.core.shared import EntryFacts, EntryId

T0 = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def entry(
    name: str,
    rank: int | None = 1500,
    spoken: int | None = None,
    filler: bool = False,
    is_name: bool = False,
    is_number: bool = False,
    spelled: bool = False,
) -> EntryFacts:
    return EntryFacts(
        EntryId(f"test:{name}"),
        None,
        rank,
        is_name,
        is_number=is_number,
        spoken_rank=spoken,
        is_filler=filler,
        spells_a_number=spelled,
    )


COMMON = [entry(f"c{n}", rank=n) for n in range(1, 9)]
"""Words every caption has: they make the window's size."""


def said(*words: EntryFacts) -> list[Word]:
    return [(w, w.entry_id.removeprefix("test:")) for w in [*words, *COMMON]]


def ids(found: list[EntryFacts]) -> list[str]:
    return [f.entry_id.removeprefix("test:") for f in found]


def past(known: int) -> Callable[[EntryFacts], bool]:
    """The learner may have the word: past their line (`known` words)."""
    return lambda f: f.frequency_rank is None or f.frequency_rank > known


def offers(window: SourceWindow, reach: int = 2000, known: int = 1000) -> list[str]:
    return [
        o.said.entry.entry_id.removeprefix("test:")
        for o in offered(
            window,
            past(known),
            lambda f: f.frequency_rank is not None and f.frequency_rank <= reach,
            known,
        )
    ]


def window_of(*captions: list[Word]) -> SourceWindow:
    window = SourceWindow()
    for n, words in enumerate(captions):
        window.add(f"c{n}", words, T0 + timedelta(seconds=10 * n))
    return window


# -- the window ------------------------------------------------------------------


def test_each_source_has_its_own_window() -> None:
    themes = ConversationThemes()
    owner = entry("owner")
    themes.heard("a1", "game", said(owner), T0)
    themes.heard("b1", "call", said(), T0)
    game, call = themes.window("game"), themes.window("call")
    assert game is not None and call is not None
    assert game.word(owner.entry_id) is not None
    assert call.word(owner.entry_id) is None


def test_captions_older_than_the_window_drop_out() -> None:
    window = SourceWindow()
    owner = entry("owner")
    window.add("c1", said(owner), T0)
    window.add("c2", said(), T0 + WINDOW - timedelta(seconds=1))
    assert window.word(owner.entry_id) is not None
    window.add("c3", said(), T0 + WINDOW + timedelta(seconds=1))
    assert window.word(owner.entry_id) is None
    assert window.captions == 2


def test_a_caption_finished_again_counts_once_and_a_withdrawn_one_leaves() -> None:
    window = SourceWindow()
    owner = entry("owner")
    window.add("c1", said(owner), T0)
    window.add("c1", said(owner, owner), T0 + timedelta(seconds=5))  # a join
    found = window.word(owner.entry_id)
    assert found is not None and (found.captions, found.times) == (1, 2)
    window.withdraw("c1")
    assert window.word(owner.entry_id) is None
    assert (window.captions, window.words) == (0, 0)


def test_an_update_comes_after_every_two_minutes_of_a_sources_talk() -> None:
    themes = ConversationThemes()
    due = [
        themes.heard(f"c{n}", "video", said(), T0 + timedelta(seconds=30 * n))
        for n in range(9)
    ]
    # the talk begins at 0 s: due at 120 s and 240 s, not before
    assert [n * 30 for n, d in enumerate(due) if d] == [120, 240]
    assert timedelta(minutes=2) == EVERY
    # silent for longer than the window: the talk begins again
    later = T0 + timedelta(seconds=240) + WINDOW + timedelta(seconds=1)
    assert not themes.heard("c9", "video", said(), later)
    assert themes.heard("c10", "video", said(), later + EVERY)


# -- what the conversation offers -------------------------------------------------------


def test_a_word_said_in_only_one_caption_is_not_offered() -> None:
    once, twice = entry("once"), entry("twice")
    window = window_of(said(once, once, twice), said(twice), said())
    assert offers(window) == ["twice"]


def test_names_numbers_fillers_and_everyday_talk_are_never_offered() -> None:
    words = [
        entry("Bob", is_name=True),
        entry("二十", is_number=True),
        entry("fourteen", rank=4200, spelled=True),  # a number spelled out
        entry("嗯", rank=3570, filler=True),
        entry("就是说", rank=11167, spoken=2495),  # said far more than written
        entry("便宜", rank=3857, spoken=1806),  # not 3 times: a topic word
    ]
    window = window_of(said(*words), said(*words))
    assert offers(window, reach=5000) == ["便宜"]


def test_a_word_heard_all_the_time_counts_as_known() -> None:
    house = entry("house", rank=2628, spoken=900)  # under 3 times: not everyday
    assert not everyday(house)
    assert known_by_speech(house, 1000) and not known_by_speech(house, 800)
    window = window_of(said(house), said(house))
    assert offers(window, reach=5000, known=1000) == []
    assert offers(window, reach=5000, known=800) == ["house"]


def test_stretch_words_come_first_once_said_in_enough_captions() -> None:
    owner = entry("业主", rank=14337)  # past the learner's window
    estate = entry("小区", rank=12749)
    vehicle = entry("车辆", rank=1800)  # in it
    captions = [said(owner, vehicle) for _ in range(STRETCH_IN)]
    captions += [said(estate) for _ in range(STRETCH_IN - 1)]
    window = window_of(*captions)
    found = offered(window, past(1000), lambda f: (f.frequency_rank or 0) <= 2000, 0)
    assert [(o.said.form, o.chosen) for o in found] == [
        ("业主", Chosen.STRETCH),
        ("车辆", Chosen.THEME),
    ]  # 小区, past the window in 3 captions, waits
    assert found[0].rate == STRETCH_IN / (2 * STRETCH_IN - 1)


def test_theme_words_come_keyest_first() -> None:
    rare, common = entry("rare", rank=1900), entry("common", rank=1100)
    window = window_of(said(rare, common), said(rare, common), said())
    assert offers(window) == ["rare", "common"]


def test_a_word_the_learner_may_not_have_is_not_offered() -> None:
    word = entry("known")
    window = window_of(said(word), said(word))
    assert offered(window, lambda f: False, lambda f: True, 0) == []


# -- look-alikes and the theme's name ----------------------------------------------------


def test_look_alikes() -> None:
    assert look_alike("发表", "发布")  # one character apart
    assert not look_alike("发表", "发表会")  # not the same length
    assert not look_alike("车", "茶")  # one character alone
    assert look_alike("remote", "remove")  # one letter
    assert look_alike("expense", "expensive")  # two, both long
    assert not look_alike("cat", "cart ")
    assert not look_alike("button", "battery")
    assert not look_alike("same", "same")


def test_the_theme_is_named_by_its_keyest_words_at_any_level() -> None:
    owner, estate, manage = (
        entry("业主", 14337),
        entry("小区", 12749),
        entry("物业", 18225),
    )
    then = entry("然后", rank=460, spoken=130)  # everyday talk
    filler = entry("嗯", rank=3570, filler=True)
    piece = entry("潇", rank=9000)  # one character: a piece of a name
    window = window_of(
        *[said(owner, estate, manage, then, filler, piece, piece) for _ in range(3)],
        said(owner, owner),
    )
    assert ids([s.entry for s in theme_name(window)]) == ["业主", "物业", "小区"]
    assert theme_name(SourceWindow()) == []


def test_one_rare_chinese_character_or_a_word_with_no_place_is_never_stretched() -> (
    None
):
    # 黄潇璐 cut into 黄 / 潇 / 璐 by the word split: pieces of a name
    piece, owner = entry("潇", rank=9000), entry("业主", rank=14337)
    then = entry("那时候", rank=None)  # a phrase the ranks didn't count
    window = window_of(*[said(piece, owner, then) for _ in range(STRETCH_IN)])
    assert offers(window) == ["业主"]
    assert [s.form for s in theme_name(window)] == ["业主"]


def test_a_word_never_said_in_small_letters_is_taken_for_a_name() -> None:
    julia = replace(entry("julia", rank=9000), names_capitalised=True)
    rubber = replace(entry("rubber", rank=4735), names_capitalised=True)
    haus = entry("Haus", rank=9100)  # German: every noun has a capital
    window = SourceWindow()
    for n in range(STRETCH_IN):
        said = [(julia, "Julia"), (rubber, "Rubber" if n == 0 else "rubber")]
        window.add(f"c{n}", [*said, (haus, "Haus")], T0)
    assert sorted(offers(window)) == ["Haus", "rubber"]
    assert "Julia" not in [s.form for s in theme_name(window)]


def test_the_form_kept_is_in_small_letters_once_it_has_been_said_so() -> None:
    pressure = entry("pressure", rank=2500)
    window = SourceWindow()
    window.add("c1", [(pressure, "pressure")], T0)
    window.add("c2", [(pressure, "Pressure")], T0)  # a sentence's first word
    found = window.word(pressure.entry_id)
    assert found is not None and found.form == "pressure" and not found.capitalised
