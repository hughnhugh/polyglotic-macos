# 0196 The Mac release is signed with our own self-signed certificate

- **Status:** accepted; its release zip (`build.release_zip`) replaced by
  0202, Velopack's portable zip
- **Date:** 2026-11-16
- **Decided by:** the user, 2026-11-16 ~23:00 ("a self-signed certificate
  so permissions carry over between versions"; polyglotic-hq 422). Claude
  made the certificate at 23:01.

## Situation

The Mac app (decision 0186) was signed ad hoc. macOS keeps a learner's
answers to its permission prompts (system audio, the microphone) and the
Keychain's trust in the app under the app's *designated requirement*. An
ad-hoc signature's requirement is the build's hash, so every new version
would ask for both permissions again and could ask about the keychain
item. Apple's Developer ID (US$99 a year) would also make Gatekeeper
accept the app, but needs an Apple developer account, which the user
hasn't chosen to buy.

## Decision

- A self-signed code-signing certificate, `CN=Polyglotic Mac Signing`
  (valid 10 years), signs every Mac release. It lives only as two secrets
  on the public Mac repo (`MACOS_SIGNING_P12`, base64 PKCS#12, and
  `MACOS_SIGNING_PASSWORD`) and, during a run, in a temporary keychain on
  GitHub's Mac, deleted at the end (`.github/workflows/macos.yml`).
- The job sets `POLYGLOTIC_CODESIGN_IDENTITY` to the certificate's SHA-1;
  `tools.package.build.sign` signs with it (`--timestamp=none`: Apple's
  timestamp service is for its own certificates) and records the
  signature's `authority`. `signature_problems` fails the build if
  codesign couldn't sign, the bundle doesn't verify, or a certificate was
  named but the app came out ad hoc (PyInstaller's ad-hoc signature stays
  underneath, so a failed signing still verifies).
- Without the secrets (this private repo, a fork) the app is signed ad hoc
  as before. A `release` run refuses to go on without the certificate and
  checks the app's authority is `Polyglotic Mac Signing`.
- A `release` run keeps `Polyglotic-<version>-macos-arm64-alpha.zip` and
  its `.sha256` one day (`build.release_zip`), for the release step
  (polyglotic-hq 422's `publish-mac.sh`) to check and upload.

## What it gives, and what it doesn't

- **Gives:** the same designated requirement for every version
  (`identifier "io.polyglotic.desktop" and certificate leaf = H"..."`),
  so permissions granted to one version hold for the next, and the
  keychain item the app made stays readable without a prompt. This is
  what macOS documents for designated requirements; it has not yet been
  seen on a tester's Mac across two versions.
- **Doesn't:** Gatekeeper still treats the app as from an unidentified
  developer. Each downloaded version must be opened once with System
  Settings › Privacy & Security › Open Anyway. No notarization, no
  hardened runtime.

## Why

It's free, and it removes the worst of an update on the Mac (granting
both permissions again) while there's no Developer ID. Alternatives: ad
hoc (every update asks again), or Developer ID now (money and an Apple
account: the user's call, not taken yet).

## What would make us reverse it

Buying a Developer ID. Note that moving to it changes the designated
requirement once: every learner is asked for the permissions one more
time on that version.

## How we'd reverse it

Put the Developer ID certificate in the same two secrets (and add
notarization and the hardened runtime to the job). `sign` and the build
don't change. If the self-signed certificate leaks, make a new one and
replace the secrets: learners are asked again once.
