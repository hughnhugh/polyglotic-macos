"""Releases: the app's version, update channel and feature flags.

Owns the rules: which channel to follow (win-x64-alpha, win-x64-beta,
win-x64-stable), when an update applies (at the next start, never during a
capture; forced only when the server says "update required"), and the
feature flags received in `welcome`, with the last values kept for when
the app is offline. The updater itself (Velopack) is infrastructure,
outside core, behind `ports.updates.Updater`.

- `updates`: when to look for, download and apply an update; which channel
  to follow (decision 0017).
- `notes`: the release notes the app carries, and which of them show after
  an update - once per version (decision 0137).
"""
