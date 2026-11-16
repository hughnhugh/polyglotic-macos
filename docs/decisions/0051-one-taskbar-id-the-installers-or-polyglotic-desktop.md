# 0051 Windows knows the app by one taskbar ID: the installer's when installed, `Polyglotic.Desktop` from source

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** Claude, for polyglotic-hq project 245 (the user,
  2026-11-08: "Does the app still say it's python.exe?"). Reversible - a
  technical choice - until testers pin the app: see "How we'd reverse it".

## Situation

Windows groups windows on the taskbar, pins them and draws their button
by an AppUserModelID: one the process sets explicitly
(`SetCurrentProcessExplicitAppUserModelID`), else one it makes from the
exe's path. Microsoft's rule: an app that sets one must give the same one
to its shortcuts, or a pinned shortcut and the running app are two
buttons.

- **From source** nothing set one, so the app was `python.exe` to Windows:
  grouped with any other Python, under Python's ID.
- **Installed,** Velopack's start-up (`velopack.App().run()`, the first
  thing `main()` does) already sets one: the pack's `--aumid`, else
  `velopack.<pack ID>` (velopack's source at tag 1.2.161,
  `src/lib-rust/src/app.rs` and `locator.rs`, read 2026-11-08). `tools/package/pack.sh` passes no `--aumid`, so the
  installed app is `velopack.Polyglotic`, and Velopack's Start-menu and
  desktop shortcuts get no ID at all (`shortcuts.rs`: an empty
  `PKEY_AppUserModel_ID`). They don't agree.
- A rehearsal install is packed under its own pack ID (polyglotic-hq
  projects/README.md), and must stay a separate app to Windows.

## Decision

- **One port, `ports.system.TaskbarIdentity`:** names this process to the
  taskbar unless something already has, and says the name it has. The
  Windows adapter is `platform.windows.taskbar.app_identity`, picked by
  `main.os_adapters()` (decision 0038).
- **`main()` calls it first thing after picking the OS's adapters,**
  before any window, with `TASKBAR_ID = "Polyglotic.Desktop"`, and logs
  the ID it ends up with.
- **Installed, the installer's ID stands:** Velopack has named the process
  by then, from the pack, so the app keeps it. A rehearsal pack (its own
  pack ID) is therefore a separate app to Windows with no change to the
  code. **From source** the app is `Polyglotic.Desktop`.
- **Tested:** the adapter in a fresh process each time - it names the app,
  and keeps an ID already set (`tests/test_windows_taskbar_identity.py`);
  the real app from source on a private desktop has `Polyglotic.Desktop`
  (`tests/test_private_desktop.py`).

**Not decided here (polyglotic-hq 245's report):** the pack's `--aumid`.
For the shortcuts, a pinned button and the running app to agree, `pack.sh`
needs `--aumid Polyglotic.Desktop`, taken from the same variable as
`--packId` so a rehearsal's differs too. Velopack then gives that ID to
the shortcuts and to the process, and from source and installed are one
app.

## Why

- The installer is the only part that knows the pack ID and makes the
  shortcuts, so the installed ID belongs to it; the app reading Velopack's
  files to work it out again would be a second source of the same fact.
- `Polyglotic.Desktop` rather than `velopack.Polyglotic`: the ID can't
  change once testers have pinned the app, and it shouldn't carry an
  installer's name we might replace. Microsoft's form is
  `Company.Product[.SubProduct]`, no spaces, at most 128 characters.
- Microsoft's own advice for apps an installer manages (ClickOnce, in
  "Application User Model IDs"): they "should not assign explicit
  AppUserModelIDs themselves, because doing so will conflict with the
  AppUserModelIDs assigned" by the installer.
- Keeping an ID already set, rather than always setting ours: always
  setting `Polyglotic.Desktop` would make every rehearsal install the real
  app to Windows (one taskbar button, shared pins), unless each rehearsal
  patched the code.
- A port, not a direct call in `main`: decision 0038's rule (the OS's
  pieces picked in one place). macOS and Linux have their own equivalents
  (a bundle ID; Qt's `setDesktopFileName`) for their adapters.

## What would make us reverse it

- Velopack stops naming the process, or names it after the app's code has
  run: then the installed app would take `Polyglotic.Desktop`, and the
  pack's `--aumid` must say the same.
- From source sharing the real app's ID proves a nuisance (a developer's
  source run grouped under the learner's pinned Polyglotic): give source
  runs `Polyglotic.Desktop.Source`.

## How we'd reverse it

- The from-source ID is one constant in `main` (`TASKBAR_ID`); always
  setting it instead of keeping the installer's is one line in the
  adapter. Minutes.
- **The installed ID is the expensive one:** once testers have pinned the
  app, a changed ID leaves their pins pointing at an app that never runs
  (a second button appears). Settle `pack.sh`'s `--aumid` before the
  first outside tester installs (2026-11-16).
