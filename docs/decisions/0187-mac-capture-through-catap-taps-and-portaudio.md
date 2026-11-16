# 0187 The Mac captures through Core Audio taps (catap) and the mic through PortAudio

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** polyglotic-hq project 411 (the user, 2026-11-16: "I want
  to port this over"; 408's report chose catap and sounddevice; 171's
  research chose taps over ScreenCaptureKit). Claude reviews it with the
  pull request. The Mac's side of [0006](0006-windows-capture-with-own-ctypes-wasapi.md).

## Situation

On a Mac, one app's sound, everything else and the whole system's are
captured with Core Audio's process taps (macOS 14.2 and later); the mic
with a normal Core Audio input. A tap's audio arrives on Core Audio's
real-time thread: Python there, holding the interpreter's lock, would drop
audio (171). Windows' capture is our own ctypes code (0006), but a tap
also needs Objective-C objects (`CATapDescription`) and a private
aggregate device. Nobody on the team has a Mac (2026-11-16).

## Decision

- **Taps through catap** (0.6.1, MIT, PyPI 2026-11-05;
  `platform/macos/capture.py`): its native library runs the real-time
  callback into a ring and hands buffers to a Python thread of its own; we
  build the tap's description (one app's processes, a global tap leaving
  some out, or one output device's) and read its buffers.
- **The mic through PortAudio** (sounddevice 0.5.6, MIT): Core Audio's
  input at the device's own rate.
- **Our own conversion** for both: mixed to mono, low-passed and resampled
  to 16kHz (a 63-tap windowed sinc at 7.2kHz, then linear interpolation),
  stamped on `time.perf_counter` and kept continuous (`platform/timeline.py`,
  shared with Windows).
- **Both are dependencies for `sys_platform == 'darwin'` only**, imported
  when a capture first starts; on Windows and Linux nothing changes.
- **A permission not given** records silence, not an error: the capture
  says `ports.capture.NOT_ALLOWED` after 10 s of only zeros while Core
  Audio says something it taps plays.

## Why

- catap is readable Python over PyObjC plus about 600 lines of C,
  MIT, tested in CI on macOS 15 and 26, and does the hard part - the
  real-time thread - the way Apple's sample does. Read for this record
  (2026-11-16): its README and licence, `bindings/process.py`,
  `bindings/device.py`, the tap description's constructors and
  `session.py`'s `RecordingSession` (not its native C, its recorder or its
  multitrack code).
- Our own native helper (171's other option: Swift or C streaming 16kHz
  over a pipe) would be more code to build, sign and ship, for the same
  calls.
- PortAudio is the proof of concept's mic path on Windows, and its Core
  Audio side is mature. catap's own input path is for multitrack sessions
  and experimental.
- Resampling ourselves keeps one tested path for every rate Core Audio
  hands us (48k, 44.1k, 96k, 24k), rather than asking each API to convert.

## What would make us reverse it

- catap breaks on a macOS release, falls behind, or a bug in it drops
  audio we can't fix upstream.
- Its first-run checks on a Mac (polyglotic-hq 410's job, a tester) show
  taps of Chromium's or Electron's helpers, or device switches, failing in
  ways its API can't handle.
- Resampling costs too much CPU on a low-end Mac (it hasn't been measured
  on one).

## How we'd reverse it

`platform/macos/capture.py`'s `_TapStream` is the only code that touches
catap (plus `apps._read` and `devices.audio_devices`, which list
processes and devices). A replacement - our own PyObjC and ctypes over
Core Audio, or a native helper - delivers the same pieces (`Stream.put`:
the data and its format) and everything else stays: a day or two of work
plus a Mac to check it on. Dropping catap from `pyproject.toml` changes
nothing on Windows.
