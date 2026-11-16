# 0201 A Mac's caption windows are panels above full-screen apps, and the app an accessory while only they show

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** Claude (polyglotic-hq 429), from the user's "implement
  mac feature parity" (2026-11-16 ~23:45) and Apple's recipe in
  polyglotic-hq 171's RESEARCH.md; a reversible adapter choice. The Dock
  icon coming and going is the user's to overrule (the report's decision).

## Situation

On Windows the caption windows stay above a borderless full-screen game
(`platform/windows/on_top.py`, polyglotic-hq 141). The first Mac build
had Qt's always-on-top flag only: Qt gives such a window the modal-panel
level (8), which stays below another app's full-screen Space, and the
window lives on one Space (QTBUG-39212, closed Won't Do). Learners watch
videos and play games full-screen, so captions that vanish there miss the
product's main use.

Apple's Developer Technical Support (Developer Forums, May 2026, tested on
macOS 26 with Safari, QuickTime and full-screen YouTube) gives the way:
the app an *accessory* (a regular app can't layer above another app's
full-screen Space), the window a non-activating panel at the screen
saver's level (1000), joining every Space and full-screen apps' as an
auxiliary.

## Decision

`platform/macos/on_top.py` implements the existing `OnTop` and
`ForegroundWatch` ports (no new port):

- `MacOnTop.put_on_top` sets each caption window's `NSWindow` (Qt's tool
  windows are already `NSPanel`s): level 1000; collection behaviour
  `canJoinAllSpaces | canJoinAllApplications | fullScreenAuxiliary |
  stationary | ignoresCycle`, with what conflicts cleared; the
  non-activating panel style; `hidesOnDeactivate` off; then
  `orderFrontRegardless`, which never activates the app.
- `MacOnTop.game_in_front` is always True: Qt sets a window's level again
  whenever its flags change (locking hides it and shows it again), so the
  interface's `keep_on_top` sets the windows whenever it runs.
- `FrontWatch` hears macOS's notifications - another app active, the
  Space changed, one of the app's windows shown or hidden - and calls
  `changed` (the interface then runs `keep_on_top`); and it keeps the
  activation policy: an ordinary app (in the Dock) while an ordinary
  window shows (Home, a dialog: level 0), else an accessory.
- Objective-C is reached through ctypes (`platform/macos/objc.py`, as
  `cf.py` reaches Core Foundation), not PyObjC: no new dependency, no
  change to `uv.lock`, a smaller bundle.

Proven on GitHub's Mac by `tools/macos_parity_checks.py` (the macOS job's
`parity` part): TextEdit made full-screen, the caption window's place read
from macOS's window list (levels and order, never pictures).

## Why

- The ports already say what's needed ("these windows at the top of the
  band, none activated"; "tell me when another app comes to the front"),
  so the interface doesn't change: the Mac's adapter does the Mac's work.
- An accessory app has no Dock icon or menu bar; switching only while no
  ordinary window shows keeps the Dock icon while Home is open (the usual
  pattern for menu-bar apps), and the menu-bar icon stays either way.
- Not taken: a Qt event filter on the whole application to catch every
  show (a Python call per event, in an app with performance budgets);
  `LSUIElement` in Info.plist (no Dock icon ever, even with Home open);
  PyObjC (a dependency of several packages for a dozen messages).

## What would make us reverse it

- A macOS where the screen saver's level or the collection behaviour no
  longer puts the windows over a full-screen app (the parity check fails).
- Learners asking for the Dock icon to stay (then `LSUIElement` off and
  the policy fixed at regular, accepting captions below full-screen apps
  - or the reverse, never in the Dock).
- Games in exclusive full-screen (a `CGDisplayCapture`d display) or Game
  Mode hiding the windows: then a per-game rule, as Windows' 141.

How we'd reverse it: `macos_adapters` in `main.py` picks the adapter;
`not_yet`'s Qt-only stand-in was three lines.
