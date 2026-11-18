# 0105 CI's timed start holds a lock on the PC alone; the heavy steps share it

- **Status:** accepted (reversible)
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 312, at Claude's request (2026-11-14: "a way to run the UI lab's timing job alone on the PC ... a runner lock or a concurrency group"). Claude accepted keeping the lock in ProgramData, given the runners' folders' permissions, with no ACL changes. Claude reviews it with the pull request.

## Situation

The two Windows runners (`hughs-pc-windows`, `hughs-pc-windows-2`) are two services on the user's PC, and they run two desktop jobs at once.

The start test (`tests/ui/test_start_with_a_big_learner.py`, 400 ms) slows about 45-55 ms for each 10 % of the PC in use (312). In 184 UI lab runs between 2026-11-10 and 2026-11-13, its median depended on what the other runner was doing:

| Other runner | Median | Runs over 400 ms |
|---|---|---|
| idle | 375 ms | 0 of 20 |
| a Checks job | 380 ms | 11 of 110 |
| the other UI lab | 382 ms | 3 of 33 |

From 2026-11-13 14:00 UTC, with agents busy, the start was 472 ms beside the other UI lab (7 of 8 over), whose language walk runs four processes at once.

## Decision

`tools/ci_lock.py` is a reader-writer lock on one file, `C:\ProgramData\polyglotic-ci\steps.lock`, taken with Windows' `LockFileEx` on its first byte. In `ci.yml`:
- the start test's step holds it **alone**;
- Checks (Windows)' pytest and the UI lab's language walk hold it **shared**.

An alone holder waits for the shared ones to finish and keeps new ones waiting. Shared holders run beside each other, as before.

- **Where:** in ProgramData, because no runner folder is open to both accounts (`icacls`, 2026-11-14).
  - `C:\polyglotic-runner`: `polyglotic-runner:(M)`, the user's own account `(RX)`, Administrators, SYSTEM.
  - `C:\polyglotic-runner2`: the same for `polyglotic-runner2`.
  - So neither runner can open a lock in the other's folder. In ProgramData every account may make files and read the others' (`Users:(OI)(CI)(RX)`, `(CI)(WD,AD,WEA,WA)`), and reading is enough to lock. The user's own account (agents, `local_ci.sh`) can take it there too.
- **Never left held:** a `LockFileEx` lock belongs to the open file handle. Windows releases it when the handle closes, and closes every handle of a process when the process ends. So a cancelled, timed-out or killed job can't leave the PC locked (tested: a killed holder's lock is free at once).
- **Never hangs a job:** a step waits at most 10 minutes (`--most-minutes`).
  - A step held alone then fails with "ci_lock: gave up after 10 min: other CI steps held the PC's lock ... - not this change; re-run the job".
  - A shared step runs unlocked and says so.
  - The UI lab job's limit goes from 25 to 30 minutes for that wait.
- **Never fails a step otherwise:** where the lock can't be had, or off Windows, the command runs unlocked and the log says so.
- **Optional off CI:** `--if-present` takes the lock only if CI's file is already on this PC, and never makes it.

### When the PC doesn't calm (added 2026-11-14, at Claude's request)

On 2026-11-14 a pull request's start waited its minute at 77-79 % busy, got no calm and failed. That load came from outside CI's steps: agents' local runs, the user's own work, and the containers.

- **A longer first wait:** with the lock held alone, the start test's first try waits up to 3 minutes for a calm PC; later tries wait 1 minute. Under the lock, nothing new of CI's (or of a local run that takes the lock shared) starts, so what is running ends and the PC calms.
- **The failure says what the parts say:** a failure on a busy PC adds what the start's parts show against main's record on this PC (`tools/start_record.py`, 314). Either "no part grew: the whole start slowed, as a busy PC does - re-run on a calmer PC", or which part grew, by how much.
- **It still fails.** A start slower all round looks just like a busy PC in the parts (`start_record`: "a start 30 % slower all round shows nothing"), so "reported, not failed" would let that kind of regression through. Only a calm try passes the start.
- **Local runs (HQ's rule, not this repo's):** agents' and `local_ci.sh`'s heavy runs (the whole suite, the UI lab, timing benches) take the lock shared with `--if-present`. CI's start then measures without them.
- The UI lab job's limit is 40 minutes: up to 10 for the lock, about 6 for the start's waits, and the lab itself.

## Why

- **GitHub's `concurrency` can't say "this step alone, the rest side by side".** A group lets one of its jobs run at a time; with `queue: max` up to 100 wait (GitHub's docs, read 2026-11-14). Putting the UI lab and Checks in one group would run them one after the other, and a group covers one repository only.
- **The lock covers only what needs it.** Only the timed start holds it alone; the rest of both jobs runs as before.
- **Not taken:**
  - **One Windows runner:** it halves CI's throughput; the second runner was added for 10 queued jobs (147).
  - **An ACL change** to share a runner folder: it needs an admin and the user, for no gain over ProgramData.

## What would make us reverse it

- The other runner often waiting minutes on the start ("ci_lock: ..., after N s waiting" in the logs), so the queue grows.
- A step failing with "gave up": the lock held for 10 minutes means a step that should be shared was held alone, or a hang.
- The load the start sees still coming mostly from outside CI (agents, the user's own work). Then the lock helps little and its cost is the wait.

## How we'd reverse it

Take the `python -m tools.ci_lock alone|shared --` prefix off the three steps in `ci.yml`, and set the UI lab's limit back to 25 minutes. Delete `tools/ci_lock.py` and its tests. Delete the folder `C:\ProgramData\polyglotic-ci` from the PC (nothing else uses it).
