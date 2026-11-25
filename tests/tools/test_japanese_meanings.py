import json
import sqlite3
from pathlib import Path

from tools.dictionaries.japanese_meanings import drafts

from polyglotic_desktop.adapters.meanings_file import SqliteMeanings, write_meanings
from polyglotic_desktop.adapters.sqlite_dictionary import (
    SqliteDictionary,
    write_dictionary,
)
from polyglotic_desktop.ports.dictionary import EntryRecord


def test_align_drafts_by_id_and_unique_gloss(tmp_path: Path) -> None:
    source = tmp_path / "tomoshi.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE entries (id INTEGER, data TEXT)")
        for table in ("zh_defs", "zh_defs_zhtw"):
            db.execute(
                f"CREATE TABLE {table} (entry_id INTEGER, locale TEXT, data TEXT)"
            )
        senses = {
            "senses": [
                {"glosses": [{"lang": "eng", "text": text}]}
                for text in ("station", "ambiguous", "ambiguous", "town", "other")
            ]
        }
        for n in (1, 2, 3):
            db.execute("INSERT INTO entries VALUES (?, ?)", (n, json.dumps(senses)))
            for table, locale, glosses in (
                ("zh_defs", "zh-CN", ("车站", "同", "歧", "城区", "其他")),
                ("zh_defs_zhtw", "zh-TW", ("車站", "同", "歧", "城區", "其他")),
            ):
                data = {
                    "senses": {
                        str(i): {"glosses": [{"text": g}]}
                        for i, g in enumerate(glosses)
                    }
                }
                db.execute(
                    f"INSERT INTO {table} VALUES (?, ?, ?)",
                    (n, locale, json.dumps(data)),
                )
    en = {"ja:a": "town\nstation\nambiguous", "ja:b": "station"}
    zh = {**en, "ja:b": "車站"}
    [(entry_id, cn, tw)] = drafts(source, en, zh, {"1": "ja:a", "2": "ja:b"})
    assert (entry_id, cn, tw) == (
        "ja:a",
        ("城区", "车站", "ambiguous"),
        ("城區", "車站", "ambiguous"),
    )
    output = tmp_path / "draft.meanings"
    write_meanings(output, {}, [(entry_id, cn, True)])
    rider = SqliteMeanings(output)
    try:
        assert rider.info["machine_made"] == "1"
        assert rider.meanings(entry_id) is None
    finally:
        rider.close()


def test_traditional_glosses_are_optional(tmp_path: Path) -> None:
    path = tmp_path / "jmdict.sqlite"
    records = [
        EntryRecord("ja:a", "駅", "", "えき", ("车站",)),
        EntryRecord("ja:b", "駅員", "", "えきいん", ("station staff (駅員)",)),
    ]
    forms = {record.headword: [record.entry_id] for record in records}
    write_dictionary(path, {}, records, forms)
    legacy = SqliteDictionary(path, traditional_glosses=True)
    try:
        assert legacy.records("駅") == records[:1]
    finally:
        legacy.close()

    write_dictionary(path, {}, records, forms, traditional_glosses={"ja:a": ("車站",)})
    original = SqliteDictionary(path)
    traditional = SqliteDictionary(path, traditional_glosses=True)
    try:
        assert original.records("駅") == records[:1]
        assert traditional.records("駅")[0].meanings == ("車站",)
        assert traditional.records("駅員") == records[1:]
        assert traditional.record("ja:a") == traditional.records("駅")[0]
    finally:
        original.close()
        traditional.close()


def test_correct_reviewed_tomoshi_senses(tmp_path: Path) -> None:
    source = tmp_path / "tomoshi.db"
    mace = "mace"
    imitate = "to imitate; to copy; to mock; to replace; to model after"
    sleep = (
        "to cry out in one's sleep (e.g. from having a nightmare); "
        "to moan (in anguish) in one's sleep"
    )
    cordon_bleu = "cordon bleu; dish of veal or ham with Swiss cheese"
    examples = (
        (2489030, (mace,), ("权杖",), ("權杖",)),
        (2410500, (imitate, "to trace; to forge"), ("嘲弄", "描摹"), ("嘲弄", "描摹")),
        (1574780, (sleep,), ("在睡梦中叫喊",), ("芍藥",)),
        (2831181, (cordon_bleu,), ("科尔顿布卢",), ("科爾頓布魯",)),
        (9999999, (mace,), ("权杖",), ("權杖",)),
    )
    entries = {}
    ids = {}
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE entries (id TEXT, data TEXT)")
        for table in ("zh_defs", "zh_defs_zhtw"):
            db.execute(f"CREATE TABLE {table} (entry_id TEXT, locale TEXT, data TEXT)")
        for seq, english, cn, tw in examples:
            entry = f"jmdict:{seq}"
            ids[str(seq)] = entry
            entries[entry] = "\n".join(english)
            original = {
                "senses": [
                    {"glosses": [{"lang": "eng", "text": gloss}]} for gloss in english
                ]
            }
            db.execute("INSERT INTO entries VALUES (?, ?)", (seq, json.dumps(original)))
            for table, locale, glosses in (
                ("zh_defs", "zh-CN", cn),
                ("zh_defs_zhtw", "zh-TW", tw),
            ):
                translated = {
                    "senses": {
                        str(i): {"glosses": [{"text": text}]}
                        for i, text in enumerate(glosses)
                    }
                }
                db.execute(
                    f"INSERT INTO {table} VALUES (?, ?, ?)",
                    (seq, locale, json.dumps(translated)),
                )

    actual = {
        entry: (cn, tw) for entry, cn, tw in drafts(source, entries, entries, ids)
    }
    assert actual["jmdict:2489030"] == (("肉豆蔻衣",), ("肉豆蔻衣",))
    assert actual["jmdict:2410500"] == (
        ("模仿；复制；替代；仿造", "描摹"),
        ("模仿；複製；替代；仿造", "描摹"),
    )
    assert actual["jmdict:1574780"] == (
        ("在睡梦中叫喊",),
        ("在睡夢中驚叫；在睡夢中呻吟",),
    )
    assert actual["jmdict:2831181"] == (
        ("蓝带肉排（夹瑞士奶酪）",),
        ("藍帶肉排（夾瑞士起司）",),
    )
    assert actual["jmdict:9999999"] == (("权杖",), ("權杖",))
