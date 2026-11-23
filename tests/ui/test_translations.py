"""The interface's translations (decision 0034, polyglotic-hq 156): every
string the code shows reaches the translation files, English's counts read
as English, each language's text keeps its placeholders, and the app picks
its language from the setting or Windows'."""

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, Qt, QTranslator
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, MemorySettingsStore
from tools.i18n import __main__ as i18n
from tools.i18n import extract, keep, ts

from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.core.lexicon.entries import SCHEMES
from polyglotic_desktop.main import feedback_versions, start_interface_language
from polyglotic_desktop.ui import interface_language
from polyglotic_desktop.ui.interface_language import (
    ENGLISH,
    OFFERED,
    formats,
    install,
    pick,
)
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.languages import name_list
from polyglotic_desktop.ui_next.lookup_card import heard_in
from polyglotic_desktop.ui_next.words_page import SCHEME_NAMES, heard_times, words_count

PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
COUNT = re.compile(r"%L?n")


def test_every_string_reaches_the_translation_files() -> None:
    """Nothing the translations can't reach (an f-string, a joined string,
    "(s)" outside a count) and each `.ts` up to date with the code: else
    `python -m tools.i18n update`."""
    assert i18n.problems() == []


def test_every_offered_language_has_its_files() -> None:
    """A language in the picker has its translation file - and every file
    is a language in the picker (polyglotic-hq 294). The `.qm` files are
    built before the tests (`tests/conftest.py`), where the app loads them."""
    files = {p.stem.removeprefix("polyglotic_") for p in i18n.TS_DIR.glob("*.ts")}
    assert files == set(OFFERED) == set(i18n.LANGUAGES)
    for language in OFFERED:
        assert i18n.qm_path(language).parent == interface_language.TRANSLATIONS
        assert i18n.qm_path(language).exists()


def test_the_compiled_files_are_built_not_committed() -> None:
    """Two pull requests that change text conflicted in the `.qm` binaries
    every time (polyglotic-hq 179; decision 0034, amended 2026-11-08): git
    ignores them, and nothing has them committed."""
    repo = Path(__file__).resolve().parents[2]
    if not (repo / ".git").exists():
        pytest.skip("not a git checkout (a source archive): nothing to ask git")
    built = [i18n.qm_path(code).relative_to(repo).as_posix() for code in OFFERED]
    ignored = subprocess.run(
        ["git", "check-ignore", *built],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sorted(ignored.stdout.splitlines()) == sorted(built)
    committed = subprocess.run(
        ["git", "ls-files", "*.qm"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert committed.stdout == ""


def test_build_compiles_each_language_from_its_ts(
    qapp: QApplication, tmp_path: Path
) -> None:
    """What CI, the UI lab and the package build run: each `.qm` from its
    `.ts`, and Qt reads the translations in it."""
    built = i18n.build(tmp_path)
    assert sorted(path.name for path in built) == sorted(
        i18n.qm_path(language).name for language in OFFERED
    )
    chinese = ts.read(i18n.ts_path("zh_CN"))
    (context, source, comment), translation = next(
        (key, t)
        for key, t in chinese.translations.items()
        if len(t.forms) == 1 and t.forms[0]
    )
    translator = QTranslator()
    assert translator.load(str(tmp_path / i18n.qm_path("zh_CN").name))
    assert (
        translator.translate(context, source, comment or None) == translation.forms[0]
    )
    before = {path: path.stat().st_mtime_ns for path in built}
    i18n.build(tmp_path)  # the same again: an open file isn't rewritten
    assert {path: path.stat().st_mtime_ns for path in built} == before


ABOUT_WINDOWS = {
    # Windows' own setting: the probe asks it (decision 0122)
    ("Learning", "Paused: Windows says this connection is metered"),
    ("Help", "Caption apps you add (Windows 11)"),
    (
        "Help",
        "On Home, add up to %Ln app(s) with sound open; each gets a caption window",
    ),
    ("Help", "With one app added on Home, turn on Also caption everything else"),
    # 285 (decision 0076): what Windows here can capture, and why apps are off
    ("Home", "instead of apps (the only choice on this version of Windows)"),
    ("Home", "instead of apps: Windows on this PC couldn't caption one app alone"),
    ("DesktopApp", "Windows on this PC couldn't caption one app alone, so"),
    ("Home", "With one app only - Windows can leave just one app out"),
    # 176's day 2 (#269): starting with Windows is Windows' own feature, asked
    # only on the installed Windows app
    ("Home", "Start Polyglotic with Windows?"),
    ("Home", "Start with Windows"),
    ("Home", "It waits in the tray, so captions are a click away when you play"),
    # 251, 313: where the PC's clock is set is Windows' own Settings page
    ("Home", "this PC says it's {date}, which can't be right. Turn on Set time"),
    ("Home", "This PC's date or time looks wrong: it says {date}, {time}."),
    ("SignInDialog", "This PC says it's {date}, which can't be right, and a secure"),
    # 286: a voice for a word is added in Windows' own Settings (Windows' voices)
    ("LookupCard", "No {language} voice on this PC yet. Windows adds one for free"),
    ("LookupCard", "Opens Windows' Settings, where voices are added"),
    # 289: a dictation key Windows keeps for itself (Win+L, Ctrl+Alt+Del...)
    ("DictationKey", "Windows keeps that one for itself: choose another."),
}
"""The interface's words that are about Windows itself: what its versions
can capture, and its own start-up (each string's start)."""


def test_the_interface_says_this_pc_unless_it_means_windows() -> None:
    """The PC's sound settings, its default device, everything it plays,
    the language and theme "Like this PC" - not Windows', which is wrong on
    a Mac (polyglotic-hq 179). Windows only where it's Windows' own limit."""
    said = {
        (m.context, m.source) for m in extract.read().messages if "Windows" in m.source
    }
    assert {
        (context, start)
        for context, start in ABOUT_WINDOWS
        if any(c == context and s.startswith(start) for c, s in said)
    } == ABOUT_WINDOWS
    assert len(said) == len(ABOUT_WINDOWS), sorted(said)


def test_an_ellipsis_is_one_character_not_three_dots() -> None:
    """Every string the interface shows writes an ellipsis as the one
    character - "Signing in…", "Reading your words…" - as its menu items do
    ("Report a problem…"), never three full stops (polyglotic-hq 228's
    #347, 235)."""
    dots = sorted(m.source for m in extract.read().messages if "..." in m.source)
    assert dots == []


def test_english_counts_read_as_english(qapp: QApplication) -> None:
    """No "1 caption(s)": English's forms come from its translation file,
    which the app installs at start (and the tests' application too)."""
    assert heard_in(1) == "Heard in 1 caption"
    assert heard_in(1234) == "Heard in 1,234 captions"  # digits grouped (%Ln)
    assert heard_times(1) == "heard once" and heard_times(3) == "heard 3 times"
    assert words_count(1) == "1 word" and words_count(0) == "0 words"
    english = ts.read(i18n.ts_path(ENGLISH))
    for (_context, source, _comment), translation in english.translations.items():
        assert len(translation.forms) == 2, source  # one, and more than one
        assert not any("(s)" in f or "(es)" in f for f in translation.forms), source


def test_a_count_without_its_file_says_s(qapp: QApplication) -> None:
    """Why the English file matters: without it Qt shows the source's
    "(s)" - the fault 133 found, now caught by the test above."""
    text = QCoreApplication.translate("LookupCard", "Heard in %Ln caption(s)", None, 1)
    assert text == "Heard in 1 caption"
    bare = QCoreApplication.translate("Nowhere", "Heard in %n caption(s)", None, 1)
    assert bare == "Heard in 1 caption(s)"


@pytest.mark.parametrize("language", [code for code in OFFERED if code != ENGLISH])
def test_translations_keep_what_their_english_has(language: str) -> None:
    """A translation that loses or renames `{app}` would fail `.format()`
    when it's shown; a count's forms keep `%n`, and there are as many as
    the language has (`keep.PLURAL_FORMS`); an HTML tag stays as it was
    (polyglotic-hq 294: `keep.broken`)."""
    file = ts.read(i18n.ts_path(language))
    wrong = [
        (context, source, keep.broken(source, translation.forms, language))
        for (context, source, _comment), translation in file.translations.items()
        if not translation.empty  # not translated yet: the English shows
        and keep.broken(source, translation.forms, language)
    ]
    assert wrong == []


@pytest.mark.parametrize("language", [code for code in OFFERED if code != ENGLISH])
def test_every_string_is_drafted(language: str) -> None:
    """Every string has at least a draft, so no English shows in another
    language's interface (translations/README.md: draft each new string)."""
    file = ts.read(i18n.ts_path(language))
    empty = [source for (_c, source, _d), t in file.translations.items() if t.empty]
    assert empty == []


ASCII_BESIDE_HAN = re.compile(r"[\u4e00-\u9fff][?,:;!]|[?,:;!][\u4e00-\u9fff]| - ")
"""English's " - ", or an ASCII ? , : ; ! against a Chinese character. Not
brackets or ";;": a file filter's "文本 (*.txt);;字幕 (*.srt)" is Qt's syntax."""


@pytest.mark.parametrize("language", ["zh_CN", "zh_TW"])
def test_chinese_writes_its_own_punctuation(language: str) -> None:
    """The glossaries: full-width punctuation, and English's " - " between
    two parts becomes "：", "，" or "——" (polyglotic-hq 235; 223's QA saw
    "Plus 已结束 - 字幕已停止")."""
    file = ts.read(i18n.ts_path(language))
    ascii_marks = [
        form
        for translation in file.translations.values()
        for form in translation.forms
        if ASCII_BESIDE_HAN.search(form.replace(";;", " "))
    ]
    assert ascii_marks == []


def test_traditional_chinese_says_help_and_kind_in_taiwans_words() -> None:
    """說明 is the Help page's name, not the verb "help" (幫助); a kind of
    thing is 類型, not 型別, a programming word (polyglotic-hq 235; 184's and
    223's QA)."""
    file = ts.read(i18n.ts_path("zh_TW"))
    said = {source: t.forms for (_c, source, _d), t in file.translations.items()}
    assert not [forms for forms in said.values() if any("型別" in f for f in forms)]
    helps = [  # "what would help", "They help us" (this PC's and this Mac's: 409)
        forms[0]
        for source, forms in said.items()
        if source.startswith(("Tell us what went wrong or what", "Daily counts of how"))
    ]
    assert len(helps) == 3
    assert all("幫助" in each and "說明" not in each for each in helps)


@pytest.mark.parametrize("language", [code for code in OFFERED if code != ENGLISH])
def test_dictations_note_names_detect_as_its_list_does(language: str) -> None:
    """Dictation's note uses the same translated Detect label as the list."""
    file = ts.read(i18n.ts_path(language))
    said = {source: t.forms[0] for (_c, source, _d), t in file.translations.items()}
    note = next(
        text
        for source, text in said.items()
        if source.startswith("Choose a language or use {detect} when dictation")
    )
    assert "{detect}" in note


@pytest.mark.parametrize(
    ("language", "transcript", "not_it"),
    [("zh_CN", "字幕记录", "文字记录"), ("zh_TW", "字幕記錄", "文字紀錄")],
)
def test_a_transcript_is_the_glossarys_word_everywhere(
    language: str, transcript: str, not_it: str
) -> None:
    """GLOSSARY-zh_CN.md: a transcript is 字幕记录 (字幕記錄 in Taiwan's).
    235 changed Home's and Help's Plus lines; Help's "What we keep" still
    said 文字记录 (polyglotic-hq 237)."""
    file = ts.read(i18n.ts_path(language))
    forms = [form for t in file.translations.values() for form in t.forms]
    assert not [form for form in forms if not_it in form]
    assert any(transcript in form for form in forms)


def test_the_extractor_reads_the_wrappers_and_finds_what_it_cant_translate(
    tmp_path: Path,
) -> None:
    module = tmp_path / "page.py"
    module.write_text(
        "from PySide6.QtWidgets import QApplication\n"
        "_CONTEXT = 'Page'\n"
        "def _tr(text):\n"
        "    return QApplication.translate(_CONTEXT, text)\n"
        "def _trn(text, n):\n"
        "    return QApplication.translate('Page', text, None, n)\n"
        "class Card:\n"
        "    def build(self, name, n):\n"
        "        #: a button\n"
        "        _tr('Save')\n"
        "        self.tr('Open', 'a file')\n"
        "        _trn('%n word(s)', n)\n"
        "        _tr(name)\n"
        "        _tr(f'Hello {name}')\n"
        "        _tr('Saved ' + name)\n"
        "        _tr('1 word(s)')\n"
        "        _trn('words', n)\n"
        "TITLE = _tr('Words')\n"
        "LATER = QT_TRANSLATE_NOOP('Page', 'Later')\n",
        encoding="utf-8",
    )
    found = extract.read_file(module)
    assert [
        (m.context, m.source, m.comment, m.numerus, m.note) for m in found.messages
    ] == [
        ("Page", "Save", "", False, "a button"),
        ("Card", "Open", "a file", False, ""),
        ("Page", "%n word(s)", "", True, ""),
        ("Page", "1 word(s)", "", False, ""),
        ("Page", "words", "", True, ""),
        ("Page", "Words", "", False, ""),
        ("Page", "Later", "", False, ""),
    ]
    assert [p.split(": ", 1)[1].split(":")[0] for p in found.problems] == [
        "an f-string to translate",
        "a joined string to translate",
        "'(s)' outside a plural",
        "a count without %n",
        "translated at import, before the interface's language is installed",
    ]


def test_english_forms_come_from_the_source() -> None:
    assert ts.english_forms("%n caption(s)") == ("%n caption", "%n captions")
    assert ts.english_forms("%Ln match(es)") == ("%Ln match", "%Ln matches")


@pytest.mark.parametrize(
    ("chosen", "windows", "language"),
    [
        (None, ["en-AU", "zh-Hans-CN"], "en"),
        (None, ["zh-Hans-CN", "en-US"], "zh_CN"),
        (None, ["zh-CN"], "zh_CN"),
        (None, ["zh-SG"], "zh_CN"),
        (None, ["zh"], "zh_CN"),
        # Traditional isn't offered yet: not Simplified unasked
        (None, ["zh-Hant-TW", "zh-Hans-CN"], "zh_CN"),
        (None, ["zh-HK"], "en"),
        (None, ["vi-VN", "fr-FR"], "en"),  # none offered: English
        ("zh_CN", ["en-US"], "zh_CN"),  # the learner's choice wins
        ("en", ["zh-CN"], "en"),
        ("xx", ["zh-CN"], "zh_CN"),  # a choice not offered (a newer version's)
        (None, [], "en"),
    ],
)
def test_the_language_is_the_choice_else_windows_else_english(
    chosen: str | None, windows: list[str], language: str
) -> None:
    assert pick(chosen, windows, ("en", "zh_CN")) == language


def test_a_language_not_offered_yet_is_english() -> None:
    assert pick("zh_TW", ["zh-TW"], ("en", "zh_CN")) == "en"
    assert pick(None, ["zh-CN"], ("en",)) == "en"


@pytest.mark.parametrize(
    ("windows", "language"),
    [
        (["de-AT", "en-US"], "de"),  # a drafted language, like this PC
        (["pt-BR"], "pt_BR"),
        (["pt-PT"], "pt_BR"),  # Portugal's Windows reads Brazil's Portuguese
        (["fil-PH"], "fil"),
        (["tl"], "fil"),
        (["ja-JP"], "ja"),
        (["nb-NO", "es-MX"], "es"),  # the first offered
    ],
)
def test_like_this_pc_finds_every_main_language(
    windows: list[str], language: str
) -> None:
    """polyglotic-hq 294: "Like this PC" picks a language when Windows is
    in it, drafts included."""
    offered = ("en", "de", "es", "ja", "pt_BR", "fil", "zh_CN")
    assert pick(None, windows, offered) == language


def test_the_picker_lists_each_language_by_its_own_name_none_first() -> None:
    """polyglotic-hq 294: by own name, accents set aside, so each script's
    names are together and no pair is pinned first."""
    names = {
        "en": "English",
        "zh_CN": "简体中文",
        "zh_TW": "繁體中文",
        "es": "Español",
        "de": "Deutsch",
        "vi": "Tiếng Việt",
        "tr": "Türkçe",
        "id": "Bahasa Indonesia",
        "ru": "Русский",
        "uk": "Українська",
        "hi": "हिन्दी",
        "th": "ไทย",
        "ja": "日本語",
        "ko": "한국어",
    }
    assert [name for _code, name in interface_language.picker(names)] == [
        "Bahasa Indonesia",
        "Deutsch",
        "English",
        "Español",
        "Tiếng Việt",
        "Türkçe",
        "Русский",
        "Українська",
        "हिन्दी",
        "ไทย",
        "한국어",  # Hangul's letters (its syllables, accents set aside)
        "日本語",
        "简体中文",
        "繁體中文",
    ]
    assert dict(interface_language.picker()) == OFFERED  # every one, by default


def test_tell_us_what_reads_wrong_opens_the_feedback_form(qapp: QApplication) -> None:
    """The draft's "Tell us what reads wrong" is the feedback route the app
    already has: "Suggest something" (decision 0087). English, the tests'
    language, isn't a draft: Settings doesn't say it is."""
    built = Built()
    try:
        asked: list[str] = []
        built.desktop.feedback_wanted.connect(asked.append)
        assert built.hub.settings.language_draft.isHidden()
        built.hub.settings.translation_feedback_wanted.emit()
        assert asked == ["suggestion"]
    finally:
        built.close()


@pytest.mark.parametrize("language", [code for code in OFFERED if code != ENGLISH])
def test_a_language_says_its_a_draft_while_its_file_has_drafts(language: str) -> None:
    """Said honestly (polyglotic-hq 294, decision 0087): Settings marks a
    language as a machine draft (`DRAFTS`) exactly while its file still has
    a string no native reader has reviewed ("?")."""
    file = ts.read(i18n.ts_path(language))
    drafted = any(not t.done for t in file.translations.values())
    assert interface_language.is_draft(language) == drafted


@pytest.fixture
def chinese(qapp: QApplication) -> Iterator[list[QTranslator]]:
    """Simplified Chinese installed for one test, then taken off again."""
    installed = install(qapp, "zh_CN")
    yield installed
    for translator in installed:
        qapp.removeTranslator(translator)
    QLocale.setDefault(formats(ENGLISH, QLocale.system()))  # as the tests start


def test_chinese_installs_ours_english_counts_and_qts_own(
    chinese: list[QTranslator],
) -> None:
    files = sorted(Path(t.filePath()).name for t in chinese)
    assert files == ["polyglotic_en.qm", "polyglotic_zh_CN.qm", "qtbase_zh_CN.qm"]
    assert QLocale().language() == QLocale.Language.Chinese


def test_the_interface_reads_in_chinese(chinese: list[QTranslator]) -> None:
    """Our words, a count in Chinese's one form, a name list with 、 or 和,
    and Qt's own buttons."""
    assert heard_in(1) == "在 1 条字幕中听到"
    assert heard_in(1234) == "在 1,234 条字幕中听到"
    assert heard_times(1) == "听到 1 次"
    assert name_list(["蒙古语", "哈萨克语"]) == "蒙古语和哈萨克语"
    cancel = QCoreApplication.translate("QPlatformTheme", "Cancel")
    assert cancel == "取消"


def test_the_feedback_forms_versions_read_in_the_interfaces_punctuation(
    chinese: list[QTranslator],
) -> None:
    """polyglotic-hq 235 (223's QA): the form's "Also sent: Polyglotic 0.0.0,
    windows-11" had an ASCII comma among the Chinese sentence's own."""
    app = AppInfo("0.1.0", "windows-11", os_version="10.0.26200")
    assert feedback_versions(app) == "Polyglotic 0.1.0，windows-11（10.0.26200）"


def test_the_feedback_forms_versions_in_english() -> None:
    app = AppInfo("0.1.0", "windows-11", os_version="10.0.26200")
    assert feedback_versions(app) == "Polyglotic 0.1.0, windows-11 (10.0.26200)"


def test_numbers_and_dates_follow_windows_in_the_same_language() -> None:
    """An Australian English Windows keeps its dates and Monday first in an
    English interface; a Chinese interface on it writes Chinese dates."""
    australia = QLocale("en_AU")
    assert formats("en", australia) == australia
    assert formats("en", australia).firstDayOfWeek() == Qt.DayOfWeek.Monday
    assert formats("zh_CN", australia).language() == QLocale.Language.Chinese
    assert formats("en", QLocale("de_DE")) == QLocale("en")


def test_the_start_installs_the_chosen_language(qapp: QApplication) -> None:
    """main's start: English's counts at least, whatever is chosen (here
    English, so nothing else)."""
    store = MemorySettingsStore()
    Settings(store).update(interface_language="en")
    installed = start_interface_language(qapp, store)
    try:
        assert [Path(t.filePath()).name for t in installed] == ["polyglotic_en.qm"]
    finally:
        for translator in installed:
            qapp.removeTranslator(translator)


def test_the_setting_is_kept_and_a_bad_one_dropped() -> None:
    store = MemorySettingsStore()
    settings = Settings(store)
    assert settings.value.interface_language is None  # like Windows
    settings.update(interface_language="zh_CN")
    assert Settings(store).value.interface_language == "zh_CN"
    store.save({**store.load(), "interface_language": "../../x"})
    assert Settings(store).value.interface_language is None


def test_every_level_schemes_name_is_marked_for_translation() -> None:
    """Words says the scheme's name ("HSK 3.0 (2025 exam syllabus)") from
    core, translated through its marked copy - a renamed scheme fails here."""
    assert {scheme.name for scheme in SCHEMES.values()} == set(SCHEME_NAMES)


def test_traditional_chinese_reads_in_taiwans_words(qapp: QApplication) -> None:
    installed = install(qapp, "zh_TW")
    try:
        files = sorted(Path(t.filePath()).name for t in installed)
        assert files == ["polyglotic_en.qm", "polyglotic_zh_TW.qm", "qtbase_zh_TW.qm"]
        assert heard_in(3) == "在 3 條字幕中聽到"
        assert QCoreApplication.translate("MainWindow", "Settings") == "設定"
    finally:
        for translator in installed:
            qapp.removeTranslator(translator)
        QLocale.setDefault(formats(ENGLISH, QLocale.system()))


def test_a_japanese_interface_puts_japans_font_before_chinas() -> None:
    """polyglotic-hq 294: a Japanese interface's kanji in a Japanese face
    (Yu Gothic UI), never YaHei's Chinese shapes - in its font list and
    behind every font (menus, tooltips)."""
    try:
        style.use_interface_language("ja")
        families = style.UI_FAMILIES
        assert families.index("Yu Gothic UI") < families.index("Microsoft YaHei UI")
        behind = [f.lower() for f in QFont.substitutes("Segoe UI")]
        assert behind.index("yu gothic ui") < behind.index("microsoft yahei ui")
    finally:
        style.use_interface_language("en")
    assert "Yu Gothic UI" not in style.UI_FAMILIES
    assert "yu gothic ui" not in [f.lower() for f in QFont.substitutes("Segoe UI")]


def test_a_traditional_interface_puts_taiwans_font_first() -> None:
    """Han characters look different in Taiwan's and the mainland's fonts:
    JhengHei first for Traditional, YaHei first otherwise."""
    try:
        style.use_interface_language("zh_TW")
        families = style.UI_FAMILIES
        assert families.index("Microsoft JhengHei UI") < families.index(
            "Microsoft YaHei UI"
        )
        assert "'Microsoft JhengHei UI', 'Microsoft YaHei UI'" in style.stylesheet(
            style.Theme()
        )
    finally:
        style.use_interface_language("en")
    families = style.UI_FAMILIES
    assert families.index("Microsoft YaHei UI") < families.index(
        "Microsoft JhengHei UI"
    )
