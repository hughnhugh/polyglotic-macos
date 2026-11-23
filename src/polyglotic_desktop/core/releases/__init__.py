"""Releases: the app's version, update channel and feature flags.

Owns the rules: which channel to follow (alpha, beta or stable, of this
platform's builds: win-x64-*, macos-arm64-*, linux-x64-*), when an update applies (at the next start, never during a
capture; forced only when the server says "update required"), and the
feature flags received in `welcome`, with the last values kept for when
the app is offline. The updater itself (Velopack) is infrastructure,
outside core, behind `ports.updates.Updater`.

- `updates`: when to look for, download and apply an update; which channel
  to follow (decision 0017).
- `notes`: the release notes the app carries, and which of them show after
  an update - once per version (decision 0137).
- `flags`: the app's feature flags, each with an owner and an expiry - the
  one way code reads one, from the edges (decision 0263).
"""
