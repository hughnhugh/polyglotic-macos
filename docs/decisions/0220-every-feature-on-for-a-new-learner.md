# 0220 Every feature on for a new learner; the settings file records what was changed

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user asked for it (polyglotic-hq 478, 2026-11-18:
  "record user mic in first window is the default", "Default all
  functional features as on"); Claude chose which switches are features
  and how the file tells a choice from a default

## Situation

A new learner met the app with most of what it does turned off: their own
speech wasn't captioned, word links were off, dictation was off, a hidden
window stayed hidden when speech started, and readings went over every
word. Each was a deliberate "off until chosen" when it was built.

The settings file (`ui.settings.AppSettings.to_stored`) holds every
setting on every save, whether the learner chose it or not. So a file
can't say whether `"dictation": false` was turned off or never touched -
except for the Lab (`caption_lab` stores only what moved, 284) and the
caption mode (`caption_mode_chosen`, 176).

## Decision

- **On for a new learner:** dictation (Right Ctrl held alone), word links
  (as a caption window's word links button turns them on: with their
  lines, `LINKS_WHEN_ON`), a hidden window shown again when its app's
  speech starts (`show_hidden_on_speech`), and readings only over the
  words past what the learner knows (`reading_past`).
- **The first caption window shows my speech** (`StoredWindows.first_window`,
  `for_new`): the first window of something the learner captions on a PC
  where no window is kept but Home's sample's and Use as my default isn't
  chosen (0217's set-up, which since 2026-11-18 asks in every window that
  opens until it is). Later windows' set-ups show their own switch, off. The set-up shows its switch, on, with a line saying what it
  sends. It goes with the set-up: only where `main` offers it
  (`CaptionWindows(offer_set_up=True)`), so the UI lab's and the tests'
  windows start as before. The sample's window is a trial: it neither asks the set-up nor
  counts as the first, nor shows my speech.
- **The OS's leave to hear the mic is asked then** (`ports.system.MicPermission`;
  a Mac's `platform.macos.mic_permission`, AVFoundation's
  `requestAccessForMediaType:`; Windows asks none). `main.MicAsked` turns
  "Caption my own speech" on only with it: never asked, after macOS's
  question is answered yes; refused, then or before, every window's switch
  goes off and Home and the windows say why and where to allow it.
- **Reset to defaults** in Look goes back to the new learner's look
  (`LookView(first=...)`, `main`'s `caption_look(AppSettings())`), not the
  plain `CaptionLook()` the UI lab and the tests use.
- **Existing users keep what they have.** A file from 0.1.7 or before
  holds every key, so each switch it holds counts as chosen and stays.
- **From now on the file records what was changed** (`AppSettings.changed`,
  every setting `Settings.update` changed, by name). A switch in
  `FOLLOW_DEFAULT` that isn't in the record takes the default of the
  version running, so the next change of default reaches whoever never
  touched it. A file without the record counts every valid key it holds as
  changed.
- **The live-update interval follows the default too** (polyglotic-hq 494,
  DECISIONS.md #211: 1.0 s, from 1.5 s; put on this record by 506 rather
  than a key of its own). Every version before the record saved 1.5 s
  whether chosen or not (`_mode_from_interval` reads it the same way), so
  a file without the record holding 1.5 s doesn't count it as changed: it
  moves to 1.0 s once, and any other interval stays.

Left off, and why (polyglotic-hq 478's report has the whole table): which
apps are captioned (the learner's choice; nothing is captured until then,
DECISIONS.md #25 - replaced by 0225: everything the PC plays is on for a
new learner), everything else beside one app, consent (usage
statistics, crash reports, word counts: opt-in, topic 3), diagnostics
(each caption's delay), a spelling variant (Australian), start with
Windows (asked after a good session), joined windows, and the Lab's
alternatives (own speech's tint and bar beside its place on the right,
the learning load in place of the new-word marks, the new layout and its
choices).

## Why

- The user asked for features on, and the mic in the first window, on
  2026-11-18.
- Recording what changed is the only way a default can change later
  without flipping someone's choice; the Lab already works this way.
- Asking the Mac's permission up front, rather than opening the mic and
  waiting ten seconds of silence (`capture.SilenceWatch`), lets a refusal
  turn the switch off at once and say so.

## What would make us reverse it, and how

- **Testers find a default intrusive** (dictation catching Right Ctrl in a
  game, a hidden window coming back): change its default in
  `AppSettings`. Learners who never touched it since 0.1.8 follow; those
  who did keep theirs.
- **The record grows or misleads** (a setting the app changes for the
  learner counted as their choice): take that name out in `with_changed`,
  or stop recording and drop `changed` - older versions ignore it, and
  files keep their values as before.
- **The first window's mic is unwanted:** `for_new`'s `first` rule goes;
  the set-up's row stays as the window's switch.
