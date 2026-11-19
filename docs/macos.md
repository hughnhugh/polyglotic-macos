# The Mac: what's done, where it's proven, and what isn't

Each Mac-parity project keeps its own sections here (polyglotic-hq 428,
429, 430): what was built, where it was proven, what wasn't, and why.

What the Mac build has of the Windows app's OS pieces, and how far each is
proven. One section per piece: **done** (what the code does), **proven
where**, **not proven**, and **why**. Proven on GitHub's Mac means the
macOS job (`.github/workflows/macos.yml`, run through polyglotic-hq's
`scripts/macos_mirror.sh`): an Apple silicon `macos-26` machine with a
desktop session, no speakers or mic of its own (BlackHole only), and no
person at it.

Started by polyglotic-hq 428 (2026-11-17): the hotkeys, the card's voice,
the menu-bar icon and starting at sign-in. What the Mac doesn't have yet is
in `src/polyglotic_desktop/platform/macos/not_yet.py`.

## Hotkeys: ⌃⌘L, ⌃⌘P, ⌃⌘H

- **Done:** `platform/macos/hotkeys.py`. Lock, pause and hide are
  Control+Command and the letter (polyglotic-hq DECISIONS #193's
  recommendation: ⌥⌘H is "Hide Others" in every Mac app, ⌥⌘L and ⌥⌘P are
  Finder's). Registered with Carbon's `RegisterEventHotKey` (exclusive),
  which needs no Accessibility or Input Monitoring permission; macOS calls
  the handler on the main thread from Qt's event loop. A combination
  another app holds is reported taken, the rest still work, and the log
  names it, as on Windows; the menus, Home, Help and the caption windows
  then stop naming it (`hotkeys_not_working`, `hotkey_works`). The menus
  write "⌃⌘L" (Qt's Meta is the Control key, its Ctrl Command); the
  translated texts that say "Ctrl+Alt+L" (German "Strg+Alt+L") are
  rewritten "⌃⌘L" on a Mac (`ui_next.os_words.hotkeys_here`) - the
  symbols are the same in every language.
- **Proven where:** the logic on any OS (`tests/test_macos_parity.py`,
  Carbon faked); on GitHub's Mac, the job's `parity` part
  (`tools/macos_parity_checks.py`): the three taken and each pressed by
  AppleScript (System Events, which the runner lets osascript drive) runs
  its action; a second process asking for them is told they're taken; given
  back, they're free again. Passed in runs 43879574434 and 43884975285
  (2026-11-17, `macos-26`), as did the menus' "⌃⌘L"; the suite's texts
  read ⌃⌘ on the Mac (9 tests that expected Ctrl+Alt now read the keys as
  the OS writes them).
- **Not proven:** a real keyboard and a person; a game in full screen in
  front (429's piece); another app that holds ⌃⌘L for real.
- **Limits:** keys are by position (Carbon takes key codes): L, P and H are
  where a US keyboard has them. That is the same key on QWERTY, AZERTY and
  QWERTZ; on Dvorak and other layouts the hotkeys are the keys in those
  places, not the letters printed on them. Reading the layout
  (`UCKeyTranslate`) would fix it.

## The card's voice

- **Done:** `platform/macos/voices.py`, under the same `SpeakerThread` as
  Windows' voices (decision 0077). The voices are AVFoundation's
  `AVSpeechSynthesisVoice.speechVoices` - every voice in System Settings >
  Accessibility > Spoken Content, the enhanced and premium ones a learner
  downloaded included - less the novelty voices and the learner's
  Personal Voice; within a language the best quality first, then the one
  macOS uses for it, since the card says a word in the first voice of its
  language. A word is made by `AVSpeechSynthesizer`'s
  `writeUtterance:toBufferCallback:` (the samples, so the captions' hush
  and the silence trimmed work as on Windows) and played by an
  `AVAudioPlayer` on the default output as it is when the word starts. The
  card's "No voice" line and its button say how macOS adds a voice and
  open Spoken Content. Objective-C is called through ctypes
  (`platform/macos/objc.py`; no new dependency, decision 0006).
- **Recorded words first:** desktop #788 (polyglotic-hq 418, 423) puts a
  language's recorded words before the OS's voices
  (`platform/recorded_voices.RecordedVoices`, wrapping a `Voices`). The
  Mac's `speaker` in `main.macos_adapters` takes `recordings` and wraps
  `MacVoices` the way Windows' wraps `WindowsVoices` (polyglotic-hq 443,
  where the two met); the voices and the player here needed no change.
- **Proven where:** the order, the pace and the buffers' reading on any OS;
  on GitHub's Mac (`parity`): 165 voices in 49 languages listed (first
  English: Samantha), and the card's whole path - `SpeakerThread`,
  `MacVoices`, `AudioPlayer` - saying "Polyglotic" on BlackHole (0.82 s of
  sound, `sounding` and `ended` told) while the mic on BlackHole heard it
  (peak 0.52; run 43884975285, 2026-11-17). "hello" made at each pace the
  card uses, one word after another (`voice_made`), crashed twice: each
  word's block was freed after its last buffer and macOS released it
  later. One block now serves every word (`MacVoices._block`); the third
  run's result is in the pull request.
- **Not proven:** that it sounds right to a listener; a learner's
  downloaded premium voices (the runner has the stock ones); the Spoken
  Content link (`x-apple.systempreferences:` with the Accessibility
  extension and `SpokenContent`) - nothing on the runner can show which
  page System Settings opened; the slower pace's feel (0.35 on macOS's
  scale for the card's 0.7: the measured lengths are in `parity.json`).

## The menu-bar icon

- **Done:** `ui/icons.menu_bar_icon` and three template masters
  (`ui/assets/icons/tray-template-*.svg`): black and its opacity only, so
  macOS draws them in the menu bar's own colour, light or dark, and
  highlighted. A template has no pink: listening has the dots cut out,
  idle the bar alone, paused the pause mark. `DesktopApp` uses them on a
  Mac (`tray_icons`).
- **Proven where:** on any OS, that each is a template and the states read
  apart at 16 px (`tests/ui/test_icons.py`); on GitHub's Mac (run
  43884975285), the icon shown in the menu bar as a template (Qt gave it
  38 x 30 at the right of the bar), and `light_menu_bar` following dark
  mode switched on and off by AppleScript. `menu-bar.png` shows the icons drawn as
  macOS draws a template on a light and a dark menu bar - made from the
  icon, not captured from the screen (the project never captures screens).
- **Not proven:** the menu bar itself, seen. Nothing here pictures the
  screen; a person's look at it on a Mac is the proof that's left.

## Starting at sign-in

- **Done:** `platform/macos/startup.py`: the app as a login item through
  `SMAppService.mainAppService` (macOS 13+; the app needs 14.2) -
  register, unregister, status. Home's offer after a good session shows on
  a Mac again, in the Mac's words ("Open Polyglotic when you log in?",
  "Open at login"; Login Items in System Settings can turn it off), only
  in the packed app, as on Windows.
- **Proven where:** the port's rules on any OS (`LoginItem` over a faked
  service: on only while macOS says enabled, a refusal quiet and logged);
  on GitHub's Mac, the packed app's `--check-parity` (run 43884975285):
  ServiceManagement, Carbon and AVFoundation load in the ad hoc signed
  bundle; macOS said "not found" (3) before, "enabled" (1) once added -
  no approval asked - and "not registered" (0) once taken off. An app never
  added answers "not found": the app reads both as off.
- **Not proven:** a log-in after it - the runner can't log out and in. A
  status of "requires approval" (2) means macOS wants the learner's yes in
  Login Items first; the app then counts it as off.
- **Limits:** macOS opens a login item without arguments, so the app can't
  be told `--in-tray` as Windows' Run value tells it: on a Mac it opens
  with its window at log-in, and the offer's text says "It opens when you
  log in". Opening in the menu bar alone needs the app to see it was
  opened as a login item (the open event's `keyAELaunchedAsLogInItem`, if
  `SMAppService` sets it) - a project of its own.

## Updates by themselves (polyglotic-hq 430, decision 0202)

**Done.**
- The Mac release is Velopack's packages: the portable zip testers
  download first (`Polyglotic-macos-arm64-alpha.zip` on the bucket), the
  full package installed Macs update to, and the channel's feed
  (`tools/package/pack.sh`, on GitHub's Mac). The app inside the zip has
  Velopack's `UpdateMac` and `sq.version`, so the first install can update
  itself; 422's plain zip couldn't, and is gone.
- `vpk pack` signs the bundle again after adding its files, with our
  certificate and the build's flags (`tools/package/macos_codesign.sh`:
  no Apple timestamp, no hardened runtime). The designated requirement
  stays the build's, so permissions carry over (decision 0196).
- The feed is signed on the PC with Windows' key (HQ's `publish-mac.sh`);
  the key is never on GitHub. Upload order as Windows': package, zip, the
  feed's signature, the feed.
- The app keeps the signed feed's checked files in
  `~/Library/Caches/Polyglotic/verified-feed`, outside its bundle.

**Proven on GitHub's Mac** (macOS 26, Apple silicon; the public copy,
signed with `Polyglotic Mac Signing`; polyglotic-hq 430's report has each
run):
- The release part (run 43872700892, version 0.1.6, nothing published):
  the full package (88.0 MB), the portable zip (85.6 MB) and the feed,
  with the version's notes; the zip's app verifies and has the built
  app's designated requirement (`identifier "io.polyglotic.desktop" and
  certificate root = H"3517db95..."`); SHA256SUMS checked there and again
  on the PC, where `publish-mac.sh publish` (dry run) signed the feed with
  the feed's key and checked the signature.
- An update rehearsed (`tools/package/macos_update_rehearsal.sh`): the
  build packed as 0.0.1 and 0.0.2 into a feed in a folder, 0.0.1 unzipped
  into `~/Applications` and seen as installed by Velopack, 0.0.2 found and
  downloaded by the app, and applied by Velopack's UpdateMac at the next
  start ("Package version 0.0.2 applied successfully", run 43872700892),
  which then restarts the app through `open` with the same arguments.
  Run 43882120900 (2026-11-17) went through to the end: the restarted
  0.0.2 wrote its check, the updated app verifies (`codesign --verify
  --deep --strict`), is still `Polyglotic Mac Signing` with the built
  app's designated requirement, has no quarantine attribute, and starts
  again as installed. The app's own stamp still says 0.0.1 there: the
  rehearsal packs one build twice, as Windows' does; Velopack's
  `sq.version` says 0.0.2. `spctl` rejects it, as it does every app
  without a Developer ID; with no quarantine, Gatekeeper doesn't check it
  at launch.

**Not proven, and why:**
- **The signed feed over https on a Mac.** The rehearsal reads a feed in a
  folder, as Windows' rehearsal does (package.yml); the signature check is
  the same Python on both, and a folder feed skips it. Seen first when
  the first Mac tester updates from 0.1.7 to the next version.
- **Gatekeeper on a tester's Mac.** The runner has no quarantine. An
  update is downloaded by the app itself and unpacked by Velopack, neither
  of which marks files as quarantined, so the updated app shouldn't need
  Open Anyway again (the runner shows no quarantine attribute on it). Only
  the first, downloaded zip does.
- **App Translocation.** A quarantined app opened where it was unzipped
  (Downloads) runs from a read-only copy macOS makes; Velopack 1.2.161
  doesn't detect it and its update would fail. The help page's "Move
  Polyglotic to Applications, then open it there" step avoids it, and the
  app checks at its start (polyglotic-hq 433, decision 0205): run from
  such a copy, it asks once to move itself to Applications and opens again
  from there, or says how to do it by hand. On GitHub's Mac
  (`tests/test_macos_translocation.py`), Security's calls answer and the
  move clears the quarantine attribute; but Security won't make a
  translocated copy for a test ("Operation not permitted" with Safari's
  quarantine flags, run 43907575317), so the copy itself - and the packed
  app opened from Downloads by a person, with Gatekeeper's Open Anyway -
  isn't seen yet: the first Mac tester's run is the proof.
- **`/Applications` owned by another user.** Velopack asks for an
  administrator's password (osascript) when it can't replace the bundle;
  the runner's `~/Applications` never needs it.
- **Permissions and the keychain after an update, on a real Mac.** The
  requirement is checked equal on the runner; macOS keeping the
  microphone, system audio and the keychain item across it is Apple's
  documented behaviour, not yet seen.
- **No `.pkg` installer**: it would need Apple's installer certificate,
  and an unsigned one is harder to open than the zip.
- **Deltas**: off, as on Windows' signed feed (full packages only).

## The build's Python (polyglotic-hq 523)

**Done:** the macOS job pins its Python: `UV_PYTHON` (an exact version,
3.12.15 from 2026-11-20) with `UV_PYTHON_PREFERENCE=only-managed`, so uv
builds the venv - and PyInstaller packs - uv's own CPython
(python-build-standalone). `tools/package/macos_python.py` checks the pin
holds at the start of every run.

**Why:** 0.1.7 was packed with the runner image's python.org 3.12.10,
whatever version the image had that week. Its OpenSSL read roots only from
python.org's own folder, which GitHub's Mac has and a learner's Mac doesn't:
every learner's sign-in failed (polyglotic-hq 512, decision 0236).

**Moving the pin:** by hand, with the lockfile's next refresh; the pack
part's `--check-tls` (no python.org folder) and `--check-install` prove the
new one.

## Intel Macs (polyglotic-hq 430)

**Not built.** What it takes, found 2026-11-17:
- **onnxruntime** is the only one of the app's packages with no Intel-Mac
  wheel: 1.23.2 (2025-10-27) was the last; 1.24 onwards are Apple silicon
  only. 1.23.2 gives exactly 1.31.1's speech probabilities on the app's
  own samples (every frame of `en.flac` and `zh.flac`, checked on Windows
  x64). Everything else has an x86_64 or universal2 wheel (PySide6,
  catap, sounddevice and PyNaCl universal2; numpy, soundfile and velopack
  x86_64).
- **A runner:** `macos-13` is gone (December 2025); `macos-15-intel` is
  GitHub's last Intel image, until fall 2027.
- **A channel:** protocol.md has only `macos-arm64-*`; an Intel build
  needs `macos-x64-alpha` added on the server first.
- **The build:** the layout's `libsndfile_arm64.dylib` per architecture,
  `pack.sh`'s `--runtime osx-x64`, and the Mac job on the Intel image.

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
`tools/macos_full_screen_checks.py` (the macOS job's `parity` part; polyglotic-hq
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

## Esc and clicks elsewhere (polyglotic-hq 438)

**Done.** The `KeyState` port, as Windows has it (`platform/macos/keys.py`):
dictation's Esc cancels what isn't typed yet; a settings popover and the
pinned lookup card close on Esc or a click elsewhere, and the card goes
back on Backspace.
- Pressed since last asked: AppKit's global monitor
  (`addGlobalMonitorForEventsMatchingMask:handler:`), for presses that go
  to other apps. Only Esc, Backspace and "a mouse button" are kept; every
  other key is dropped as it arrives, nothing is logged, and nothing is
  consumed.
- Held now: a mouse button, from `CGEventSourceButtonState` (a press in
  the app's own windows, which the monitor doesn't hear).
- Only while asked about: the monitor comes with the first ask (dictation
  listening, a popover open, the card pinned - every 40-50 ms) and goes
  2 s after the last, at the next press it hears.

**Permissions:** none new.
- Mouse-downs need none.
- Key-downs reach the monitor only with **Accessibility**, which
  dictation's typing already asks for. Apple's `NSEvent` documentation:
  "Key-related events may only be monitored if accessibility is enabled
  or if your application is trusted for accessibility access".
- Without Accessibility, Esc and Backspace read as never pressed; clicks
  elsewhere still work.
- No **Input Monitoring**: no event tap, and the app never calls
  `CGEventSourceKeyState`.

**Proven on GitHub's Mac** (macOS 26.7.2, polyglotic-hq 438's run 3,
2026-11-17; the runner's processes have Accessibility, and Input
Monitoring too):
- `escape_cancels`: dictation listening (`ui.dictation.Dictating` on
  stand-ins for the mic and the server, the real `MacKeys`), TextEdit in
  front; System Events pressed Esc (key code 53) and the hold was
  cancelled ("cancelled" on the sign).
- `click_elsewhere`: a caption window's settings popover open with the
  real `MacKeys`; a click in TextEdit's window closed it. The monitor
  heard a left mouse-down. The click is cliclick's (from Homebrew), a
  real mouse event. System Events' `click at` isn't one: it moved no
  cursor and the monitor heard nothing (run 2), so 429's `click` check,
  which clicks the caption window that way, proves less than it seems.
- Quartz's key state (`CGEventSourceKeyState`) never saw System Events'
  Esc, whose down and up come back to back: polling can't catch it, and
  the monitor can.

**Not proven, and why:**
- **Esc without Accessibility, and without Input Monitoring, with a
  person.** The runner's processes have both, so it can't show which one
  macOS asks of a key monitor today. Apple's documentation names
  Accessibility, the one dictation already asks for.
- **Clicks on another display, or in a full-screen game.** The runner has
  one display and no games. The monitor hears mouse-downs on any display,
  per Apple's documentation, but that's untried.

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
- Settings' "Open System Settings" (`text_input.Permission`): System
  Settings opened (polyglotic-hq 438's run 3). Which pane it opened at
  wasn't read: asking System Settings timed out.

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

## The Mac as a learner's Mac (polyglotic-hq 523, decision 0243)

**Done:** the macOS job's `learner` part, run by `macos_mirror.sh <ref>
--parts learner` (with tests, pack, parity and updates) and by
`publish-mac.sh`'s release build on the release run itself. Each check fails
the job on a fail; unknown is what the runner didn't let a script see.

| Check | What it catches | Where |
|---|---|---|
| hidden | python.org's Python, Homebrew, the developer tools and Xcode moved aside while the packed app is checked (and around pack's `--check-tls`) | `tools/macos_learner_checks.py` |
| linkage | a library loaded from outside the bundle and macOS (Homebrew's, python.org's, uv's) | same |
| downloaded | the zip from `~/Downloads` with Safari's quarantine, through Archive Utility: the seal and the designated requirement survive; Gatekeeper's verdict | same |
| opened_from_downloads | refused by Gatekeeper, Open Anyway, translocated, the move to Applications offered, moved, quarantine gone, opened again | same |
| fresh_account | a new macOS user's `--check-install` and `--check-tls` (live's /health, sign-in, the session's `wss`) | same |
| the update from the published release | polyglotic.io's zip installed, this build found, applied and restarted into; settings, keychain item and designated requirement kept | `tools/package/macos_update_from_release.sh` |
| every setting changed and put back | a setting that doesn't come back, an error box, an error logged, a part that broke | `tools/macos_settings_sweep.py` |
| sound out | a recorded word and "Say it" silent, clipped, too quiet, the wrong length or pitch | `tools/macos_parity_checks.py` (`said_recorded`, `said_by_macos`) |
| over full-screen apps, the real mouse, hover, levels (515) | a popover behind its window, a resize macOS takes, no hover with another app in front | `tools/macos_full_screen_checks.py` |

**Proven where:** GitHub's Mac (`macos-26`), through the public copy.

**Known, said as notes until fixed:** Quiet view on and off again in
Settings > Links leaves word links off and six languages' reading lines on
(`LookView.set_quiet` on its own puts the lines back, so it's the switch's
path); the sweep's `KNOWN` names it, and the fix takes it out. On GitHub's Mac a word
of a reading is told 0.10-0.17 s late (`test_speaking.py`'s word-timing
test, xfail there): its waits oversleep on the runner.

**Not proven:** the full captioning session from the packed app to live
(needs a validation invite on live for the public copy: DECISIONS #190 item
2); a GUI session for the fresh user (the runner can't log one in); Gatekeeper
as a learner meets it after Open Anyway in System Settings (emulated by the
quarantine's approved flag).

## What still needs a person (polyglotic-hq 523)

What GitHub's Mac can't judge. Each is a two-minute item in a preview's
what-to-try, not a test of everything:

1. **The trackpad and the cursor:** drag a caption window's corner and each
   edge with the trackpad, with a video in front. Does a resize cursor
   show? Does the size stay after quitting and starting again?
2. **Retina:** look at a caption window and the lookup card side by side
   with another app's text. Is the text as sharp?
3. **Real speakers and your ear:** press "Say it" on a common Chinese word,
   then on a phrase, through the Mac's own speakers. Is it the word, at a
   natural pace, not clipped or tinny?
4. **A full-screen video app:** play a video full screen (Safari, YouTube
   or IINA), open the caption window's settings and the language chip over
   it. Do they stay in front, and does the video stay full screen?
