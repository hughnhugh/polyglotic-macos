"""Mandarin's captions in the script the learner reads (polyglotic-hq 375;
decision 0164): each caption's Mandarin converted as it arrives - what was
said, unless it is Japanese or Cantonese, and translations written in
Mandarin (432) - the choice kept in the settings, and Taiwan's and Hong Kong's Windows
starting at Traditional."""

from tests.lexicon.sample import CEDICT_SAMPLE, chinese_sample

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
    mandarin_written,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, WithdrawalReason
from polyglotic_desktop.main import MandarinScript
from polyglotic_desktop.ui.interface_language import reads_traditional
from polyglotic_desktop.ui.settings import AppSettings

EN = Language("en")
LINK = WordLink(original=(2, 4), translation=(0, 4), key=True, confidence=0.9)


def update(language: str, original: str = "我的头发", kind=CaptionKind.FINISHED):
    return CaptionUpdate(
        CaptionId("c1"),
        SourceId("app"),
        kind,
        clauses=(
            Clause(original, translations={EN: "hair"}, links={EN: (LINK,)}),
            Clause("发展", translations={Language("zh"): "发展"}),
        ),
        language=Language(language),
        languages_heard=(Language(language),),
    )


def upper(text: str) -> str:
    return text.replace("头发", "頭髮").replace("发", "發")


def test_mandarins_originals_and_translations_into_chinese_are_converted() -> None:
    written = mandarin_written(update("zh"), upper)
    first, second = written.clauses
    assert (first.original, second.original) == ("我的頭髮", "發展")
    assert first.translations == {EN: "hair"}  # not Chinese: as it came
    assert second.translations == {Language("zh"): "發展"}  # 432
    assert first.links == {EN: (LINK,)}  # spans kept: one character for one
    assert written.caption_id == "c1" and written.language == "zh"


def test_mixed_captions_are_converted_but_japanese_and_cantonese_are_not() -> None:
    assert mandarin_written(update("en", "We had 头发"), upper).clauses[0].original == (
        "We had 頭髮"
    )
    for language in ("ja", "yue"):
        written = mandarin_written(update(language), upper)
        assert [c.original for c in written.clauses] == ["我的头发", "发展"]
        # its translation into Chinese is Mandarin all the same (432)
        assert written.clauses[1].translations == {Language("zh"): "發展"}


def second_line(said_in: str, key: str, line: str) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId("c3"),
        SourceId("app"),
        CaptionKind.FINISHED,
        clauses=(Clause("x", translations={Language(key): line}, links={EN: (LINK,)}),),
        language=Language(said_in),
        languages_heard=(Language(said_in),),
    )


def test_a_second_language_line_in_chinese_is_converted_too() -> None:
    """English heard in a window into English, Chinese its second language:
    the server keeps the Chinese line under English (protocol.md's
    `second_languages`) - the learner who chose Traditional saw it in
    Simplified (polyglotic-hq 432)."""
    seconds = {EN: Language("zh")}
    written = mandarin_written(second_line("en", "en", "头发"), upper, seconds)
    assert written.clauses[0].translations == {EN: "頭髮"}
    assert written.clauses[0].links == {EN: (LINK,)}
    # not without that second language, nor where the line is in the key's
    # own language (French heard: the line under English is English)
    assert mandarin_written(second_line("en", "en", "头发"), upper).clauses[
        0
    ].translations == {EN: "头发"}
    heard_fr = mandarin_written(second_line("fr", "en", "头发"), upper, seconds)
    assert heard_fr.clauses[0].translations == {EN: "头发"}


def test_other_scripts_lines_stay_as_they_came() -> None:
    """Japanese as Chinese's second language (kanji are not Mandarin), and
    a translation into Traditional Chinese (already Traditional)."""
    japanese = second_line("zh", "zh", "头发")
    seconds = {Language("zh"): Language("ja")}
    written = mandarin_written(japanese, upper, seconds)
    assert written.clauses[0].translations == {Language("zh"): "头发"}
    hant = mandarin_written(second_line("en", "zh-hant", "头发"), upper)
    assert hant.clauses[0].translations == {Language("zh-hant"): "头发"}


def test_a_withdrawal_passes_as_it_is() -> None:
    gone = CaptionUpdate(
        CaptionId("c2"),
        SourceId("app"),
        CaptionKind.WITHDRAWN,
        reason=WithdrawalReason.EMPTY,
    )
    assert mandarin_written(gone, upper) is gone


def test_the_session_converts_only_while_traditional_is_wanted() -> None:
    liao = "了 了 [liao3] /to finish; to understand/\n"
    dictionary = ChineseDictionary(chinese_sample(CEDICT_SAMPLE + liao))
    assert [e.reading for e in dictionary.lookup("了")][:2] == ["le", "liǎo"]
    script = MandarinScript(lambda: dictionary)
    plain = update("zh")
    assert dictionary.lookup("瞭")[0].variant_only
    assert script.caption(plain) is plain
    script.traditional = True
    shown = script.caption(plain)
    assert [c.original for c in shown.clauses] == ["我的頭髮", "發展"]
    assert shown.clauses[1].translations == {Language("zh"): "發展"}
    # a second-language line in Chinese, as the settings name it (432)
    line = second_line("en", "en", "头发")
    assert script.caption(line).clauses[0].translations == {EN: "头发"}
    script.seconds = {EN: Language("zh")}
    assert script.caption(line).clauses[0].translations == {EN: "頭髮"}
    # the dictionary now finds a converted word by its Simplified form: 瞭
    # (OpenCC's, in 瞭解) is only "variant of 了[liao3]" in CC-CEDICT
    found = dictionary.lookup("瞭")[0]
    assert found.reading == "liǎo" and not found.variant_only


def test_the_choice_is_kept_and_a_wrong_value_is_dropped() -> None:
    assert AppSettings().mandarin_script is None  # like this PC
    stored = AppSettings(mandarin_script="traditional").to_stored()
    assert AppSettings.from_stored(stored).mandarin_script == "traditional"
    assert (
        AppSettings.from_stored({"mandarin_script": "klingon"}).mandarin_script is None
    )


def test_taiwans_and_hong_kongs_windows_start_at_traditional() -> None:
    assert reads_traditional("en", ["en-AU", "zh-Hant-TW"])
    assert reads_traditional("en", ["zh-HK", "en-US"])
    assert reads_traditional("zh_TW", ["en-US"])  # the app's own language first
    assert not reads_traditional("zh_CN", ["zh-TW"])
    assert not reads_traditional("en", ["zh-Hans-CN", "zh-TW"])  # the first Chinese
    assert not reads_traditional("en", ["en-AU", "ja-JP"])
