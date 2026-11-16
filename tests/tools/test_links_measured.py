"""Word links "past what you know", measured on real captions (polyglotic-hq
338; `tools.links_measured`): no word a learner knows is linked.

The measure itself on the sample dictionaries runs everywhere. On the real
dictionaries - the folder POLYGLOTIC_REAL_DICTIONARIES names, as the UI
lab's job builds CC-CEDICT (ECDICT where it is built too) - it runs the
100 FLEURS sentences of each language at each line: none of the linked
words may be placed inside the line. Before 338 the Chinese ones linked
与, 而 and 一个 with no level set (62 % of words linked), and 美国 at
every line."""

import os
from pathlib import Path

import pytest
from tests.lexicon.sample import english_sample
from tools.links_measured import START, measure, sentences, server_links

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import (
    DEFAULT_CHINESE_SCHEME,
    ENGLISH_FREQUENCY,
)
from polyglotic_desktop.ui.learning import LearningTools
from tools import links_measured

REAL_DICTIONARIES = "POLYGLOTIC_REAL_DICTIONARIES"


def test_the_server_links_each_word_but_grammar_words() -> None:
    text = "The cat sat on 1940 mats"
    links = server_links(text, lambda run: [(0, len(run))])
    assert [text[w.start : w.end] for w in links] == [
        "cat",
        "sat",
        "on",
        "1940",
        "mats",
    ]
    assert [w.key for w in links] == [True, True, False, True, True]
    zh = "我的猫"
    split = [(0, 1), (1, 2), (2, 3)]
    assert [zh[w.start : w.end] for w in server_links(zh, lambda _: split)] == [
        "我",
        "猫",
    ]


def test_a_sample_caption_is_measured() -> None:
    """ "They keep running, awkward": ranks 35, 250, 202 (run), 2,500."""

    def tools() -> LearningTools:
        return links_measured.learner_tools(
            EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id, {}
        )

    (at_1000, at_100) = measure(
        "en", ["They keep running, awkward"], tools, [1000, 100]
    )
    assert (at_1000.links, at_1000.drawn, at_1000.inside) == (4, 1, [])
    assert at_1000.past == {"awkward": 2500}
    assert at_100.drawn == 3  # keep and running too


def real(name: str) -> Path:
    folder = os.environ.get(REAL_DICTIONARIES)
    path = Path(folder) / name if folder else None
    if path is None or not path.is_file():
        pytest.skip(f"{name} isn't built here ({REAL_DICTIONARIES})")
    return path


@pytest.mark.parametrize("code", ["zh", "en"])
def test_no_known_word_is_linked_on_real_captions(code: str) -> None:
    if code == "zh":
        path = real("cedict.sqlite")

        def tools() -> LearningTools:
            return links_measured.learner_tools(
                ChineseDictionary(SqliteDictionary(path)), DEFAULT_CHINESE_SCHEME.id, {}
            )
    else:
        path = real("ecdict.sqlite")

        def tools() -> LearningTools:
            return links_measured.learner_tools(
                EnglishDictionary(SqliteDictionary(path)), ENGLISH_FREQUENCY.id, {}
            )

    found = {m.line: m for m in measure(code, sentences(code), tools)}
    for m in found.values():
        assert m.inside == [], f"{m}: {[i.word for i in m.inside]}"
        assert 0 < m.drawn < m.links, m
    # fewer links the more is known
    shares = [found[n].share for n in (500, 1000, 2000, 5000)]
    assert shares == sorted(shares, reverse=True)
    if code == "zh":  # with no level set, as at HSK 3's 1,000 words
        assert found[START].drawn == found[1000].drawn
