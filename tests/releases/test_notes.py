"""What's new after an update (polyglotic-hq 345, decision 0137): the
release notes the app carries, read by version, and which show on Home -
once per version, never on a fresh install's first run, the newest first
when several versions were skipped."""

from pathlib import Path

from polyglotic_desktop.core.releases.notes import (
    newest_released,
    plain,
    plain_items,
    sections,
    seen_at_start,
    unseen,
    version_order,
)
from polyglotic_desktop.core.releases.updates import whats_new

FILE = """# Release notes

Some words about the file.

## Unreleased

### New

- Not released yet.

## 0.1.6 - 2026-11-20

### New

- **What's new:** after an update, Home says what changed. See
  [Help](https://example.com).

### Fixed

- A thing fixed.

## 0.1.5 - 2026-11-15

A paragraph about 0.1.5.

### Better

- Better `things`.

## 0.1.4 - 2026-11-14

### Fixed

- Fixed in 0.1.4.
"""
NOTES = sections(FILE)


def test_each_released_versions_notes_newest_first_not_unreleased() -> None:
    assert [(n.version, n.date) for n in NOTES] == [
        ("0.1.6", "2026-11-20"),
        ("0.1.5", "2026-11-15"),
        ("0.1.4", "2026-11-14"),
    ]
    assert NOTES[0].markdown.startswith("### New\n\n- **What's new:**")
    assert NOTES[0].markdown.endswith("- A thing fixed.")
    assert "Not released yet" not in "".join(n.markdown for n in NOTES)


def test_the_repos_own_notes_read() -> None:
    """RELEASE-NOTES.md as the app carries it: every version has notes."""
    text = (Path(__file__).parents[2] / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    found = sections(text)
    assert [n.version for n in found][-1] == "0.1.0"
    assert all(n.markdown for n in found)


def test_the_speaker_typing_line_says_what_f8_does_on_home() -> None:
    """Home's first sentence tells people which key to hold and what it does."""
    text = (Path(__file__).parents[2] / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    [section] = [part for part in text.split("\n## ") if "\n- Hold F8" in part]
    said = [
        line
        for line in whats_new(section, lines=99)
        if line.startswith(("Hold F8", "Re-speaking:"))
    ]
    assert said == [
        "Hold F8 to type what someone said through your speakers into another app."
    ]


def test_the_newest_released_version_is_what_a_copy_from_source_is() -> None:
    """Decision 0224: Unreleased isn't a version; the newest by number,
    whatever the file's order, written as protocol.md's versions are."""
    assert newest_released(NOTES) == "0.1.6"
    out_of_order = sections(
        "## 0.1.9 - 2026-11-01\n\n- a\n\n## 0.1.10 - 2026-11-02\n\n- b\n"
        "\n## 00.2.0 - 2026-11-03\n\n- c\n"
    )
    assert newest_released(out_of_order) == "0.2.0"
    assert newest_released(sections("# Notes\n\n## Unreleased\n\n- a\n")) is None
    assert newest_released(()) is None


def test_versions_in_order() -> None:
    assert version_order("0.1.10") > version_order("0.1.9")  # type: ignore[operator]
    assert version_order("v0.1.5") == (0, 1, 5)
    assert version_order("0.1.6-rc1") == (0, 1, 6)
    assert version_order("dev") is None


def test_a_fresh_installs_first_run_has_seen_this_version() -> None:
    assert seen_at_start(None, "0.1.6", fresh=True) == "0.1.6"
    assert unseen(seen_at_start(None, "0.1.6", fresh=True), "0.1.6", NOTES) == ()


def test_after_an_update_this_versions_notes_until_closed() -> None:
    seen = seen_at_start("0.1.5", "0.1.6", fresh=False)
    assert [n.version for n in unseen(seen, "0.1.6", NOTES)] == ["0.1.6"]
    # closed: seen is now this version, and nothing shows at the next start
    assert unseen("0.1.6", "0.1.6", NOTES) == ()


def test_several_versions_skipped_newest_first() -> None:
    assert [n.version for n in unseen("0.1.4", "0.1.6", NOTES)] == ["0.1.6", "0.1.5"]


def test_from_a_version_that_kept_nothing_this_versions_only() -> None:
    """0.1.5 and before kept no `seen`: where it came from isn't known."""
    assert [n.version for n in unseen(None, "0.1.6", NOTES)] == ["0.1.6"]


def test_nothing_newer_than_this_version_nor_after_a_downgrade() -> None:
    assert [n.version for n in unseen("0.1.4", "0.1.5", NOTES)] == ["0.1.5"]
    assert unseen("0.1.6", "0.1.5", NOTES) == ()  # back a channel: nothing


def test_run_from_source_or_with_no_notes_nothing() -> None:
    assert unseen("0.1.5", "dev", NOTES) == ()
    assert unseen("0.1.5", "0.1.7", ()) == ()
    assert unseen("garbled", "0.1.6", NOTES) == ()


def test_plain_text_for_help() -> None:
    assert plain(NOTES[0].markdown) == (
        "New\n"
        "• What's new: after an update, Home says what changed. See Help."
        "\n\n"
        "Fixed\n"
        "• A thing fixed."
    )
    assert plain(NOTES[1].markdown) == (
        "A paragraph about 0.1.5.\n\nBetter\n• Better things."
    )


def test_items_in_plain_words() -> None:
    assert plain_items(NOTES[0].markdown) == [
        "What's new: after an update, Home says what changed. See Help.",
        "A thing fixed.",
    ]
    assert plain_items("Just a paragraph.") == []
