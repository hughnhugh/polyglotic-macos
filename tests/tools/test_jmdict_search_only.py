"""JMdict's search-only kanji (polyglotic-hq 461): the particle の is listed
with 乃 and 之, both kept only so a search finds them. Its entry was headed
乃 and ranked by it, so の - Japanese's commonest word - opened on 幅
("cloth breadth") and 野 ("field") before the particle."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tools.dictionaries import jmdict


def test_a_word_whose_kanji_are_search_only_is_written_in_kana(tmp_path: Path) -> None:
    words = [
        {
            "id": "1469800",
            "kanji": [{"text": "乃", "tags": ["sK"]}, {"text": "之", "tags": ["sK"]}],
            "kana": [{"text": "の", "common": True}],
            "sense": [{"misc": [], "gloss": [{"text": "indicates possessive"}]}],
        },
        {
            "id": "1358280",
            "kanji": [
                {"text": "食べる", "common": True},
                {"text": "喰べる", "tags": ["sK"]},
            ],
            "kana": [{"text": "たべる", "common": True}],
            "sense": [{"misc": [], "gloss": [{"text": "to eat"}]}],
        },
    ]
    path = tmp_path / "jmdict.json.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "jmdict.json", json.dumps({"words": words}, ensure_ascii=False)
        )
    _, read = jmdict.read(path)
    assert [w.headword for w in read] == ["の", "食べる"]
    assert read[0].kanji == ("乃", "之")  # still found by them
