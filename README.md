# Polyglotic desktop

The app learners install. Windows first; macOS and Linux later.

It captures one app's audio (or the whole system's) and the user's mic,
detects speech on the PC, streams the speech to
[polyglotic-server](../polyglotic-server), and shows what comes back -
captions, their translation, word links - over whatever the user is doing,
with dictionary lookup and saved words.

- **Stack:** Python 3.12, PySide6 (Qt), PyInstaller one-folder, Velopack
  for installing and updating (decided 2026-11-04).
- **Talks to the server** as `../polyglotic-server/docs/protocol.md`
  describes.
- **Built from the proof of concept** (`../../vc-translator`), brought in
  piece by piece rather than copied wholesale.
- **Plans and decisions** live in `../../polyglotic-hq` - TOPICS.md (#2
  the installed app) and MVP.md.

- **How it's organised:** [ARCHITECTURE.md](ARCHITECTURE.md); decisions in
  [docs/decisions/](docs/decisions/).

Status: created 2026-11-04. Since 2026-11-04 the layout, checks and docs
are in place (project 013); since then, capture, speech detection and the
live-update timing rules (project 016); the dictionaries (project 018); the
connection to the server, signing in and a replay source (project 022).

## Build it yourself

The app's source is public under Apache-2.0
(<https://github.com/hughnhugh/polyglotic-app>). With that copy alone you
can build it, run its tests and run it from source. The server that does
the speech recognition, translation and word links isn't public; the app
talks to ours.

You need Windows 10 or 11 (64-bit) - or a Mac with Apple silicon on macOS
14.2 or later, which is in preview - plus git and
[uv](https://docs.astral.sh/uv/), which fetches Python 3.12 itself.

```
git clone https://github.com/hughnhugh/polyglotic-app.git
cd polyglotic-app
uv sync                                     # the environment, from uv.lock
uv run python -m tools.i18n build           # the interface's translations
uv run python -m tools.dictionaries.build   # the built-in dictionaries, from their public sources
uv run pytest                               # no server, account, sound device or GPU needed
uv run python -m polyglotic_desktop.main --data build/try --credentials Polyglotic/source
```

- **Without an account:** `uv run python -m tools.app_tour build/tour`
  runs the app signed in to a stand-in server on your own machine
  (`tests/fake_server.py`) and captions the app's own sample recording
  (FLEURS, CC BY 4.0). Its captions are made up - no speech recognition -
  and it saves a picture of each window in `build/tour`.
- **With our server** (`https://api.polyglotic.io`, the default): you need
  an account. The alpha is by invitation; a waitlist opens at
  <https://polyglotic.io>. The app asks for the invite code on its first
  run. `--data` and `--credentials` keep this copy's settings and sign-in
  apart from an installed Polyglotic's. Run from source, the app tells the
  server it is the newest release `RELEASE-NOTES.md` names (decision
  0224); if it says an update is needed, this copy is older than the
  server takes - get the newest source.
- **What isn't in the public copy:** the server (`polyglotic-server`: speech, translation,
  word links, accounts - the app follows its protocol, whose examples are
  in `tests/protocol_examples/`); our planning notes, which the docs name
  as `polyglotic-hq` and `DECISIONS #N`; the CI workflows, which run on our
  own machines; and the keys that sign the update feed and the dictionary
  packs' list and upload them. So `tools.package` packs the app, but
  publishing it, and the packs the app downloads, are ours to do. The
  dictionaries and packs are built from public sources only
  (`tools/dictionaries/sources.py`).
- **Licences:** the code is Apache-2.0 ([LICENSE](LICENSE),
  [NOTICE](NOTICE)). What it's built with and the data it uses keep their
  own licences ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); the
  built dictionaries' in `build/dictionaries/CREDITS.md`) - among them
  PySide6 (Qt) under the LGPL-3.0, and `anki`, a tool the tests use, under
  the AGPL-3.0; both come from PyPI, neither is in this repository.
- **The public copy has no history of its own:** it is refreshed from
  the private repository we work in, so the rest of this README is how we
  work on it - `polyglotic-server` and `polyglotic-hq` there are our
  private repositories.

## Try it

The app from source against a server on this PC - polyglotic-server with
its stand-in models, so no GPU (every caption reads "Stand-in caption, N
seconds of audio"). Both checkouts side by side (`polyglotic-server` and
`polyglotic-desktop`), [uv](https://docs.astral.sh/uv/) installed, two
PowerShell windows.

1. **The server** - in `polyglotic-server`; leave it running:

   ```
   uv sync
   New-Item -ItemType Directory -Force data
   $env:POLYGLOTIC_DATABASE_URL = "sqlite+aiosqlite:///data/try.sqlite3"
   uv run python -m polyglotic_server.adapters.sql.migrate
   uv run polyglotic-admin invite create --cohort alpha   # prints a code once: copy it
   uv run polyglotic-server                               # http://127.0.0.1:8080
   ```

2. **The app** - in `polyglotic-desktop`:

   ```
   uv sync
   uv run python -m tools.dictionaries.build   # once: fetches the dictionary sources
   uv run python -m tools.i18n build           # the interface's translations (the tests do it too)
   uv run python -m polyglotic_desktop.main --server http://127.0.0.1:8080
   ```

   The first run asks for the language you're learning, your level, what
   to share and the invite code. It then captions what you pick on Home
   (up to 3 apps, or everything the PC plays), each app in a caption
   window of its own. Ctrl+Alt+L, P and H lock, pause and hide the caption
   windows; closing the main window keeps it in the tray (Quit is there).

To keep the try-out apart from your own copy, add `--data <a folder>
--credentials Polyglotic/try` to the app's command (its settings,
learning data and sign-in then live there). To see the first run again,
quit, delete that folder (or `%APPDATA%\Polyglotic`) and sign out on the
Account page first - an invite code works once, so make another.

Real captions need the model servers, on the GPU: polyglotic-server's
test copy with `compose.use-models.yaml` (its README, "Running it"), then
`--server http://127.0.0.1:8081`.

## Development

Needs [uv](https://docs.astral.sh/uv/) (on Windows without admin rights:
`py -3.12 -m pip install --user uv`). Then:

```
uv sync                     # dev environment in .venv, from uv.lock
uv run pre-commit install   # once per clone: checks on every commit
uv run ruff check           # lint
uv run ruff format --check  # formatting
uv run mypy                 # types
uv run python -m tools.mypy_platforms  # types as macOS and Linux see them
uv run lint-imports         # the import rules (ARCHITECTURE.md)
uv run pytest               # tests
```

To check listening without a server or the UI (Windows), the developer
harness lists the apps with sound and prints what would be sent - live
updates, finished captions, joins - with nothing written to disk:

```
uv run python -m polyglotic_desktop.harness list
uv run python -m polyglotic_desktop.harness capture --app <process id> --mic
uv run python -m polyglotic_desktop.harness capture --play <public clip.wav> --play <another.wav>
```

To try it end to end against a server - polyglotic-server's stand-in copy
on this PC, say (its README: `uv run polyglotic-server`, and
`polyglotic-admin invite create` for a code) - sign the harness in once
(the token goes to Windows Credential Manager under `Polyglotic/harness`),
then listen; captions print as they come back:

```
uv run python -m polyglotic_desktop.harness sign-in --server http://127.0.0.1:8080
uv run python -m polyglotic_desktop.harness listen --server http://127.0.0.1:8080 --play <clip.wav> --targets zh
uv run python -m polyglotic_desktop.harness listen --server http://127.0.0.1:8080 --replay <clip.wav>   # no audio device
uv run python -m polyglotic_desktop.harness sign-out
```

Run from source, the app tells the server it is the newest release
`RELEASE-NOTES.md` names (decision 0224; a release build carries its tag's
version, decision 0015), so a server whose minimum that release meets
takes it. Settings > Updates still says `0.0.0`: from source it isn't a
release. Without `--server` the app connects to the live server,
`https://api.polyglotic.io`.

The app itself - main window, tray, caption windows, transcripts, the
app picker on Home - runs the same way. At first run it asks what to
share and the yes (the consent screen), then an invite code; the
Account page signs in and out later. It captures what Home's picker
says - for a new learner, everything the PC plays from the first launch,
in one caption window that sets itself up, until they pick one app on
Home (polyglotic-hq 484, decision 0225) - and keeps its settings, learning data
and the outbox of what waits
for the server in `%APPDATA%\Polyglotic` - outside the folder the
installer replaces (decision 0014):

```
uv run python -m polyglotic_desktop.main --server http://127.0.0.1:8080
```

The connection's own data - consent choices, learning data and the
outbox of what waits for the server - can be tried the same way. The
harness keeps its own copy in `%APPDATA%\Polyglotic\harness` (or
`--data`); `learn` works offline and `sync` sends what waited and applies
what came back. A second install of the same account ("a second PC") is
another `--credentials` entry with another `--data` folder, signed in
with an invite code made by `polyglotic-admin invite create --account
<id>`:

```
uv run python -m polyglotic_desktop.harness consent --usage --exposures   # default: every choice off
uv run python -m polyglotic_desktop.harness learn --save 榴莲 --known 今天     # needs the dictionaries, below
uv run python -m polyglotic_desktop.harness sync --server http://127.0.0.1:8080
uv run python -m polyglotic_desktop.harness words
uv run python -m polyglotic_desktop.harness delete-learning --server http://127.0.0.1:8080 --on-this-pc
```

(Set `PYTHONIOENCODING=utf-8` if the console can't print Chinese.)

To see the interface without the server - every window and page in its
states, on a recorded, made-up conversation (`ui/recorded_captions.py`),
as PNGs with their timings - run the UI lab (`tools/ui_lab`, offscreen;
set `QT_QPA_FONTDIR=C:/Windows/Fonts` for Windows' fonts):

```
uv run python -m tools.ui_lab --out build/ui-lab
```

For real windows without anyone's screen - on a Windows desktop of their
own, which Windows never shows - see [docs/real-windows.md](docs/real-windows.md)
(`tools/private_desktop.py`).

The dictionaries are built, not committed (decision 0009):

```
uv run python -m tools.dictionaries.build   # fetches pinned sources, writes build/dictionaries/
```

## Packing the app

What testers install is built by PyInstaller as one folder (decision
0016), from the locked environment. CI does it on pushes to `main` that
could change it, and by hand on a branch (`.github/workflows/package.yml`,
decision 0021); here:

```
uv sync --locked --no-default-groups --group package
uv run --no-sync python -m tools.dictionaries.build
uv run --no-sync python -m tools.package.build v0.1.0   # the release's tag
```

`dist/Polyglotic/` then holds `Polyglotic.exe`, the dictionaries, the
notices and licences. The build checks it (nothing missing, no `.env` or
token, no tests) and runs `Polyglotic.exe --check-install`, which builds
everything offscreen - no window, no capture, no connection - and writes
what it found; `build/package/summary.json` has the sizes and times. `uv
sync` (without the flags) puts the dev tools back.

Installed copies update themselves (decision 0017): Velopack's start-up
hooks run first, the app looks for an update at start and every 6 hours,
and a downloaded update applies at the next start - or at once when the
server answers `update_required`. From source nothing updates. To try it
against a feed in a folder on this PC: `--updates <folder>`.

## Releasing

A tag releases (decision 0018): `git tag -s v0.1.0 && git push origin
v0.1.0` starts `.github/workflows/release.yml`, which builds and packs the
app for `win-x64-alpha` (Velopack: `Polyglotic-win-x64-alpha-Setup.exe`,
the update package, `releases.win-x64-alpha.json`), uploads it to the
update storage (`tools/package/publish.sh`) and records every file's
SHA-256 on a GitHub Release for the tag - the feed as the storage serves
it, after Velopack's upload merged it with the releases already there,
checked and (once there's a key) signed as served (decision 0020). **Until the domain and the update storage exist, nothing is
uploaded:** the run keeps the build on a draft Release. One job builds
and publishes (decision 0050), so a release never needs GitHub's
artifact storage.
To make it publish:

1. Buy the domain; serve the R2 bucket at `https://updates.<domain>/` and
   the server at `https://api.<domain>`; change `main.SERVER` and
   `main.UPDATES` (and the test that expects `.invalid`) in a pull request.
2. In the repo's settings, an environment `release` with the secrets
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` (a token for the releases
   bucket only), `R2_ENDPOINT` (`https://<account id>.r2.cloudflarestorage.com`)
   and `R2_BUCKET`; and a repository variable `UPDATE_FEED`
   (`https://updates.<domain>/`), which also turns on the daily feed check
   (`.github/workflows/feed-check.yml`).
3. Optional, recommended: the SSH key that signs your tags in
   `.github/allowed_signers`; the workflow then refuses unsigned tags.
4. Before the beta, the signed feed (decision 0019): `uv run python -m
   tools.package.sign_feed generate` on a trusted PC; the private key as
   the `release` environment's secret `FEED_SIGNING_KEY` (and in the
   password manager), the public key in `main.FEED_KEYS` by a pull
   request - released only after a signed feed has been published and
   checked with that key: `uv run python -m tools.package.sign_feed
   verify releases.win-x64-alpha.json --channel win-x64-alpha --key
   <public key>` on the feed and `.sig` downloaded from the Release.

A run by hand (Actions > Release > Run workflow) on a branch is a dry
run: it builds and packs, publishes nothing. To undo a bad release,
release the last good code as a newer version.

**Dictionary packs** (decision 0122) are published apart from the app, to
the same storage under `packs/`, with a list signed by the feed's key:

```
uv run python -m tools.package.publish_packs ru --build           # dry run
uv run python -m tools.package.publish_packs ru --upload          # at a release
```

A dry run builds the packs (or takes `build/dictionaries/packs/`), stamps
each file's version, merges the list with the one published (keeping the
last pack every older app reads), signs it with `$FEED_SIGNING_KEY`, lays
out `build/packs-publish/` exactly as the bucket holds it, and prints what
would go where - files first, the list last. `--upload` puts them in the
bucket with wrangler (`npx wrangler login` first), then fetches the list
back from `updates.polyglotic.io` and checks its signature.

**Sending it to a friend** (project 032, item 11): the
`Polyglotic-win-x64-alpha-Setup.exe` link sent to them directly - never on
a public page - with its SHA-256 from the Release, and a plain sentence:
"Windows will say it's from an unknown publisher, because we don't pay for
a code-signing certificate yet; click 'More info', then 'Run anyway'. It
installs for you only, no administrator needed, and updates itself."

## Checks

CI runs the same checks, plus a secret scan (gitleaks): a pull request runs
the ones that don't need Windows, on Linux; the Windows ones (the whole
suite and the UI lab) run on a push to `main`, on a train of ready pull
requests merged together, by hand, and on a pull request that changes CI
itself or the dependencies ([decision 0167](docs/decisions/0167-the-release-train.md)).
The checks don't run for a change to Markdown alone in the root, `docs/` or
`.github/`, the secret scan always; a draft runs nothing until it's ready; a dependency audit (pip-audit) runs
weekly. All of it runs on self-hosted runners on the user's PC
([decision 0025](docs/decisions/0025-ci-on-self-hosted-runners.md)). Changes arrive as pull requests - see [CLAUDE.md](CLAUDE.md).

## Licence

Apache-2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE). What the app is built
with, and the dictionaries and samples it uses, keep their own licences:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
