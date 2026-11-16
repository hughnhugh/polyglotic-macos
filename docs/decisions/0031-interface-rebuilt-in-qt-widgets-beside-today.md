# 0031 The interface is rebuilt in Qt Widgets, beside today's, on plain-Python views

- **Status:** accepted; the last part of point 2 (the switch-over's one
  change) replaced by [0032](0032-switch-over-new-interface-is-the-app.md)
- **Date:** 2026-11-07
- **Decided by:** the user, 2026-11-07 00:11 ("go ahead and do the
  rebuild"), on polyglotic-hq DECISIONS.md #53 (the shape: a window per
  app with the original and one translation, at most 3 apps, a transcript
  per app; the budgets) and project 108's report (Qt Widgets done well -
  Claude's technical call, recorded in #53). How it proceeds: polyglotic-hq
  project 110's brief. #50's scope freeze holds: rebuild what exists, add
  nothing.

## Situation

The first real run (2026-11-06) felt slow and awkward. Project 108
measured why: not Python, Qt, SQLite, the translucent windows or the
audio threads, but four choices in today's `ui/` - caption text drawn as
stroked painter paths (`strokePath` is 75-85 % of every slow action),
all 150 kept captions rebuilt on any width, text-size or Learning change
(1.0-1.3 s frozen; 250-330 ms for a lookup or Known), the transcript's
document rebuilt whole on every caption (87-116 ms), and
`QApplication.setStyleSheet` restyling every widget on a theme change
(180 ms). Its prototypes in Qt Widgets and in Qt Quick did the same
actions in 0.5-6 ms. The user asked for the client to be redesigned from
first principles (#53); project 109 draws the new structure. Today's
interface must keep working for the alpha while the new one is built.

## Decision

1. **Qt Widgets, done well** - not Qt Quick, not a web view:
   - caption and lookup surfaces are **custom-painted**: text laid out
     with `QTextLayout` and painted directly, never turned into painter
     paths. If 109 keeps an outline over video, it is drawn once per
     caption x width x text size and cached, never re-stroked per frame;
   - **lists measure only what shows:** caption windows and transcripts
     share one caption layout engine (`ui_next/caption_layout.py`) that
     lays out newest first, stops when the view is full, and caches each
     caption's layout per caption x width x text size. No widget per
     row; no document rebuilt per caption;
   - **marks repaint, never re-lay out:** highlights and word links are
     drawn as format ranges at paint time, so a Learning change (Known,
     Add to deck) repaints what shows and lays out nothing;
   - **no app-wide stylesheet repolish:** painted surfaces take their
     colours at paint time; standard controls get a palette or a
     stylesheet scoped to their own window.
2. **Its own package, beside today's:** `src/polyglotic_desktop/ui_next/`,
   in the same layer as `ui/`. Neither imports the other (import-linter
   `layers`). It is launched by a **developer switch** on main's command
   line, hidden from its help and never shown to users; the switch comes
   with the first window (the rebuild's part 2). Today's `ui/` stays the
   default until `ui_next/` covers every feature on 109's map; then one
   change deletes `ui/`, renames `ui_next/` to `ui/` and removes the
   switch.
3. **Plain-Python views between core and Qt:** `ui_next/views/` holds one
   view per surface - what it shows (core's captions as lines in the
   chosen language, the text size, following or scrolled back) and what
   changed - with no Qt (import-linter `views-no-qt`). Qt widgets draw a
   view and hand the user's actions back to it. Views are tested without
   Qt; core keeps the rules (the caption display rules stay in
   `core.listening.display`).
4. **Measured, always:** a `perf` package (named spans; a watchdog that
   logs any interface-thread slot over 50 ms by name and duration, never
   caption text or words; timings as JSON) in its own layer between the
   interface and core, so `ui`, `ui_next` and `main` can all use it.
5. **The budgets are tests.** 108's budgets (DECISIONS.md #53): at most 8
   ms of interface-thread work per frame while resizing, moving or
   scrolling; a new caption drawn in 8 ms (16 with a transcript showing,
   at 1,000 lines); a click shows its change within 50 ms; the lookup
   within 100 ms of the hover delay (50 pinned); a page switch 50 ms cold,
   16 warm; text size, language or display 50 ms; theme 150 ms; the window
   0.5 s after start from source (1.5 s packed); nothing on the interface
   thread over 50 ms; no periodic timer under 250 ms when nothing moves.
   Each new part's budget test runs offscreen in CI and fails the pull
   request over budget. The UI lab (`tools/ui_lab/`) drives states
   offscreen and writes a PNG and a timing JSON per state; CI gates the
   new parts on it and records today's interface's numbers without
   gating them.

## Why

- 108's two prototypes met every budget by 100x or more, so the toolkit
  is not the variable; Widgets keeps one language, every existing test
  and the offscreen harness, where Qt Quick adds QML, property plumbing,
  100-300 ms of start-up per window and a software rasterizer in CI. A
  web view adds a second runtime and still needs native code for
  click-through windows over games.
- Building beside `ui/` keeps the alpha working at every merge and lets
  each new surface be compared with the old one in the lab; rebuilding in
  place would leave the app half-old, half-new for weeks.
- Views without Qt keep what a surface shows testable at the speed of
  plain tests, and keep Qt to drawing - the layer that went wrong.
- Budgets as tests are what stops this happening again: 108 found the
  slowness only by measuring.

## What would make us reverse it

- A surface that can't meet its budget in Widgets after the layout
  engine's caching (most likely a long transcript with rich marks).
- A web product planned, so a shared web interface pays for its runtime.
- The developer switch still needed long after 109's map is covered -
  a sign the old interface is being kept alive instead of retired.

## How we'd reverse it

- **Toolkit:** views and core don't change; a Qt Quick surface would bind
  to the same views (108's QML prototype did that shape). Only the
  painted surface is rewritten - a few days per surface.
- **The package beside `ui/`:** if the rebuild stops, delete `ui_next/`
  and its tests and contracts; `ui/` is untouched by it.
- **Views:** they can be folded into the widgets that use them if they
  prove ceremony - a mechanical change per surface.
- **A budget:** change its number in one place (`perf.budgets`), with a
  reason, through the user (they agreed the budgets in #53).
