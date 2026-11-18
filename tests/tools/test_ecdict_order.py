"""The order of an English word's Chinese meanings (tools.dictionaries.
ecdict_order, polyglotic-hq 463): the everyday meaning first."""

import pytest
from tools.dictionaries import ecdict_order
from tools.dictionaries.ecdict_order import by_use, label, ordered, with_first

CAN = ("vt. 装罐", "n. 罐头, 容器", "aux. 能, 可以", "[计] 作废字符")
"""ECDICT's "can": the card opened on 装罐, "to can" as in tins."""
CAN_USES = {"AUX": 2400, "VERB": 3, "NOUN": 5}


def test_a_line_is_labelled_by_its_part_of_speech() -> None:
    assert label("vt. 装罐") == "vt." and label("aux. 能, 可以") == "aux."
    assert label("[计] 作废字符") == "" and label("先生") == ""
    assert label("a. 好的") == "a."


def test_the_part_of_speech_english_uses_most_comes_first() -> None:
    """ "can" is an auxiliary 2,400 times in the treebank: 能, 可以 first.
    A noun 5 times in 2,408 is under `MIN_SHARE`, so it counts as none
    and ECDICT's order stands for the rest."""
    assert by_use(CAN, CAN_USES) == [
        "aux. 能, 可以",
        "vt. 装罐",
        "n. 罐头, 容器",
        "[计] 作废字符",
    ]
    assert by_use(CAN, None) == list(CAN)  # no counts: ECDICT's order


def test_lines_of_one_part_of_speech_keep_ecdicts_order() -> None:
    lines = ("n. 井", "adv. 很好地", "adv. 很", "interj. 好啦")
    assert by_use(lines, {"ADV": 10, "INTJ": 8}) == [
        "adv. 很好地",
        "adv. 很",
        "interj. 好啦",
        "n. 井",
    ]


def test_our_own_first_lines_move_replace_or_add() -> None:
    """A bare label moves ECDICT's line; a line of our own replaces
    ECDICT's line with its label, or is added when there is none."""
    may = ("n. 五月", "aux. 愿能, 可以, 愿意")
    assert with_first("may", may, ["aux. 可能, 也许, 可以"]) == [
        "aux. 可能, 也许, 可以",
        "n. 五月",
    ]
    have = ("aux. 已经", "vt. 有, 怀有")
    assert with_first("have", have, ["vt."]) == ["vt. 有, 怀有", "aux. 已经"]
    st = ("[计] 段表, 状态",)
    assert with_first("ST", st, ["abbr. 街 (Street)"]) == ["abbr. 街 (Street)", *st]
    with pytest.raises(ValueError, match="no 'adv.' line"):
        with_first("may", may, ["adv."])  # an ECDICT update moved it


def test_only_the_commonest_entries_are_reordered_but_our_lines_always_apply() -> None:
    uses = {"can": CAN_USES}
    assert ordered("can", CAN, 30, uses, {})[0] == "aux. 能, 可以"
    assert ordered("can", CAN, ecdict_order.TOP + 1, uses, {}) == CAN
    assert ordered("can", CAN, None, uses, {"can": ["aux."]})[0] == "aux. 能, 可以"


def test_our_own_file_reads() -> None:
    first = ecdict_order.read_first()
    assert first["have"] == ["vt."]
    assert first["may"][0].startswith("aux. ")
    assert all(label(line) for lines in first.values() for line in lines)
