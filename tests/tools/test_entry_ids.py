"""Stable entry IDs (decision 0007): the ID format, the registry, and
carrying IDs forward across dictionary releases - on small CC-CEDICT
samples written like the real file."""

import gzip
import re
from pathlib import Path

import pytest
from tools.dictionaries import cedict, update_ids
from tools.dictionaries.entry_ids import (
    ALPHABET,
    MAX_LENGTH,
    Registry,
    assign_ids,
    carry_forward,
    default_id,
)

OLD = """\
#! date=2026-09-27T12:50:23Z
電腦 电脑 [dian4 nao3] /computer/CL:臺|台[tai2]/
好 好 [hao3] /good; well/
一月份 一月份 [Yi1 yue4 fen4] /see 一月[Yi1 yue4]/
只言片語 只言片语 [zhi1 yan2 pian4 yu3] /just a word or two (idiom)/
表帶 表带 [biao3 dai4] /watch strap/
錶帶 表带 [biao3 dai4] /watch strap; watchband/
上衫 上衫 [shang4 shan1] /blouse/
過去 过去 [guo4 qu4] /to go over; to pass by; past/
"""

NEW = """\
#! date=2026-11-04T07:19:40Z
電腦 电脑 [dian4 nao3] /computer/CL:臺|台[tai2]/
好 好 [hao3] /good; well/
一月份 一月份 [yi1 yue4 fen4] /January/
隻言片語 只言片语 [zhi1 yan2 pian4 yu3] /just a word or two (idiom)/
錶帶 表带 [biao3 dai4] /watch strap; watchband/
過去 过去 [guo4 qu4] /to go over; to pass by/
過去 过去 [guo4 qu5] /(used after a verb) away; over/
足球 足球 [zu2 qiu2] /soccer ball; football/
"""


def entries(text: str) -> list[cedict.CedictLine]:
    return list(cedict.parse(text.splitlines()))


def carry(registry: Registry, old: str, new: str) -> dict[str, str]:
    """Carries IDs from `old` to `new` and returns the new release's IDs."""
    carry_forward(
        registry,
        [e.source_entry() for e in entries(old)],
        [e.source_entry() for e in entries(new)],
        cedict.THRESHOLDS,
        "test",
    )
    return assign_ids(registry, (e.key for e in entries(new)))


def test_an_entry_id_is_the_dictionary_and_ten_base32_characters() -> None:
    entry_id = default_id("cedict", "電腦 电脑 [dian4 nao3]")
    assert re.fullmatch(f"cedict:[{ALPHABET}]{{10}}", entry_id)
    assert len(entry_id) <= MAX_LENGTH
    assert default_id("cedict", "電腦 电脑 [dian4 nao3]") == entry_id
    assert default_id("cedict", "電腦 电脑 [dian4 nao3]", salt=1) != entry_id


def test_the_hash_never_changes() -> None:
    # Entry IDs are stored on the server: changing how they're made would
    # orphan every learner's word statuses. These values are fixed forever.
    assert default_id("cedict", "電腦 电脑 [dian4 nao3]") == "cedict:y7p98nwvxq"
    assert default_id("ecdict", "run") == "ecdict:njx2am9103"


def test_keys_without_a_record_get_their_hash() -> None:
    registry = Registry("cedict")
    ids = assign_ids(registry, ["a", "b"])
    assert ids == {"a": default_id("cedict", "a"), "b": default_id("cedict", "b")}
    assert registry.ids == {}


def test_a_taken_hash_is_salted_and_recorded_so_it_never_moves() -> None:
    # "x" was given "a"'s hash earlier (say "a"'s entry was corrected to "x").
    registry = Registry("cedict", ids={"x": default_id("cedict", "a")})
    ids = assign_ids(registry, ["a", "x"])
    assert ids["x"] == default_id("cedict", "a")
    assert ids["a"] == default_id("cedict", "a", salt=1)
    assert registry.ids["a"] == ids["a"]
    assert assign_ids(registry, ["a", "x"]) == ids


def test_unchanged_entries_keep_their_ids_with_nothing_recorded() -> None:
    registry = Registry("cedict")
    before = assign_ids(Registry("cedict"), (e.key for e in entries(OLD)))
    after = carry(registry, OLD, NEW)
    for key in ("電腦 电脑 [dian4 nao3]", "好 好 [hao3]", "過去 过去 [guo4 qu4]"):
        assert after[key] == before[key] == default_id("cedict", key)
        assert key not in registry.ids


def test_a_corrected_entry_keeps_its_id() -> None:
    registry = Registry("cedict")
    before = assign_ids(Registry("cedict"), (e.key for e in entries(OLD)))
    after = carry(registry, OLD, NEW)
    # Capital letter (a name) corrected, meanings rewritten
    assert (
        after["一月份 一月份 [yi1 yue4 fen4]"]
        == before["一月份 一月份 [Yi1 yue4 fen4]"]
    )
    # Traditional form corrected
    assert (
        after["隻言片語 只言片语 [zhi1 yan2 pian4 yu3]"]
        == before["只言片語 只言片语 [zhi1 yan2 pian4 yu3]"]
    )
    assert (
        registry.ids["一月份 一月份 [yi1 yue4 fen4]"]
        == before["一月份 一月份 [Yi1 yue4 fen4]"]
    )


def test_a_merged_entry_points_to_the_entry_it_became() -> None:
    registry = Registry("cedict")
    before = assign_ids(Registry("cedict"), (e.key for e in entries(OLD)))
    after = carry(registry, OLD, NEW)
    old_id = before["表帶 表带 [biao3 dai4]"]
    assert old_id not in after.values()
    assert registry.resolved_merges()[old_id] == after["錶帶 表带 [biao3 dai4]"]


def test_removed_and_added_entries() -> None:
    registry = Registry("cedict")
    changes = carry_forward(
        registry,
        [e.source_entry() for e in entries(OLD)],
        [e.source_entry() for e in entries(NEW)],
        cedict.THRESHOLDS,
        "test",
    )
    assert changes.removed == ["上衫 上衫 [shang4 shan1]"]
    # A new reading of 过去 is a new entry, not a change of the old one,
    # which is still there.
    assert changes.added == ["足球 足球 [zu2 qiu2]", "過去 过去 [guo4 qu5]"]
    assert len(changes.carried) == 2 and len(changes.merged) == 1


def test_a_removed_entry_that_comes_back_gets_its_old_id() -> None:
    registry = Registry("cedict")
    carry(registry, OLD, NEW)
    back = carry(registry, NEW, NEW + "上衫 上衫 [shang4 shan1] /blouse/\n")
    assert back["上衫 上衫 [shang4 shan1]"] == default_id(
        "cedict", "上衫 上衫 [shang4 shan1]"
    )


def test_an_old_key_that_reappears_after_its_id_moved_on_gets_a_new_one() -> None:
    registry = Registry("cedict")
    first = carry(registry, OLD, NEW)
    again = carry(registry, NEW, NEW + "一月份 一月份 [Yi1 yue4 fen4] /a place name/\n")
    assert (
        again["一月份 一月份 [yi1 yue4 fen4]"] == first["一月份 一月份 [yi1 yue4 fen4]"]
    )
    reappeared = again["一月份 一月份 [Yi1 yue4 fen4]"]
    assert reappeared not in first.values()
    assert len(set(again.values())) == len(again)


def test_an_entry_split_in_two_gives_its_id_to_the_likelier_half() -> None:
    old = "差 差 [cha1] /difference; to differ; wrong/\n"
    new = "差 差 [cha4] /to differ; wrong/\n差 差 [cha3] /bad; poor/\n"
    registry = Registry("cedict")
    ids = carry(registry, old, new)
    assert ids["差 差 [cha4]"] == default_id("cedict", "差 差 [cha1]")
    assert ids["差 差 [cha3]"] == default_id("cedict", "差 差 [cha3]")


def test_entries_with_the_same_characters_but_different_meanings_stay_apart() -> None:
    old = "仇 仇 [qiu2] /surname Qiu/\n"
    new = "仇 仇 [chou2] /hatred; animosity; enemy/\n"
    registry = Registry("cedict")
    changes = carry_forward(
        registry,
        [e.source_entry() for e in entries(old)],
        [e.source_entry() for e in entries(new)],
        cedict.THRESHOLDS,
        "test",
    )
    assert changes.carried == [] and changes.removed == ["仇 仇 [qiu2]"]


def test_the_registry_survives_a_save_and_load(tmp_path: Path) -> None:
    registry = Registry("cedict")
    carry(registry, OLD, NEW)
    path = tmp_path / "cedict.tsv"
    registry.save(path)
    loaded = Registry.load(path, "cedict")
    assert loaded.ids == registry.ids and loaded.merged == registry.merged
    assert loaded.notes == registry.notes


def test_merges_resolve_through_chains_and_refuse_loops() -> None:
    registry = Registry(
        "cedict", merged={"cedict:a": "cedict:b", "cedict:b": "cedict:c"}
    )
    assert registry.resolved_merges() == {
        "cedict:a": "cedict:c",
        "cedict:b": "cedict:c",
    }
    registry.merged["cedict:c"] = "cedict:a"
    with pytest.raises(ValueError, match="loop"):
        registry.resolved_merges()


def test_cedict_lines_with_the_same_key_become_one_entry() -> None:
    lines = entries(
        "好 好 [hao3] /good/\n好 好 [hao3  ] /well/\n# a comment\nnot an entry\n"
    )
    assert lines == [cedict.CedictLine("好", "好", "hao3", ("good", "well"))]


def test_update_ids_writes_the_registry(tmp_path: Path) -> None:
    old, new = tmp_path / "old.txt.gz", tmp_path / "new.txt.gz"
    for path, text in ((old, OLD), (new, NEW)):
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(text)
    registry = tmp_path / "cedict.tsv"
    assert (
        update_ids.main(["cedict", str(old), str(new), "--registry", str(registry)])
        == 0
    )
    loaded = Registry.load(registry, "cedict")
    assert len(loaded.ids) == 2 and len(loaded.merged) == 1
    assert "2026-09-27 to 2026-11-04" in loaded.notes["一月份 一月份 [yi1 yue4 fen4]"]
