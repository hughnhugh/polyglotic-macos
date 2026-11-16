# 0054 The first run is one run of screens, each after the first with Back, before anything is built on their answers

- **Status:** accepted; its language step replaced by
  [0085](0085-the-first-run-asks-no-language.md) (polyglotic-hq 293)
- **Date:** 2026-11-08
- **Decided by:** Claude, for polyglotic-hq project 250 (the user's
  rehearsal feedback F4, 2026-11-08: "There should be back buttons for the
  install flow too"). Reversible - a technical choice; polyglotic-hq 248
  proposes the first run's next shape, and this one makes room for it.

## Situation

The first run asked four things, each a dialog on its own, from different
places in `main()`:

1. the language being learned (`learned_language`) - before the learner's
   tools were built, because the language picks the dictionary and the
   learning data;
2. the level (`LevelPicker`) - after the main window and the caption
   windows were built on those tools;
3. Your data and the yes (`agree_at_start`) - after that;
4. the code (`SignInDialog`) - over the main window, once the event loop
   ran (`once_running`, polyglotic-hq 133).

Back from the level to the language is the hard one: a different answer
means different tools, and by then the windows were built on the first
ones. Back from the code to Your data meant reopening screens after the
app had started capturing nothing yet but listening for a session.

## Decision

- **`main.first_run` asks them as one run**, before anything is built on
  their answers: the language (until chosen), the level (while that
  language has none), Your data (the first run, or the agreement's new
  words), then the code (after any of those, when this PC isn't signed
  in). `ui.first_run.run` takes the steps in order; every screen after the
  first shown has **Back**, the screen before, shown again as it was left
  (the same dialog, not a new one - a level picker per language).
- **The learner's tools are built for the language as soon as it's
  known,** and again if Back changes it; the ones left behind have their
  learning store closed. `tools.prepare()`, the windows and everything
  else come after the run.
- **Closing a screen does what it did:** the language and the level go on
  without an answer; Your data without the yes raises `NotAgreed` and the
  app quits (polyglotic-hq DECISIONS.md #88); the code goes on signed out.
- **Answers are kept on their own Next only.** The yes to the tester
  agreement is now stamped when Continue is pressed, not when the box is
  ticked, so a tick followed by Back gives none.
- **The code is asked before the window on a first run.** A later start
  that's signed out still asks it over the window, as before
  (`once_running`), and a first run that asked it doesn't ask again.
- The screens before the window have no window to take a stylesheet from:
  they get the learner's theme themselves (`theme.apply`, as `DesktopApp`
  does).

## Why

- One run is the only place Back can go everywhere: each screen's answer
  is still open to change until the run ends, and nothing has been built
  on it.
- Building the tools inside the run, per language, keeps the language's
  real effect (the dictionary, the learning data) without asking the
  learner to restart after changing their mind.
- The code before the window matches polyglotic-hq 248's proposed order
  (the yes, Your data, the code, then Home), and nothing in the window
  waits on it.

## What would make us reverse it

- polyglotic-hq 248's B4 (the language and the level asked where their
  effect shows, not at the first run): then the run is the yes, Your data
  and the code, and the tools no longer depend on it.
- Testers finding the code before the window confusing (they don't see
  Home until they've entered or skipped it).

## How we'd reverse it

- To change the order or drop a screen: edit the steps' list in
  `main.first_run`; `ui.first_run.run` doesn't care what they are.
- To put the code back over the window: drop the "code" step and remove
  the `code_asked` condition on `once_running(sign_in)` in `main()`.
- To build the tools before the run again: only possible if the language
  is no longer asked in it (248's B4).
