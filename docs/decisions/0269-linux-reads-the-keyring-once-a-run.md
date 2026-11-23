# 0269 Linux reads the keyring once a run, and answers from that

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 561), from 550's finding that a
  locked keyring can hold the interface up to 120 s; reversible inside
  `platform/linux/secret_service.py`.

## Situation

On Linux the device token is in the desktop's keyring (the Secret Service,
decision 0258). A keyring can be locked - after an automatic sign-in to
the desktop, GNOME's login keyring is - and then each read shows the
keyring's own password box and waits for the learner's answer, up to
`PROMPT_SEC` (120 s).

The app asks whether it's signed in many times, most of them on its
interface thread: at the start (the first run's code, whether this PC has
signed in before), Home's state, the account menu, feedback, dictation,
the sign-in dialog. Each question read the keyring again. With the box
dismissed or left unanswered, every question showed the box again and held
the interface up to 120 s - after Home was on screen too.

## Decision

`SecretServiceStore` reads the keyring once a run: the first question
(the start's, before the window is built) reads it, one reader at a time,
and every later question, on any thread, is answered from what that read
found. The app's own saves, sign-outs and deletes change what's kept as
they change the keyring. A read the keyring refused (its box dismissed or
unanswered) is kept as "not signed in" for the run; signing in writes the
token, which asks the keyring again.

So a locked keyring shows its box at most once a run, at the start, and
Home never waits on the keyring once it's shown, except for what the
learner does to it (signing in or out writes, which a locked keyring may
ask about).

Tested with fakes on every OS (one read for many questions, a dismissed
box not shown again, two threads asking at once), and on GitHub's Ubuntu
runner with gnome-keyring's login collection locked and nobody to answer:
the first question comes back within the box's time, the next ones at
once (`linux.yml`, "A locked keyring").

## Why

- The token changes only through the app itself (one copy per user and
  data folder), so reading it once loses nothing.
- Windows and the Mac read their stores each time because those answer at
  once, unlocked whenever the learner is signed in to the PC.
- Not chosen: reading on a thread of its own while the start goes on
  "signed in, waiting for the keyring". The app has no such state - Home,
  the first run and the session decide on "signed in or not" - and adding
  one touches `main`'s start and the session for a case a learner sees
  once. The start still waits for the box, once, before the window: on
  GNOME the box is system-modal, so nothing else could be used meanwhile.

## What would make us reverse it

- A learner who dismisses the box by mistake has to restart the app (or
  sign in again) to be read again - if testers hit that, offer "Try the
  keyring again" from Home's sign-in notice.
- KDE, where the box is an ordinary window: if learners leave it behind a
  game and the start waits, read on a thread of its own and add the
  "waiting for the keyring" state.

## How we'd reverse it

Remove `_read`'s memory in `SecretServiceStore` (about 15 lines); the
keyring is then read at each question, as before.
