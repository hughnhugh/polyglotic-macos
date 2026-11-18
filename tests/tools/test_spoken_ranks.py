"""`tools/spoken_ranks.py` (polyglotic-hq 491): each pack word's rank in
the subtitles' counts - English by its lemma, as the app counts words - kept
only where the pack ranks it rarer in writing; words the pack hasn't got
(or has only as names) never rank."""

from pathlib import Path

from tools.spoken_ranks import spoken_ranks


def counts(tmp_path: Path, lines: str) -> Path:
    path = tmp_path / "counts.txt"
    path.write_bytes(lines.encode("utf-8"))
    return path


def test_kept_only_where_the_pack_ranks_the_word_rarer(tmp_path: Path) -> None:
    pack = {"谢谢": 6361, "的": 1, "业主": 14337}
    found = spoken_ranks(
        counts(tmp_path, "的 900\n谢谢 500\n嗯嗯 400\n"), pack, {}, False
    )
    # 的: 1st said and 1st written, no rarer; 嗯嗯: not in the pack
    assert found == [("谢谢", 2)]


def test_english_counts_by_lemma(tmp_path: Path) -> None:
    pack = {"go": 50, "um": 5615, "run": 300}
    lemmas = {"went": "go", "goes": "go", "running": "run"}
    found = spoken_ranks(
        counts(tmp_path, "um 1000\nwent 600\ngoes 500\nrunning 10\n'll 900\n"),
        pack,
        lemmas,
        True,
    )
    # go: 1,100 in all, 1st said, 50th written - kept; um 2nd, kept; run 3rd
    assert found == [("go", 1), ("um", 2), ("run", 3)]
