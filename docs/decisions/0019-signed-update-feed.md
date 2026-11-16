# 0019 The signed update feed: Ed25519, checked by the app before Velopack reads it - built, switched off

- **Status:** accepted (built; **on since 0.1.1, 2026-11-11**: `main.FEED_KEYS` holds the user's key, polyglotic-hq DECISIONS.md #97);
  what is signed and when - the feed as served, with its channel - replaced
  by [0020](0020-feed-signed-as-served.md)
- **Date:** 2026-11-05
- **Decided by:** the design - project 032 (section 2, option B),
  recommended to the user for before the beta (DECISIONS.md #13, waiting
  for the user's yes). Built ahead, switched off, by project 035 (D5) on
  2026-11-05. Claude reviews it with the pull request. **Switching it on is
  the user's decision #13.**

## Situation

Velopack checks each package's size and SHA-256 against the feed, but
nothing checks the feed: whoever can write the update storage, change the
domain's DNS or misuse the upload token can serve every tester other code
(project 032, P9-P11). Authenticode signing costs money and doesn't check
the feed either; Velopack accepts a local folder as its source, so the app
can check the feed itself.

## Decision

- **CI signs, the app checks.** The release workflow signs
  `releases.<channel>.json`'s exact bytes with an Ed25519 key held only as
  the `release` environment's secret `FEED_SIGNING_KEY`
  (`tools/package/sign_feed.py`), and uploads `releases.<channel>.json.sig`
  (base64) beside it.
- **The app** (`adapters/signed_feed.py`), with the public keys built in
  (`main.FEED_KEYS`): fetches the feed and signature over HTTPS; refuses
  the feed unless a built-in key signed it; takes the newest full package
  (as Velopack would), refusing a file name that isn't a plain name;
  streams it to disk and refuses it unless its size and SHA-256 are the
  signed feed's; writes the signed feed beside it, in
  `<install folder>\verified-feed\<channel>\`; and gives Velopack that
  folder, with deltas off. A refused feed leaves no new feed there:
  updates stop, nothing installs.
- **Off until switched on:** `FEED_KEYS = ()` - Velopack reads the feed
  directly (the alpha). A build-time constant, not a runtime flag: a
  server-sent flag that could turn verification off would defeat it.
  Switching on: generate a key pair (`python -m tools.package.sign_feed
  generate`), the private key into the secret, the public key into
  `FEED_KEYS` by a pull request, released **after** the first signed feed
  is published (an app that requires a signature before one exists can't
  update).
- **Key change:** two public keys may be built in; a release adds the new
  one, the workflow then signs with the new key, a later release drops the
  old one.
- **Library:** PyNaCl 1.6.2 (Apache-2.0; libsodium inside, ISC) for
  Ed25519 - not our own crypto. Chosen over `cryptography` 50.0.2 by size:
  measured 2026-11-05, `cryptography` added 9.9MB on disk and 3.6MB to the
  download (81.1MB zipped, over MVP.md's 80MB budget); PyNaCl's wheel is
  0.24MB. `--check-install` verifies RFC 8032's first test vector, so a
  build whose libsodium doesn't load fails.

## Why

- **Closes "steal the bucket or domain and ship code to every tester"**
  for about the cost of one library: someone holding the storage or DNS
  can now only freeze or break updates, which the daily feed check
  notices.
- **No money, no vendor:** unlike Authenticode, which is still wanted at
  the paid launch (SmartScreen) - the two complement each other.
- **Full packages only:** the app checks one file it can hash; deltas
  rebuilt by Velopack aren't re-hashed (project 032, finding 8).
- **Alternatives not taken:** TUF (python-tuf) - complete (rollback,
  freeze, key thresholds) but heavy for one publisher; minisign or
  signify - the same Ed25519 idea with another file format and a tool to
  ship.

## What would make us reverse it

- Full packages (~77MB) on every update annoying testers: sign each delta
  too, and check them the same way.
- A second publisher, or keys held offline: TUF's roles and thresholds.
- Velopack gaining its own feed signatures: use them instead.
- **Channel switches becoming routine** (added 2026-11-06, from
  polyglotic-hq project 066's security pass, Low 6). The signature has no
  expiry and no counter, so whoever holds the update storage can serve
  an *old*, genuinely signed feed. Usually that only freezes updates: the
  app installs only a newer version (`signed_feed._newer`), and
  `min_app_version` and the daily feed check catch a freeze. But when the
  server moves an app to another channel (`welcome.channel`), the app
  takes that channel's newest full package whatever its version
  (`refresh(..., switching=True)`) and Velopack installs it with
  `AllowVersionDowngrade` (`core/releases/updates.py`, `check_for`) - so
  a stale feed could hand a switching app any older release of that
  channel. Accepted while switches are rare: it needs the storage *and*
  a switch the server ordered. If they become routine, add an expiry or
  a counter to what is signed (TUF's "timestamp" role) and refuse a feed
  older than the last one seen.

## How we'd reverse it

`FEED_KEYS = ()` turns it off; deleting `adapters/signed_feed.py`, the
three lines in `VelopackUpdater` and the workflow's signing step removes
it - an hour.
