"""Mandarin's captions in the script the learner reads (polyglotic-hq 375;
decision 0164): each caption's Mandarin converted as it arrives - its
originals only, never a translation or a Japanese or Cantonese caption -
the choice kept in the settings, and Taiwan's and Hong Kong's Windows
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


def test_mandarins_originals_are_converted_and_nothing_else() -> None:
    written = mandarin_written(update("zh"), upper)
    first, second = written.clauses
    assert (first.original, second.original) == ("我的頭髮", "發展")
    assert first.translations == {EN: "hair"}  # a translation stays as picked
    assert second.translations == {Language("zh"): "发展"}
    assert first.links == {EN: (LINK,)}  # spans kept: one character for one
    assert written.caption_id == "c1" and written.language == "zh"


def test_mixed_captions_are_converted_but_japanese_and_cantonese_are_not() -> None:
    assert mandarin_written(update("en", "We had 头发"), upper).clauses[0].original == (
        "We had 頭髮"
    )
    for language in ("ja", "yue"):
        assert mandarin_written(update(language), upper) == update(language)


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
