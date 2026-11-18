# 0236 A Mac's secure connections trust the roots macOS ships

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude, for polyglotic-hq 512 (a P1: a Mac tester couldn't
  sign in, 2026-11-18 12:21). The user asked for the fix to be released
  as soon as possible ("release that fix asap", 2026-11-18 12:26). The
  choice of root list is Claude's, and the user can reverse it.

## Situation

The app checks our server's certificate with Python's `ssl` (OpenSSL
3.0), through one place: `connection.tls.trusted()`, which every client
context comes from (sign-in, the listening session, the signed update
feed, dictionary packs, feedback, problem reports). On Windows
`ssl.create_default_context()` reads Windows' certificate stores.

On a Mac it reads only OpenSSL's default places. In the packed Mac app
that place is python.org's Python's
(`/Library/Frameworks/Python.framework/Versions/3.12/etc/openssl/cert.pem`,
seen in the packed app on GitHub's Mac, run 44216331910). GitHub's Mac
has python.org's Python 3.12 installed there, with 118 roots, so the app
connected on GitHub's Mac. A learner's Mac doesn't have that file. With
no roots, every handshake failed verification, and
`connection.failures` read that as something on the network in the way.
The tester saw "Something on this network is in the way" on Enter your
code, with two valid codes, and none of their tries reached our server.
Earlier Mac checks (408, 430, 433) ran against a stand-in server without
TLS, or on GitHub's Mac, so none of them could see the failure.

## Decision

On a Mac, `trusted()` also loads macOS's own root list,
`/etc/ssl/cert.pem` (`tls.MAC_ROOTS`). That is the list Apple ships and
updates with macOS, and the one macOS's own LibreSSL reads (its
OPENSSLDIR is `/private/etc/ssl`). OpenSSL still does the verifying,
exactly as on Windows. If the file can't be read, a warning is logged
once and the app goes on with what OpenSSL found. Windows and Linux are
unchanged (`MAC_ROOTS` is None there).

How it's held:
- `tests/test_tls_mac_roots.py` uses a Mac whose OpenSSL finds no roots.
  It proves the store holds macOS's list, a TLS connection, and that
  sign-in's own path reaches the server.
- The packed app's `--check-tls` runs in `macos.yml`'s pack part (and so
  in every Mac release build). It hides python.org's folder, as on a
  learner's Mac, then fetches live's `/health` and signs in with a code
  that's no one's. The job fails unless the server answers both.

Decision 0104 (a certificate outside its dates is tried again, its leaf
checked against the build time) works on a Mac as on Windows. It rests on
OpenSSL's verify codes and its `NO_CHECK_TIME` flag, and both still apply.

## Why

- **It's the Mac's own list,** shipped and updated by Apple, with nothing
  for us to keep up to date. The tester's bridge
  (`SSL_CERT_FILE=/etc/ssl/cert.pem`) is the same file and proved it.
- **OpenSSL stays the verifier,** so 0104's retry without the dates, the
  verify codes `connection.failures` reads, and the handshake check
  classes (`_CheckedSocket`, `_CheckedObject`) behave the same on both
  systems. That is the smallest change, and it could ship as a hotfix
  (0.1.8) the same day.

Not taken:
- **truststore** (MIT), which verifies with macOS's Security framework
  (`SecTrustEvaluateWithError`). It turns OpenSSL's verification off
  (`CERT_NONE`, host names unchecked) around the handshake and checks the
  chain after it (its `_macos.py`, read 2026-11-18). That replaces the
  verifier 0104 is built on, swaps the context's verify mode on every
  use, and would make a Mac verify differently from Windows. It is
  right for keychain-only roots (a company's, an antivirus's), but too
  big for a hotfix. It's a candidate for the reversal below.
- **certifi** (Mozilla's list, MPL-2.0): it adds a dependency and a list
  we'd have to keep up to date through our own releases, and it isn't
  the Mac's own list. PyInstaller's certifi hook would also set
  `SSL_CERT_FILE` for the whole process, on Windows too, unless kept
  off it.

## What would make us reverse it

- A Mac learner behind something that adds its own root to the keychain
  (a company's TLS inspection, an antivirus) can't connect, though the
  browser on the same Mac can. `/etc/ssl/cert.pem` doesn't hold keychain
  additions.
- A macOS release that drops or empties `/etc/ssl/cert.pem`. The
  warning says so in the log, and the packed app's `--check-tls` on
  GitHub's Mac would fail on a newer macOS image.

## How we'd reverse it

Only `trusted()` and its test change. To trust the keychain too, read
the keychain's anchors (`SecTrustCopyAnchorCertificates`, and the user's
and admin's trust settings) into the OpenSSL context, as
`load_default_certs` does with Windows' stores. That keeps OpenSSL and
0104 and is about a day's work with a Mac test. Moving to truststore on
the Mac instead means reworking 0104's retry for the Security framework's
errors, which is several days. Either is a new record that replaces
this one.
