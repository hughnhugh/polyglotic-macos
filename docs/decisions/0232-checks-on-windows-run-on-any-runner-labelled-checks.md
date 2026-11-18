# 0232 Checks (Windows) runs on any runner labelled `checks`; the second PC's runner takes nothing else

- **Status:** accepted (reversible; changes where decision 0025's Checks (Windows) runs, not when - that's 0167)
- **Date:** 2026-11-18
- **Decided by:** Claude, 2026-11-18, on polyglotic-hq project 504's
  proposal (its brief: "If its goldens differ, don't let it take UI lab
  jobs (labels) until resolved"; "move load off the main PC"). Claude
  reviews it with the pull request.

## Situation

The user's PC carries the live server, and on 2026-11-18 its memory (31 GB,
the live Docker VM 15.8 GB) stalled the trains for hours; the two Windows
runners' jobs (~2.4 GB each) are the biggest load that can move. The user
has a second PC (`gpubox`: Windows 10 22H2, Ryzen 5 5600X, 16 GB), and
polyglotic-hq 504 put a third Windows runner on it, `gpubox-windows`.

Its trial run (both Windows jobs on it alone, 2026-11-18, run 44202642634):

- **UI lab:** 193 of 215 states drew as their goldens; 22 didn't (Windows
  10 has no Segoe Fluent Icons and an older Malgun Gothic, and one popover
  moves with the icons). The start with 30,000 words took 510 ms against
  its 400 ms budget. The goldens and main's timing record belong to the
  user's PC (decisions 0031, 0136).
- **Checks (Windows):** 6,632 passed, 3 failed: the trial's own workflow
  edit; `test_this_pc_is_as_before`, which wants Windows 11; and a pack
  learner's start, whose interface thread froze a median 101 ms against
  100 on the slower CPU. pytest took 16 minutes (12-13 on the user's PC),
  close to the job's 20. (Segoe Fluent Icons, which the band's tests
  measure with, is installed on gpubox from Microsoft's design download.)

With bare `[self-hosted, windows]`, any job lands on any Windows runner.

## Decision

- **Checks (Windows) runs on any runner labelled `checks`**
  (`runs-on: [checks]`), with 30 minutes instead of 20.
- **The second PC's runner carries only labels of its own** (`gpubox`,
  `polyglotic`, and `checks` once its Checks pass): registered with
  `--no-default-labels`, never `self-hosted` or `windows`. So it takes
  Checks and nothing else; the UI lab, the release, Package, audit and the
  dictionary packs stay `[self-hosted, windows]`, on the user's PC.
- The user's PC's two runners carry `checks` too. Moving Checks off them
  is taking the label away (polyglotic-hq `scripts/RUNNERS.md`), once the
  second PC passes it.

`tests/test_workflows.py` holds Checks' label and time and the other two
jobs' labels. Labels are set on GitHub (`gh api -X POST
repos/hughnhugh/polyglotic-desktop/actions/runners/<id>/labels -f
"labels[]=checks"`).

## Why

- **Opt in, not opt out:** a runner on another machine takes only the jobs
  proven there. Labels on the user's PC's runners for the jobs that must
  stay (`goldens`, `release`) would have let the second PC take every
  unlabelled job too (Package, audit), none of them tried there.
- **Checks is the job worth moving:** the whole suite, ~2.4 GB, on every
  train and push to main. The UI lab can't move (its goldens and timings).
- Not taken: re-approving goldens on the second PC (then the user's PC
  would be the odd one out); upgrading it to Windows 11 (the user's call,
  and its fonts must then match); a runner group (an organisation
  feature).

## What would make us reverse it

- The second PC off for long while it holds Checks: give a runner on the
  user's PC `checks` again; queued jobs wait up to 24 hours meanwhile.
- The second PC drawing the goldens' pixels (Windows 11 at the same
  fonts): it could take the UI lab too, with the default labels back.
