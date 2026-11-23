# 0264 Presets hold the caption settings, and every change is saved into the one in use

- **Status:** accepted; its saving at once replaced by [0283](0283-a-preset-changes-only-when-its-saved.md) (polyglotic-hq 587)
- **Date:** 2026-11-20
- **Decided by:** the user asked for presets (polyglotic-hq 556's brief, 2026-11-20 ~20:00: "These user presets should save everytime they are customised within that preset"); Claude answered the design's questions the same evening (polyglotic-hq 556's DESIGN.md, section 9), for the user to review

## Situation

The user wants presets for use cases: Conversation, Video / film / TV,
Learning and the learner's own. Each one is a whole way of using captions,
picked from the caption window's bar and edited in Settings, and anything
changed while one is chosen is saved into it at once. About thirty caption
settings are involved (what shows, word help, the look, timing, the
windows), read today by the caption windows, Settings, the server's
languages and the session summary. All of them read `AppSettings`.

## Decision

- **A preset is data:** a key, the values it names (`ui.use_presets.BUILT_IN`), and the learner's own changes to it (`AppSettings.preset_values`).
  - It holds the settings in `PRESET_SETTINGS`; everything else is the same in every preset.
  - Every preset takes what it doesn't name from Everyday (the app's defaults, plus the learner's changes made there).
- **The chosen preset's values are the flat settings, as before.** Picking one writes its values over them (`chosen`). So nothing that reads a setting knows about presets, and an older version reads the file as it always did.
- **Saving:** `Settings.change` (and `update`, through it) works out the chosen preset's own changes again on every change (`saved_into`): what differs from what the preset would have.
- **Reading the file:** the flat values win for the chosen preset, so a change an older version made after a rollback is kept.
- **The migration:** a file from before presets that changed any preset setting becomes Custom, chosen and kept whole. One that changed none, or a new install, starts on Everyday.
- **No new display code.** Video's subtitle place uses the windows' existing placement (`views.placement.subtitle_slot`, `CaptionWindow.take_place`). Original only uses each window's existing Original only, with its language kept aside (`StoredWindows.kept_languages`). Smoothness and centred lines come from 552's settings when they land: Video names them, one line each.
- **Enforced by:** `tests/ui/test_use_presets.py`, and `test_every_preset_setting_is_a_setting`, which fails if `BUILT_IN` names a value a setting doesn't take.

## Why

- **Presets as flat values plus stored differences** kept every reader of the settings unchanged. The alternative, every reader asking a "current preset" object, would have touched the caption windows, Settings, the session and the summary.
- **Saving the differences, not snapshots,** lets a later version's new default reach a preset that never changed that setting (decision 0220's `FOLLOW_DEFAULT` keeps working).
- **Showing what was said, readings, word links and my speech as options inside a preset,** not as presets of their own, lets them combine with a use (Video with the original only) without the list multiplying.

## What would make us reverse it

- Presets need settings that aren't `AppSettings` fields: per-window ones such as each window's language, or the Lab's.
- Learners find "every change saves into the preset" surprising. The usage data (`preset_*` in the session summary) and their reports would show it.

## How we'd reverse it

- **Per-window settings:** they get a field each, as Video's place did (`subtitles`, `subtitle_size`, `subtitle_width`). Small.
- **Explicit saving instead of saving at once:** one change. `Settings.change` stops calling `saved_into`, and a "Save in this preset" button calls it.
- **Dropping presets altogether:** the flat settings are already what the app reads. Delete `use_presets`, the four fields and the two cards. The file keeps the keys it doesn't know.
