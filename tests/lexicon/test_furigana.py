"""Furigana over Japanese (polyglotic-hq 511, 383's brief; 370 measured it):
kana over each word's kanji runs, the okurigana left out by matching, a
counter read by its number - from the word split's kana. Then the word
split's own reading (Sudachi small, the dictionary the app ships), with
its known misreadings put right. Made-up sentences."""

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.adapters.japanese_split import JapaneseSplit
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.furigana import (
    FuriganaReader,
    hiragana,
    readings_of,
)
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_split import SplitWord


def read(text: str, *words: tuple[str, str]) -> list[tuple[str, str, bool]]:
    """The furigana of `text` split into `words` (surface, kana), in order."""
    split, at = [], 0
    for surface, kana in words:
        at = text.index(surface, at)
        split.append(SplitWord(at, at + len(surface), kana=kana))
        at += len(surface)
    return [
        (text[r.start : r.end], r.text, r.ends_word)
        for word in split
        for r in readings_of(text, word)
    ]


def test_katakana_becomes_hiragana() -> None:
    assert hiragana("タベル・ラーメン") == "たべる・らーめん"


def test_the_kana_beside_the_kanji_is_left_out() -> None:
    assert read("食べました", ("食べ", "タベ")) == [("食", "た", True)]
    assert read("美味しい", ("美味しい", "オイシイ")) == [("美味", "おい", True)]
    assert read("お茶", ("お茶", "オチャ")) == [("茶", "ちゃ", True)]


def test_each_run_of_kanji_in_a_word_has_its_own_reading() -> None:
    assert read("取り扱い", ("取り扱い", "トリアツカイ")) == [
        ("取", "と", False),
        ("扱", "あつか", True),
    ]


def test_no_reading_without_kanji_or_kana() -> None:
    assert read("ラーメンです", ("ラーメン", "ラーメン"), ("です", "デス")) == []
    assert read("謎", ("謎", "")) == []


def test_a_reading_that_wont_match_goes_over_the_word() -> None:
    """1人 is ひとり: the digit is read too, so it can't be matched."""
    assert read("1人で", ("1人", "ヒトリ")) == [("1人", "ひとり", True)]
    # the kana it starts and ends with stay out
    assert read("お土産を", ("お土産", "オミヤゲ")) == [("土産", "みやげ", True)]


def test_a_counter_is_read_by_the_number_before_it() -> None:
    """Sudachi small reads 本 ぽん and 分 ふん after any number."""
    assert read("2本", ("2", "ニ"), ("本", "ポン")) == [("本", "ほん", True)]
    assert read("1本", ("1", "イチ"), ("本", "ポン")) == [("本", "ぽん", True)]
    assert read("3本", ("3", "サン"), ("本", "ポン")) == [("本", "ぼん", True)]
    assert read("10分", ("10", "イチレイ"), ("分", "フン")) == [("分", "ぷん", True)]
    assert read("４分", ("４", "ヨン"), ("分", "フン")) == [("分", "ぷん", True)]
    assert read("5分", ("5", "ゴ"), ("分", "フン")) == [("分", "ふん", True)]
    assert read("21対20", ("21", "ニイチ"), ("対", "ツイ"), ("20", "ニレイ")) == [
        ("対", "たい", True)
    ]
    # not after a number: its own reading
    assert read("本が", ("本", "ホン")) == [("本", "ほん", True)]


# -- the word split's kana, by Sudachi small ------------------------------------------


def furigana(text: str) -> list[tuple[str, str]]:
    pack = BasicDictionary(FakeDictionaryFile([], {}), JapaneseSplit(), "ja")
    reader = FuriganaReader(pack)
    return [(text[r.start : r.end], r.text) for r in reader.readings(text)]


def test_sudachi_gives_each_words_kana() -> None:
    assert furigana("友達と東京で飲みました") == [
        ("友達", "ともだち"),
        ("東京", "とうきょう"),
        ("飲", "の"),
    ]


def test_a_people_or_a_rivers_name_is_read_as_one() -> None:
    """370: Sudachi small reads 人 にん and 川 かわ after a name."""
    assert furigana("日本人とアラブ人と外国人") == [
        ("日本", "にほん"),
        ("人", "じん"),
        ("人", "じん"),
        ("外国", "がいこく"),
        ("人", "じん"),
    ]
    assert furigana("アマゾン川") == [("川", "がわ")]
    assert furigana("管理人") == [("管理", "かんり"), ("人", "にん")]


def test_the_everyday_reading_not_sudachis() -> None:
    assert furigana("私は明日、月曜日に言う") == [
        ("私", "わたし"),
        ("明日", "あした"),
        ("月曜", "げつよう"),
        ("日", "び"),
        ("言", "い"),
    ]


# -- words the pack has as one ---------------------------------------------------------


def joined(
    text: str, split: list[tuple[str, str, str]], *heads: tuple[str, str]
) -> list[tuple[str, str]]:
    records = [
        EntryRecord(f"jmdict:{n}", h, "", kana, ("x",), 100)
        for n, (h, kana) in enumerate(heads)
    ]
    forms: dict[str, list[str]] = {}
    for record in records:
        forms.setdefault(record.headword, []).append(record.entry_id)
    pack = FakeDictionaryFile(records, forms)

    class Cut:
        def words(self, line: str) -> list[SplitWord]:
            found, at = [], 0
            for surface, kana, lemma in split:
                at = line.index(surface, at)
                found.append(
                    SplitWord(
                        at, at + len(surface), (lemma,) if lemma else (), kana=kana
                    )
                )
                at += len(surface)
            return found

    reader = FuriganaReader(BasicDictionary(pack, Cut(), "ja"))
    return [(text[r.start : r.end], r.text) for r in reader.readings(text)]


def test_a_compound_the_split_cut_is_read_as_the_pack_reads_it() -> None:
    """Sudachi small cuts 辛抱強く into 辛抱 and 強く and reads つよ: the pack
    has 辛抱強い, said しんぼうづよい - a compound's sound change."""
    split = [("辛抱", "シンボウ", ""), ("強く", "ツヨク", "強い")]
    assert joined("辛抱強く", split) == [("辛抱", "しんぼう"), ("強", "つよ")]
    assert joined("辛抱強く", split, ("辛抱強い", "しんぼうづよい")) == [
        ("辛抱強", "しんぼうづよ")
    ]


def test_only_kanji_meeting_kanji_and_one_reading_join() -> None:
    # a particle between: not a compound
    split = [("雨", "アメ", ""), ("が", "ガ", ""), ("降る", "フル", "")]
    assert joined("雨が降る", split, ("雨が降る", "あめがふる")) == [
        ("雨", "あめ"),
        ("降", "ふ"),
    ]
    # two readings in the pack: the split's own
    split = [("一", "イチ", ""), ("日", "ニチ", "")]
    pack = (("一日", "いちにち"), ("一日", "ついたち"))
    assert joined("一日", split, *pack) == [("一", "いち"), ("日", "にち")]
