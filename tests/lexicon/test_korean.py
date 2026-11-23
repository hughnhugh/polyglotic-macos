"""Korean words to what a dictionary lists them by (core.lexicon.korean_forms;
polyglotic-hq 510): particles off a noun, endings off a verb or an
adjective, the least cut off first."""

from polyglotic_desktop.core.lexicon.korean_forms import bases, bases_after_bracket


def test_a_noun_without_its_particles() -> None:
    assert bases("학교에서")[0] == "학교"
    assert bases("학생들은")[:2] == ("학생들", "학생")  # the plural, then the noun
    assert "사람" in bases("사람이")
    assert "친구" in bases("친구예요")
    assert "서울" in bases("서울에서부터")


def test_a_verb_or_adjective_as_its_dictionary_form() -> None:
    assert "먹다" in bases("먹었는데")
    assert "가다" in bases("갔어요")  # 가 + 았어요
    assert "하다" in bases("했지만")  # 하 + 였지만
    assert "보다" in bases("봐요")  # 보 + 아요
    assert "마시다" in bases("마셨다")  # 마시 + 었다
    assert "가다" in bases("갑니다")  # 가 + ㅂ니다
    assert "가다" in bases("간다")  # 가 + ㄴ다
    assert "크다" in bases("큰데")  # 크 + ㄴ데
    assert "공부하다" in bases("공부했고")
    assert "가다" in bases("가셨다")  # the honorific's past


def test_the_irregular_stems_it_guesses() -> None:
    assert "덥다" in bases("더워요")  # ㅂ
    assert "듣다" in bases("들어요")  # ㄷ
    assert "살다" in bases("사는")  # ㄹ, lost before ㄴ


def test_a_one_syllable_stem_is_a_verb_first_a_longer_one_a_noun() -> None:
    assert bases("먹는")[0] == "먹다"  # not 먹, ink
    assert bases("학교는")[0] == "학교"


def test_only_hangul_and_never_the_word_itself() -> None:
    assert bases("Seoul") == () and bases("") == ()
    assert "학교" not in bases("학교")


def test_a_merged_infinitive_and_a_noun_with_hada_or_jeok() -> None:
    assert "통하다" in bases("통해")  # 통하 + 여, no ending after it
    assert "중요" in bases("중요한")  # 중요하다, if the dictionary hasn't got it
    assert bases("중요한").index("중요하다") < bases("중요한").index("중요")
    assert "세계" in bases("세계적으로")


def test_the_copulas_forms_and_a_noun_made_a_verb() -> None:
    assert "장소" in bases("장소인")  # 인: the copula, before a noun
    assert "포식자" in bases("포식자였으므로")
    assert "마무리" in bases("마무리되었으며")  # 마무리되다, if not listed
    assert "독립" in bases("독립적인")
    assert "유전" in bases("유전적")


def test_more_irregular_stems_contractions_and_adverbs() -> None:
    assert "따르다" in bases("따라")
    assert "모르다" in bases("몰라")
    assert "바쁘다" in bases("바빠")
    assert "굽다" in bases("구운")  # ㅂ: 구우 + ㄴ
    assert bases("이건")[0] == "이것"
    assert "단호" in bases("단호히")
    assert "이득" in bases("이득일")


def test_particles_on_particles_come_off_in_turn() -> None:
    """A particle after a particle or the copula (polyglotic-hq 516): 월까지이다
    is 월 + 까지 + 이다; 것인지는 것 + 인지 + 는."""
    assert "월" in bases("월까지이다")
    assert "것" in bases("것인지는")
    assert "돌연변이" in bases("돌연변이만이")
    assert "것" in bases("것이라면서")


def test_more_endings_the_probe_met() -> None:
    assert "하다" in bases("한다는")  # 하 + ㄴ다는
    assert "가다" in bases("간다면")  # 가 + ㄴ다면
    assert "찍다" in bases("찍으려")  # 찍 + 으려
    assert "의도" in bases("의도치")  # 의도하지, written short
    assert "숨기다" in bases("숨겨지거나")  # 숨기 + 어지다: passive
    assert "의미" in bases("의미있는")  # 의미 있는, written closed


def test_a_particle_alone_is_looked_up_as_the_dictionarys_particle() -> None:
    """After a quote or a bracket a particle stands alone ('브로드사이드'라고):
    the dictionary lists it with a hyphen, -라고 (polyglotic-hq 516)."""
    assert bases("라고")[0] == "-라고"
    assert bases("에서")[0] == "-에서"
    assert bases("는다")[0] == "-는다"  # an ending
    assert "-학교" not in bases("학교")


def test_hae_is_hadas_before_any_other_stem() -> None:
    """했다 and 해 are 하다's (하 + 였, 하 + 여): 해다, a rare spelling, had
    come first and 했다 opened on "newborn baby" (polyglotic-hq 516)."""
    assert bases("했다").index("하다") < bases("했다").index("해다")
    assert bases("해서").index("하다") < bases("해서").index("해다")
    assert bases("냈다").index("내다") < bases("냈다").index("나다")  # 내 + 었


def test_only_a_particle_that_comes_last_is_taken_off_another() -> None:
    assert "고속" not in bases("고속도로")  # expressway: not 고속 + 도 + 로
    assert "학교" in bases("학교에서도")


def test_a_common_noun_of_one_syllable_with_its_particle_is_the_noun() -> None:
    """일을, 물을, 집을 are 일 (work), 물 (water), 집 (house) with 을: they
    had opened on 일다 (to rise), 묻다 (to ask), 집다 (to pick up)
    (polyglotic-hq 516). A stem in ㄹ takes no ending in 으 (살다 + 을 is
    살, not 살을), so 말을 is never 말다's; 먹은 and 먹는 stay 먹다's."""
    assert bases("일을")[0] == "일"
    assert bases("물을")[0] == "물"
    assert bases("집을")[0] == "집"
    assert bases("길을")[0] == "길"
    assert "말다" not in bases("말을") and "일다" not in bases("일을")
    assert bases("먹은")[0] == "먹다" and bases("먹는")[0] == "먹다"
    assert "듣다" in bases("들으면")  # ㄷ's ㄹ before 으 stays


def test_a_particle_after_a_bracket_is_the_words_before_it() -> None:
    """'파티마 대성당(성지)이' - the split cuts 이 off at the bracket: it is
    the subject particle, -이, not 이 ("this") (polyglotic-hq 516)."""
    from polyglotic_desktop.adapters.spaced_split import SpacedSplit

    line = "대성당(성지)이 있다. 그 이 사람"
    words = {line[w.start : w.end]: w for w in SpacedSplit("ko").words(line)}
    assert words["이"].lemmas == ()  # 그 이 사람: no bracket before it
    after = [w for w in SpacedSplit("ko").words(line) if line[w.start - 1] == ")"]
    assert [w.lemmas for w in after] == [("-이",)]
    assert bases_after_bracket("는") == ("-는",) and bases_after_bracket("학교") == ()


def test_a_verb_with_a_prefix_the_dictionary_hasnt_got_is_its_verb() -> None:
    assert "뿜다" in bases("내뿜는")  # 내- (out) + 뿜다 (spout)
    assert "돌다" in bases("되돌아")
