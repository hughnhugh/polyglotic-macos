import pytest

from polyglotic_desktop.core.lexicon.romaji import romaji


@pytest.mark.parametrize(
    ("kana", "expected"),
    [
        ("たべた", "tabeta"),
        ("がっこう", "gakkō"),
        ("とうきょう", "tōkyō"),
        ("ほん", "hon"),
        ("げんいん", "gen'in"),
        ("こんにちは", "konnichiwa"),
        ("を", "o"),
        ("コーヒー", "kōhī"),
        ("ティー", "tī"),
        ("ちょっと", "chotto"),
        ("きゃ", "kya"),
        ("きゅ", "kyu"),
        ("きょ", "kyo"),
        ("しゃ", "sha"),
        ("しゅ", "shu"),
        ("しょ", "sho"),
        ("ちゃ", "cha"),
        ("ちゅ", "chu"),
        ("ちょ", "cho"),
        ("にゃ", "nya"),
        ("ひゃ", "hya"),
        ("みゃ", "mya"),
        ("りゃ", "rya"),
        ("ぎゃ", "gya"),
        ("じゃ", "ja"),
        ("びゃ", "bya"),
        ("ぴゃ", "pya"),
        ("まっちゃ", "matcha"),
        ("きって", "kitte"),
        ("ざっし", "zasshi"),
        ("いっつう", "ittsū"),
        ("あんない", "annai"),
        ("しんよう", "shin'yō"),
        ("かんい", "kan'i"),
        ("しんあい", "shin'ai"),
        ("ぢ", "ji"),
        ("づ", "zu"),
        ("ふぁ", "fa"),
        ("ふぃ", "fi"),
        ("ふぇ", "fe"),
        ("ふぉ", "fo"),
        ("てぃ", "ti"),
        ("でぃ", "di"),
        ("とぅ", "tu"),
        ("どぅ", "du"),
        ("つぁ", "tsa"),
        ("つぃ", "tsi"),
        ("つぇ", "tse"),
        ("つぉ", "tso"),
        ("うぃ", "wi"),
        ("うぇ", "we"),
        ("うぉ", "wo"),
        ("ヴァ", "va"),
        ("ヴィ", "vi"),
        ("ヴェ", "ve"),
        ("ヴォ", "vo"),
        ("シェ", "she"),
        ("ジェ", "je"),
        ("チェ", "che"),
        ("おおきい", "ōkii"),
        ("くうき", "kūki"),
        ("スーパー", "sūpā"),
        ("パーティー", "pātī"),
        ("ABCかな", "ABCkana"),
        ("ゐ", "wi"),
        ("ゑ", "we"),
    ],
)
def test_modified_hepburn(kana: str, expected: str) -> None:
    assert romaji(kana) == expected


@pytest.mark.parametrize(("kana", "expected"), [("は", "wa"), ("へ", "e"), ("を", "o")])
def test_particles_use_their_spoken_form(kana: str, expected: str) -> None:
    assert romaji(kana, particle=True) == expected


def test_non_particle_ha_and_he_keep_lexical_reading() -> None:
    assert romaji("は") == "ha"
    assert romaji("へ") == "he"
