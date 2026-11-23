# 0268 Linux captures one app from its streams' own monitors, fixed to each stream

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 561), from 546's plan (section 1,
  `app_capture`) and 547's spike on GitHub's runners; reversible inside
  `platform/linux/`.

## Situation

The first Linux build captioned everything the PC plays and the mic only
(decision 0258): `app_capture_support` said no, so Home offered no apps.
One app at a time - a game's or a call's voices without the browser's
video beside them - is the app's main way of listening on Windows and the
Mac, and Home's picker, the caption windows and the "everything else"
source are already built for it.

Linux's sound servers (PipeWire's pulse server on every current desktop,
PulseAudio before it) list each stream an app plays as a sink input, and
let a client record one sink input alone from its output's monitor.

## Decision

- **One app** is a record stream on each stream it plays, from the monitor
  of the output it plays to, with `pa_stream_set_monitor_stream` - only
  that stream's sound - through libpulse, as everything else is (0258).
  547 measured 109 dB between two players' tones on Ubuntu 24.04's
  PipeWire 1.0.5.
- **Each record stream is fixed to its stream** (`PA_STREAM_DONT_MOVE`).
  Without it, when the app's stream ends WirePlumber moves the record
  stream to the mic, and the app's caption window captions the learner
  (547: 3 s of the mic). With it the record stream fails; the capture
  takes the app's next stream.
- **An app is its executable's name** (`application.process.binary`), from
  the stream, else from its client (a native PipeWire player puts it only
  there, 547), and its process the one the server saw connect
  (`pipewire.sec.pid`) before the one the app gave (a sandboxed app's own
  number). Under Wine (a Windows game through Proton) the program's own
  name, since every such program's executable is Wine's. Never the
  stream's title (`media.name`: a file, a tab, a song).
- **Several streams of an app are summed** on the app's clock, 100 ms
  behind their arrival so a late piece still counts; one stream alone goes
  straight on, with no added wait.
- **The app has closed** once it plays nothing, the process it was chosen
  by is gone and no other process of it runs; until then a pause is
  silence.
- **Everything else** is every other app's streams the same way, summed,
  leaving out that app (known by its process) and Polyglotic's own.
- **The apps playing** for Home's picker are the sink inputs grouped by
  that key, read once per half second on a connection of its own, waiting
  at most a second for the sound server (the picker asks on the
  interface's thread). The known apps' Linux executables are listed in
  `platform/linux/categories.py`, public names only where Windows' list
  (and so the tracking plan) has them.
- `app_capture_support` is "yes" wherever libpulse loads.

Tested with a stand-in server on every OS, and on GitHub's Ubuntu runner
with real PipeWire: two players, two tones, each capture hearing only its
own; and the app's tour on GNOME and KDE, the app chosen on Home's list
while another plays (`linux.yml`).

## Why

- One library for every source, as 0258 chose: no native PipeWire API,
  which ctypes can't reasonably reach, and no `pactl`/`parec`, which Ubuntu
  doesn't install.
- Summing in the app keeps "everything else" on the same route. OBS's way
  (a virtual sink and links, native PipeWire) mixes in the server and
  needs PipeWire's own API.
- Keying an app by its executable matches what Windows does (the
  executable's name) and keeps an app one entry however many streams it
  plays.

## What would make us reverse it

- Testers' apps whose streams carry no executable (some sandboxes): key
  them by `application.id` or the Flatpak's app id.
- A sound server that refuses monitor streams of one sink input (none
  found): fall back to everything the PC plays, saying so, as an older
  Windows 10 does (decision 0076).
- Summed audio that drifts between streams over long sessions: sum by
  sample count per stream rather than by stamp.

## How we'd reverse it

`capture.AppCapture` and `EverythingElseCapture` and `apps.py` are Linux's
alone; `app_capture_support` back to "no" hides apps again (Home's own
note says why). About a day to change the route inside `platform/linux/`.
