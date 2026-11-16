"""Which language a looked-up word is said in, and which voice says it
(`ui_next.views.speech`, polyglotic-hq 286): the word's language, never the
interface's; Taiwan's voice for a traditional form, the mainland's for a
simplified one, never Hong Kong's (Cantonese) for Mandarin; the usual
region first; any region of a language otherwise. Plain Python."""

from polyglotic_desktop.ports.speaker import Voice
from polyglotic_desktop.ui_next.views.lookup import Card, Shows
from polyglotic_desktop.ui_next.views.speech import (
    NORMAL,
    SLOWER,
    pace,
    voice_for,
    word_language,
)

DAVID = Voice("1", "Microsoft David", "en-US")
GEORGE = Voice("2", "Microsoft George", "en-GB")
HUIHUI = Voice("3", "Microsoft Huihui", "zh-CN")
HANHAN = Voice("4", "Microsoft Hanhan", "zh-TW")
TRACY = Voice("5", "Microsoft Tracy", "zh-HK")
AN = Voice("6", "Microsoft An", "vi-VN")
SABINA = Voice("7", "Microsoft Sabina", "es-MX")
THIS_PC = (DAVID, HUIHUI, HANHAN, AN)  # the user's PC, 2026-11-11 (one of each)


def test_a_words_language_is_its_own() -> None:
    assert word_language(Card("电脑", Shows.ENTRY, True)) == "zh"
    assert word_language(Card("電腦", Shows.ENTRY, True, traditional=True)) == "zh-hant"
    assert word_language(Card("computer", Shows.CHINESE_FOR, True)) == "en"
    assert word_language(Card("keep", Shows.ENTRY, True)) == "en"
    # a basic dictionary's word, and a row with no dictionary: the row's
    assert word_language(Card("saber", Shows.ENTRY, True, language="es")) == "es"
    assert word_language(Card("食べる", Shows.ENTRY, True, language="ja")) == "ja"
    assert (
        word_language(Card("唔該", Shows.NO_DICTIONARY, True, language="yue")) == "yue"
    )
    # the dictionary out: the word can still be said
    assert word_language(Card("电脑", Shows.DICTIONARY_OUT, True)) == "zh"
    assert word_language(Card("  ", Shows.NOT_FOUND, True)) is None


def test_chinese_is_said_by_the_mainland_or_taiwan_never_hong_kong() -> None:
    assert voice_for(THIS_PC, "zh") == HUIHUI
    assert voice_for(THIS_PC, "zh-hant") == HANHAN
    assert voice_for((HUIHUI,), "zh-hant") == HUIHUI  # Mandarin all the same
    assert voice_for((HANHAN,), "zh") == HANHAN
    assert voice_for((TRACY, DAVID), "zh") is None  # Cantonese isn't Mandarin
    assert voice_for((TRACY, HUIHUI), "yue") == TRACY
    assert voice_for(THIS_PC, "yue") is None  # Mandarin isn't Cantonese


def test_the_usual_region_first_then_any_of_the_language() -> None:
    assert voice_for((GEORGE, DAVID), "en") == DAVID
    assert voice_for((GEORGE,), "en") == GEORGE
    assert voice_for((SABINA,), "es") == SABINA  # Spain's first, Mexico's will do
    assert voice_for(THIS_PC, "vi") == AN
    assert voice_for(THIS_PC, "ja") is None  # no Japanese voice on this PC
    assert voice_for((Voice("8", "Microsoft Pattara", "th-TH"),), "th") is not None
    assert voice_for((), "en") is None


def test_the_voices_own_pace_then_slower_in_turn() -> None:
    assert [pace(n) for n in range(4)] == [NORMAL, SLOWER, NORMAL, SLOWER]
    assert SLOWER < NORMAL
