"""A selection read aloud in its spoken form (`core.listening.read_aloud`,
polyglotic-hq 495 from 488's read-back): mended only at caption cuts - a
syllable or word said on both sides said once, a cut's stray full stop or
capital taken out; fillers gone; years read as years; read a sentence at a
time; and each character of the spoken form knowing where in the selection
it came from, so the word being said lights there. Real captions from 459's
and 453's FLEURS runs (488's `texts488.py`)."""

from polyglotic_desktop.core.listening.read_aloud import Stretch, read_aloud


def spoken(language: str, *captions: str) -> str:
    """Captions one after another (a cut between each), spoken."""
    return read_aloud(
        [Stretch(text, key) for key, text in enumerate(captions)], language
    ).text


def test_a_syllable_said_on_both_sides_of_a_cut_is_said_once() -> None:
    assert (
        spoken(
            "zh",
            "因为远离大陆，哺乳动物无法长途跋涉而来，使得巨龟成为克隆群岛主",
            "主要的食草动物。",
        )
        == "因为远离大陆，哺乳动物无法长途跋涉而来，使得巨龟成为克隆群岛主要的食草动物。"
    )


def test_a_repeat_away_from_a_cut_stays() -> None:
    assert spoken("zh", "谢谢你。") == "谢谢你。"
    assert spoken("zh", "我们看看", "吧。") == "我们看看吧。"


def test_a_cuts_full_stop_mid_sentence_goes() -> None:
    assert spoken(
        "es",
        "El uso adecuado de los blogs puede empoderar a los alumnos para que "
        "sean más analíticos y críticos.",
        "a través de la respuesta activa a los contenidos de Internet.",
    ) == (
        "El uso adecuado de los blogs puede empoderar a los alumnos para que sean "
        "más analíticos y críticos a través de la respuesta activa a los "
        "contenidos de Internet."
    )


def test_a_cuts_capital_mid_sentence_is_lowered_but_a_name_keeps_its_own() -> None:
    assert spoken(
        "en",
        "to help countries affected by global warming to cope",
        "With the impacts.",
    ) == ("to help countries affected by global warming to cope with the impacts.")
    assert spoken("en", "a fund to help", "Africa.") == "a fund to help Africa."


def test_a_word_said_on_both_sides_of_a_cut_is_said_once() -> None:
    assert spoken("en", "hopes to cope", "cope with it.") == "hopes to cope with it."


def test_one_caption_is_not_mended() -> None:
    together = [Stretch("hopes to cope", 1), Stretch("cope With it.", 1)]
    assert read_aloud(together, "en").text == "hopes to cope cope With it."


def test_fillers_go() -> None:
    assert (
        spoken("en", "The UN, um, also hopes to finalize, uh, a fund.")
        == "The UN also hopes to finalize a fund."
    )
    assert spoken("en", "Um, I think so.") == "I think so."
    assert (
        spoken("zh", "嗯，亚马逊河也是，呃，地球上最宽的河流。")
        == "亚马逊河也是，地球上最宽的河流。"
    )


def test_words_that_are_also_fillers_elsewhere_stay() -> None:
    assert spoken("zh", "金额不对啊。") == "金额不对啊。"
    assert spoken("zh", "嗯哪个？") == "嗯哪个？"  # not alone: a word's start
    assert spoken("en", "5 mm of rain, umbrella.") == "5 mm of rain, umbrella."


def test_years_are_read_as_years_in_english() -> None:
    made = spoken(
        "en",
        "In the end, wooden wheels were replaced by iron wheels. 1767. "
        "The first all-iron track was introduced in 1767.",
    )
    assert made == (
        "In the end, wooden wheels were replaced by iron wheels. seventeen "
        "sixty-seven. The first all-iron track was introduced in seventeen "
        "sixty-seven."
    )
    assert spoken("en", "Since 1900, and by 1905.") == (
        "Since nineteen hundred, and by nineteen oh five."
    )
    assert spoken("en", "in 1066.") == "in ten sixty-six."


def test_a_count_stays_a_count() -> None:
    for text in (
        "1767 people came.",
        "It costs $1767.",
        "About 1,767 of them.",
        "In 1767.5 seconds.",
        "In 2026.",
        "in 1005.",
    ):
        assert spoken("en", text) == text


def test_a_chinese_year_is_read_digit_by_digit() -> None:
    assert (
        spoken("zh", "1767年，第一条全铁轨道问世。")
        == "一七六七年，第一条全铁轨道问世。"
    )
    assert spoken("zh", "他有1767个。") == "他有1767个。"
    assert spoken("ja", "1767年です。") == "1767年です。"  # 千七百... is right


def test_it_is_read_a_sentence_at_a_time() -> None:
    made = read_aloud(
        [
            Stretch("最终，木轮被铁轮所取代。一七六七年。", 0),
            Stretch("第一条全铁轨道问世。", 1),
        ],
        "zh",
    )
    assert made.chunk_texts() == (
        "最终，木轮被铁轮所取代。",
        "一七六七年。",
        "第一条全铁轨道问世。",
    )
    english = read_aloud(
        [Stretch("He met Dr. Smith in St. Peter's Square. It was 1.5 km away! Yes", 0)],
        "en",
    )
    assert english.chunk_texts() == (
        "He met Dr. Smith in St. Peter's Square.",
        "It was 1.5 km away!",
        "Yes",
    )


def test_each_word_said_lights_where_the_selection_shows_it() -> None:
    stretches = [Stretch("  the giant turtle", 4), Stretch("turtle eats. Then", 5)]
    made = read_aloud(stretches, "en")
    assert made.text == "the giant turtle eats. Then"
    first, second = made.chunks
    assert made.came_from(0, 4, 9) == ((0, 6, 11),)  # "giant", after the spaces
    eats = made.text.index("eats") - first[0]
    assert made.came_from(0, eats, eats + 4) == ((1, 7, 11),)
    assert made.came_from(1, 0, 4) == ((1, 13, 17),)  # "Then"
    assert made.came_from(0, 0, second[1]) == ((0, 2, 18), (1, 7, 12))
    assert made.came_from(5, 0, 1) == ()


def test_a_year_said_in_words_lights_its_figures() -> None:
    made = read_aloud([Stretch("Built in 1767.", 0)], "en")
    assert made.text == "Built in seventeen sixty-seven."
    at = made.text.index("sixty")
    assert made.came_from(0, at, at + len("sixty-seven")) == ((0, 9, 13),)


def test_nothing_to_say() -> None:
    made = read_aloud([Stretch("  ", 0)], "en")
    assert made.text == ""
    assert made.chunks == ()
