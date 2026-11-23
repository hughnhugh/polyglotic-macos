from collections.abc import Collection
from dataclasses import replace

import pytest
from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.listening import _clause
from polyglotic_desktop.core.lexicon.class_evidence import for_spans
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.listening.captions import Language, WordClass, WordLink
from polyglotic_desktop.core.listening.display import (
    DisplayOptions,
    LinkDetail,
    WordLinks,
    counterpart,
    group_links,
    numbered_links,
)
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_classes import (
    ClassSpan,
    SenseClasses,
    WordClassEvidence,
)
from polyglotic_desktop.ui.recorded_captions import APP, EN, ZH, clause, finished
from polyglotic_desktop.ui_next.views.captions import CaptionLines

NOUN = WordClass.NOUN
VERB = WordClass.VERB
ADJECTIVE = WordClass.ADJECTIVE


def test_v1_word_link_classes_are_independently_optional_and_open_to_new_values() -> (
    None
):
    wire = protocol.Clause.model_validate(
        {
            "original": "Hunger",
            "translations": {"en": "hungry"},
            "links": {
                "en": [
                    {
                        "original": [0, 6],
                        "translation": [0, 6],
                        "key": True,
                        "confidence": 0.8,
                        "original_pos": "noun",
                        "translation_pos": "adjective",
                    },
                    {
                        "original": [0, 6],
                        "translation": [0, 6],
                        "key": True,
                        "confidence": 0.8,
                    },
                    {
                        "original": [0, 6],
                        "translation": [0, 6],
                        "key": True,
                        "confidence": 0.8,
                        "original_pos": "future_class",
                        "translation_pos": "adjective",
                    },
                ],
            },
        }
    )
    result = _clause(wire).links[Language("en")]
    assert [(k.original_pos, k.translation_pos) for k in result] == [
        (NOUN, ADJECTIVE),
        (None, None),
        (None, ADJECTIVE),
    ]


def test_grouped_counterparts_keep_each_original_class_and_abstain_on_conflict() -> (
    None
):
    links = [
        WordLink((0, 7), (0, 8), True, 0.8, NOUN, ADJECTIVE),
        WordLink((9, 15), (0, 8), True, 0.7, VERB, VERB),
    ]
    (group,) = group_links(links, 15, 8)
    assert group.original_pos == (NOUN, VERB)
    assert group.translation_pos is None
    original, translation = numbered_links(links, LinkDetail.MOST)
    assert [word.pos for word in original] == [NOUN, VERB]
    assert translation[0].pos is None
    assert {word.link for word in (*original, *translation)} == {0}


@pytest.mark.parametrize(
    ("classes", "server", "expected"),
    [
        (((NOUN,), (VERB,)), VERB, VERB),
        (((NOUN,), (VERB,)), ADJECTIVE, None),
        (((VERB,),), ADJECTIVE, VERB),
        (((VERB,),), None, VERB),
        (((VERB,), ()), ADJECTIVE, None),
        (((VERB,), ()), VERB, VERB),
        (((VERB,), None), ADJECTIVE, ADJECTIVE),
        ((), ADJECTIVE, ADJECTIVE),
        ((), None, None),
    ],
)
def test_context_and_complete_lexical_evidence(
    classes: tuple[SenseClasses, ...],
    server: WordClass | None,
    expected: WordClass | None,
) -> None:
    assert _classified_line(classes, server) == expected


def _classified_line(
    classes: tuple[SenseClasses, ...], server: WordClass | None
) -> WordClass | None:
    run = EntryRecord(
        "en:run",
        "run",
        "",
        "",
        tuple(str(i) for i in range(len(classes) or 1)),
        sense_classes=classes,
    )
    dictionary = EnglishDictionary(FakeDictionaryFile([run], {"run": [run.entry_id]}))
    lines = CaptionLines(
        [APP], ZH, keep=2, options=DisplayOptions(word_links=WordLinks.COLOURS)
    )
    lines.class_evidence = lambda text, lang, spans: (
        for_spans(dictionary, text, lang, spans) if lang == EN else {}
    )
    said = clause("Run!", "跑！", (("Run", "跑"),), into=ZH)
    said = replace(said, links={ZH: (replace(said.links[ZH][0], original_pos=server),)})
    lines.apply(finished("finish", said, language=EN))
    (line,) = lines.lines
    caption = lines.caption(line.key)
    assert caption is not None
    context = counterpart(caption, line.rows, 0, (0, 3))
    assert context is not None
    linked = next(row.links[0] for row in line.rows if row.text == "Run!")
    assert context.pos == linked.pos
    return linked.pos


def test_separate_endpoint_languages_fallback_links_and_cached_replacement() -> None:
    french = Language("fr")
    german = Language("de")
    lines = CaptionLines(
        [APP],
        EN,
        keep=2,
        second=french,
        options=DisplayOptions(word_links=WordLinks.COLOURS),
    )
    calls: list[tuple[str, tuple[ClassSpan, ...]]] = []

    def evidence(
        text: str, lang: str, spans: Collection[ClassSpan]
    ) -> dict[ClassSpan, WordClassEvidence]:
        calls.append((lang, tuple(spans)))
        cls = NOUN if lang == EN else VERB
        return {span: WordClassEvidence(frozenset({cls}), False) for span in spans}

    lines.class_evidence = evidence
    said = clause("Run!", "Cours !", (("Run", "Cours"),), into=french)
    link = said.links[french][0]
    said = replace(said, links={french: (link, link)}, written_in={french: german})
    lines.apply(finished("finish", said, language=EN))
    assert calls == [(EN, ((0, 3),)), (german, ((0, 5),))]
    (line,) = lines.lines
    caption = lines.caption(line.key)
    assert caption is not None
    assert [row.links[0].pos for row in line.rows] == [NOUN, VERB]
    original = counterpart(caption, line.rows, 0, (0, 3))
    translation = counterpart(caption, line.rows, 1, (0, 5))
    assert original is not None and original.pos == NOUN
    assert translation is not None and translation.pos == VERB
    assert len(calls) == 2
    lines.class_evidence = lambda *_: {}
    assert lines.refresh_link_classes()
    assert all(row.links[0].pos is None for row in lines.lines[0].rows)
    assert not lines.refresh_link_classes()


def test_only_whole_entries_and_all_capitalized_homographs_supply_evidence() -> None:
    entries = [
        EntryRecord("en:run", "run", "", "", ("to run",), sense_classes=((VERB,),)),
        EntryRecord("en:Run", "Run", "", "", ("a surname",), sense_classes=((NOUN,),)),
        EntryRecord("en:one", "one", "", "", ("a digit",), sense_classes=((NOUN,),)),
    ]
    dictionary = EnglishDictionary(
        FakeDictionaryFile(
            entries,
            {entry.headword: [entry.entry_id] for entry in entries},
            lemmas={"ran": "run"},
        )
    )
    assert for_spans(
        dictionary,
        "Run one ran 中run",
        EN,
        [(0, 3), (0, 2), (0, 7), (4, 7), (8, 11), (12, 16)],
    ) == {
        (0, 3): WordClassEvidence(frozenset({NOUN, VERB}), False),
        (8, 11): WordClassEvidence(frozenset({VERB}), False),
    }
