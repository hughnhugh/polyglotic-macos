# The Mac: what's done, where it's proven, and what isn't

Each Mac-parity project keeps its own sections here (polyglotic-hq 428,
429, 430): what was built, where it was proven, what wasn't, and why.

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
  The updated app's own checks: see the report.

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
  doesn't detect it and its update would fail. The help page's "Put it in
  Applications" step avoids it; nothing in the app checks yet.
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
