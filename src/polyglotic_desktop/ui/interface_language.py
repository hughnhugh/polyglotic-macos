"""The language the interface is in - its menus, buttons, help and notes
(decision 0034).

It's separate from the language being learned and the languages captions
are translated into: a Chinese speaker learning English reads the app in
Chinese and its captions in English, with Chinese translations.

- **Which one:** the learner's choice in Settings, or - until they choose -
  the first of Windows' display languages the app is offered in, else
  English. Traditional Chinese is Taiwan's (zh_TW), for a Taiwan, Hong
  Kong or Macau Windows too; Portuguese is Brazil's (pt_BR), for
  Portugal's Windows too; Filipino is "fil" (Windows' "fil-PH", or "tl").
- **The picker** lists each language by its own name (Deutsch, 日本語),
  sorted by that name with its accents set aside - Latin scripts first,
  then the others by script - and none pinned first (`picker`;
  polyglotic-hq 294).
- **Drafts:** a language whose text is a machine draft no native reader
  has checked yet (`DRAFTS`) says so in Settings, with a way to tell us
  what reads wrong (decision 0087).
- **Its translations:** ours (`assets/translations/polyglotic_<code>.qm`,
  compiled from `translations/*.ts` by `tools.i18n`) and Qt's own for its
  standard buttons and menus (OK, Cancel, Copy...). English has a file too:
  only its counts' two forms ("1 caption", "3 captions") - every other
  English text is the code's.
- **Numbers, dates and the week's first day** follow Windows' regional
  format when it's in the interface's language (an Australian English
  Windows keeps 2/11/2026 and Monday first), else the interface
  language's own (`QLocale.setDefault`) - so a Chinese interface never
  shows English month names.

It's set once, before the first window, and a change applies at the next
start: the windows set their text as they're built.
"""

import unicodedata
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

import PySide6
from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

TRANSLATIONS = Path(__file__).with_name("assets") / "translations"
ENGLISH = "en"
# each language offered, by code, and its name as its readers write it
# (shown untranslated, so a learner who can't read the current one finds
# their own). Each has its file, translations/polyglotic_<code>.ts.
OFFERED = {
    ENGLISH: "English",
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt_BR": "Português (Brasil)",
    "it": "Italiano",
    "ja": "日本語",
    "ko": "한국어",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
    "tr": "Türkçe",
    "ru": "Русский",
    "pl": "Polski",
    "nl": "Nederlands",
    "uk": "Українська",
    "fil": "Filipino",
    "th": "ไทย",
    "hi": "हिन्दी",
    "ms": "Bahasa Melayu",
    "cs": "Čeština",
}
DRAFTS = frozenset(OFFERED) - {ENGLISH}
"""Languages whose text is a machine draft no native reader has checked
yet (translations/README.md): Settings says so (decision 0087). Every one
but English today; take a language out as a native reader reviews its
file. A test checks it against the files: a language with a draft ("?")
in its file is here, and one fully reviewed isn't."""
_SIMPLIFIED = ("zh-hans", "zh-cn", "zh-sg", "zh-my")
_TRADITIONAL = ("zh-hant", "zh-tw", "zh-hk", "zh-mo")
_SAME = {"pt": "pt_BR", "tl": "fil", "in": "id"}
"""Windows' language -> the interface language it reads: Portugal's
Windows reads Brazil's Portuguese; Tagalog's Filipino; Indonesian's old
code."""


def _read_in(tag: str) -> str:
    """The interface language a Windows language tag ("zh-Hans-CN",
    "en-AU", "pt-PT") is read in: "zh_CN", "en", "pt_BR"."""
    tag = tag.replace("_", "-").lower()
    if tag.startswith(_TRADITIONAL):
        return "zh_TW"
    if tag == "zh" or tag.startswith(_SIMPLIFIED):
        return "zh_CN"
    base = tag.split("-")[0]
    return _SAME.get(base, base)


def reads_traditional(interface: str, windows_languages: Sequence[str]) -> bool:
    """Whether this PC reads Chinese in Traditional characters: its
    interface is in Traditional Chinese, or else the first Chinese of
    Windows' display languages is Taiwan's, Hong Kong's or Macau's - what
    "Show Mandarin in" starts at (polyglotic-hq 375)."""
    if interface in ("zh_TW", "zh_CN"):
        return interface == "zh_TW"
    for tag in windows_languages:
        tag = tag.replace("_", "-").lower()
        if tag == "zh" or tag.startswith("zh-"):
            return tag.startswith(_TRADITIONAL)
    return False


def picker(offered: Mapping[str, str] = OFFERED) -> list[tuple[str, str]]:
    """Each language offered, (code, own name), as the picker lists them:
    by own name with accents set aside ("Español" among the E's), so Latin
    scripts come first, then Cyrillic, Devanagari, Thai, Han and Hangul -
    each script's together. None is pinned first (polyglotic-hq 294)."""

    def key(item: tuple[str, str]) -> str:
        name = unicodedata.normalize("NFKD", item[1])
        return "".join(c for c in name if not unicodedata.combining(c)).casefold()

    return sorted(offered.items(), key=key)


def is_draft(language: str) -> bool:
    """Whether `language`'s text is a machine draft (`DRAFTS`)."""
    return language in DRAFTS


def in_use(app: QCoreApplication) -> str:
    """The interface language `app` was started in - its property
    "interface_language", which `main` and the UI lab set as they install
    it - else English."""
    language = app.property("interface_language")
    return language if isinstance(language, str) and language else ENGLISH


def pick(
    chosen: str | None,
    windows_languages: Sequence[str],
    offered: Collection[str] = tuple(OFFERED),
) -> str:
    """The interface's language: `chosen` (the setting) if it's offered,
    else the first of `windows_languages` (Windows' display languages, in
    the user's order) that is, else English."""
    if chosen is not None and chosen in offered:
        return chosen
    for tag in windows_languages:
        if (found := _read_in(tag)) in offered:
            return found
    return ENGLISH


def windows_languages() -> list[str]:
    """Windows' display languages, in the user's order ("en-AU", ...)."""
    return QLocale.system().uiLanguages()


def _qts_own(language: str) -> Path:
    """Qt's translation of its own words (OK, Cancel, Copy): where Qt says
    it is, else beside PySide6 - where the packed app has it
    (`tools/package/polyglotic.spec` keeps it for each language offered)."""
    name = f"qtbase_{language}.qm"
    told = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / name
    return (
        told if told.exists() else Path(PySide6.__file__).parent / "translations" / name
    )


def install(app: QCoreApplication, language: str) -> list[QTranslator]:
    """`language`'s translations installed on `app` (its children, so they
    last as long as it does); numbers set to its locale. A missing file
    leaves that text in English rather than failing the start."""
    files = [TRANSLATIONS / f"polyglotic_{ENGLISH}.qm"]  # counts, beneath
    if language != ENGLISH:
        files += [_qts_own(language), TRANSLATIONS / f"polyglotic_{language}.qm"]
    installed = []
    for file in files:  # the last installed is asked first
        translator = QTranslator(app)
        if translator.load(str(file)) and app.installTranslator(translator):
            installed.append(translator)
    QLocale.setDefault(formats(language, QLocale.system()))
    return installed


def formats(language: str, system: QLocale) -> QLocale:
    """The locale numbers and dates are written in: Windows' regional
    format if it's `language`'s, else `language`'s own."""
    own = QLocale(language)
    return system if system.language() == own.language() else own
