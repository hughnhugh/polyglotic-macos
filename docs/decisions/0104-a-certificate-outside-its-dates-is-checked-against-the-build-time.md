# 0104 A certificate outside its dates is tried again, its leaf checked against when the app was built

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user, 2026-11-14 (polyglotic-hq 313): on a tester's
  sign-in screen showing "Check this PC's date and time", with the date
  right, "you should handle it rather than not let the user log in" - a
  PC with a wrong date still signs in and captions, with security kept.
  The rule and its bound are Claude's (313's brief and report); the user
  can reverse them.

## Situation

The app verifies our server's certificate with Python's `ssl` (OpenSSL
3.0), trusting what `load_default_certs` reads from Windows: the ROOT
store *and* the CA (intermediates) store, all as trust anchors. OpenSSL
stops at the first error. When it builds the path through a certificate
in those stores that is out of date - an old cross-signed root such as
"ISRG Root X2 by ISRG Root X1" (ended 2025-09-15), an antivirus's own -
it fails with verify code 10 (expired) or 9 (not yet valid), and the app
said "Check this PC's date and time" on a PC whose date was right. The
browser on the same PC verifies another way and is fine. A wrong clock
fails the same way: every certificate looks out of date. Either way the
learner was turned away.

OpenSSL checks the dates last (with the signatures, top down), after the
path, the trust and the host name; so code 9 or 10 says nothing about
the signatures below the certificate that failed.

Reproduced on 2026-11-14 against the live `api.polyglotic.io`, which
sends leaf <- YE1 <- Root YE <- ISRG Root X2 (cross-signed by X1, from
2026-05-13): a trust store of ISRG Root X1 and the old "X2 by X1"
(ended 2025-09-15), without the self-signed X2, fails with code 10 on a
right clock; with the self-signed X2, or without the old cross-sign, it
connects. Turning off OpenSSL's trusted-first still fails with code 10.

## Decision

`connection/tls.py`, for every connection the app makes itself - the
session's WebSocket, sign-in, feedback, problem reports and the update
feed:

1. **The first try is as before:** Python's default context.
2. **Only a failure on dates (9 or 10) is tried again**, once, with
   `X509_V_FLAG_NO_CHECK_TIME` (0x200000) added to `verify_flags`: OpenSSL
   still checks the path to a root Windows trusts, every signature on it
   and the host name. Never `CERT_NONE`, never `check_hostname = False`.
   Any other failure is refused as before.
3. **The leaf's dates are then checked by the app**, during the handshake
   and before anything is sent (an `SSLSocket`/`SSLObject` subclass's
   `do_handshake`): it is let through unless it **ended before this copy
   of the app was built**. The build time is stamped into `release.json`
   (`built`, UTC); from source, or a stamp from before this, the date this
   code was written (2026-11-14). A time the app was built has certainly
   passed, whatever the PC's clock says.
4. **The other certificates' dates are not held against the connection**
   once everything else checks: they are the CAs' and Windows' stores'.
5. **Every verification failure is logged once** per host, code and path:
   the verify code and message, this PC's time and UTC offset, each
   certificate's subject, issuer and dates (marked if out of date at the
   PC's time), and what the try again found (`inside`: another certificate
   was the stale one; `clock_behind`; `clock_ahead`; or refused). Only
   our own host's name is logged; another host's name in a certificate is
   left out.

6. **What the learner sees** (the second pull request):
   - let through with this PC's time outside the leaf's dates (behind its
     start, or past its end): connected, and one quiet line on Home's
     banner - "This PC's date or time looks wrong: it says {date},
     {time}" and where to set it (Set time automatically, Sync now);
     nothing stops. Let through because another certificate in the path
     was the stale one: nothing to say - the clock may be right;
   - refused (the leaf ended before the build) with this PC's clock
     before the build too - wrong for certain: "This PC says it's {date},
     which can't be right" and where to set it (`Unreachable.CLOCK`);
   - refused with the clock after the build: the leaf really is out of
     date, so it isn't the clock - "something on this network is in the
     way with an out-of-date certificate - most often an antivirus's
     HTTPS scanning, or a VPN" (`Unreachable.OUT_OF_DATE`).

Tested against a real TLS handshake on 127.0.0.1 with certificates made
for each test (`tests/test_tls.py`).

## Why

- **What an attacker would need** for the try again to help them: the
  private key of a certificate for our host, from a CA Windows trusts,
  that ended *after the app was built* - and a place on the network
  between the PC and our server. The PC's clock needn't be wrong: on a
  right clock, such a leaf is let through for as long as the app isn't
  updated past its end. Our leaves' keys are Cloudflare's and never leave
  it; an attacker who held one would more likely hold the current one,
  which works anyway. A leaf that ended before the build is refused,
  whatever the clock says - so an old leaked key (the case expiry exists
  for) never gets through, and a PC whose clock is set years back can't
  be served one.
- **The bound is the build time, with no grace (N = 0 days).** It's the
  latest time the app can prove has passed without asking anyone. A
  grace would accept leaves known to be out of date. The window is the
  time since the app's last update; testers update within days.
- **Not-yet-valid costs nothing:** a leaf a trusted CA signed for our host
  that starts later than the PC's clock is a real certificate; taking it
  early adds no key anyone didn't already need. So a clock behind is
  always let through (while the leaf ends after the build), including the
  first hours after a renewal on a PC whose clock is a few hours behind.
- **Intermediates and roots out of date:** a stale cross-sign of a root
  that is itself still trusted, or an antivirus's root that Windows
  trusts, is what the tester's PC most likely had. Python never checked
  revocation, so a CA certificate's end date bought little; the CAs' keys
  are the CAs'. Everything else in the path is still checked.
- **No time from the network:** a time learned over the connection (the
  server's, an HTTP `Date`) comes from whoever answers - it can't decide
  whether to trust that answer. A signed time from our server would (see
  below); it needs the protocol.
- **Alternatives not taken:** `certifi`'s roots (not bundled; it would
  ignore Windows' own roots, including an antivirus's that the learner
  chose); Windows' own verification through `truststore` (a dependency,
  and the session's asyncio path and every urllib call would change);
  turning off OpenSSL's trusted-first (tried on the live chain with the
  stale cross-sign in the store: still code 10, and no help for a wrong
  clock).
- **The update is protected by its signature, not TLS** (decision 0019):
  the feed's Ed25519 signature and the package's signed size and SHA-256.
  The update host (Cloudflare R2, Google Trust Services' chain) fails the
  same way on a wrong clock, so it takes the same path.

## What would make us reverse it

- A leaked key for one of our certificates, or Cloudflare saying one
  might be: release an app built after that certificate's end at once
  (the bound then refuses it), or tighten the rule.
- Python 3.13+ changing `_sslobj` (the chain in the log): the log loses
  the path, nothing else; `tests/test_tls.py` shows it.
- OpenSSL changing `X509_V_FLAG_NO_CHECK_TIME`: the tests fail.

## How we'd reverse it

Drop the try again in `tls.urlopen` and the session's `_connect` (two
call sites) and failures on dates are refused as before; the stamp's
`built` can stay. A signed time from our server (an Ed25519-signed
timestamp, like the feed's) would replace the build time as the floor and
give an upper bound too - a protocol change, proposed in 313's report.
