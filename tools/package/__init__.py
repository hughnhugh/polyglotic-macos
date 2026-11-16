"""Building the app testers install (D5).

- `stamp`: the release's version from its git tag, written into the app as
  `release.json` (decision 0015).
- `build`: `python -m tools.package.build v0.1.0` packs the app with
  PyInstaller as one folder (`polyglotic.spec`, entry point `entry.py`),
  adds the dictionaries, notices and licences (`licenses/`), checks the
  result and runs its self-check (decision 0016).
- `release_notes`: a version's notes from `RELEASE-NOTES.md`, the one
  source the GitHub Release, What's new and the Discord post use (G7).
- `release_plan`: what a Release run does - release, hotfix, promotion or
  dry run - and `promote` with `pack.sh`: a build repacked for another
  channel, checked to be the same files (decision 0044).
"""
