# The Mac's own pieces: what's done, where it's proven, what isn't

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
  back, they're free again. See the latest run's `parity.json`.
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
  (`platform/recorded_voices.RecordedVoices`, wrapping a `Voices`). It
  isn't on this branch's base yet; when the two meet, the Mac's `speaker`
  in `main.macos_adapters` takes `recordings` and wraps `MacVoices` the way
  Windows' wraps `WindowsVoices` - the voices and the player here need no
  change.
- **Proven where:** the order, the pace and the clip's format on any OS;
  on GitHub's Mac (`parity`): the voices listed, "hello" made at each pace
  the card uses (how long each takes is in `parity.json`), and the card's
  whole path - `SpeakerThread`, `MacVoices`, `AudioPlayer` - saying a word
  on BlackHole while the mic on BlackHole hears it.
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
  apart at 16 px (`tests/ui/test_icons.py`); on GitHub's Mac, the icon
  shown in the menu bar as a template, and `light_menu_bar` following dark
  mode switched by AppleScript. `menu-bar.png` shows the icons drawn as
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
  on GitHub's Mac, the packed app's `--check-parity`: ServiceManagement
  loads in the bundle and macOS adds the app to its login items and takes
  it off, each state it gave in `packed-parity.json`.
- **Not proven:** a log-in after it - the runner can't log out and in. A
  status of "requires approval" (2) means macOS wants the learner's yes in
  Login Items first; the app then counts it as off.
- **Limits:** macOS opens a login item without arguments, so the app can't
  be told `--in-tray` as Windows' Run value tells it: on a Mac it opens
  with its window at log-in, and the offer's text says "It opens when you
  log in". Opening in the menu bar alone needs the app to see it was
  opened as a login item (the open event's `keyAELaunchedAsLogInItem`, if
  `SMAppService` sets it) - a project of its own.
