# 0057 The installer gives the app and its shortcuts one taskbar ID: the pack ID's `.Desktop`

- **Status:** accepted; settles what [0051](0051-one-taskbar-id-the-installers-or-polyglotic-desktop.md) left open ("Not decided here: the pack's `--aumid`")
- **Date:** 2026-11-09
- **Decided by:** Claude, taking polyglotic-hq project 245's option A (its report, 2026-11-08), done in project 264. Reversible, a technical choice, until testers pin the app (2026-11-16).

## Situation

- Decision 0051: the installed app keeps the taskbar ID its installer gives it, and from source it's `Polyglotic.Desktop`.
- `tools/package/pack.sh` passed Velopack no `--aumid`. So:
  - the installed app was `velopack.Polyglotic`;
  - Velopack's Start-menu and desktop shortcuts had no ID at all.

  A pinned shortcut and the running app were therefore two taskbar buttons, and from source and installed were two apps to Windows.
- Once outside testers pin the app (the alpha, 2026-11-16), a changed ID leaves their pins behind.

## Decision

- `pack.sh` packs with `--packId "$id"` and `--aumid "$id.Desktop"`, where `id=Polyglotic`. Velopack gives that ID to the installed process (its start-up, before the app's code runs) and to the shortcuts it makes.
- The real app is `Polyglotic.Desktop` everywhere: installed, its shortcuts, and from source (`main.TASKBAR_ID`).
- A rehearsal packed under another pack ID gets another taskbar ID with it, so it stays a separate app to Windows.
- The Microsoft Store's copy keeps its package's own ID (decision 0056).
- Enforced by `tests/tools/test_package_build.py`: the pack ID's `.Desktop` is `main.TASKBAR_ID`, and pack.sh passes both.

## Why

- One button for the app, pinned or running, from the first tester's first pin. That's what Microsoft's rule for explicit IDs asks: the process and its shortcuts must carry the same one.
- Derived from the pack ID, not written twice, so a rehearsal can't take the real app's ID by forgetting to change it.
- **Not taken** (245's report):
  - `--aumid velopack.Polyglotic` bakes an installer's name into an ID that can never change;
  - leaving it unset keeps the two buttons.

## What would make us reverse it

- Velopack stops honouring `--aumid` for the process or the shortcuts. Package's install test on a runner's account would show the process's ID.
- A source run sharing the learner's pinned ID proves a nuisance. Then give source runs `Polyglotic.Desktop.Source` (0051's own reversal); the installed ID stays.

## How we'd reverse it

- Before 2026-11-16: one line in pack.sh, minutes.
- After testers pin the app: any change leaves their pins pointing at an app that never runs, so don't.
