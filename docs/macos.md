# The Mac: what's done, where it's proven, and what isn't

Each Mac-parity project keeps its own sections here (polyglotic-hq 428,
429, 430): what was built, where it was proven, what wasn't, and why.

## Caption windows over full-screen apps and every Space (polyglotic-hq 429, decision 0201)

**Done.**
- The caption windows, the joined window, the lookup card, the settings
  popover and the dictation sign (Qt's tool windows, already `NSPanel`s)
  are set at the screen saver's level (1000),
  on every Space and every app's full-screen Space as an auxiliary, left
  in place by Mission Control, out of Command-`'s cycle, as non-activating
  panels that don't hide when the app isn't active
  (`platform/macos/on_top.py`, `MacOnTop`).
- Qt puts a window back at its own level when its flags change (locking
  hides and shows it), so the interface's `keep_on_top` sets them again
  each time it runs: when macOS says another app is active, the Space
  changed or one of the app's windows was shown or hidden (`FrontWatch`),
  and when a caption comes (at most once a second).
- The app is an accessory for its whole run: no Dock icon, no menu bar of
  its own, not in Command-Tab; the menu-bar icon opens Home, Settings and
  Quit (`LSUIElement` in the packed app's Info.plist; `MacOnTop` sets it
  when run from source). GitHub's Mac showed why it must be from the
  start: a window first shown while the app was in the Dock never joins a
  full-screen app's Space, even once the app is an accessory.
- Each of them shows although the app isn't the active one (Qt's
  `WA_MacAlwaysShowToolWindow`): Qt hides an inactive app's tool windows,
  and Polyglotic is never the active app while the learner is in a game
  or a video - the dictation sign never showed over TextEdit without it.
- Locked windows let clicks through (Qt's `WindowTransparentForInput` is
  `ignoresMouseEvents`).

**Proven on GitHub's Mac** (macOS 26.7, Apple silicon), by
`tools/macos_parity_checks.py` (the macOS job's `parity` part; polyglotic-hq
429's runs 2 to 4, 2026-11-17), against TextEdit made full-screen,
reading macOS's window list (levels and order, never pictures):
- a caption window shown before TextEdit went full-screen, and one shown
  after, are on its Space above it (level 1000), and TextEdit stays in
  front and full-screen;
- with Qt's flags alone (the baseline) the window isn't there;
- locked (Qt hides and shows it again at its own level) it is set again
  and lets clicks through; unlocked, a click on it (System Events) leaves
  TextEdit in front and full-screen;
- a window first shown while the app was in the Dock never joins the
  full-screen Space, even after the app becomes an accessory; one first
  shown while it's an accessory does (why the app has no Dock icon);
- the packed app with `LSUIElement` packs, signs and passes
  `--check-install`.

**Not proven, and why:**
- **Games.** A game in its own full-screen Space is what TextEdit's
  full-screen proves; a game that captures the display
  (`CGDisplayCapture`, older or ported games in "exclusive" full-screen)
  draws above every window, and macOS gives no way over it. The runner has
  no games. Game Mode (macOS 14+) wasn't tried.
- **Several displays, Stage Manager, the notch.** The runner has one
  display.
- **A tooltip over a caption window** on a full-screen Space: Qt gives
  tooltips the screen saver's level itself, but not every Space.
- **Esc and clicks elsewhere** (the `KeyState` port) still read nothing on
  a Mac (`not_yet.held`): a settings popover closes on a click in it, and
  Esc in another app doesn't cancel dictation.

## Dictation typing into other apps (polyglotic-hq 429)

**Done.**
- The words are typed into the app in front as Unicode key events
  (`CGEventKeyboardSetUnicodeString`, one character per key down and up,
  no modifiers on them so a Command still held isn't a shortcut), never
  through the clipboard (`platform/macos/text_input.py`). Only into the
  window that had the keyboard when the speech was cut: the front app's
  frontmost ordinary window, from macOS's window list (numbers, levels and
  owners only).
- macOS's Accessibility permission: asked by macOS's own box the first
  time dictation's key is taken during a run without it
  (`AXIsProcessTrustedWithOptions`). Until it's given nothing is typed,
  and the app says why (polyglotic-hq 438; the `TypingPermission` port,
  `text_input.Permission`, None on Windows):
  - the sign says "Not allowed to type - see Settings > Dictation", for 5
    seconds rather than 2: it's something to do, not a passing word. The
    sign itself can't offer a button: it lets clicks through, so that the
    app being typed into keeps the keyboard and a full-screen game doesn't
    lose its Space;
  - Settings > Dictation says Polyglotic isn't allowed to type into other
    apps and where to allow it (System Settings > Privacy & Security >
    Accessibility), with **Open System Settings**, which opens that pane
    (`x-apple.systempreferences:...?Privacy_Accessibility`). It asks
    macOS again (without its box) each time the page shows and whenever
    the sign says it, so the note goes once the permission is given.
- Dictation's key (`platform/macos/hold_key.py`): a key with modifiers
  through Carbon's `RegisterEventHotKey` (no permission, taken from other
  apps while held, down and up said by Carbon); a modifier alone - Right
  Command, the default ("right_ctrl": Qt's Ctrl is Command on a Mac) - from
  the modifiers' state, with another key pressed meanwhile read as a
  shortcut. No event tap: no Input Monitoring permission, nothing else
  typed passes through the app.
- Settings' key box reads a Mac's keys and writes them as a Mac does
  ("Right ⌘", "⌃⌘D") - its own pull request (#808).

**Proven on GitHub's Mac** (macOS 26.7, polyglotic-hq 429's runs 1 to 3,
2026-11-17; the runner's processes have the Accessibility permission):
- "héllo 你好 😀 ok" typed into TextEdit, read back through Accessibility
  (TextEdit capitalised the first letter itself); `keyboard_window` is
  TextEdit's window;
- Control+Command+D registered through Carbon, pressed by System Events:
  down then up, and TextEdit got no "d"; a second taker of the same
  combination is refused (so "another app has it" is said);
- Left Command held alone (System Events): down then up, from the
  modifiers' state (its side's bit, 0x8, seen).

**Not proven, and why:**
- **The permission's box and a learner granting it.** The runner's
  processes already have Accessibility; no one can click the box there.
  Whether typing works at once after granting, or only after the app is
  started again, is unknown.
- **The permission across updates.** macOS keeps it for the same
  designated requirement; with our own certificate (decision 0196) that
  should hold - seen first on the first tester's update.
- **Right Command held by a person.** System Events can't press one side
  of a modifier; Left Command alone was pressed instead. That macOS's
  modifier state has each side's bit is Apple's documented `NX_DEVICE*`
  masks.
- **A shortcut begun before the key** (C held, then Right Command):
  Windows sees C still down; a Mac without Input Monitoring can't read
  other keys' state, so it starts dictation and the hold is dropped if
  short.
- **The app's own hotkeys as dictation's key.** Settings refused Ctrl+Alt+
  L, P and H as on Windows; a Mac's hotkeys are Control+Command (428), and
  Carbon refuses a second taker, so such a key was said to be "another
  program's". Fixed in its own pull request (polyglotic-hq 438, #815):
  on a Mac, ⌃⌘L, P and H are refused as the app's own.
- **Apps that ignore Unicode key events** (some games, remote desktops,
  terminals in raw mode) - as on Windows, they get nothing.
