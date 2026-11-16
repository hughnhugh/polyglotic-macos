# 0122 Dictionary packs arrive by a signed list on the update storage, downloaded when a language is added

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user chose delivery A, packs downloaded when wanted
  (polyglotic-hq DECISIONS.md #125, 2026-11-14: "Yes go with A, 330mb is
  not outrageous too can be a fallback option"). The design below is
  Claude's, for polyglotic-hq project 327; reversible. Builds on decisions
  0019 and 0020 (the signed feed), 0035 (basic packs) and 0089 (packs
  kept with the learner's data).

## Situation

No dictionary pack reached an installed copy (298): nothing downloaded
them, and only the developer switch `--basic-dictionaries` opened them.
Russian's pack is about 62 MB per meanings language; Spanish's about 30;
Japanese's 11 plus Sudachi's 110 MB word split. Putting all of them in
the installer adds about 330 MB that most learners never use. The update
storage (`updates.polyglotic.io`, an R2 bucket behind Cloudflare) and the
app's check of what it serves (an Ed25519 key built into the app) already
exist.

## Decision

**Where.** On the update storage, under `packs/`:
- `packs/v1/list.signed` - the signature (a line of base64), then the
  list, in **one file**: a publish replaces both at once, so no app ever
  reads a new signature beside an old list (two files uploaded one after
  the other left a gap a refresh could fall into). `v1` is the list's
  own format: a list an older app can't read goes to `packs/v2/`, and
  `v1` stays for the apps that read it.
- `packs/files/<dictionary>-<meanings>-<version>.sqlite.gz` - one name
  per version, never replaced, so a download carried on from is always
  the same file, and a cache can't serve a mix of two. Gzipped: Russian's
  62.4 MB file comes down as 13.3 MB (measured 2026-11-14), unpacked on
  this PC. Every app that reads the list unpacks, so no uncompressed copy
  is ever needed for an older one.

No new bucket, domain or certificate: the same storage, TLS and
Cloudflare as the updates.

**The list** carries a **serial**, one more at every publish, and names,
for each language and meanings language, every version published: the file, its size and SHA-256 as installed, the
download's (gzipped) size and SHA-256, its version (dotted numbers,
`2026.11.14`), the file's format (`sqlite_dictionary.FORMAT`),
the word split it needs (`spaced`: letters and simplemma; `japanese`:
Sudachi), the oldest app that reads it (`min_app`), its licence, a one-line
credit and the credits in full (written beside the file on this PC, as
CC BY-SA asks). `core.lexicon.packs` reads it.

**Old apps are never offered a pack they can't read.** The app takes the
newest version whose format it reads, whose word split it has, and whose
`min_app` it meets (`best_offer`); when a new format comes, the last
version in the old one stays listed for the apps that read only that.
With only unreadable versions, the app says a newer Polyglotic reads it
(`needs_newer_app`) and offers nothing. A pack that adds a table an older
app ignores (as `form_readings` did) keeps its format; only a change an
older app would misread raises it.

**Trust.** The list is signed by the update feed's key (decision 0019),
checked against `main.FEED_KEYS` - one trust path, not two. What is
signed is `Polyglotic dictionary packs 1\n` and the list's exact bytes,
so a feed's signature can't pass for a list's or the other way round.
Each download is checked whole against the list's size and SHA-256
before it's unpacked, the unpacked file against its own before anything
opens it, then opened as the language, tier, meanings and version the
list says. Someone holding the storage or the domain can stop packs
arriving, never change one.

**An old list served again.** The app keeps the last list it accepted
and refuses one with a lower serial, so an old, genuinely signed list
can't hide a newer pack; and it never replaces a pack on this PC with an
older version, whatever a list says. A PC that has never read a list
can't tell an old one from the newest: what it offers is still a pack we
signed, checked whole - an older dictionary, not another one. (The update
feed has the same limit, decision 0019.)

**Which hosts learn the PC's address.** The list and every download come
over `https://` from the list's own host; a redirect elsewhere, or off
`https`, is refused before it's followed (`connection.tls`'s
`same_host`). The developer switches `--packs-from` (a stand-in storage,
`https://` or a loopback `http://`) and `--packs-key` (a key it may be
signed with, beside the built-in ones) work only from source: an
installed copy ignores both and says so in its log, so a shortcut can't
point it at another host or make it trust another key.

**What the learner sees** (Learning, and the step where a language is
added): the language's dictionary with its size and a Download button;
while it downloads, a bar and a line saying what it is doing - checking
the list, downloading 12 of 48 MB, checking the file, opening it - and
for each way it can stand still: waiting for a connection, paused on a
metered connection (Download anyway), trying again in N seconds (try 2 of
5), no room (how much it needs), refused (why). Cancel and Retry. A
download that makes no progress for 30 seconds says so and is tried again.
Home says once when a download finishes or fails if the learner has left
Learning. The language works without lookups meanwhile, and its lookups
start at once when the pack opens - no restart. Learning lists each pack
on this PC with its version and size, and Remove; stopping a language
offers to remove its pack.

**Only what the app knows** (polyglotic-hq 330, 2026-11-14 - a release
may come before any list is published): no line promises a download the
app can't know exists. With none to be had - not in the list held, or
none published at all (the storage answers 404 for the list, as before
the first upload) - a language's card says "No dictionary yet" and what
works without one, and its row "isn't ready yet" with Retry, which finds
one published since. With no list read yet, or one that couldn't be
read (offline, a server error, refused), the card promises nothing
either way and its row says it's checking, or couldn't check. "Learn
another language" says the same from the list held.

**Bandwidth.** A download the learner asks for runs at once, one at a
time, unthrottled; on a connection Windows calls metered it asks first.
A newer version of a pack on this PC is fetched in the background only on
a connection Windows doesn't call metered, and the list is checked for one
at most once a day (first two minutes after the start, never before the
first window). On a metered connection the update waits, and Learning
says so with Get it now. Swapped in when checked (the lookup's dictionary
is replaced on the interface thread between lookups; the old file is
closed, then deleted), saved words and statuses carried by entry ID
(decision 0089).

**On this PC.** Packs are kept with the learner's data (decision 0089),
`%APPDATA%\Polyglotic\dictionaries`, under their published names, so an
update of the app keeps them. A download is a `.gz.part` file beside them,
carried on from with a `Range` request, as the update's is (polyglotic-hq
302), then unpacked to `.part` and renamed. Free space for both is checked
first. What's on this PC is
read from each file's own `info` (language, meanings, version): no second
record to drift from it.

**Privacy.** Fetching a pack tells Cloudflare, which serves the storage,
this PC's IP address and the file's name - and so which language is
wanted. We keep no record of who downloaded what; the app sends nothing
else. The privacy notice says Cloudflare serves the app's updates; a line
saying it also serves dictionaries, and processes the IP address to
deliver them, is the user's call (polyglotic-hq 327's report).

## Why

- **One storage and one key:** nothing new to buy, secure or rotate; the
  feed's checks are already in every installed copy.
- **Immutable file names** make resuming and caching safe; a version's
  file never changes under a download.
- **Capabilities, not only versions:** an app knows which formats and word
  splits it has; `min_app` is the last resort for anything else.
- **Not taken:** a bucket of its own (a second set of credentials and DNS
  for no gain); TUF (decision 0019's reasons); Velopack for packs (it
  installs apps, and would put packs in the install folder an update
  replaces); every pack in the installer (B, kept as a build switch, off
  by default: decision 0124).

## What would make us reverse it

- Packs in the hundreds of MB, or many languages: a CDN with regional
  storage (SCALING.md's regions), or deltas between pack versions.
- The update feed's key moving offline or to TUF: the list follows it.
- Learners on roaming profiles (decision 0089's reversal).

## How we'd reverse it

`main.PACKS` is the one address; `adapters.pack_list` and
`adapters.pack_downloads` the only readers. Moving the storage is a new
address in a release; a new signing scheme is a new prefix and a new
`packs/v2/`. Turning delivery off is leaving the list unpublished: the app
says no dictionary is ready yet, as before.
