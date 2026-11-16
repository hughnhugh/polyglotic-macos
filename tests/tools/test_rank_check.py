"""A pack's ranks are refused when their top words carry the junk
polyglotic-hq 325 found (374)."""

from __future__ import annotations

from dataclasses import replace

from tools.dictionaries import rank_check

from polyglotic_desktop.ports.dictionary import EntryRecord


def ranked(*words: str, pos: str = "noun") -> list[EntryRecord]:
    """One entry per word, ranked in the order given."""
    return [
        EntryRecord(f"x{n}", w, "", "", (f"({pos}) a meaning",), frequency_rank=n)
        for n, w in enumerate(words, start=1)
    ]


def common(n: int) -> list[EntryRecord]:
    return ranked(*(f"word{chr(97 + i % 26)}{'z' * (i // 26)}" for i in range(n)))


def test_a_clean_list_passes() -> None:
    assert rank_check.problems(ranked("и", "в", "не", "что-то"), "ru") == []


def test_an_affix_in_the_top_is_refused() -> None:
    found = rank_check.problems(ranked("и", "в-", "-ить"), "ru")
    assert found == ["2 affixes in the top 3: в- -ить"]


def test_a_number_in_the_top_is_refused() -> None:
    found = rank_check.problems(ranked("le", "311", "9-3", "homme"), "fr")
    assert found == ["2 numbers in the top 4: 311 9-3"]


def test_junk_past_the_top_isnt_looked_at() -> None:
    affix = EntryRecord("y", "-mente", "", "", ("(suffix) -ly",), frequency_rank=1001)
    records = [*common(rank_check.TOP), affix]
    assert rank_check.problems(records, "es") == []


def test_a_words_entries_share_its_rank_and_count_once() -> None:
    # в "in" and в the letter's name share rank 1: one word, not two
    records = [
        EntryRecord("a", "в", "", "", ("(prep) in",), frequency_rank=1),
        EntryRecord("b", "в", "", "", ("(character) the letter",), frequency_rank=1),
        EntryRecord("c", "и", "", "", ("(conj) and",), frequency_rank=2),
    ]
    assert [w for w, _ in rank_check.ranked_words(records)] == ["в", "и"]


def test_names_past_their_share_are_refused() -> None:
    names = ranked(
        *(f"Name{chr(97 + i % 26)}{'x' * (i // 26)}" for i in range(41)), pos="name"
    )
    words = [
        replace(r, frequency_rank=(r.frequency_rank or 0) + 41) for r in common(959)
    ]
    found = rank_check.problems(names + words, "es")
    assert len(found) == 1
    assert found[0].startswith("41 names in the top 1,000 (at most 40): Namea Nameb")
    # forty in a thousand are real names a learner hears (Россия, Москва;
    # Hindi's news-heavy list has 31: India, Delhi, Gandhi - polyglotic-hq 380)
    assert rank_check.problems(names[1:] + words, "es") == []


def test_a_word_with_a_meaning_besides_its_name_isnt_a_name() -> None:
    records = [
        EntryRecord("a", "Вера", "", "", ("(name) Vera",), frequency_rank=1),
        EntryRecord("b", "Вера", "", "", ("(noun) faith",), frequency_rank=1),
    ]
    assert not rank_check.is_name(rank_check.ranked_words(records)[0][1])


def test_latin_words_in_a_language_not_written_in_it_are_refused() -> None:
    english = [f"the{chr(97 + i)}" for i in range(11)]
    found = rank_check.problems(ranked("и", *english), "ru")
    assert found and found[0].startswith(
        "11 Latin-alphabet words in the top 12 (at most 10)"
    )
    assert rank_check.problems(ranked("и", *english[:10]), "ru") == []
    assert rank_check.problems(ranked(*english), "en") == []


def test_filipino_by_the_apps_code_is_written_in_latin() -> None:
    """The pack is "tl", as the app and kaikki call Filipino: its own words
    ("sa", "ng", "ang") had all been counted as foreign (polyglotic-hq
    387: 978 of its top 1,000)."""
    tagalog = ranked(*(f"sa{chr(97 + i)}" for i in range(11)))
    assert rank_check.problems(tagalog, "tl") == []


def test_a_vietnamese_list_of_syllables_is_refused() -> None:
    syllables = ranked("tôi", "không", "là", "học", "sinh")
    found = rank_check.problems(syllables, "vi")
    assert found and "ranks syllables, not words" in found[0]
    words = ranked("tôi", "không", "học sinh", "là", "có thể")
    assert rank_check.problems(words, "vi") == []
