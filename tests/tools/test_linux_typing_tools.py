"""What 571's typing check counts as typed (tools/linux_typing_check.py) -
the check itself runs on GitHub's Linux runners."""

from tools import linux_typing_check


def _case(name: str) -> linux_typing_check.Case:
    return next(c for c in linux_typing_check.cases("ibus") if c.name == name)


def test_chinese_counts_only_as_the_words_meant() -> None:
    pinyin = _case("pinyin")
    assert linux_typing_check.typed("你好", pinyin)
    assert not linux_typing_check.typed("nihao ", pinyin)
    assert not linux_typing_check.typed("にほんご", pinyin)


def test_japanese_counts_as_typed_in_kana_before_its_conversion() -> None:
    japanese = _case("japanese")
    assert linux_typing_check.typed("日本語", japanese)
    assert linux_typing_check.typed("にほんご", japanese)
    assert not linux_typing_check.typed("nihongo", japanese)


def test_each_mode_types_its_frameworks_pinyin() -> None:
    assert [c.name for c in linux_typing_check.cases("ibus")] == ["pinyin", "japanese"]
    assert [c.name for c in linux_typing_check.cases("ibus-unnamed")] == ["pinyin"]
    assert [c.name for c in linux_typing_check.cases("fcitx5")] == [
        "pinyin",
        "japanese",
    ]
    fcitx5 = linux_typing_check.cases("fcitx5-kubuntu")
    assert [c.name for c in fcitx5] == ["pinyin"]
    assert fcitx5[0].attempts[0].engine == (("fcitx5-remote", "-s", "pinyin"),)
