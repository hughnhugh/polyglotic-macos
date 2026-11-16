# 0102 A consent choice is dated after the one it replaces, and goes again at most once a day

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, on polyglotic-hq project 311's brief (the user, 2026-11-14 ~02:55: "also investigate this error ... consent_missing"); a reversible technical choice, reviewed with the pull request

## Situation

The server takes an install's consent choice with the latest `at` as its
latest, and the protocol's times are to the millisecond. An alpha tester's
first run makes two choices in a row: the boxes they ticked, then
"diagnostics on for alpha testers" (`main.diagnostics_on_for_testers`).
On Windows, Python 3.12's clock moves in ticks of about 15.6 ms, and on one
tester's PC both choices got the same millisecond. The server kept the
first, "usage statistics off", and refused every usage batch
(`consent_missing`). The app answered each refusal by sending its choice
again - every session, under a new id, at the same time: still a tie. By
2026-11-14 the server held 223 choices for that install, two more each
sync session (polyglotic-hq 311).

## Decision

- **A new choice is dated at least a millisecond after the one it
  replaces, whatever the clock says** (`exchange._dated_after`): the
  clock's time if that is past the replaced choice's millisecond, else
  that millisecond plus one.
- **`consent_missing` sends the choice again only if it allows what was
  refused, and at most once in 24 hours for the install**, by this PC's
  clock (a note in the outbox, `consent_sent_again`; a note ahead of the
  clock - the clock set back - doesn't hold it back). One log line each
  time it goes. What was refused is still held back and sent once more
  after the server has the consent, as before.
- A new install's own resend (`_new_install`) is unchanged.
- Tested in `tests/test_exchange.py` (the tie, the clock set back, the
  affected PC's sessions against the server's rule before 311).

## Why

- Ties come from the clock, not from what the user did: the second
  choice was made after the first. Dating it after the first says so, in
  the millisecond the protocol can carry; the server (its decision 0062)
  now also takes the one received last on a tie, but an app shouldn't
  rely on that.
- **Not re-dating choices already made.** A PC that holds a tie from an
  older app keeps it; the server's fix and its clean-up put that right
  without the app changing a record of when the user chose.
- Once a day rather than once a session: a server that keeps refusing
  after the choice went again won't be convinced by the same choice an
  hour later, and every resend was a row on the server. Once a day still
  repairs a server whose record was lost (a restore) on the first
  refusal.

## What would make us reverse it

A server that needs the choice again more often (it loses records within
a day), or a need to date choices by the server's clock instead.

## How we'd reverse it

`_dated_after` back to the clock's time, and `_may_send_again` returning
True: a few lines in `connection/exchange.py`; the note can be left or
removed.

## Known limit

A choice dated far ahead by a wrong clock pushes every later choice past
it. The server refuses a choice more than a day ahead, so those wait on
the PC until the clock passes them - safe (the PC itself follows the
latest choice at once), but the server's record lags until then.
