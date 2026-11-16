# 0092 The mouse wheel scrolls the page, never a setting it passes over

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user asked for the outcome, 2026-11-13 (polyglotic-hq
  DECISIONS #129, second feedback round): "scrolling settings will
  inadvertently change many settings as you navigate the page (scrolling
  over certain icons)". The rule and the mechanism are polyglotic-hq
  project 304's (its brief: "a control takes the wheel only once it has
  been clicked into ... by one shared mechanism"); Claude reviews them
  with the pull request.

## Situation

Qt gives the wheel to whatever is under the pointer. A closed list changes
its choice, and a slider or number box changes its value, while the page
around it doesn't move. A list also takes the keyboard from the wheel
(Qt's `WheelFocus`), so the arrow keys then change it too. Settings >
Captions is a long page of lists and sliders, and its Lab adds six more
sliders: scrolling it changed the timing, the background, the Lab's values
and the app's language picker on the way down. The same happened on a
transcript's rail, Learning and Words.

The walk in `tests/ui_next/test_wheel_scrolls_the_page.py`, run without
the rule, found 13 controls the wheel changed on the main window's pages.
On real windows (Windows' own wheel messages, on a private desktop), the
wheel over Longest wait for text changed it and took the keyboard, and
over the background slider moved it, while the page stayed where it was.

## Decision

- **The rule,** on every page that scrolls (every page of the main window,
  Settings and its Lab among them, and a transcript's settings rail):
  - the wheel over a list, slider or number box scrolls the page, as if
    the control weren't there;
  - a list takes the wheel only while it's open: its own choices scroll;
  - a slider or number box takes the wheel once it's been clicked, while
    the pointer stays on it. Moving off it, the keyboard moving on or the
    control going out of sight lets it go;
  - the wheel never gives a control the keyboard: their `WheelFocus`
    becomes `StrongFocus` (a click or Tab);
  - the keyboard works as it did.
- **One guard, put on by the pages themselves:** `ui_next.wheel.guard(page)`,
  called by `home.Page` (the base of every main-window page) and by
  `transcript_window.SettingsRail`. The guard looks at the page when it
  shows, and again whenever its content's layout changes, so a row added
  later (Speech's second languages) is caught too. It watches only the
  lists, sliders and number boxes it finds there.
- **Enforced by a test** that walks every page of the main window (every
  Settings section, the Lab among them), a transcript's rail and a caption
  window's settings popover with each list open. It turns the wheel a
  notch each way over every list, slider, number box, button and list of
  choices, and fails on any that changes, or on a list, slider or number
  box the wheel would give the keyboard. A new page built on `Page` is
  guarded without a step of its own.

## Why

- **The pages, not the whole application.** The first version was one
  event filter on the application, installed by `main`, covering every
  control anywhere. It cost too much: every event of every window went
  through Python. On the whole hub, measured 2026-11-14 on the user's PC:
  - a theme change went from 126 to 175-185 ms;
  - building and showing the hub took 25-40 ms more.

  On #549's first CI run, the start with 30,000 words met, which runs
  `main` and so had the filter, went over its budget (565-596 ms against
  400, with the PC 23 % busy). The UI lab's theme-change state went over
  too, but that state doesn't run `main`. It was the busy PC: it went
  over again later without any filter, with the PC 78 % busy. Watching
  only the controls costs nothing measurable:
  - a theme change of the hub measured 93-98 ms with the guard and
    94-109 ms without;
  - the lab's theme-change state measured 76.9 ms with it and 77.1-80.2
    ms without.
- **Not a step per control.** The Lab's sliders are another project's file,
  and new pages keep coming. The base page carries the guard, and the
  walk test fails on any control a new kind of page leaves unguarded.
- **The page gets the wheel explicitly.** The guard hands it to the scroll
  area the control is in, rather than ignoring it and leaving Qt to pass
  it up. Qt passes a wheel up only for real input, so the tests could
  check only half of that path. Handing it on is the same for both.
- **"While the pointer stays on it".** The pointer leaving is what the
  guard can see on the control itself. Windows also says the pointer left
  when a window comes up under it, and on a private desktop (no cursor)
  at once after a click. Either way the page scrolls, and nothing
  changes: the safe side.
- **Not "never".** A clicked slider taking the wheel is how Windows' own
  controls behave, and fine adjustment of the Lab's sliders needs it.
- **Alternatives not taken:**
  - Qt's `SH_ComboBox_AllowWheelScrolling` style hint covers only lists,
    and has no "once clicked".
  - Focus alone ("takes the wheel while it has the keyboard") leaves a
    list that was just used changing as the page scrolls past it, which
    is the fault itself.

## What would make us reverse it

- Learners who expect the wheel to step through a list without opening it
  (testers saying so, or support mail).
- A list or slider somewhere other than a scrolling page that people
  change by accident: today two dialogs of the older `ui` package have
  one each, the feedback form's kind and the level picker's scheme. They
  don't scroll, so the wheel changes them only when it's turned over
  them on purpose.

## How we'd reverse it

Remove the two `wheel.guard(...)` lines (`home.Page`,
`transcript_window.SettingsRail`) and the module with its test. To loosen
it instead, for example to let a list take the wheel while it has the
keyboard, add `QComboBox` to `CLICKED_INTO`; the walk test then says
which controls change. Nothing is stored, so nothing migrates.
