"""The release check before a tag (polyglotic-hq RELEASING.md section 2,
project 225): each item it can answer from git and GitHub passes or fails
with its evidence, against stand-ins for both."""

from datetime import date
from pathlib import Path

import pytest
from tools.release_check import (
    declared_flags,
    flags_in_order,
    main_is_green,
    migration_count,
    notes_written,
    package_paths,
    schemas_since_last_release,
)

from tools import release_check

SHA = "c" * 40
OLDER = "b" * 40
NEWER = "d" * 40
PACKAGE_YML = Path(release_check.REPO, ".github", "workflows", "package.yml")
NOTES = "## Unreleased\n\n### New\n\n## 0.1.0 - 2026-11-12\n\n### New\n\n- First.\n"


def fake_git(
    files: dict[str, str] | None = None,
    on_main: bool = True,
    ancestors: tuple[str, ...] = (OLDER,),
    changed: str = "",
    tag: str | None = None,
) -> release_check.Git:
    """git as the check calls it: `show REF:PATH`, `merge-base --is-ancestor`,
    `diff --name-only`, `describe`."""
    files = files or {}

    def git(*args: str) -> str | None:
        if args[0] == "show":
            return files.get(args[1])
        if args[:2] == ("merge-base", "--is-ancestor"):
            if args[2] == SHA:
                return "" if on_main else None
            return "" if args[2] in ancestors else None
        if args[0] == "diff":
            return changed
        if args[0] == "describe":
            return tag
        raise AssertionError(args)

    return git


def fake_runs(
    ci: list[dict[str, object]], package: list[dict[str, object]]
) -> release_check.Runs:
    return lambda workflow, _: ci if workflow == "ci.yml" else package


def run(
    head: str, conclusion: str = "success", status: str = "completed"
) -> dict[str, object]:
    return {
        "headSha": head,
        "status": status,
        "conclusion": conclusion,
        "databaseId": 7,
    }


PACKAGE_FILES = {
    f"{SHA}:.github/workflows/package.yml": PACKAGE_YML.read_text(encoding="utf-8")
}


def test_package_paths_are_package_ymls_own() -> None:
    paths = package_paths(PACKAGE_YML.read_text(encoding="utf-8"))
    assert "src" in paths
    assert "uv.lock" in paths


def test_main_green_and_package_passed_before_it_with_nothing_changed() -> None:
    item = main_is_green(
        SHA,
        fake_git(PACKAGE_FILES),
        fake_runs([run(SHA)], [run(NEWER), run(OLDER, "cancelled"), run(OLDER)]),
    )
    assert item.passed, item.evidence
    assert "Package passed on bbbbbbb" in item.evidence[1]


@pytest.mark.parametrize(
    ("git", "ci", "package", "says"),
    [
        (
            fake_git(PACKAGE_FILES, on_main=False),
            [run(SHA)],
            [run(SHA)],
            "isn't on origin/main",
        ),
        (fake_git(PACKAGE_FILES), [], [run(SHA)], "CI hasn't run"),
        (
            fake_git(PACKAGE_FILES),
            [run(SHA, "", "in_progress")],
            [run(SHA)],
            "in_progress",
        ),
        (
            fake_git(PACKAGE_FILES),
            [run(SHA, "failure")],
            [run(SHA)],
            "CI on ccccccc: failure",
        ),
        (
            fake_git(PACKAGE_FILES),
            [run(SHA)],
            [run(SHA, "failure")],
            "Package on ccccccc: failure",
        ),
        (
            fake_git(PACKAGE_FILES, changed="src/a.py\n"),
            [run(SHA)],
            [run(OLDER)],
            "run Package by hand",
        ),
        (fake_git(PACKAGE_FILES), [run(SHA)], [run(NEWER)], "no Package run"),
    ],
)
def test_main_isnt_green(
    git: release_check.Git, ci: list, package: list, says: str
) -> None:
    item = main_is_green(SHA, git, fake_runs(ci, package))
    assert not item.passed
    assert says in " ".join(item.evidence)


def test_the_notes_at_the_commit() -> None:
    git = fake_git({f"{SHA}:RELEASE-NOTES.md": NOTES})
    assert notes_written(SHA, "0.1.0", git).passed
    missing = notes_written(SHA, "0.2.0", git)
    assert not missing.passed
    assert "no '## 0.2.0" in missing.evidence[0]
    assert not notes_written(SHA, "0.1.0", fake_git()).passed


def schema(count: int) -> str:
    return f"_MIGRATIONS: tuple[tuple[str, ...], ...] = ({'(),' * count})\n"


def schema_files(ref: str, learning: int, outbox: int) -> dict[str, str]:
    return {
        f"{ref}:{release_check.SCHEMAS['learning']}": schema(learning),
        f"{ref}:{release_check.SCHEMAS['outbox']}": schema(outbox),
    }


def test_the_first_release_has_nothing_to_migrate_from() -> None:
    item = schemas_since_last_release(SHA, fake_git(schema_files(SHA, 5, 2)))
    assert item.passed
    assert item.evidence == [
        "learning: version 5, the first release - nothing to migrate from",
        "outbox: version 2, the first release - nothing to migrate from",
    ]


def test_a_schema_since_the_last_release_is_named_and_one_that_went_down_fails() -> (
    None
):
    files = schema_files(SHA, 6, 1) | schema_files("v0.1.0", 5, 2)
    item = schemas_since_last_release(SHA, fake_git(files, tag="v0.1.0"))
    assert not item.passed
    assert (
        "learning: 5 -> 6 since v0.1.0 - it runs first on the alpha" in item.evidence[0]
    )
    assert item.evidence[1] == "outbox: version 1, lower than 2 at v0.1.0"


def test_the_count_is_read_from_source() -> None:
    assert migration_count("_MIGRATIONS: tuple = ((), (), ())") == 3
    assert migration_count("_MIGRATIONS = ((),)") == 1
    with pytest.raises(ValueError, match="no _MIGRATIONS"):
        migration_count("")


SERVER_FLAGS = """
DECLARED: tuple[Flag, ...] = (
    Flag(name="a", description="", owner="claude", expires=date(2027, 1, 31), default=False),
    Flag(name="b", description="", owner="", expires=date(2026, 11, 1), default=0),
)
"""


def test_flags_with_an_owner_and_an_expiry_to_come() -> None:
    flags = declared_flags(SERVER_FLAGS)
    assert flags[0] == {
        "name": "a",
        "description": "",
        "owner": "claude",
        "expires": date(2027, 1, 31),
        "default": False,
    }
    item = flags_in_order(SERVER_FLAGS, today=date(2026, 11, 8))
    assert not item.passed
    assert item.evidence[:3] == [
        "a: claude, expires 2027-01-31",
        "b: no owner",
        "b: expired on 2026-11-01",
    ]


def test_no_flags_is_in_order_and_too_many_isnt() -> None:
    assert flags_in_order("DECLARED: tuple[Flag, ...] = ()\n", date(2026, 11, 8)).passed
    many = (
        "DECLARED = ("
        + "".join(
            f'Flag(name="f{i}", owner="x", expires=date(2027, 1, 1)),'
            for i in range(11)
        )
        + ")"
    )
    item = flags_in_order(many, date(2026, 11, 8))
    assert not item.passed
    assert "11 flags declared: more than 10" in item.evidence
    assert not flags_in_order(None, date(2026, 11, 8)).passed


APP_MAIN = """SERVER = "https://api.polyglotic.io"
UPDATES = "https://updates.polyglotic.io/"
FEED_KEYS: tuple[str, ...] = ("k",)
"""
SERVER_SESSION = "PROTOCOLS = {1}\n"
SERVER_MAIN = """class Config:
    min_app_version: str = "0.1.0"
"""


def app_files(main: str = APP_MAIN, protocol: int = 1) -> dict[str, str]:
    return {
        f"{SHA}:{release_check.APP_MAIN}": main,
        f"{SHA}:{release_check.APP_PROTOCOL}": f"PROTOCOL = {protocol}\n",
    }


def server_files(minimum: str = "0.1.0") -> dict[str, str]:
    return {
        f"origin/main:{release_check.SERVER_SESSION}": SERVER_SESSION,
        f"origin/main:{release_check.SERVER_MAIN}": SERVER_MAIN.replace(
            "0.1.0", minimum
        ),
        f"origin/main:{release_check.SERVER_FLAGS}": "DECLARED = ()\n",
    }


def test_real_addresses_and_a_server_that_takes_this_app() -> None:
    item = release_check.what_the_app_needs(
        SHA, "0.1.0", fake_git(app_files()), fake_git(server_files())
    )
    assert item.passed, item.evidence
    assert item.evidence[:3] == [
        "main.SERVER: https://api.polyglotic.io",
        "main.UPDATES: https://updates.polyglotic.io/",
        "main.FEED_KEYS: 1 key(s)",
    ]


@pytest.mark.parametrize(
    ("main", "protocol", "minimum", "says"),
    [
        (
            APP_MAIN.replace("api.polyglotic.io", "api.polyglotic.invalid"),
            1,
            "0.1.0",
            "main.SERVER is",
        ),
        (
            APP_MAIN.replace("https://updates", "http://updates"),
            1,
            "0.1.0",
            "main.UPDATES is",
        ),
        (APP_MAIN, 2, "0.1.0", "protocol 2: polyglotic-server's origin/main takes {1}"),
        (APP_MAIN, 1, "0.2.0", "below the server's default min_app_version 0.2.0"),
    ],
)
def test_what_the_app_needs_isnt_there(
    main: str, protocol: int, minimum: str, says: str
) -> None:
    item = release_check.what_the_app_needs(
        SHA,
        "0.1.0",
        fake_git(app_files(main, protocol)),
        fake_git(server_files(minimum)),
    )
    assert not item.passed
    assert says in " ".join(item.evidence)


def test_no_feed_keys_is_said() -> None:
    main = APP_MAIN.replace('("k",)', "()")
    item = release_check.what_the_app_needs(
        SHA, "0.1.0", fake_git(app_files(main)), fake_git(server_files())
    )
    assert item.passed
    assert "isn't checked (DECISIONS #13: before the beta)" in item.evidence[2]


def test_the_report_fails_on_any_item_and_reminds_of_the_live_server_and_the_tag() -> (
    None
):
    files = (
        PACKAGE_FILES
        | {f"{SHA}:RELEASE-NOTES.md": NOTES}
        | schema_files(SHA, 5, 2)
        | app_files()
    )
    items = release_check.check(
        "0.1.0",
        SHA,
        fake_git(files),
        fake_git(server_files()),
        fake_runs([run(SHA)], [run(SHA)]),
        date(2026, 11, 8),
    )
    assert [i.number for i in items] == [1, 2, 3, 4, 5]
    assert all(i.passed for i in items), [i.evidence for i in items]
    text = release_check.report("0.1.0", SHA, items)
    assert text.count("PASS") == 5
    assert "3. (by hand) the live server" in text
    assert "6. (the user) the signed tag" in text
