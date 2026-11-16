# 0186 The Mac app is a signed bundle, proved on GitHub's Mac by hand

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, within the user's "the Mac now" (2026-11-16,
  polyglotic-hq topic #10, 408's report, project 410). The bundle
  identifier and the permission prompts' wording are drafts until the user
  approves them; the job's first run waits for the user's decision on
  macOS minutes (polyglotic-hq DECISIONS #190).

## Situation

The app was packed for Windows only: one PyInstaller folder, files the
build adds (dictionaries, notices, release notes, licences) beside
`Polyglotic.exe`. A Mac app is an app bundle with an Info.plist; macOS
ends an app that touches the microphone or a Core Audio tap without a
sentence saying why; `Contents/MacOS` may hold only code, since the
bundle's signature seals everything else; and Apple silicon needs every
binary signed. Nothing checked any of it on a Mac.

## Decision

- **The bundle:** the spec makes `Polyglotic.app` on macOS (Apple silicon
  only: onnxruntime has no Intel-Mac wheel), with Qt's cocoa plugin kept.
  Its Info.plist comes from `tools/package/build.py`'s `info_plist`:
  identifier `io.polyglotic.desktop`, minimum macOS 14.2 (Core Audio's
  process taps), `NSMicrophoneUsageDescription` and
  `NSAudioCaptureUsageDescription`.
- **The build's files go in `Contents/Resources`** (`build.Layout`), and
  the packed app finds them through `main.beside_the_app`, which knows
  both layouts from where the program is.
- **Signed ad hoc** after the build's files are in (`codesign --force
  --deep --sign -`), or with the certificate `POLYGLOTIC_CODESIGN_IDENTITY`
  names; verified, and its designated requirement recorded.
- **Proved on GitHub's macOS machine, by hand only:** `.github/workflows/macos.yml`
  (`workflow_dispatch`): the tests, mypy as macOS sees the code, the
  import rule, the app's tour on real windows (`tools/app_tour.py`), the
  packed app's `--check-install`, and what the machine allows for capture
  (`tools/macos_measure.py`). Enforced by `tests/test_workflows.py`.

## Why

- The identifier is what macOS keeps a learner's permissions under, so it
  has to be chosen once, before a tester grants one; the domain's reverse
  (`io.polyglotic`) is Apple's convention.
- Resources, not beside the program: a data file in `Contents/MacOS`
  breaks the signature's seal, and Apple's guidance puts data in Resources.
  Finding it from the program's own path keeps the rule in one function
  with no OS check.
- Ad hoc first: a Developer ID costs US$99 a year and notarisation needs
  it; a first tester can open an ad-hoc app through System Settings.
  The cost: each new ad-hoc build asks for the permissions again, since
  its designated requirement is its hash.
- By hand only: macOS minutes cost US$0.062 each on a private repo (408);
  on every pull request it would be the US$840 a month 171 priced.

## What would make us reverse it

- A Developer ID (the beta): sign with it, notarise, and the hardened
  runtime with the audio-input entitlement.
- Testers re-granting permissions after every build: a stable self-signed
  certificate kept as a secret (`POLYGLOTIC_CODESIGN_IDENTITY`).
- A Mac on the user's desk or a self-hosted Mac runner: the job moves
  there and may run on pull requests.

## How we'd reverse it

The identity is one environment variable; a runner is the job's `runs-on`.
Changing the identifier after testers have one loses their permissions
(they grant them again) - the only part that's costly to change.
