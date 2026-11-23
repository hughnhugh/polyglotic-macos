"""A language's name reads right in the middle of a sentence, in every
interface language: "Decirla en inglés", not "en Inglés"; "голос для языка
«английский»", not "для языка английский" (polyglotic-hq 560, after 551
found about 50 such strings)."""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale
from tools.i18n import __main__ as i18n
from tools.i18n import ts

from polyglotic_desktop.ui.interface_language import ENGLISH, OFFERED
from polyglotic_desktop.ui_next.languages import in_sentence

SRC = Path(__file__).parents[2] / "src" / "polyglotic_desktop"
NAMED = re.compile(r"\{languages?\}")
LOWER_IN_SENTENCE = ("es", "fr", "it", "pt_BR", "cs", "pl", "ru", "uk", "vi")
# A few names to write each string with: one word, a qualified one, one
# that starts with a vowel (French's and Italian's articles), Mandarin
NAME = re.compile(r"[A-Z][a-z]+( \([A-Z][a-z]+( [a-z]+)*\))?$")
"""A language's name, as a source string: "Arabic", "Mandarin (Simplified
characters)" - not "Always hear as"."""
SAMPLES = ("English", "Chinese (Traditional)", "Arabic", "Mandarin")


@pytest.fixture
def interface() -> Iterator[None]:
    before = QLocale()
    yield
    QLocale.setDefault(before)


def speaks(language: str) -> None:
    """The interface's language, as `ui.interface_language.install` sets it."""
    QLocale.setDefault(QLocale(language))


def test_a_name_mid_sentence_is_in_lower_case(interface: None) -> None:
    speaks("es")
    assert in_sentence("Decirla en {language}", language="Inglés") == (
        "Decirla en inglés"
    )
    assert in_sentence(
        "¿Aprendes también {language}?", language="Chino (tradicional)"
    ) == ("¿Aprendes también chino (tradicional)?")


def test_a_name_that_starts_a_sentence_keeps_its_capital(interface: None) -> None:
    speaks("es")
    assert in_sentence(
        "{language}: versión {version}", language="Inglés", version=2
    ) == ("Inglés: versión 2")
    assert (
        in_sentence(
            "El diccionario de {language} se usa en cuanto aprendas {language}. "
            "{language} sigue.",
            language="Inglés",
        )
        == "El diccionario de inglés se usa en cuanto aprendas inglés. Inglés sigue."
    )
    assert in_sentence("¿{language}?", language="Inglés") == "¿Inglés?"


def test_vietnamese_lowers_only_tieng(interface: None) -> None:
    speaks("vi")
    assert (
        in_sentence("Đọc bằng {language}", language="Tiếng Anh") == "Đọc bằng tiếng Anh"
    )


def test_a_list_of_names_is_in_lower_case_after_its_first(interface: None) -> None:
    speaks("es")
    assert (
        in_sentence(
            "subtítulos en {languages}", languages=["Inglés", "Chino (simplificado)"]
        )
        == "subtítulos en inglés y chino (simplificado)"
    )
    assert in_sentence("{languages}.", languages=["Mongol", "Kazajo"]) == (
        "Mongol y kazajo."
    )


@pytest.mark.parametrize("language", ["en", "de", "nl", "id", "ja"])
def test_languages_that_dont_lower_a_name_keep_it(
    language: str, interface: None
) -> None:
    speaks(language)
    assert (
        in_sentence("Say it in {language}", language="English") == "Say it in English"
    )
    assert in_sentence("Auf {language} vorsprechen", language="Spanisch") == (
        "Auf Spanisch vorsprechen"
    )


def test_the_other_names_are_filled_as_format_fills_them(interface: None) -> None:
    speaks("fr")
    assert (
        in_sentence(
            "{language} : {size!r} {count:>3}", language="Anglais", size="5", count=7
        )
        == "Anglais : '5'   7"
    )


def test_every_name_in_the_interface_goes_through_in_sentence() -> None:
    """No `.format(language=...)` is left in the new interface or `main`:
    a name filled there would keep its list capital mid-sentence."""
    files = [SRC / "main.py", *sorted((SRC / "ui_next").rglob("*.py"))]
    formatted = [
        f"{file.name}:{node.lineno}"
        for file in files
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and any(k.arg in ("language", "languages") for k in node.keywords)
    ]
    assert formatted == []


def strings(language: str) -> list[tuple[str, str]]:
    """(English, translation) of every string a language's name fills, in
    `language`'s file - each form of a count."""
    file = ts.read(i18n.ts_path(language))
    return [
        (source, form)
        for (_context, source, _comment), translation in file.translations.items()
        if NAMED.search(source)
        for form in translation.forms
    ]


def names(language: str) -> list[str]:
    """SAMPLES as `language` names them in a list."""
    file = ts.read(i18n.ts_path(language))
    found = {
        source: translation.forms[0]
        for (context, source, _comment), translation in file.translations.items()
        if context == "Languages" and source in SAMPLES
    }
    return [found[sample] for sample in SAMPLES]


def test_the_strings_with_a_name_are_all_found() -> None:
    assert len(strings("es")) >= 49


@pytest.mark.parametrize("language", LOWER_IN_SENTENCE)
def test_no_name_keeps_its_capital_mid_sentence(language: str, interface: None) -> None:
    """Every string a name fills, written with several names: a capital
    name only where a sentence starts."""
    speaks(language)
    wrong = []
    for source, form in strings(language):
        for name in names(language):
            others: dict[str, object] = {
                field: "9" for field in re.findall(r"\{(\w+)\}", form)
            }
            others.update(language=name, languages=[name])
            text = in_sentence(form, **others)
            for found in re.finditer(re.escape(name), text):
                before = re.split(r"[.!?…]\s", text[: found.start()])[-1]
                if any(char.isalnum() for char in before):
                    wrong.append((source, text))
    assert wrong == []


# The words a language puts before a bare name that a nominative can't
# follow: prepositions that take another case, and "language" in another
# case ("для языка английский" - Russian wants "для языка «английский»");
# French's and Italian's articles, which elide before a vowel ("le anglais")
WRONG_BEFORE = {
    "cs": r"v|ve|pro|z|ze|na|o|k|ke|s|se|u|bez|od|po|při",
    "pl": r"w|we|z|ze|dla|na|o|po|od|bez|przy|przez|u|języka|językiem|języku",
    "ru": r"в|во|для|из|на|о|об|по|с|со|к|ко|у|от|без|до|при|языка|языку|языком|языке",
    "uk": r"в|у|для|з|із|зі|на|по|до|від|без|при|про|мови|мову|мовою|вчити|вчите|й|і",
    "fr": r"le|la|de|du|que",
    "it": r"il|lo|la|del|dello|della|al|allo|nel|per",
}


@pytest.mark.parametrize("language", sorted(WRONG_BEFORE))
def test_a_bare_name_follows_only_words_its_case_fits(language: str) -> None:
    pattern = re.compile(
        rf"(?<!\w)(?:{WRONG_BEFORE[language]}) \{{languages?\}}", re.IGNORECASE
    )
    wrong = [form for _source, form in strings(language) if pattern.search(form)]
    assert wrong == []


def test_turkish_says_de_after_dili_not_after_a_name() -> None:
    """Turkish's "de"/"da" follows the vowel before it: "İngilizce de",
    "Rusça da" - after a name it would be wrong for half of them."""
    wrong = [
        form
        for _source, form in strings("tr")
        if re.search(r"\{languages?\} d[ea]\b", form)
    ]
    assert wrong == []


def test_korean_names_take_the_particle_after_a_vowel() -> None:
    """Every Korean language name ends in a syllable without a final
    consonant ("영어", "중국어(번체)"), so a name takes 를, 가, 는, 로 -
    not "을(를)", the form for a word nobody knows."""
    file = ts.read(i18n.ts_path("ko"))
    syllables = [
        [char for char in translation.forms[0] if "가" <= char <= "힣"]
        for (context, source, _c), translation in file.translations.items()
        if context in ("Languages", "LearningLanguage") and NAME.match(source)
    ]
    closed = [s for s in syllables if s and (ord(s[-1]) - ord("가")) % 28]
    both = [
        f
        for _s, f in strings("ko")
        if re.search(r"\}(을\(를\)|이\(가\)|은\(는\)|\(으\)로)", f)
    ]
    assert (closed, both) == ([], [])


@pytest.mark.parametrize("language", ["id", "ms"])
def test_indonesian_and_malay_say_bahasa_before_a_name_in_a_sentence(
    language: str,
) -> None:
    """ "dalam bahasa Spanyol", "ke bahasa Spanyol": the list's bare
    "Spanyol" is the country's people after a preposition."""
    pattern = re.compile(r"\b(dalam|ke|berbicara|bercakap) \{languages?\}")
    assert [f for _s, f in strings(language) if pattern.search(f)] == []


def test_the_old_level_picker_starts_with_the_name() -> None:
    """`ui.level_picker` can't use `in_sentence` (`ui` doesn't import
    `ui_next`): its question keeps the name first, where its capital is
    right, in every language that lowers a name mid-sentence."""
    question = "About how many {language} words do you know?"
    late = [
        (language, form)
        for language in LOWER_IN_SENTENCE
        for source, form in strings(language)
        if source == question and not form.startswith("{language}")
    ]
    assert late == []


def test_every_offered_language_was_checked() -> None:
    checked = {*LOWER_IN_SENTENCE, *WRONG_BEFORE, "tr", "ko", "id", "ms"}
    left = set(OFFERED) - {ENGLISH} - checked
    # their names need no other form in a sentence: German's and Dutch's
    # nouns keep their capital, Filipino uses English's, and Hindi,
    # Thai, Japanese and Chinese have no case and no particle that
    # changes with the name
    assert left == {"de", "nl", "fil", "hi", "th", "ja", "zh_CN", "zh_TW"}
