# 0014 The user's data lives in `%APPDATA%\Polyglotic`, outside the installer's folder

- **Status:** accepted (replaces the "Where" of decisions 0010 and 0013)
- **Date:** 2026-11-05
- **Decided by:** project 035 (D5) on 2026-11-05, from Velopack's
  documentation; Claude reviews it with the pull request. The folder name
  follows the app ID, `Polyglotic`, which the user agreed on 2026-11-04
  (polyglotic-hq ENGINEERING.md, "Releases").

## Situation

Decisions 0010 and 0013 planned the learner's data - settings,
`learning.sqlite`, `outbox.sqlite` - in `%LOCALAPPDATA%\Polyglotic`. The
installer (Velopack, D5) installs the app to `%LOCALAPPDATA%\{packId}`,
and the app ID (`packId`) is `Polyglotic`: the same folder. Velopack's
documentation (read 2026-11-05) says "during install/uninstall, the entire
`{packId}` folder is replaced or removed", and recommends
`%AppData%\{packId}` - roaming app data - for "important user settings"
that should survive an uninstall.

So with the old plan, uninstalling the app - or running `Setup.exe` again
to repair it - would delete the learner's saved words, statuses, settings
and anything waiting in the outbox. The developer's own data, made by
running from source, would be deleted by the first install of a build.

## Decision

- `main.data_folder()` is `%APPDATA%\Polyglotic` (Windows' roaming app
  data, `C:\Users\<name>\AppData\Roaming\Polyglotic`). The developer
  harness keeps its own copy in `%APPDATA%\Polyglotic\harness`.
- The install folder (`%LOCALAPPDATA%\Polyglotic`) holds only what the
  installer puts there: the app, `Update.exe`, downloaded packages.
- Nothing moves data from the old folder: no tester has installed yet. A
  developer with data in `%LOCALAPPDATA%\Polyglotic` moves
  `settings.json`, `learning.sqlite` and `outbox.sqlite` by hand (or
  starts again) - before installing a build, which would delete them.
- The device token stays in Windows Credential Manager (unchanged).
- Checked by `tests/ui/test_main_data.py`
  (`test_the_users_data_is_outside_the_install_folder`).

## Why

- **Uninstalling or repairing the app mustn't delete what the learner
  built.** The learner's data is the product's value to them; losing it
  to a reinstall would be the worst kind of bug.
- **The usual home for an installer like ours:** Velopack's own advice;
  Squirrel apps (Velopack's predecessor) such as Discord and Slack do the
  same - code in local app data, the user's data in roaming app data
  (from memory, not checked on 2026-11-05).
- **Alternatives not taken:**
  - *Another app ID* (say `Polyglotic.App`), keeping the data in
    `%LOCALAPPDATA%\Polyglotic`: the app ID was agreed with the user and
    can't change once testers install; two folders with nearly the same
    name would confuse anyone looking.
  - *A sibling folder in local app data* (`%LOCALAPPDATA%\Polyglotic
    Data`): works, but against the platform's convention and Velopack's
    advice.
  - *Inside the install folder, one level above `current`* (Velopack's
    place for things that should go with an uninstall): survives updates,
    but not an uninstall or a repair.

## What would make us reverse it

- Roaming profiles: on a work PC whose profile roams between machines,
  `%APPDATA%` is copied at sign-in and sign-out, and SQLite files there
  could be copied while open. Home PCs - our testers - don't roam. If
  testers on managed PCs report problems, move the SQLite files to local
  app data (outside the install folder) and keep only `settings.json`
  roaming.
- An uninstall that should remove the learner's data too (a "remove my
  data" box): that would be an uninstall hook, not a change of folder.

## How we'd reverse it

`main.data_folder()` and the harness's `DATA` are the only places that
name the folder; changing them, plus a one-time move of the files on
start, is under an hour.
