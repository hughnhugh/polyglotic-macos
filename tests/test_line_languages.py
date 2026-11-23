"""Each translation line in the language the server says it is written in
(polyglotic-hq 497; server decision 0097; decision 0231).

490's case: a window into English, Chinese its second language, a speaker
switching between Mandarin and English. Since server decision 0096 a
clause's line follows the clause's own language, so in a caption labelled
Mandarin an English clause's line under English is Chinese:
"It's not what I expected in the beginning," -> 这与我最初的预期不同。. The app
read the line's language from the caption's label - English - so the line
had no pinyin, no Traditional and was saved as English. Made-up text only.
"""

import csv
import io
from datetime import UTC, datetime

from polyglotic_desktop.core.listening.caption_model import caption_model
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
    line_language,
    mandarin_written,
)
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    RowKind,
    caption_rows,
)
from polyglotic_desktop.core.listening.history import Caption, keep_translations
from polyglotic_desktop.core.listening.settling import settle
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.core.listening.transcript import as_csv, translation_text

EN = Language("en")
ZH = Language("zh")
HANT = Language("zh-hant")
SECONDS = {EN: ZH}
NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)

SAID = "It's not what I expected in the beginning,"
LINE = "这与我最初的预期不同。"
EXPECTED = WordLink((16, 24), (6, 8), True, 0.9)  # expected - 预期


def english_clause(written: Language | None = None) -> Clause:
    """490's English clause, its Chinese line kept under English - the
    server saying it is `written` in (None: an older server, silent)."""
    return Clause(SAID, {EN: LINE}, {EN: (EXPECTED,)}, {EN: written} if written else {})


CHINESE_CLAUSE = Clause(
    "对，最后就回到这里。", {EN: "Right, and then back to here."}, {}, {EN: EN}
)


def mandarin_caption(*clauses: Clause) -> Caption:
    return Caption(
        1,
        CaptionId("a"),
        SourceId("app"),
        False,
        False,
        clauses,
        ZH,
        (ZH, EN),
        NOW,
        NOW,
    )


def test_a_lines_language_is_the_servers_word_for_it() -> None:
    said = english_clause(ZH)
    assert line_language(said, EN, ZH, ZH) == ZH
    assert line_language(said, EN, ZH, None) == ZH
    # an older server's: worked out from the caption's language, as before
    older = english_clause()
    assert line_language(older, EN, ZH, ZH) == EN
    assert line_language(older, EN, EN, ZH) == ZH  # polyglotic-hq 427


def test_the_chinese_line_of_an_english_clause_is_a_chinese_row() -> None:
    """Its row is in Chinese - its font, its pinyin and its lookups - and
    its links are still the target's."""
    caption = mandarin_caption(english_clause(ZH), CHINESE_CLAUSE)
    rows = caption_rows(caption, EN, ZH, DisplayOptions())
    translations = [r for r in rows if r.kind is RowKind.TRANSLATION]
    assert [(r.text, r.language, r.target) for r in translations] == [
        (LINE, ZH, EN),
        ("Right, and then back to here.", EN, EN),
    ]
    # the window's model, as the one layout reads it
    model = caption_model(caption, EN, ZH)
    assert [c.language for c in model.clauses] == [ZH, EN]


def test_without_the_servers_word_the_row_is_as_before() -> None:
    caption = mandarin_caption(english_clause())
    rows = caption_rows(caption, EN, ZH, DisplayOptions())
    assert rows[1].language == EN


def test_a_line_kept_under_a_second_target_says_its_own() -> None:
    """A window into Japanese, Chinese its second, with no Japanese line
    (it failed): it shows the line kept under Chinese - a second target,
    which a Mandarin caption has in Chinese's own second, English. Its
    language is the server's, not the key's."""
    clause = Clause("你好。", {ZH: "Hello."}, {}, {ZH: EN})
    rows = caption_rows(mandarin_caption(clause), Language("ja"), ZH, DisplayOptions())
    assert (rows[1].text, rows[1].language, rows[1].target) == ("Hello.", EN, ZH)


def update(*clauses: Clause, language: Language = ZH) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId("c1"),
        SourceId("app"),
        CaptionKind.FINISHED,
        clauses=clauses,
        language=language,
        languages_heard=(language, EN),
    )


def traditional(text: str) -> str:
    return text.replace("这与", "這與").replace("预期", "預期")


def test_the_chinese_line_is_written_in_the_learners_script() -> None:
    """Traditional for a learner who reads it (decision 0164): the line is
    Mandarin, so it is converted - and the English one beside it isn't."""
    written = mandarin_written(
        update(english_clause(ZH), CHINESE_CLAUSE), traditional, SECONDS
    )
    assert written.clauses[0].translations == {EN: "這與我最初的預期不同。"}
    assert written.clauses[0].links == {EN: (EXPECTED,)}  # one character for one
    assert written.clauses[0].written_in == {EN: ZH}
    assert written.clauses[1].translations == CHINESE_CLAUSE.translations
    # a line the server says is Traditional already is left as it is
    hant = Clause(SAID, {EN: "这与我最初的预期不同。"}, {}, {EN: HANT})
    (kept,) = mandarin_written(update(hant), traditional, SECONDS).clauses
    assert kept.translations == hant.translations


def test_the_chinese_line_is_saved_as_chinese() -> None:
    caption = mandarin_caption(english_clause(ZH), CHINESE_CLAUSE)
    rows = list(csv.reader(io.StringIO(as_csv([caption], [EN, ZH], seconds=SECONDS))))
    assert rows[1][5:] == [
        SAID + "对，最后就回到这里。",
        SAID + " Right, and then back to here.",
        LINE + "对，最后就回到这里。",
    ]
    assert translation_text(caption, [EN, ZH], SECONDS) == (
        f"{SAID} Right, and then back to here.\n{LINE}对，最后就回到这里。"
    )


def test_a_kept_translation_keeps_its_language() -> None:
    """A live update without a clause's translation keeps the one before -
    and what it is written in."""
    before = (english_clause(ZH),)
    after = (Clause(SAID),)
    (kept,) = keep_translations(before, after, live=True)
    assert kept.translations == {EN: LINE} and kept.written_in == {EN: ZH}
    # an older server's kept line says nothing
    (kept,) = keep_translations((english_clause(),), after, live=True)
    assert kept.written_in == {}


def test_settled_words_keep_the_updates_languages() -> None:
    """Words shown long enough stay, the update's row around them - with
    its translation and what that is written in."""
    shown = (Clause("It is not what I expected", {EN: "不是"}, {}, {EN: ZH}),)
    (row,) = settle(shown, (english_clause(ZH),), len("It is not "))
    assert row.original == "It is not what I expected in the beginning,"
    assert row.translations == {EN: LINE} and row.written_in == {EN: ZH}
