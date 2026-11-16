# 0017 Updates: Velopack behind a port; core decides when; applied at the next start

- **Status:** accepted; amended by [0090](0090-a-downloaded-update-is-offered-with-restart-now.md) (a downloaded update offered, with Restart now)
- **Date:** 2026-11-05
- **Decided by:** the rules - updates download quietly and apply at the
  next start, never during a capture; forced only by "update required";
  testers may follow another channel - the user, 2026-11-04 (polyglotic-hq
  ENGINEERING.md, "Releases"; project 010). `AllowVersionDowngrade` only in
  a change of channel: project 032's checklist for D5 (item 9). The
  mechanism: project 035 (D5), 2026-11-05. Claude reviews it with the pull
  request.

## Situation

The installer (Velopack 1.2.161) installs the app and updates it from a
feed: `releases.<channel>.json` and its packages at `https://updates.<our
domain>/`. Its Python library offers `App().run()` (the installer's hooks,
and applying a downloaded update at start), and an `UpdateManager` (check,
download, apply). The server's `welcome` names the channel to follow, and
`update_required` (close 4001) means it refuses this version.

## Decision

- **`velopack.App().run()` is the first line of `main()`**
  (`adapters.velopack_updates.run_installer_hooks`): the installer's hooks
  exit there, and a downloaded newer version is applied there, by
  restarting into it - "the next start".
- **The rules are in core** (`core/releases/updates.py`, `Updates`), and
  the installer behind a port (`ports/updates.py`, `Updater`), implemented
  by `adapters/velopack_updates.py`:
  - look at start - before the interface is built, so a release that fails
    later in start-up can still be replaced - and every 6 hours; download
    quietly; nothing restarts the app while it runs;
  - `update_required` goes straight to the updater: download and restart
    now (no captions can come until it's updated, so nothing is
    interrupted that was working);
  - follow `welcome.channel` when it's one of the three channels the app
    knows; only then may the release be lower (`AllowVersionDowngrade`).
    Velopack doesn't apply a lower version at start, so a downgrade
    applies as the app exits (silently, no restart);
  - a channel the app doesn't know is ignored (protocol.md's rule 1).
- **`main.BackgroundUpdates`** runs those rules on one thread of their own,
  one call at a time; a failure - no network, no feed yet - is logged by
  its kind, never raised.
- **The feed** is `main.UPDATES`, `https://updates.polyglotic.io/`
  until the domain exists (decision 0015); `--updates` may name a folder on
  this PC instead, for trying updates. Plain `http://` is refused.
- **Each channel is packed from its own build**, so the release stamp's
  channel (decision 0015) matches the installer's.

## Why

- **Testable without an install:** the rules are tested against a fake
  updater; the adapter against a fake `UpdateManager`, and for real (run
  from source, Velopack finds no install and does nothing).
- **Swappable:** another installer (MSIX, the Store) is another adapter.
- **Safe defaults:** Velopack checks every package's size and SHA-256
  against the feed and won't downgrade unless told; we tell it only in a
  change of channel. What the feed itself can't prove - that we published
  it - is the signed feed's job (project 032, section 2; next step).
- **Alternatives not taken:** checking only at start (an app left running
  for days would never see an update); applying on quit for every update
  (Velopack's "next start" is its documented default, and quitting then
  starting at once could race the updater).

## What would make us reverse it

- Testers finding the restart at start disruptive: apply at quit instead
  (`apply_at_exit` for every update).
- Percentage rollouts or pausing a rollout: the feed comes from our server
  (project 010) - the adapter's address changes, the rules don't.
- The signed feed (DECISIONS.md #13): the adapter fetches and verifies the
  feed itself, then gives Velopack a verified local folder; the port and
  the rules stay.

## How we'd reverse it

The rules are one module; the installer one adapter; `main` wires them in a
dozen lines. Replacing Velopack is a new adapter plus the release
workflow's packing step - a few days with testing.

## Added: on a metered connection, an update waits for the learner (2026-11-15, polyglotic-hq 345)

- A look on a connection Windows calls metered (the dictionary packs'
  check, `platform.windows.network_cost`, decision 0122) finds the update
  and doesn't download it: `Updates.held`, `Found.METERED`. Home's update
  card says "Version X is available: N MB to download", why it waits, and
  offers **Download anyway** (`Updates.download_anyway`) and Later; Settings
  says it waits. The next look on a connection that isn't metered
  downloads it as before; nothing changes off a metered connection.
- The size is what Velopack would download (`velopack_updates.download_size`):
  its deltas' when deltas are allowed, this copy has the release they start
  from and there are at most `MAX_DELTAS`; else the full package. **The
  signed feed never uses deltas** (decision 0019: the app checks one full
  package it can hash), so every real update says the full package's size
  (about 90 MB at 0.1.5).
- **On the signed feed, a look checks the feed only** (`VerifiedFeed.refresh`
  with `package=False`); the package is fetched and checked into Velopack's
  folder by the download step (`fetch_package`). Before, the look fetched
  the ~90 MB package itself, so holding back Velopack's download alone
  saved nothing: 345's rehearsal on a local signed feed caught it.
- "Update required" downloads on any connection: without it there are no
  captions at all.
- Not taken: asking again during the download as the packs do (Velopack's
  download can't be paused); checking more often than every six hours for
  the connection to change (the learner can Download anyway, and the next
  start looks at once).
