"""Languages by name, for the new interface: the caption window's language
chip, the language spoken above a caption, and the Languages panel's
choices and notes.

The same names, codes and order as today's `ui.languages` (which this
package can't import - decision 0031; that module goes when `ui/` does).
The codes are protocol.md's; the names go through Qt's translation tools,
in the same "Languages" context, so one translation serves both.
"""

import re
import string
import unicodedata
from collections.abc import Iterable, Sequence

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QLocale

from polyglotic_desktop.core.listening.captions import Language

_CONTEXT = "Languages"

# code -> English name; translated where shown
_NAMES = {
    "en": QT_TRANSLATE_NOOP("Languages", "English"),
    "zh": QT_TRANSLATE_NOOP("Languages", "Chinese (Simplified)"),
    "zh-hant": QT_TRANSLATE_NOOP("Languages", "Chinese (Traditional)"),
    "yue": QT_TRANSLATE_NOOP("Languages", "Cantonese"),
    "fr": QT_TRANSLATE_NOOP("Languages", "French"),
    "pt": QT_TRANSLATE_NOOP("Languages", "Portuguese"),
    "es": QT_TRANSLATE_NOOP("Languages", "Spanish"),
    "ja": QT_TRANSLATE_NOOP("Languages", "Japanese"),
    "tr": QT_TRANSLATE_NOOP("Languages", "Turkish"),
    "ru": QT_TRANSLATE_NOOP("Languages", "Russian"),
    "ar": QT_TRANSLATE_NOOP("Languages", "Arabic"),
    "ko": QT_TRANSLATE_NOOP("Languages", "Korean"),
    "th": QT_TRANSLATE_NOOP("Languages", "Thai"),
    "it": QT_TRANSLATE_NOOP("Languages", "Italian"),
    "de": QT_TRANSLATE_NOOP("Languages", "German"),
    "vi": QT_TRANSLATE_NOOP("Languages", "Vietnamese"),
    "ms": QT_TRANSLATE_NOOP("Languages", "Malay"),
    "id": QT_TRANSLATE_NOOP("Languages", "Indonesian"),
    "tl": QT_TRANSLATE_NOOP("Languages", "Filipino"),
    "hi": QT_TRANSLATE_NOOP("Languages", "Hindi"),
    "pl": QT_TRANSLATE_NOOP("Languages", "Polish"),
    "cs": QT_TRANSLATE_NOOP("Languages", "Czech"),
    "nl": QT_TRANSLATE_NOOP("Languages", "Dutch"),
    "uk": QT_TRANSLATE_NOOP("Languages", "Ukrainian"),
}
# How a spoken language is named: Chinese speech is "Mandarin" - its
# target's name describes a script.
_SPOKEN = {"zh": QT_TRANSLATE_NOOP("Languages", "Mandarin"), "yue": "Cantonese"}
# DECISIONS.md #40, as today's `ui.languages` says it. No line says which
# spoken languages are captioned less accurately (#23's note): the user
# asked it gone, 2026-11-13
_NOT_OFFERED_NOTE = QT_TRANSLATE_NOOP(
    "Languages",
    "Mongolian and Kazakh aren't offered yet: the translation model writes "
    "them in a script most of their speakers don't read.",
)
# Offered once and taken off (#40): a saved choice of one falls back, and
# Home says so once (polyglotic-hq projects 088 and 144)
_TAKEN_OFF = {
    "mn": QT_TRANSLATE_NOOP("Languages", "Mongolian"),
    "kk": QT_TRANSLATE_NOOP("Languages", "Kazakh"),
}
_TAKEN_OFF_NOTE = QT_TRANSLATE_NOOP(
    "Languages",
    "Taken off your caption windows' languages, as they aren't offered any "
    "more: {languages}.",
)


def _tr(text: object) -> str:
    return QCoreApplication.translate(_CONTEXT, str(text))


def name_list(names: Iterable[str]) -> str:
    """Names in a list as the interface's language writes one: "Mongolian
    and Kazakh", "蒙古语和哈萨克语" (decision 0034)."""
    return QLocale().createSeparatedList(list(names))


# The interface languages that write a language's name in lower case inside
# a sentence - "decirla en inglés", "lire en anglais", "nói tiếng Anh" - and
# capitalise it only where a list or menu shows it, or a sentence starts
# with it: CLDR's names in Spanish, French, Italian, Portuguese, Czech,
# Polish, Russian and Ukrainian are these lower-case forms (its
# contextTransforms capitalise them for a list or menu), and Vietnamese
# writes "tiếng" in lower case mid-sentence. The others keep the name as a
# list shows it: German's and Dutch's nouns, Indonesian's proper names,
# scripts without case (polyglotic-hq 560)
_LOWER_IN_SENTENCE = frozenset(
    {
        QLocale.Language.Spanish,
        QLocale.Language.French,
        QLocale.Language.Italian,
        QLocale.Language.Portuguese,
        QLocale.Language.Czech,
        QLocale.Language.Polish,
        QLocale.Language.Russian,
        QLocale.Language.Ukrainian,
        QLocale.Language.Vietnamese,
    }
)
# The {names} in an interface string that hold language names
_NAMED = frozenset({"language", "languages"})
# Where a sentence ends: its stop and the space after it, or a new line
_SENTENCE_END = re.compile(r"[.!?…。！？]\s|\n")


def in_sentence(text: str, **values: object) -> str:
    """`text` - an interface string, translated - with its `{names}` filled
    in (as `str.format`), its language names written as the interface's
    language writes them in a sentence: "Decirla en inglés", "El diccionario
    de inglés", but "Inglés: versión 2" where one starts it. `language` is
    one language's name; `languages` is one, or several to list
    (`name_list`). Every string a language name fills goes through this
    (polyglotic-hq 560)."""
    lower = QLocale().language() in _LOWER_IN_SENTENCE
    formatter = string.Formatter()
    written: list[str] = []
    for literal, field, spec, conversion in formatter.parse(text):
        written.append(literal)
        if field is None:
            continue
        value, key = formatter.get_field(field, (), values)
        if key in _NAMED:
            names = [value] if isinstance(value, str) else list(value)
            starts = _starts_sentence("".join(written))
            value = name_list(
                name if (starts and i == 0) or not lower else _lower_first(name)
                for i, name in enumerate(names)
            )
        if conversion:
            value = formatter.convert_field(value, conversion)
        written.append(formatter.format_field(value, spec or ""))
    return "".join(written)


def _starts_sentence(written: str) -> bool:
    """Whether what follows `written` starts a sentence: nothing but
    punctuation ("¿", "(") since its start or the last sentence's end."""
    ends = list(_SENTENCE_END.finditer(written))
    since = written[ends[-1].end() :] if ends else written
    return not any(char.isalnum() for char in since)


def _lower_first(name: str) -> str:
    """`name` with its first letter in lower case: "Chino (simplificado)" ->
    "chino (simplificado)", "Tiếng Anh" -> "tiếng Anh"."""
    return name[:1].lower() + name[1:]


# Whether Mandarin's lines are shown in Traditional characters now ("Show
# Mandarin in", `main.shows_traditional`): `shown_name` names them by it
_mandarin_traditional = False


def show_mandarin_in_traditional(on: bool) -> None:
    """Mandarin's lines are shown in Traditional characters (`on`) or
    Simplified ones from now: `main` says so at the start and whenever
    "Show Mandarin in" changes (polyglotic-hq 433)."""
    global _mandarin_traditional
    _mandarin_traditional = on


def mandarin_in_traditional() -> bool:
    """Whether Mandarin's lines are shown in Traditional characters now
    (`show_mandarin_in_traditional`): their captions take Traditional
    Chinese's face (polyglotic-hq 482)."""
    return _mandarin_traditional


def language_name(code: str) -> str:
    """A target language's name, to pick it or name it as a language:
    "French"; Mandarin's target is "Chinese", whatever script its lines are
    shown in (polyglotic-hq 433: a picker saying "Chinese (Simplified)" over
    Traditional lines); `zh-hant`'s is "Chinese (Traditional)"."""
    if code == "zh":
        return _chinese()
    name = _NAMES.get(code)
    return _tr(name) if name else code


def shown_name(code: str) -> str:
    """The language a line is written in, as a transcript's Save and Copy
    and the windows' status label it: Mandarin's by the script it's shown in
    - "Chinese (Traditional)" when "Show Mandarin in" is Traditional (each
    line is converted as it arrives, decision 0204), else "Chinese
    (Simplified)" - and every other language by its name."""
    if code == "zh":
        return _tr(_NAMES["zh-hant" if _mandarin_traditional else "zh"])
    return language_name(code)


def _chinese() -> str:
    """Chinese as a language, either script (as Learning names it)."""
    return QCoreApplication.translate("LearningLanguage", "Chinese")


def spoken_names(codes: Iterable[str]) -> str:
    """ "Mandarin", or "Mandarin + English" for a caption mixing languages."""
    return " + ".join(spoken_name(code) for code in codes)


def spoken_name(code: str) -> str:
    """A spoken language by name, in the interface's language: "Mandarin",
    "Swedish" - any the speech model hears (`core.listening.spoken`)."""
    name = _SPOKEN.get(code) or _NAMES.get(code) or _HEARD_ONLY.get(code)
    return _tr(name) if name else code.upper()


# Each spoken language in its own words, as its speakers write it: not
# translated (polyglotic-hq 317 - a learner finds the language they hear by
# the name they'd see on screen in it, the interface's beside it)
_OWN_NAMES = {
    "en": "English",
    "zh": "普通话",
    "yue": "廣東話",
    "ar": "العربية",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pt": "Português",
    "id": "Bahasa Indonesia",
    "it": "Italiano",
    "ko": "한국어",
    "ru": "Русский",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "ja": "日本語",
    "tr": "Türkçe",
    "hi": "हिन्दी",
    "ms": "Bahasa Melayu",
    "nl": "Nederlands",
    "sv": "Svenska",
    "da": "Dansk",
    "fi": "Suomi",
    "pl": "Polski",
    "cs": "Čeština",
    "tl": "Filipino",
    "fa": "فارسی",
    "el": "Ελληνικά",
    "hu": "Magyar",
    "mk": "Македонски",
    "ro": "Română",
}


def own_name(code: str) -> str:
    """A spoken language in its own words ("Русский"), or "" if unknown."""
    return _OWN_NAMES.get(code, "")


def spoken_choice_text(code: str) -> str:
    """A spoken language as a list offers it: the interface's name and its
    own, "Russian · Русский" - once where they're the same ("English")."""
    name, own = spoken_name(code), own_name(code)
    if not own or own.casefold() == name.casefold():
        return name
    return f"{name} · {own}"


def spoken_order(
    codes: Iterable[str],
    recent: Sequence[str] = (),
    own: Sequence[str] | None = None,
) -> list[str]:
    """`codes` (the spoken languages) in a list's order: the ones named
    last (`recent`, newest first), then the learner's own - `own`, else
    Windows' (`own_languages`), Chinese in either script as Mandarin -
    then the rest by name in the interface's language (293)."""
    offered = list(codes)
    mine = own_languages() if own is None else own
    first = [c for c in recent if c in offered]
    first += [c.split("-")[0] for c in mine]
    first = [c for c in dict.fromkeys(first) if c in offered]
    rest = sorted((c for c in offered if c not in first), key=spoken_name)
    return [*first, *rest]


def _folded(text: str) -> str:
    """`text` for matching what's typed: lower case, without accents."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in plain if not unicodedata.combining(c))


def spoken_matches(code: str, typed: str) -> bool:
    """Whether a spoken language is one the learner is looking for: `typed`
    found in its name in the interface's language, in its own, in English
    or its code - any case, accents or not ("russ", "рус", "espanol")."""
    wanted = _folded(typed.strip())
    if not wanted:
        return True
    english = _SPOKEN.get(code) or _NAMES.get(code) or _HEARD_ONLY.get(code) or ""
    found = (spoken_name(code), own_name(code), str(english), code)
    return any(wanted in _folded(name) for name in found)


# -- the two ways a source is heard (polyglotic-hq 317, decision 0108): Detect,
# or one language named - said the same way wherever the choice is


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QCoreApplication.translate("Languages", text, None, n)


def detect_name() -> str:
    """Detect as a list offers it: "Detect automatically"."""
    #: A choice for a source's spoken language: the speech model finds the
    #: language itself, each time someone speaks
    return _tr(QT_TRANSLATE_NOOP("Languages", "Detect automatically"))


def detect_short(count: int) -> str:
    """Detect as a chip shows it, with how many languages it covers:
    "Detect · 30 languages"."""
    #: Short, on a button: the spoken language is found automatically, among
    #: this many languages
    return _trn("Detect · %Ln language(s)", count)


def detect_covers(count: int) -> str:
    """Under Detect in a list: what it covers."""
    return _trn("Any of the %Ln language(s) below", count)


def named_heading() -> str:
    """Over the languages in a list: what choosing one does."""
    #: A heading over a list of languages: pick one and the app hears this
    #: app's speech as that language every time, rather than detecting it
    return _tr(QT_TRANSLATE_NOOP("Languages", "Always hear as"))


def named_short(code: str) -> str:
    """A language named, as a chip shows it: "Always Russian"."""
    #: Short, on a button: this app's speech is always heard as {language}
    #: (named by the learner, not detected)
    said = _tr(QT_TRANSLATE_NOOP("Languages", "Always {language}"))
    return in_sentence(said, language=spoken_name(code))


def find_placeholder() -> str:
    """In the box over the list, before anything is typed."""
    return _tr(QT_TRANSLATE_NOOP("Languages", "Find a language"))


def none_found() -> str:
    return _tr(QT_TRANSLATE_NOOP("Languages", "No language by that name"))


def own_languages() -> list[str]:
    """The caption languages the learner reads: Windows' display languages
    that captions are translated into (`own_targets`), in their order."""
    return own_targets(QLocale.system().uiLanguages())


def target_languages(own: Sequence[str] | None = None) -> list[Language]:
    """Every language that can be picked: the learner's own first - `own`,
    else Windows' (`own_languages`) - then the rest by name. None is pinned
    on top for everyone (polyglotic-hq 293: English and Chinese first made
    the app look as if it were only for them)."""
    first = [c for c in (own_languages() if own is None else own) if c in _NAMES]
    rest = sorted((c for c in _NAMES if c not in first), key=language_name)
    return [Language(c) for c in [*first, *rest]]


def not_offered_note() -> str:
    """Why Mongolian and Kazakh can't be picked (#40)."""
    return _tr(_NOT_OFFERED_NOTE)


def taken_off(codes: Iterable[str]) -> tuple[str, ...]:
    """Those of `codes` that were offered once and aren't now (#40), each
    once, in order."""
    return tuple(dict.fromkeys(c for c in codes if c in _TAKEN_OFF and c not in _NAMES))


def taken_off_note(codes: Iterable[str]) -> str:
    """Home's notice for saved languages taken off (#40), by name."""
    names = [_tr(_TAKEN_OFF[c]) for c in taken_off(codes)]
    return in_sentence(_tr(_TAKEN_OFF_NOTE), languages=names)


# Languages dictation can be set to that aren't caption languages: the
# speech model hears them, the translator isn't offered them (283)
_HEARD_ONLY = {
    "sv": QT_TRANSLATE_NOOP("Languages", "Swedish"),
    "da": QT_TRANSLATE_NOOP("Languages", "Danish"),
    "fi": QT_TRANSLATE_NOOP("Languages", "Finnish"),
    "fa": QT_TRANSLATE_NOOP("Languages", "Persian"),
    "el": QT_TRANSLATE_NOOP("Languages", "Greek"),
    "hu": QT_TRANSLATE_NOOP("Languages", "Hungarian"),
    "mk": QT_TRANSLATE_NOOP("Languages", "Macedonian"),
    "ro": QT_TRANSLATE_NOOP("Languages", "Romanian"),
}
# Chinese dictation says which characters it types (the server's scripts)
_DICTATED = {
    "zh": QT_TRANSLATE_NOOP("Languages", "Mandarin (Simplified characters)"),
    "yue": QT_TRANSLATE_NOOP("Languages", "Cantonese (Hong Kong characters)"),
}


def dictation_language_name(code: str) -> str:
    """A language dictation can be set to, by name - Chinese with the
    characters it types: "Mandarin (Simplified characters)"."""
    name = _DICTATED.get(code) or _NAMES.get(code) or _HEARD_ONLY.get(code)
    return _tr(name) if name else code


def dictation_choices(
    codes: Iterable[str], own: Sequence[str] | None = None
) -> list[tuple[str, str]]:
    """`codes` (the languages dictation can be set to) as (code, name): the
    learner's own first - `own`, else Windows' (`own_languages`), Chinese
    in either script as Mandarin - then the rest by name (293)."""
    offered = list(codes)
    mine = own_languages() if own is None else own
    first = list(dict.fromkeys(c.split("-")[0] for c in mine))
    first = [c for c in first if c in offered]
    rest = sorted((c for c in offered if c not in first), key=dictation_language_name)
    return [(c, dictation_language_name(c)) for c in [*first, *rest]]


def learned_name(code: str) -> str:
    """A language learned, by name (Learning, the lookup's "Learn it too?"):
    Chinese - not "Chinese (Simplified)": both scripts are learned together
    - English, or a caption language's name."""
    if code == "zh":
        return _chinese()
    if code == "en":
        return QCoreApplication.translate("LearningLanguage", "English")
    return language_name(code)


_SAID_WITH_Y = ("uk", "uy", "uni", "eu", "one")
"""Names starting with a vowel letter said with a consonant first: "a
Ukrainian voice", "a Uyghur one"."""


def an_before(name: str) -> bool:
    """Whether English says "an" before `name` - by its first sound, not
    its letter: an English voice, an Urdu one, a Ukrainian one (polyglotic-hq
    551: the card said "Add a English voice"). A string that puts an
    article before a name has an "an" twin for it."""
    word = name.strip().lower()
    return word[:1] in ("a", "e", "i", "o", "u") and not word.startswith(_SAID_WITH_Y)


# Windows' tags for Traditional Chinese, by script or by region (as
# `ui.interface_language` reads them), and its codes that aren't ours
_TRADITIONAL_TAGS = ("zh-hant", "zh-tw", "zh-hk", "zh-mo")
_WINDOWS_CODES = {"fil": "tl"}


def caption_language_of(tag: str) -> str | None:
    """The caption language a Windows language tag ("zh-Hant-TW", "en-AU",
    "fil-PH") is read in - "zh-hant", "en", "tl" - or None if it isn't one
    captions are translated into."""
    tag = tag.replace("_", "-").lower()
    if tag.startswith(_TRADITIONAL_TAGS):
        code = "zh-hant"
    else:
        base = tag.split("-")[0]
        code = _WINDOWS_CODES.get(base, base)
    return code if code in _NAMES else None


def own_targets(windows_languages: Iterable[str]) -> list[str]:
    """The caption languages the learner reads: Windows' display languages
    (in the user's order) that captions are translated into, each once."""
    found = (caption_language_of(tag) for tag in windows_languages)
    return list(dict.fromkeys(code for code in found if code))


def named_question(code: str) -> str:
    """A caption window's question once Detect has heard one language
    steadily: "This sounds like Russian. Always hear it as Russian?"."""
    #: Asked on a caption window after several captions in a row in one
    #: language; Yes names it, so every caption is heard as {language}
    return in_sentence(
        _tr(
            QT_TRANSLATE_NOOP(
                "Languages",
                "This sounds like {language}. Always hear it as {language}?",
            )
        ),
        language=spoken_name(code),
    )
