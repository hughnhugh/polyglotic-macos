"""Build Japanese-to-Chinese draft meanings from Tomoshi's open SQLite release.

Decompress tomoshi-dict-open.db.zst from SOURCE first. Supply matching English
and Chinese Polyglotic JMdict packs and their pinned JMdict ZIP. Output files
use the meanings rider schema and keep the draft flag on every imported row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from polyglotic_desktop.adapters.meanings_file import write_meanings
from polyglotic_desktop.core.lexicon.chinese import is_han
from tools.dictionaries import jmdict
from tools.dictionaries.entry_ids import Registry, assign_ids
from tools.dictionaries.packs import JMDICT, REGISTRY

SOURCE = "https://github.com/tomoshi-app/tomoshi-dict-data/releases/tag/v2026-11-16"
SOURCE_DIGEST = "86d95f8f0760ce6cc8505c467c6b5613010a3ba8a0ea4c9e9427eb521f0e29bc"
LICENCE = "CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)"


# Project 902's review of the pinned release. Key by JMdict sequence and exact
# English sense so corrections follow the sense, even if the pack reorders it.
# A missing replacement keeps the upstream gloss for that locale.
CORRECTIONS: dict[tuple[int, str], tuple[str | None, str | None]] = {
    (2489030, "mace"): ("肉豆蔻衣", "肉豆蔻衣"),
    (2410500, "to imitate; to copy; to mock; to replace; to model after"): (
        "模仿；复制；替代；仿造",
        "模仿；複製；替代；仿造",
    ),
    (
        1574780,
        (
            "to cry out in one's sleep (e.g. from having a nightmare); "
            "to moan (in anguish) in one's sleep"
        ),
    ): (None, "在睡夢中驚叫；在睡夢中呻吟"),
    (2831181, "cordon bleu; dish of veal or ham with Swiss cheese"): (
        "蓝带肉排（夹瑞士奶酪）",
        "藍帶肉排（夾瑞士起司）",
    ),
    (1923040, "young girls who imitate the style of singer Amuro Namie"): (
        "安室系女孩（模仿安室奈美惠的穿搭）",
        "安室系女孩（模仿安室奈美惠的穿搭）",
    ),
    (2821560, "sprinkling salt on a raw vegetable and rubbing it in"): (
        "盐揉（蔬菜）",
        "鹽揉（蔬菜）",
    ),
    (2123120, "mochi cut thin, dried, and baked or fried"): (
        "日式糯米脆饼",
        "日式糯米脆餅",
    ),
    (2843362, "rural local self-government (Muromachi period)"): (
        "惣村（室町时期的自治村落）",
        "惣村（室町時代的自治村落）",
    ),
    (
        1304400,
        (
            "to kill (a human) using a blade (sword, machete, knife, etc.); "
            "to slice (off); to lop (off); to cut (off)"
        ),
    ): ("斩杀；切断；砍掉；割掉", "斬殺；切斷；砍掉；割掉"),
    (
        1522770,
        "number (of long, cylindrical things, movies, trains, home runs, etc.)",
    ): (
        "数量（以「本」计，如细长物、电影、列车、本垒打）",
        "數量（以「本」計，如細長物、電影、列車、全壘打）",
    ),
    (
        2829768,
        "ceremony honouring the spirits of ancestors (esp. the Bon festival)",
    ): ("祭祖仪式（尤指盂兰盆节）", "祭祖儀式（尤指盂蘭盆節）"),
    (1722450, "place for storing things; container; compartment; closet; pocket"): (
        "储物处；容器；隔间；壁橱；口袋",
        "收納空間；容器；隔間；壁櫥；口袋",
    ),
}


def source_database(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def digest(path: Path) -> str:
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def parent_entries(path: Path, language: str) -> dict[str, str]:
    with closing(source_database(path)) as db:
        info = dict(db.execute("SELECT key, value FROM info"))
        if (info.get("dictionary"), info.get("meanings_language")) != (
            "jmdict",
            language,
        ):
            raise ValueError(f"{path}: expected the {language} JMdict pack")
        return dict(db.execute("SELECT id, meanings FROM entries"))


def drafts(
    database: Path,
    entries: dict[str, str],
    chinese: dict[str, str],
    ids: dict[str, str],
) -> Iterator[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    if entries.keys() != chinese.keys():
        raise ValueError("The English and Chinese JMdict entry IDs differ")
    with closing(source_database(database)) as db:
        db.execute("PRAGMA temp_store=FILE")
        for seq, cn_data, tw_data, original in db.execute(
            "SELECT cn.entry_id, cn.data, tw.data, entry.data FROM zh_defs AS cn "
            "JOIN zh_defs_zhtw AS tw USING (entry_id) "
            "JOIN entries AS entry ON entry.id = cn.entry_id "
            "WHERE cn.locale = 'zh-CN' AND tw.locale = 'zh-TW'"
        ):
            entry_id = ids.get(str(seq))
            if entry_id is None or entry_id not in entries:
                continue
            if entries[entry_id] != chinese[entry_id]:
                continue
            english = entries[entry_id].splitlines()
            source = [
                "; ".join(g["text"] for g in sense["glosses"] if g["lang"] == "eng")
                for sense in json.loads(original)["senses"]
            ]
            source_counts, parent_counts = Counter(source), Counter(english)
            cn_senses = json.loads(cn_data)["senses"]
            tw_senses = json.loads(tw_data)["senses"]
            aligned = {}
            for ordinal, gloss in enumerate(source):
                if not gloss or source_counts[gloss] != 1 or parent_counts[gloss] != 1:
                    continue
                key = str(ordinal)
                cn = chinese_gloss(cn_senses.get(key, {}).get("glosses", ()))
                tw = chinese_gloss(tw_senses.get(key, {}).get("glosses", ()))
                if cn and tw:
                    revised_cn, revised_tw = CORRECTIONS.get(
                        (int(seq), gloss), (None, None)
                    )
                    aligned[gloss] = revised_cn or cn, revised_tw or tw
            if aligned:
                yield (
                    entry_id,
                    tuple(
                        aligned[gloss][0] if gloss in aligned else gloss
                        for gloss in english
                    ),
                    tuple(
                        aligned[gloss][1] if gloss in aligned else gloss
                        for gloss in english
                    ),
                )


def chinese_gloss(glosses: list[dict[str, str]]) -> str:
    return "；".join(
        text
        for gloss in glosses
        if (text := gloss["text"].strip())
        and "\n" not in text
        and "\r" not in text
        and any(map(is_han, text))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tomoshi", type=Path, required=True)
    parser.add_argument("--jmdict", type=Path, required=True)
    parser.add_argument("--english", type=Path, required=True)
    parser.add_argument("--chinese", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--version", default="2026.11.16")
    args = parser.parse_args()
    for path, expected in ((args.tomoshi, SOURCE_DIGEST), (args.jmdict, JMDICT.sha256)):
        if digest(path) != expected:
            parser.error(f"{path}: digest differs from the pinned source")
    _, entries = jmdict.read(args.jmdict)
    ids = assign_ids(
        Registry.load(REGISTRY / "jmdict.tsv", "jmdict"), (e.seq for e in entries)
    )
    rows = list(
        drafts(
            args.tomoshi,
            parent_entries(args.english, "en"),
            parent_entries(args.chinese, "zh"),
            ids,
        )
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for column, language in enumerate(("zh", "zh_TW"), start=1):
        write_meanings(
            args.out / f"jmdict-{language}-{args.version}-draft.meanings",
            {
                "dictionary": "jmdict",
                "language": "ja",
                "meanings_language": language,
                "version": args.version,
                "licence": LICENCE,
                "source": f"Tomoshi (Y1Z), JMdict (EDRDG), {SOURCE}",
                "source_sha256": SOURCE_DIGEST,
                "changes": "Sense-aligned to Polyglotic JMdict; stored as machine drafts",
                "parent_en_sha256": digest(args.english),
                "parent_zh_sha256": digest(args.chinese),
            },
            ((entry_id, (cn, tw)[column - 1], True) for entry_id, cn, tw in rows),
        )
    print(f"{len(rows):,} draft entries per locale")


if __name__ == "__main__":
    main()
