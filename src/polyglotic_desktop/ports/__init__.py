"""The interfaces core needs from outside (decision 0008).

Each port is a small `typing.Protocol` plus the plain value types that
cross it, named for what core needs rather than for any technology:
- `capture` - `AppList` and `AudioCapture`, implemented per OS in `platform`;
- `mic_bleed` - `MicBleedCheck`, implemented in `platform`;
- `dictionary` - `DictionaryFile`, one dictionary's entries on disk,
  implemented in `adapters`;
- `learning` - `LearningStore`, the learner's own learning data on this
  PC, implemented in `adapters`;
- `credentials` - `CredentialStore`, the install id and device token,
  implemented in `adapters` (Windows Credential Manager);
- `settings` - `SettingsStore`, the user's settings, implemented in
  `adapters` (a JSON file);
- `outbox` - `Outbox`, what waits on the PC to be sent to the server, and
  `consent` - `ConsentStore`, the user's consent choices: both implemented
  in `adapters` (SQLite, decision 0013);
- `updates` - `Updater`, the installer's updates, implemented in
  `adapters` (Velopack, decision 0017).
`main` chooses an implementation and hands it to core.

Ports sit below core: core imports ports; ports import nothing from this
package and no infrastructure library (import-linter checks).
"""
