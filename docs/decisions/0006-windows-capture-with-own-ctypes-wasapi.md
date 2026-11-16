# 0006 Windows capture is our own WASAPI code through ctypes

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** project 016 (build project D2), 2026-11-04, after the
  time-boxed probe its brief asked for; Claude reviews it with the pull
  request.
- **Amended by:** [0076](0076-one-app-alone-tried-on-windows-10.md)
  (2026-11-11): one app alone is tried on Windows 10 from build 19041, not
  only from Microsoft's documented 20348.

## Situation

The MVP captions one app at a time on Windows (process loopback), with the
whole system as the fallback and the user's mic (MVP.md). The proof of
concept captured the whole system and the mic with PyAudioWPatch, which
has no per-app capture. Project 005 named the options for one app: our own
ctypes code (the proof of concept's `audio_devices.py` already drives Core
Audio through ctypes), or a young library - `flexaudio` 0.8.1 (Rust core)
or `proc-tap` 1.1.1 ("Beta"), both MIT. It warned that the activation call
may need the main thread and an agile completion handler.

## Decision

**Our own ctypes code for all three sources** (`platform/windows/`):
- one app: `ActivateAudioInterfaceAsync` on `VAD\Process_Loopback` with
  the app's process tree, and an agile completion handler built from ctypes
  callbacks;
- the whole system: WASAPI loopback on an output device;
- the mic: WASAPI capture;
- one capture loop for all three, asking Windows for 16kHz mono float
  (its audio engine converts), stamped with WASAPI's QPC times;
- the apps with sound from `IAudioSessionManager2`, the devices from
  `IMMDeviceEnumerator`.

PyAudioWPatch and PortAudio are not used.

## Why

- **The probe worked first time (about 10 minutes, 2026-11-04, Windows 11
  build 26200):** a quiet FLEURS clip played by a test player process was
  captured alone, at 16kHz mono float directly, peak 0.0499 against the
  clip's 0.05; WASAPI's packet times were 9-12ms behind `perf_counter`
  (the capture latency) - the same clock. It also worked **from a worker
  thread** in the multithreaded COM apartment: the main-thread requirement
  is for Store apps' permission prompts, not desktop apps.
- One code path instead of two libraries: device loopback and the mic are
  the same IAudioClient with a different activation, so the device
  following, silence handling and timing are written once. Opening devices
  by id also removes the proof of concept's need to restart PortAudio for
  devices plugged in after it started.
- Letting Windows convert to 16kHz mono replaces the proof of concept's
  linear resampling with Windows' own resampler, and nothing to tune.
- No new dependency (ctypes is the standard library); nothing young or
  "Beta" in the path every caption takes.
- **Not taken:** `flexaudio` and `proc-tap` - not needed once ctypes
  worked; both are young and would add a native dependency to package and
  audit. They remain the fallback if Windows changes something we can't
  follow.

**Measured on this PC, 2026-11-04 (8s each, levels only, nothing kept):**
the test player's app capture delivered its 6.01s of audio and ended by
itself when the player closed; system loopback delivered 7.95s of 8.09s
with the quiet part filled as silence; both mics delivered continuous
frames (the headset's muted, the webcam's at a room-noise level).

## What would make us reverse it

- Process loopback or the completion handler misbehaves on machines we
  can't reproduce (other Windows 11 builds, Windows 10 20348+) in ways a
  library has already solved.
- macOS or Linux capture arrives as a library that also covers Windows
  well - one dependency for all three.

## How we'd reverse it

Write a new class behind the `AudioCapture` port (`start`, `stop`,
`capturing`, `error`) using the library, and choose it in `main`. Nothing
else changes: the rest of the app sees only 16kHz mono audio with times.
About a day per library, plus testing.
