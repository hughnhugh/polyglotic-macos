# Real windows without the user's screen

For QA and the UI judge (polyglotic-hq project 205, 2026-11-08). The
tool is `tools/private_desktop.py`; its smoke test is
`tests/test_private_desktop.py`.

Windows shows one desktop at a time, the *input desktop*. A desktop made
with `CreateDesktop` is never shown unless something switches to it, and
nothing here does. A program started there makes real windows: Qt's
`windows` platform, not `offscreen`. They have Windows' own z-order,
always-on-top band, hit-testing and activation, and none of them reaches
the user's screen. So a real-window check no longer needs the user's
screen, as long as it's one of the checks in the first table below.

## Run it

```
uv run python -m tools.private_desktop run --timeout 300 --windows build/windows.json -- COMMAND ...
uv run python -m tools.private_desktop python --shots build/shots --grab-after 5 -- your_qt_program.py ...
```

- `run` starts any command there, with `QT_QPA_PLATFORM=windows`. It waits,
  then prints the command's output. At the timeout it ends the command
  and everything it started. `--windows` lists the desktop's windows every
  second as JSON, top of the z-order first: position, always-on-top,
  click-through, no-activate, its thread's active window, DWM's cloaked
  state and DPI.
- `python` runs a Python program the same way. Once, `--grab-after`
  seconds after the program's `QApplication` exists, it saves a picture
  of each window the program shows. The pictures come from the program's
  own `grab()`, never from a screen capture.
- **The app itself** runs through `tests/app_on_a_desktop.py`, never
  `polyglotic_desktop.main` directly: the driver swaps out the hotkeys
  (see below) and the PC's list of apps with sound.
- In a test: `with PrivateDesktop() as desktop: started = desktop.start([...])`,
  then `desktop.windows(started)`, `desktop.window_at(x, y)` (which window
  the mouse would reach; nothing is clicked), `windows_here(started)`
  (should be empty) and `started.wait()`.

**QA's driver** (203's `drive_app.py`) runs as a command:
`run -- .venv/Scripts/python.exe <drive_app.py> RUN --real ...`. Give it
its own `--credentials` entry. It already registers no hotkeys and keeps
its own cursor. **The lab** is offscreen by design; don't approve goldens
from real windows: the pictures would come from another platform
(not tried under 205).

## What it covers (measured 2026-11-08)

| Check | On a private desktop |
|---|---|
| The app starts, shows its windows, and the learner's Quit ends it (exit 0, nothing left) | Yes: `test_the_app_starts_and_quits_on_a_desktop_of_its_own`, about 4 s |
| Always on top: a second app's topmost window comes up over the captions; `WindowsOnTop.put_on_top` puts them back above it, in order | Yes, read from outside |
| Click-through: the mouse at a locked caption window reaches the app underneath; at an unlocked one, the window itself | Yes (`window_at`) |
| The caption windows never take activation: no-activate, never their thread's active window; the other app keeps its own | Yes |
| Windows' own windows, styles, DWM's view (not cloaked), DPI | Yes |
| Each window's icon as Windows has it - the one its title bar, the taskbar's button and Alt-Tab draw - is Polyglotic's, small and big | Yes, read from outside (`tools/window_icon.py`, 245); how the real taskbar and Alt-Tab show it is still the user's screen |
| Real-window numbers (start time, GDI and USER objects) | They're the process's own, so they're read the same way as on the user's screen. The start is timed there in CI: `tools/learner_start.py --real-windows`, `tests/ui/test_start_with_real_windows.py` (322, decision 0111). GDI and USER objects: not measured |
| Qt's high-DPI paths at 150 % | Partly: `QT_SCALE_FACTOR=1.5` gives Qt's split between logical and real pixels (960 x 300 became 1440 x 450), but Windows still reports the monitor's own DPI |

**Where it works:** in the signed-in user's session, which is where an
agent's shell runs. On the CI runners, which are services in session 0,
only the interactive window station (`WinSta0`) can show a user interface
(Microsoft's "Window Stations" page). The app starts, paints and quits
there, but its windows are never visible to Windows, and hit-testing finds
nothing. The tests ask `can_show_windows()` and check visibility and
`window_at` only where it says yes.

## What still needs the user's screen

- **The tray, partly.** That desktop has no taskbar, so a tray icon has
  nowhere to go; Qt still says a tray is available. A stand-in taskbar
  (`tools/stand_in_taskbar.py`, 215) takes the icon there. It checks:
  - the icon arrives, with its tooltip and picture, and changes;
  - Qt finds where it is;
  - the taskbar's clicks reach the app: the right click opens the tray's
    menu upwards from the icon, and the left one brings the window back;
  - Quit from that menu ends the app, and the icon goes.

  Microsoft doesn't document what Windows sends a taskbar, so the tests
  check it against what the app sent. Still the user's screen:
  - a taskbar anywhere but the bottom: the work area is the user's, and
    the stand-in never changes it;
  - the overflow area;
  - Windows' own drawing of the icon and its tooltip;
  - a light or dark taskbar.
- **Hotkeys.** Windows keeps one hotkey table for the whole session, so the
  app's Ctrl+Alt+L, P and H, taken on a private desktop, are taken from the
  user too. Swap them out, as `tests/app_on_a_desktop.py` does. Real key
  presses only reach the input desktop.
- **A game in front.** Only the input desktop has a foreground window, so
  `GetForegroundWindow` is null there and `game_in_front()` is always
  false. The trigger for putting the captions back on top can't happen;
  call `put_on_top` directly.
- **The real mouse.** The cursor belongs to the input desktop: reading it
  is refused, so hover that follows the pointer, and drags with the real
  mouse, can't be checked. Send Qt events from inside instead.
- **Windows' own scaling and text size,** mixed-DPI monitors, and how a
  translucent window looks over another app. The pictures are each
  window's own painting, not what Windows composes.

## Rules

- Never call `SwitchDesktop`, `SendInput`, `keybd_event`, `mouse_event`,
  `SetCursorPos` or `QCursor.setPos`. They act on the user's desktop, or
  Windows refuses them.
- Pictures come only from the program's own `grab()`.
- One run at a time per agent. The desktop closes at the end of `with` and
  ends what it started. Desktops use a heap Windows keeps small.
