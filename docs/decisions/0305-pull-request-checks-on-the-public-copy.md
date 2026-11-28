# 0305 A pull request's Linux checks run on the public test copy

- **Status:** accepted
- **Date:** 2026-11-27
- **Decided by:** the user agreed DECISIONS #266 (desktop pull requests run
  their suites through the public test copy) and #267 (no paid private
  minutes) on 2026-11-27; polyglotic-hq project 981 built it.

## Situation

Checks (Linux) ran on this PC's self-hosted Linux runner (decisions 0025,
0038). That runner's container reached its 3.8 GB cap beside the live
server's models, so polyglotic-hq 963a switched it off. A job that asks
for it now waits forever: 0.1.13's train (#1258) and the hotkeys fix
(#1259) both showed `Checks (Linux)` pending, while the same suite passed
on GitHub's machines through the public test copy
(`polyglotic-linux-spike`, `GitHub's machines / Checks (Linux)`).
GitHub-hosted runners for this private repository would cost minutes.

## Decision

`Checks (Linux)` keeps its name and its place on every pull request and
push to main, but runs on the `light` runner (768 MiB, one CPU) and only
sends and waits (`tools/public_copy_checks.py`):

- the checked-out tree, committed files only, less what a public copy
  never carries (polyglotic-hq's `remote_test.py` rules), scanned with
  gitleaks and the owner's patterns before anything leaves;
- pushed to two scratch branches of the public copy, whose
  `remote-test.yml` runs the tests in slices across three machines and
  the static checks (ruff, format, mypy, the platforms' mypy,
  import-linter) on a fourth;
- the result read back from the JUnit reports: the job fails on a failed
  check or a missing report, lists a missed timing budget without failing
  (the train judges budgets, as `remote_test.py` does), links both runs,
  and deletes the branches and reports.

The two warnings (the size ratchet and the literals) stay on `light`:
they need the pull request's base and only read source. The release's tag
job moves to `light` too. A test (`tests/test_workflows.py`) fails if any
job asks for a label only the switched-off runner has. The token is a
fine-grained one for the public copy alone (`PUBLIC_COPY_TOKEN`); the
owner's patterns are a secret (`PUBLIC_COPY_SCAN`) because they can't be
written in a tree that goes public. Without either, nothing is pushed and
the check fails.

Not on the public copy: `tests/test_schema_versions.py` (it needs the
private repository's release tags). Checks (Windows) runs it on the train
and on main, and the release check repeats it before a tag.

## Why

The public copy's standard runners are free, its upload is settled
(DECISIONS #247), and its path is already the one the train uses. The
alternatives: GitHub-hosted runners here (paid minutes, #267); the Linux
runner back on with a lower cap (its suite needs 3.7 GB, beside live);
gpubox's Linux (project 893 measured 2.59 GiB free during Windows CI).

## What would make us reverse it

The public copy's queue regularly making pull requests wait much longer
than the old runner's 14-20 minutes, the free plan changing, or a reason
to stop sending unreleased code to a public repository. The single
`light` runner is held while it waits, so pull requests' checks queue
behind each other: a second `light` runner is the first remedy.
