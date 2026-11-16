# 0023 Learning done after a deletion counts as after it, whatever the PC's clock

- **Status:** accepted
- **Date:** 2026-11-05
- **Decided by:** polyglotic-hq project 061 (brief item 1, from project
  059's deep review, Low 3); Claude reviews

## Situation

A deletion of the learning data reaches every device (polyglotic-server
decision 0020): the server numbers it and records its time **by the
server's clock**, drops learning events dated at or before it, and every
device drops what waits from before it. But a learning event's time is
**the PC's clock**. So:

- On a PC whose clock is a minute behind the server's, a word saved in
  the minute after deleting is stamped before the deletion. The server
  drops it (and still answers `received`, so nothing retries), and once
  the deletion is applied here, so does the app. The word stays on this
  PC but never reaches the account's other devices.
- On the PC that deleted, the request can wait offline. The server
  records the deletion when the request arrives, so everything done
  between pressing Delete and reconnecting is "before" it and dropped -
  however good the clock.
- The PC that deleted learned the deletion's number and time only at its
  next session if a session was already open (it didn't ask for
  `learning_sync`).

## Decision

**"After the deletion" is judged by this PC's own clock**, from a moment
it knows is after the deletion:
- on the PC that deleted, **when it asked** (pressing Delete);
- on any other, **when it applied the deletion** (a `learning_state`
  naming one it hadn't seen).

A learning event made after that moment is sent **stamped just after the
deletion** if this PC's clock put it at or before the deletion - each a
millisecond after the last one raised (protocol times are to the
millisecond), so the latest still wins on the server. One stamped at or
before both the deletion and that moment (a status republished with its
old time after a dictionary update, say) is from before: dropped, as
before.

**The PC that deleted holds its learning events from the request until
it knows the deletion's time**, and asks for `learning_sync` as soon as
the server answers `learning_deleted`, so it knows within seconds when
online. A request that waited offline then loses nothing done meanwhile.
What waits is kept on disk (outbox notes `learning_delete_asked`,
`learning_after_deletion`), so closing the app in between changes
nothing. A server that names no deletion (one from before polyglotic-
server #99) releases what was held as it is.

No protocol change: the server's rule is unchanged; the app chooses the
time it sends. In `connection/exchange.py` (`DataExchange`); tested in
`tests/test_exchange.py`.

## Why

- The privacy promise needs "from before the deletion" to stay dropped;
  the learner needs what they did after it kept. Only the device knows
  which of its own events came after its own request or after it heard
  of the deletion - by comparing its clock with itself, which a slow
  clock doesn't disturb.
- Not taken: **trusting the app's clock for the deletion's time** (the
  request carrying the app's time) - a protocol change, and a wrong
  clock would then decide what the server keeps for every device.
- Not taken: **the server accepting anything from the deleting install
  after the deletion** - a migration and a second rule on the server, and
  it would still lose events on other PCs right after they apply it.
- Not taken: **accept and document only** (059's other option) - the
  offline case loses a whole stretch of the learner's work, not seconds.

## What's left

- **Another device's events made after the deletion but before it heard
  of it**, stamped before it by a clock behind the server's, are still
  dropped - by the server, and by that device when it applies the
  deletion. It can't tell them from events made before. Seconds or
  minutes of a slow clock, on a device that hadn't synced.
- The reverse, as before (decision 0020): a device whose clock is
  *ahead* can send something made just before the deletion stamped after
  it, and it is kept.
- If another device deletes while this PC's own request waits, this PC
  takes the newest deletion it hears of after its request is answered as
  its own: what it did after pressing Delete is kept past both.
- Exposure counts are by UTC day and unchanged: the deletion's whole day
  is dropped, as decision 0020 says.

## What would make us reverse it

- Data the learner deleted coming back - a raised stamp on something
  that was in fact from before. It would show as entries on the server
  dated a few milliseconds after a deletion.
- A protocol version in which the server stamps events itself, or a
  deletion names the device's own time: then this rule goes.

## How we'd reverse it

`DataExchange._stamp`, `_raised`, `_release` and the hold in `_next` -
one module; without them, events are sent with their own stamps and
judged by the deletion's time alone, as before 061. The two outbox
notes would be left unread.
