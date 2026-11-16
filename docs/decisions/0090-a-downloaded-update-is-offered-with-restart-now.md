# 0090 A downloaded update is offered on Home and in the tray, with Restart now

- **Status:** accepted (amends 0017: the learner may now restart into an update)
- **Date:** 2026-11-13
- **Decided by:** the user, 2026-11-13 (polyglotic-hq journal, feedback
  3): "Updates should happen automatically and pop up to install it";
  placed in the launch order as "a prompt to install an update"
  (polyglotic-hq DECISIONS #122, B). The how is polyglotic-hq project
  299's brief: a quiet line on Home and the tray, never a window over a
  game or a call; Later asks again at the next start; never a restart by
  itself while captions or dictation run. Claude reviews it with the pull
  request.

## Situation

Decision 0017 downloads updates quietly and applies them at the next
start, and nothing restarts the app while it runs, except "update
required". Learners who keep Polyglotic in the tray for days, or start it
with Windows, ran an old version long after a new one had downloaded, and
nothing told them one was waiting. Settings' Check now said nothing at all
about what it found.

## Decision

- **Offered, never forced:** once an update has downloaded, Home shows a
  quiet card under the state: "Version X is ready. Restart to install
  it.", what's new in two lines, Restart now and Later. The tray's menu
  shows "Restart to install version X" under Open. It is never a window of
  its own and never a Windows notification, because either could come up
  over a game or a call.
- **What's new** is the release's own notes, as the feed carries them
  (Velopack's `NotesMarkdown`, from RELEASE-NOTES.md's section for the
  version: `vpk pack --releaseNotes`). It shows the first two items, each
  cut to one sentence (`core.releases.updates.whats_new`). With no notes
  in the feed, the card shows the version alone.
- **Restart now** is the only thing that restarts the app. It quits as
  Quit does, so the windows, settings and transcripts are saved. Velopack
  then applies the update once the process has gone
  (`wait_exit_then_apply_updates(restart=True)`) and starts the new
  version. The port's `apply_at_exit` gains `restart`.
- **Later** hides Home's card until the next start (`RestartOffer`). The
  looks every 6 hours don't bring it back, even for a newer version. The
  tray's line stays, because it asks nothing. The next start installs
  the update anyway (0017).
- **Settings says what the last look found** (`Found`): up to date; ready,
  with Restart now; the update server out of reach; a download that
  failed; or a copy that can't update itself. To tell those apart, the
  port names its failures (`FeedUnreachable`, `DownloadFailed`).
- "Update required" is unchanged: it still goes straight to the updater
  (0017).

## Why

- The learner decides when captions stop. A restart cuts captions and
  dictation for a few seconds, so only their click does it. A prompt
  that restarts on a timer or "when idle" could still land mid-call.
- Home and the tray are where the learner already looks. A dialog or a
  toast is what the user ruled out for games and calls.
- The notes' one source stays RELEASE-NOTES.md (polyglotic-hq RELEASING.md
  section 10). The feed carries them, so no other download is needed.
- Not taken: a modal "Update now?" dialog at start, which interrupts the
  start; and restarting by itself once captions stop, which would surprise
  someone who had just paused.

## What would make us reverse it

- Testers dismissing the card and staying on old versions for weeks. The
  sessions' app versions on the admin page show it. Then the offer may
  need to come back after a few days, or "update required" be used sooner.
- Testers finding the card noisy. It could then show only after the app
  has run a while.

## How we'd reverse it

Remove `UpdateShown`'s wiring in `main` and the card's and tray line's
widgets. The core rules (`look`, `RestartOffer`, `whats_new`) and the
port's `restart` flag can stay unused or go. That is about an hour's work.
The feed's notes cost nothing either way.
