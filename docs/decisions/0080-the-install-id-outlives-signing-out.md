# 0080 The install id outlives signing out, and each server keeps its own sign-in

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** the user, 2026-11-11 (polyglotic-hq DECISIONS #115):
  "reinstallation / updating should just reuse the first invite code. I
  shouldn't need new invite codes when using the same machine", and "can
  you just make the invite code work unlimited times on the same machine
  somehow? or make updates not require resigning in". Where the id is kept
  and the per-server entry are polyglotic-hq project 288's; Claude reviews
  them with the pull request.

## Situation

The server now signs an install in again with the code it was used with
(server decision 0057) - it knows the install by the random install id the
app sends. But the app kept the id only as the user name of its device
token's Credential Manager entry, and deleted the entry when signing out or
when the server refused the token: the next sign-in came from a new id, a
"new PC". And every copy of the app read one entry, `Polyglotic/device`,
whatever server it talked to: on 2026-11-11 the user's PC held a test
server's token there (from running from source), the installed copy sent
it to the live server, the live server refused it, and the installed copy
asked for a code.

## Decision

- **Signing out forgets the token only:** `CredentialStore.forget()` keeps
  the entry with the install id and an empty secret; `install_id()` reads
  it signed in or not; `redeem` sends that id, a new one only on a PC that
  has never signed in. The same for a token the server refused.
- **Where it's kept and what clears it:** Windows Credential Manager, per
  Windows user, on this PC only (`CRED_PERSIST_LOCAL_MACHINE`: not roamed).
  The installer never touches it, so updating, reinstalling and
  uninstalling keep it. Deleting the entry in Control Panel > Credential
  Manager, deleting the Windows user, or resetting Windows clears it - then
  the PC is a new install to the server. Never a hardware or Windows
  identifier: the id is the random UUID the app made at its first sign-in.
- **Signing out still starts the next sign-in afresh** in the exchange:
  a note (`signed_out`) makes the next session a new install's - its
  consent sent again, learning synced from the start, nothing from before
  sent - as a new id used to.
- **Each server its own entry:** `Polyglotic/device` for the live server
  (`main.SERVER`), as every installed copy has it; `Polyglotic/device@HOST:PORT`
  for any other `--server`; `--credentials` still names one outright.
- The developer harness's `sign-out` deletes the whole entry, and the
  tests' entries are deleted with `delete()`: a trial leaves nothing behind.
- Enforced by tests: `test_windows_credentials.py` (the real Credential
  Manager, under a test entry), `test_sign_in.py`, `test_session.py`,
  `test_exchange.py`, `test_credentials_entry.py`.

## Why

- It is what lets the user's "the same code on the same machine" work
  after signing out, a refused token or a reinstall.
- **Credential Manager rather than a file in the data folder:** the entry
  is there already, outlives the data folder being deleted, and isn't
  roamed to another PC with a roaming profile, where a file in
  `%APPDATA%` would be (the same id on two PCs would be "one PC" to the
  server). One entry, not a second one for the id: an app before 288
  reads an empty secret as signed out, so nothing breaks either way.
- **Not a hardware id** (MachineGuid, a disk or network serial): the
  privacy notice promises a random id. The cost: a second Windows user on
  the same PC is "another PC".
- **A per-server entry** so a sign-in to a test server never replaces the
  live one, and the other way round. Installed copies keep their entry's
  name, so nobody is signed out by the change.

## What would make us reverse it

- Testers sharing a PC under one Windows user and wanting separate
  accounts: signing out, the next person's own code works (it's another
  account), but the PC is one install to the server.
- Accounts by email (the beta's): the install id stops mattering for
  signing in.

## How we'd reverse it

`forget()` deletes the entry again (it was one call); `redeem` keeps
sending `install_id()`, which then returns None after signing out. The
exchange's `signed_out` note is harmless either way. The per-server entry
is `main.credentials_entry`; returning `named` alone puts every server back
in one entry.
