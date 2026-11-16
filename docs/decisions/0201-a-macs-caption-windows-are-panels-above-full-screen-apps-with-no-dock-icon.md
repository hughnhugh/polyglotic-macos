# 0201 A Mac's caption windows are panels above full-screen apps, in an app with no Dock icon

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** Claude (polyglotic-hq 429), from the user's "implement
  mac feature parity" (2026-11-16 ~23:45), Apple's recipe in
  polyglotic-hq 171's RESEARCH.md and what GitHub's Mac showed; a
  reversible adapter choice. **No Dock icon is the user's to overrule**
  (429's report: the decision needed).

## Situation

On Windows the caption windows stay above a borderless full-screen game
(`platform/windows/on_top.py`, polyglotic-hq 141). The first Mac build
had Qt's always-on-top flag only: Qt gives such a window the modal-panel
level (8), which stays below another app's full-screen Space, and the
window lives on one Space (QTBUG-39212, closed Won't Do). Learners watch
videos and play games full-screen, so captions that vanish there miss the
product's main use.

Apple's Developer Technical Support (Developer Forums, May 2026, tested on
macOS 26 with Safari, QuickTime and full-screen YouTube): the app an
*accessory* (a regular app can't layer above another app's full-screen
Space), the window a non-activating panel at the screen saver's level
(1000), joining every Space and full-screen apps' as an auxiliary.

GitHub's Mac (macOS 26.7, polyglotic-hq 429's runs 1 and 2, 2026-11-17)
added what decides it: **when the window is first shown.** A caption
window first shown while the app was in the Dock never joined TextEdit's
full-screen Space, even after the app became an accessory and the window
was shown again; AppKit's own panel made after the switch, and a caption
window in a process that was an accessory before its first window, did.
So switching the Dock icon on while Home is open and off while only
captions show - the first plan - would lose any caption window first
shown while Home was open.

## Decision

- **The app is an accessory for its whole run on a Mac:** no Dock icon,
  no menu bar of its own, not in Command-Tab; the menu-bar icon opens
  Home, Settings and Quit. `LSUIElement` in the packed app's Info.plist
  (`tools/package/build.py`), and `MacOnTop` - made before the interface
  makes any caption window - sets it when run from source (Qt makes a
  plain executable a regular app).
- `platform/macos/on_top.py` implements the existing `OnTop` and
  `ForegroundWatch` ports (no new port):
  - `MacOnTop.put_on_top` sets each window handed over (Qt's tool windows
    are already `NSPanel`s): level 1000; collection behaviour
    `canJoinAllSpaces | canJoinAllApplications | fullScreenAuxiliary |
    stationary | ignoresCycle`, with what conflicts cleared; the
    non-activating panel style; `hidesOnDeactivate` off; then
    `orderFrontRegardless`, which never activates the app. The app's other
    always-on-top panels still at Qt's level (the dictation sign, a
    settings popover) are set too.
  - `game_in_front` is always True: Qt sets a window's level again
    whenever its flags change (locking hides it and shows it again), so
    the interface's `keep_on_top` sets the windows whenever it runs.
  - The caption windows, the joined window, the lookup card, the settings
    popover and the dictation sign ask Qt to show although the app isn't
    active (`WA_MacAlwaysShowToolWindow`): Qt hides an inactive app's tool
    windows, and an accessory is never active while the learner is
    elsewhere (run 3: the sign never showed over TextEdit).
  - `FrontWatch` hears macOS's notifications - another app active, the
    Space changed, one of the app's windows shown or hidden - and calls
    `changed` (the interface then runs `keep_on_top`).
- Objective-C is reached through ctypes (`platform/macos/objc.py`, 428's,
  as `cf.py` reaches Core Foundation), not PyObjC: no new dependency, no
  change to `uv.lock`, a smaller bundle.

Proven on GitHub's Mac by `tools/macos_full_screen_checks.py` (the macOS job's
`parity` part): TextEdit made full-screen, the caption window's place read
from macOS's window list (levels and order, never pictures).

## Why

- The ports already say what's needed ("these windows at the top of the
  band, none activated"; "tell me when another app comes to the front"),
  so the interface doesn't change: the Mac's adapter does the Mac's work.
- An app always an accessory is the only arrangement the runner showed
  working for every caption window, whenever it's first shown. It is the
  usual shape of a menu-bar utility.
- Not taken: switching the policy as Home opens and closes (fails as
  above); recreating a caption window's native window when the policy
  changes (fragile, and Qt's to own); a Qt event filter on the whole
  application to catch every show (a Python call per event, in an app with
  performance budgets); PyObjC (several packages for a dozen messages).

## What would make us reverse it

- The user wants the Dock icon: then `LSUIElement` off and `MacOnTop`
  without `be_an_accessory`, accepting captions below full-screen apps.
- A macOS where the screen saver's level or the collection behaviour no
  longer puts the windows over a full-screen app (the parity check fails).
- Games in exclusive full-screen (a `CGDisplayCapture`d display) or Game
  Mode hiding the windows: then a per-game rule, as Windows' 141.

How we'd reverse it: `macos_adapters` in `main.py` picks the adapter;
`not_yet`'s Qt-only stand-in was three lines; the Info.plist key is one
line.
