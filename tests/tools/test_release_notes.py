"""The release notes' one source (polyglotic-hq RELEASING.md section 10, G7):
`RELEASE-NOTES.md` parses, and a version's notes are what the GitHub
Release carries - or the release stops."""

from pathlib import Path

import pytest
import yaml
from tools.package import release_notes
from tools.package.release_notes import notes_for, parse

FILE = """# Release notes

Anything before the first section is the file's own introduction.

## Unreleased

### New

### Better

### Fixed

## 0.2.0 - 2026-11-20

A short paragraph about
the release.

### New

- Something new, wrapped
  onto a second line.

### Fixed

- A fix.

## 0.1.0 - 2026-11-12

### New

- The first alpha.
"""


def test_a_versions_notes_are_its_groups_in_order() -> None:
    section = notes_for(FILE, "v0.2.0")
    assert section.date == "2026-11-20"
    assert section.groups == {
        "New": ["Something new, wrapped onto a second line."],
        "Fixed": ["A fix."],
    }
    assert section.markdown() == (
        "A short paragraph about the release.\n\n"
        "### New\n\n- Something new, wrapped onto a second line.\n\n"
        "### Fixed\n\n- A fix.\n"
    )


def test_unreleased_is_a_section_with_no_lines() -> None:
    unreleased = parse(FILE)[0]
    assert unreleased.title == "Unreleased"
    assert unreleased.groups == {"New": [], "Better": [], "Fixed": []}


def test_a_tag_without_a_section_has_no_notes() -> None:
    with pytest.raises(LookupError, match=r"no '## 0\.3\.0"):
        notes_for(FILE, "v0.3.0")


def test_a_section_with_no_lines_has_no_notes() -> None:
    with pytest.raises(LookupError, match="no lines"):
        notes_for(FILE.replace("- The first alpha.\n", ""), "0.1.0")


@pytest.mark.parametrize(
    ("broken", "says"),
    [
        (FILE.replace("## 0.1.0 - 2026-11-12", "## 0.1.0"), "X.Y.Z - YYYY-MM-DD"),
        (FILE.replace("### Fixed\n\n- A fix.", "### Fixes\n\n- A fix."), "the groups"),
        (
            FILE.replace("A short paragraph about", "- A line before a group"),
            "belongs in",
        ),
        (FILE.replace("- A fix.", "A fix without its dash."), "starts with '- '"),
        (FILE.replace("0.2.0 - 2026", "0.0.9 - 2026"), "newest version comes first"),
        (FILE.replace("0.2.0 - 2026", "0.1.0 - 2026"), "two sections"),
    ],
)
def test_what_the_format_doesnt_allow_is_refused(broken: str, says: str) -> None:
    with pytest.raises(ValueError, match=says):
        parse(broken)


def test_the_command_writes_the_notes_or_fails(tmp_path: Path) -> None:
    source = tmp_path / "RELEASE-NOTES.md"
    source.write_text(FILE, encoding="utf-8")
    out = tmp_path / "notes.md"
    assert release_notes.main(["v0.1.0", "--file", str(source), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == "### New\n\n- The first alpha.\n"
    missing = tmp_path / "missing.md"
    assert (
        release_notes.main(["v9.9.9", "--file", str(source), "--out", str(missing)])
        == 1
    )
    assert not missing.exists()


def test_the_repos_own_notes_parse() -> None:
    """RELEASE-NOTES.md keeps the format, with Unreleased first and its three
    groups ready for the next pull request's line - and none of its lines
    under a version too (parse refuses that)."""
    sections = parse(release_notes.NOTES.read_text(encoding="utf-8"))
    assert sections[0].title == "Unreleased"
    assert list(sections[0].groups) == list(release_notes.GROUPS)
    for section in sections[1:]:
        assert section.lines() or section.intro, f"{section.title} says nothing"


def test_unreleased_names_only_settings_sections_the_app_has() -> None:
    """A line under Unreleased that sends a tester to "Settings - X" (or
    "Settings > X") names one of Settings' sections as the app has them
    now: Look, Word links, Readings, Timing, Speech, Dictation, App, Lab
    (304, 470). "Settings - Captions" went with 304, and still sent testers there (polyglotic-hq
    329's #606, and 336: the hidden windows' Behaviour is in Timing)."""
    import re

    from polyglotic_desktop.ui_next.settings_page import SECTIONS

    # Unreleased, and the newest version under it: right after a release's
    # cut Unreleased is empty, and the lines to hold are that version's
    newest = parse(release_notes.NOTES.read_text(encoding="utf-8"))[:2]
    text = " ".join(
        line
        for section in newest
        for items in section.groups.values()
        for line in items
    )
    named = re.findall(r"Settings\s*(?:-|>)\s*(Word links|[A-Z][a-z]+)", text)
    assert named, "no line names a section: the pattern no longer matches"
    keys = {"word links": "links"}  # its tab's name, and its key (470)
    assert [n for n in named if keys.get(n.lower(), n.lower()) not in SECTIONS] == []


PUBLISHED = {
    "0.1.0": "2026-11-11",
    "0.1.1": "2026-11-11",
    "0.1.2": "2026-11-11",
    "0.1.3": "2026-11-11",
    "0.1.4": "2026-11-12",
}
"""The versions testers were sent, and the day (Melbourne's) each was
published (polyglotic-hq journal, 2026-11-11 and 2026-11-12)."""


def test_every_published_version_has_its_section() -> None:
    """321: 0.1.1-0.1.4 were published with their lines left under
    Unreleased, so the next release would have claimed them again."""
    sections = parse(release_notes.NOTES.read_text(encoding="utf-8"))
    dated = {s.title: s.date for s in sections[1:]}
    for version, day in PUBLISHED.items():
        assert dated.get(version) == day, f"{version} - {day}"


@pytest.mark.parametrize(
    "unreleased",
    [
        "- A fix.",
        "- A   fix.",  # spaced differently
    ],
)
def test_unreleased_cannot_hold_a_line_a_version_shipped(unreleased: str) -> None:
    text = FILE.replace(
        "### Fixed\n\n## 0.2.0", f"### Fixed\n\n{unreleased}\n\n## 0.2.0"
    )
    with pytest.raises(ValueError, match="0.2.0 shipped"):
        parse(text)


def test_a_rewrapped_shipped_line_is_still_the_same_line() -> None:
    text = FILE.replace(
        "### New\n\n### Better",
        "### New\n\n- Something new,\n  wrapped onto a second line.\n\n### Better",
    )
    with pytest.raises(ValueError, match="0.2.0 shipped"):
        parse(text)


UNRELEASED = """# Release notes

## Unreleased

A paragraph for the release.

### New

- A new thing, wrapped
  as it was written.

### Better

### Fixed

- A fix for 0.3.0.

## 0.2.0 - 2026-11-20

### Fixed

- A fix.
"""


def test_a_cut_moves_unreleased_under_the_version() -> None:
    text = release_notes.cut(UNRELEASED, "v0.3.0", "2026-12-01")
    sections = parse(text)
    assert [s.title for s in sections] == ["Unreleased", "0.3.0", "0.2.0"]
    assert sections[0].groups == {"New": [], "Better": [], "Fixed": []}
    assert not sections[0].intro
    assert sections[1].date == "2026-12-01"
    assert sections[1].intro == ["A paragraph for the release."]
    assert sections[1].groups == {
        "New": ["A new thing, wrapped as it was written."],
        "Fixed": ["A fix for 0.3.0."],
    }  # Better had nothing: left out
    assert "- A new thing, wrapped\n  as it was written.\n" in text  # its wrapping kept
    assert text.endswith("## 0.2.0 - 2026-11-20\n\n### Fixed\n\n- A fix.\n")
    # the next pull request's line goes under the empty Unreleased, and cuts again
    following = text.replace(
        "### Fixed\n\n## 0.3.0", "### Fixed\n\n- Next.\n\n## 0.3.0"
    )
    again = parse(release_notes.cut(following, "0.3.1", "2026-12-02"))
    assert [s.title for s in again] == ["Unreleased", "0.3.1", "0.3.0", "0.2.0"]
    assert again[1].groups == {"Fixed": ["Next."]}


@pytest.mark.parametrize(
    ("version", "day", "says"),
    [
        ("0.2.0", "2026-12-01", "isn't newer"),
        ("0.1.9", "2026-12-01", "isn't newer"),
        ("0.3", "2026-12-01", "X.Y.Z - YYYY-MM-DD"),
        ("0.3.0", "2026-02-30", "day is out of range"),
        ("0.3.0", "1 Dec 2026", "X.Y.Z - YYYY-MM-DD"),
    ],
)
def test_a_cut_refuses_what_isnt_a_new_release(
    version: str, day: str, says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        release_notes.cut(UNRELEASED, version, day)


def test_a_cut_needs_lines_to_release() -> None:
    with pytest.raises(ValueError, match="no lines to release"):
        release_notes.cut(FILE, "0.3.0", "2026-12-01")


def test_the_cut_command_dry_runs_then_cuts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "RELEASE-NOTES.md"
    source.write_bytes(UNRELEASED.replace("\n", "\r\n").encode("utf-8"))
    before = source.read_bytes()
    cut = ["v0.3.0", "--file", str(source), "--cut", "--date", "2026-12-01"]
    assert release_notes.main([*cut, "--dry-run"]) == 0
    assert source.read_bytes() == before
    assert "## 0.3.0 - 2026-12-01: 1 New, 1 Fixed, from Unreleased (dry run" in (
        capsys.readouterr().out
    )
    no_date = cut[:4]
    assert release_notes.main(no_date) == 1
    assert source.read_bytes() == before
    assert release_notes.main(cut) == 0
    after = source.read_bytes()
    assert b"\r\n## 0.3.0 - 2026-12-01\r\n" in after
    assert b"\n" not in after.replace(b"\r\n", b"")  # its line endings kept
    notes = cut[:3]
    assert release_notes.main(notes) == 0  # the version's notes are there
    assert release_notes.main(cut) == 1  # and it cuts once only


def test_the_repos_own_notes_can_be_cut() -> None:
    """The release's prep step, dry: the repo's Unreleased moves whole
    under the next version, and the file still parses."""
    text = release_notes.NOTES.read_text(encoding="utf-8")
    sections = parse(text)
    newest = sections[1].title
    major, minor, patch = (int(p) for p in newest.split("."))
    following = f"{major}.{minor}.{patch + 1}"
    if not sections[0].lines():
        with pytest.raises(ValueError, match="no lines"):
            release_notes.cut(text, following, "2099-01-01")
        return
    after = parse(release_notes.cut(text, following, "2099-01-01"))
    assert not after[0].lines()
    assert after[1].title == following
    assert after[1].groups == {g: v for g, v in sections[0].groups.items() if v}
    assert after[2:] == sections[1:]


def test_the_release_workflow_carries_the_notes() -> None:
    """release.yml stops a tag without notes before the build, and puts the
    notes above the SHA-256s on the GitHub Release."""

    workflow = Path(release_notes.NOTES.parent, ".github", "workflows", "release.yml")
    jobs = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]
    command = 'python -m tools.package.release_notes "$TAG"'
    assert any(command in str(step.get("run", "")) for step in jobs["tag"]["steps"])
    assert jobs["release"]["needs"] == "tag"  # builds and publishes (0050)
    record = next(
        s for s in jobs["release"]["steps"] if "GitHub Release" in s.get("name", "")
    )
    run = record["run"]
    assert command in run
    assert run.index("version-notes.md") < run.index("SHA256SUMS")
