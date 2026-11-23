"""Publishing the dictionary packs: their files, and the signed list the
app reads (decision 0122). A dry run unless told to upload.

    uv run python -m tools.package.publish_packs ru            # dry run
    uv run python -m tools.package.publish_packs ru --upload   # Claude, at a release
    # recorded words beside the packs already published (decision 0192)
    uv run python -m tools.package.publish_packs es it pt --audio FOLDER \\
        --riders-only --version 2026.11.16                     # dry run
    # a built-in dictionary's recorded words (decision 0197): no pack
    uv run python -m tools.package.publish_packs --built-in cedict \\
        --audio FOLDER                                         # dry run
    # English's meanings in learners' languages (decision 0234)
    uv run python -m tools.package.publish_packs --built-in ecdict \\
        --meanings FOLDER                                      # dry run

What it does, in order:
1. takes each language's built pack (`tools.dictionaries.packs` writes
   `build/dictionaries/packs/`; `--build` builds them first) - a file per
   meanings language it is written in (English and Chinese; Vietnamese's
   English only) - and copies each to its published name,
   `<dictionary>-<meanings>-<version>.sqlite`, with its version stamped in
   its `info` (`pack_version`: the app reads what's on the PC from there),
   and gzips it: the `.sqlite.gz` is what goes up (Russian's 62.4 MB, 13.3);
2. writes the list: these packs, and from the list now published (fetched,
   and checked against the key, or `--previous FILE`) every older version
   an older app still needs - one it reads and the new one it doesn't (a
   new format, a new word split, a newer `min_app`). So an old app is never
   offered a pack it can't read, and never left without the one it can;
3. numbers the list one more than the one published (its `serial`: the
   app refuses an older list than one it has accepted), signs it with
   `$FEED_SIGNING_KEY` (the update feed's key: one trust path), checks the
   signature as the app will, and writes both as one file,
   `packs/v1/list.signed` - one upload replaces both, so no app can read a
   new signature beside an old list;
4. lays it all out in `--out` as the storage will hold it (a folder served
   over HTTP is a stand-in for the storage), and prints exactly what would
   be uploaded where, files first, the list last - so the list never names
   a file that isn't there yet. `--out` is emptied first only if it's
   empty or an earlier run's (it carries `OUT_MARK`);
5. with `--audio FOLDER`: each language's recorded words
   (`<dictionary>.audio`, built by `tools.dictionaries.audio`) go up as a
   **rider** of its pack (decision 0133), `<dictionary>-<version>.audio`,
   named inside each of the pack's entries with its own `min_app`
   (`--rider-min-app`: the first app that plays them; decision 0192). With
   `--riders-only` the packs are the ones the list publishes at
   `--version`, as they are: only the riders and the list go up, and an
   app that reads the packs still does. A pack published again later
   without `--audio` carries no riders: give it `--audio` again;
   with `--built-in cedict` too (or alone), a dictionary built into the
   app has its recorded words put in the list's `built_in` entry for it
   (decision 0197), `cedict-<version>.audio`. The entries the list has
   already are kept, but one for the same dictionary is replaced;
   with `--meanings FOLDER`: each named dictionary's meanings files there
   (`<dictionary>-<language>.meanings`, built by
   `tools.dictionaries.english_pairs`) go up as riders the same way, one
   per language, `<dictionary>-<language>-<version>.meanings`, from app
   `--meanings-min-app` (decision 0234). Give `--audio` and `--meanings`
   together to keep both kinds: an entry published again carries only the
   riders given;
6. with `--fonts DIR` (`tools.caption_fonts --packs` writes it): each
   caption face's files go up as riders (kind `font`, `--font-min-app`)
   of its entry in the list's `fonts` (polyglotic-hq 482, decision 0223),
   `<pack>-<style>-<version>.<ext>`; the faces the list has already stay,
   but one of the same name is replaced;
7. only with `--upload`: puts each file in the bucket with wrangler (as
   polyglotic-hq 280's publish-alpha.sh does; wrangler gets this
   environment without the signing key), then fetches the list back from
   the live address and checks it.

Nothing here runs in CI against the real storage.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from nacl.signing import SigningKey, VerifyKey

from polyglotic_desktop.adapters.audio_file import SUFFIX as AUDIO_SUFFIX
from polyglotic_desktop.adapters.audio_file import NotAnAudioFile, SqliteAudio
from polyglotic_desktop.adapters.meanings_file import SUFFIX as MEANINGS_SUFFIX
from polyglotic_desktop.adapters.meanings_file import (
    NotAMeaningsFile,
    SqliteMeanings,
)
from polyglotic_desktop.adapters.pack_list import (
    FILES,
    FOLDER,
    LIST_NAME,
    signed_list_file,
    signed_list_message,
    split_signed_list,
)
from polyglotic_desktop.adapters.signed_feed import public_keys, verify
from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary, add_info
from polyglotic_desktop.core.lexicon.packs import (
    CODE,
    LIST_FORMAT,
    BuiltIn,
    FontOffer,
    PackOffer,
    Rider,
    list_serial,
    read_built_in,
    read_fonts,
    read_pack_list,
    version_key,
)
from tools.package.sign_feed import KEY_VARIABLE, private_key_from, public_key_text

REPO = Path(__file__).resolve().parents[2]
BUCKET = "polyglotic-updates"
LIVE = "https://updates.polyglotic.io/"
"""main.UPDATES: the storage the app reads packs from."""
MIN_APP = "0.1.5"
"""The first app version that downloads packs: the default `min_app`."""
RIDER_MIN_APP = "0.1.7"
"""The first app version that plays a pack's recorded words: the default
`min_app` of a rider (decision 0192; 0.1.7 on the user's word of
2026-11-16 ~23:00)."""
MEANINGS_MIN_APP = "0.1.9"
"""The first app version that reads a dictionary's meanings files: the
default `min_app` of a meanings rider (decision 0234)."""
BUILT_IN = {"cedict": "zh", "ecdict": "en"}
"""The dictionaries built into the app that may have riders, and the
language each is learned for (main.BUILT_IN_RIDERS)."""
FONT_MIN_APP = "0.1.8"
"""The first app version that downloads caption faces (polyglotic-hq 482)."""
FONT_FORMAT = "1"
"""A caption face's file: a TrueType or OpenType font, or its licence text."""
SPLITS = {
    "fr": "elided",
    "it": "elided",
    "ja": "japanese",
    "vi": "vietnamese",
    "th": "thai",
    "yue": "han",
    "hi": "marks",
    "ar": "clitics",
    "id": "clitics",
    "ms": "clitics",
    "tr": "turkish",
    "ko": "korean",
    "fa": "joiners",
    "tl": "affixes",
    "cs": "affixes",
    "el": "affixes",
}
"""The word split each language's pack needs; `spaced` for the rest. An
app without a pack's split is never offered it (`core.lexicon.packs.Reader`):
an app from before Vietnamese's split would cut "học sinh" in two, one
from before French's would look "l'homme" up as one word, one from before
`marks` would cut Hindi's words at each vowel sign, and one from before
`clitics` would find none of Arabic's words with "and" or "the" on them
(polyglotic-hq 380; an app with `clitics` has `marks` too), and one from
before `turkish` would find a fifth of Turkish's words in no dictionary:
their suffixes are guessed off (polyglotic-hq 388; an app with `turkish`
has `clitics` too). One from before `joiners` would cut Persian's words at
their zero-width non-joiner (داستان‌های) and has none of its endings'
guesses; one from before `affixes` finds Filipino's, Czech's and Greek's
words only below the floor (77.1, 89.8 and 89.8 % of the probe's words,
not 90.8, 90.6 and 90.1; polyglotic-hq 387). An app with either has every
split before it. One from before `thai` would take a Thai phrase, written
without spaces, as one word (polyglotic-hq 389); one from before `han`
would take a Cantonese line as one word (polyglotic-hq 450), and has no
Cantonese in its basic languages. One from before `korean` finds
Korean's nouns only without their particles, and its verbs only in their
tables' forms (polyglotic-hq 510)."""
WIKTIONARY_AND_WORDFREQ = (
    "Wiktionary's contributors (via kaikki.org) and wordfreq; CC BY-SA 4.0"
)
CREDIT_LINES = {
    "wiktes": WIKTIONARY_AND_WORDFREQ,
    "wiktfr": WIKTIONARY_AND_WORDFREQ,
    "wiktru": WIKTIONARY_AND_WORDFREQ,
    "wiktar": WIKTIONARY_AND_WORDFREQ,
    "wiktde": WIKTIONARY_AND_WORDFREQ,
    "wikthi": WIKTIONARY_AND_WORDFREQ,
    "wiktid": WIKTIONARY_AND_WORDFREQ,
    "wiktit": WIKTIONARY_AND_WORDFREQ,
    "wiktpl": WIKTIONARY_AND_WORDFREQ,
    "wiktpt": WIKTIONARY_AND_WORDFREQ,
    **{
        f"wikt{code}": WIKTIONARY_AND_WORDFREQ
        for code in ("nl", "uk", "sv", "cs", "ro", "el", "tl", "mk")
    },
    "wiktfa": (
        "Wiktionary's contributors (via kaikki.org) and wordfreq, CC BY-SA 4.0; "
        "ranks also from Common Voice's sentences (CC0)"
    ),
    "wiktvi": (
        "Wiktionary's contributors (via kaikki.org), CC BY-SA 4.0; ranks counted "
        "from OPUS OpenSubtitles 2018 (opensubtitles.org)"
    ),
    "wiktth": (
        "Wiktionary's contributors (via kaikki.org), CC BY-SA 4.0; ranks counted "
        "from Common Voice's Thai sentences (CC0)"
    ),
    "jmdict": "JMdict (EDRDG), Wiktionary's contributors and wordfreq; CC BY-SA 4.0",
    "canto": (
        "CC-Canto and its Cantonese readings for CC-CEDICT (Pleco), CC-CEDICT "
        "(MDBG), rime-cantonese (CanCLID); CC BY-SA 4.0; ranks from HKCanCor "
        "(CC BY 4.0) and wordfreq"
    ),
}


def built_files(packs: Path, name: str, meanings: Sequence[str]) -> list[Path]:
    """A pack's built files, one per meanings language it is written in
    (`tools.dictionaries.packs.Pack.meanings`): `<name>.sqlite` for
    English, `<name>-zh.sqlite` for Chinese. Vietnamese's is English only."""
    return [packs / f"{name}{'' if m == 'en' else '-' + m}.sqlite" for m in meanings]


@dataclass(frozen=True)
class Upload:
    """One file to put in the bucket: where it is here, its key there."""

    path: Path
    key: str
    content_type: str


def app_keys() -> list[VerifyKey]:
    """The keys the app checks the list with (`main.FEED_KEYS`): the live
    list must pass them. Imported when needed: `main` brings in Qt."""
    from polyglotic_desktop.main import FEED_KEYS

    return public_keys(FEED_KEYS)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def stamp(
    built: Path, out_files: Path, version: str, min_app: str
) -> tuple[PackOffer, Path]:
    """`built` stamped with its version (in its `info`) under its published
    name in `out_files`, and gzipped beside it - the download; its offer,
    and the download's path (what goes up: the app unpacks it)."""
    file = SqliteDictionary(built)
    try:
        info = dict(file.info)
    finally:
        file.close()
    language, meanings = info["language"], info["meanings_language"]
    dictionary = info["dictionary"]
    name = f"{dictionary}-{meanings}-{version}.sqlite"
    target = out_files / name
    shutil.copyfile(built, target)
    add_info(target, {"pack_version": version})
    packed = target.with_name(name + ".gz")
    # mtime 0 and no file name: the same pack gzips to the same bytes
    with (
        target.open("rb") as raw,
        packed.open("wb") as out,
        gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as squeezed,
    ):
        shutil.copyfileobj(raw, squeezed, 1 << 20)
    credits_file = built.with_name(f"{dictionary}.CREDITS.md")
    credits_text = (
        credits_file.read_text(encoding="utf-8") if credits_file.is_file() else ""
    )
    offer = PackOffer(
        language=language,
        meanings=meanings,
        dictionary=dictionary,
        version=version,
        format=info["format"],
        split=SPLITS.get(language, "spaced"),
        min_app=min_app,
        file=name,
        size=target.stat().st_size,
        sha256=sha256_of(target),
        gz_size=packed.stat().st_size,
        gz_sha256=sha256_of(packed),
        licence=info.get("licence", ""),
        credits=CREDIT_LINES.get(dictionary) or info.get("licence", ""),
        credits_text=credits_text,
    )
    target.unlink()  # only the download goes up
    return offer, packed


def stamp_audio(
    built: Path, dictionary: str, out_files: Path, version: str, min_app: str
) -> tuple[Rider, Path, dict[str, str]]:
    """`dictionary`'s recorded words (`<dictionary>.audio` in `built`)
    stamped with the pack's version under their published name in
    `out_files` and gzipped beside it: the rider the list names, the
    download's path, and the file's `info` (who said them, the licence).
    SystemExit if it isn't that dictionary's audio file."""
    source = built / f"{dictionary}{AUDIO_SUFFIX}"
    try:
        file = SqliteAudio(source)
    except (OSError, NotAnAudioFile) as e:
        raise SystemExit(f"{source}: no audio file ({type(e).__name__})") from None
    info = dict(file.info)
    file.close()
    if info.get("dictionary") != dictionary:
        raise SystemExit(
            f"{source} is {info.get('dictionary')!r}'s, not {dictionary}'s"
        )
    name = f"{dictionary}-{version}{AUDIO_SUFFIX}"
    target = out_files / name
    shutil.copyfile(source, target)
    add_info(target, {"version": version})
    packed = target.with_name(name + ".gz")
    with (
        target.open("rb") as raw,
        packed.open("wb") as out,
        gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as squeezed,
    ):
        shutil.copyfileobj(raw, squeezed, 1 << 20)
    rider = Rider(
        kind="audio",
        format=info["format"],
        min_app=min_app,
        file=name,
        size=target.stat().st_size,
        sha256=sha256_of(target),
        gz_size=packed.stat().st_size,
        gz_sha256=sha256_of(packed),
    )
    target.unlink()  # only the download goes up
    return rider, packed, info


def stamp_meanings(
    built: Path, dictionary: str, out_files: Path, version: str, min_app: str
) -> list[tuple[Rider, Path]]:
    """`dictionary`'s meanings files (`<dictionary>-<language>.meanings` in
    `built`), each stamped with the version under its published name in
    `out_files` and gzipped beside it: the riders the list names and the
    downloads' paths, by language. SystemExit if one isn't the meanings
    file its name says."""
    found = []
    for source in sorted(built.glob(f"{dictionary}-*{MEANINGS_SUFFIX}")):
        language = source.name[len(dictionary) + 1 : -len(MEANINGS_SUFFIX)]
        if not CODE.fullmatch(language):
            continue  # another dictionary's (`ecdict-en...`), or a stamped one
        try:
            file = SqliteMeanings(source)
        except (OSError, NotAMeaningsFile) as e:
            raise SystemExit(
                f"{source}: no meanings file ({type(e).__name__})"
            ) from None
        info = dict(file.info)
        file.close()
        if (info.get("dictionary"), info.get("meanings_language")) != (
            dictionary,
            language,
        ):
            raise SystemExit(f"{source} isn't {dictionary}'s meanings in {language}")
        name = f"{dictionary}-{language}-{version}{MEANINGS_SUFFIX}"
        target = out_files / name
        shutil.copyfile(source, target)
        add_info(target, {"version": version})
        packed = target.with_name(name + ".gz")
        with (
            target.open("rb") as raw,
            packed.open("wb") as out,
            gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as squeezed,
        ):
            shutil.copyfileobj(raw, squeezed, 1 << 20)
        rider = Rider(
            kind="meanings",
            format=info["format"],
            min_app=min_app,
            file=name,
            size=target.stat().st_size,
            sha256=sha256_of(target),
            gz_size=packed.stat().st_size,
            gz_sha256=sha256_of(packed),
            meanings=language,
        )
        target.unlink()  # only the download goes up
        found.append((rider, packed))
    return found


def still_needed(previous: PackOffer, new: PackOffer) -> bool:
    """Whether an app that reads `previous` might not read `new`: another
    format or word split, or a newer `min_app`."""
    return (
        previous.format != new.format
        or previous.split != new.split
        or (version_key(new.min_app) or ()) > (version_key(previous.min_app) or ())
    )


def merged(new: Sequence[PackOffer], previous: Sequence[PackOffer]) -> list[PackOffer]:
    """The list to publish: `new`, then of `previous` the newest version for
    each kind of reader the new ones would leave behind (and every pack of a
    language and meanings not published now, as it was)."""
    by_key = {o.key: o for o in new}
    kept: dict[tuple[str, str, str, str, str], PackOffer] = {}
    for old in previous:
        replacing = by_key.get(old.key)
        if old.file in {o.file for o in new}:
            continue
        if replacing is not None and not still_needed(old, replacing):
            continue
        reader = (*old.key, old.format, old.split, old.min_app)
        best = kept.get(reader)
        if best is None or (version_key(old.version) or ()) > (
            version_key(best.version) or ()
        ):
            kept[reader] = old
    out = list(new) + sorted(
        kept.values(), key=lambda o: (o.language, o.meanings, version_key(o.version))
    )
    return out


OUT_MARK = ".polyglotic-packs-publish"
"""Left in `--out` by a run: the next may empty it (nothing else is)."""


def list_bytes(
    offers: Sequence[PackOffer],
    serial: int,
    built_in: Sequence[BuiltIn] = (),
    fonts: Sequence[FontOffer] = (),
) -> bytes:
    """The list as published: one JSON object, keys sorted, UTF-8 - with
    `built_in` only if there are any (decision 0197), and `fonts` (482)."""
    whole: dict[str, object] = {
        "list": LIST_FORMAT,
        "serial": serial,
        "packs": [_listed(asdict(o)) for o in offers],
    }
    if built_in:
        whole["built_in"] = [_listed(asdict(b)) for b in built_in]
    if fonts:
        whole["fonts"] = [_listed(asdict(f)) for f in fonts]
    return (
        json.dumps(whole, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    ).encode("utf-8")


def _listed(entry: dict[str, object]) -> dict[str, object]:
    """An entry as the list writes it: a rider's `meanings` only where it
    has one (a meanings rider's), so the other riders read as before."""
    riders = entry.get("riders")
    if isinstance(riders, (list, tuple)):  # `asdict` keeps a tuple a tuple
        entry["riders"] = [
            {k: v for k, v in r.items() if k != "meanings" or v} for r in riders
        ]
    return entry


def sign_list(data: bytes, key: SigningKey) -> bytes:
    """The one file published: the list's signature, checked as the app
    checks it, then the list (`pack_list.signed_list_file`)."""
    message = signed_list_message(data)
    signature = base64.b64encode(key.sign(message).signature)
    verify(message, signature, [key.verify_key])
    return signed_list_file(signature, data)


def previous_list(
    source: str | None, get: Callable[[str], bytes]
) -> tuple[tuple[PackOffer, ...], int, tuple[BuiltIn, ...], tuple[FontOffer, ...]]:
    """The list now published - `source`, a `list.signed` file, or None for
    the live one; its signature checked first - its serial, and its
    built-in dictionaries' riders; or none yet, serial 0."""
    if source:
        whole = Path(source).read_bytes()
    else:
        try:
            whole = get(LIVE + FOLDER + LIST_NAME)
        except urllib.error.HTTPError as e:
            if e.code != 404:  # anything else: the list may be there, unread
                raise SystemExit(
                    f"the live list can't be read (HTTP {e.code})"
                ) from None
            print("  no list published yet (404): starting one")
            return (), 0, (), ()
    signature, data = split_signed_list(whole)
    if not source:  # a file given is the operator's own (a dry run's stand-in)
        verify(signed_list_message(data), signature, app_keys())
    return (
        read_pack_list(data)[0],
        list_serial(data),
        read_built_in(data),
        read_fonts(data),
    )


def stamp_fonts(
    folder: Path, out_files: Path, min_app: str
) -> tuple[list[FontOffer], list[Path]]:
    """Each caption face in `folder` (`fonts.json`, by
    `tools.caption_fonts --packs`) as its list entry, each file a rider,
    gzipped into `out_files`: the entries, and the files to upload."""
    manifest = json.loads((folder / "fonts.json").read_text(encoding="utf-8"))
    offers, files = [], []
    for entry in manifest:
        riders = []
        for name in entry["files"]:
            source = folder / name
            packed = out_files / (name + ".gz")
            with (
                source.open("rb") as f,
                packed.open("wb") as raw,
                gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
            ):
                shutil.copyfileobj(f, gz)
            riders.append(
                Rider(
                    "font",
                    FONT_FORMAT,
                    min_app,
                    name,
                    source.stat().st_size,
                    sha256_of(source),
                    packed.stat().st_size,
                    sha256_of(packed),
                )
            )
            files.append(packed)
        offers.append(
            FontOffer(entry["font"], entry["family"], entry["credits"], tuple(riders))
        )
    return offers, files


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Polyglotic-release"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body: bytes = response.read()
        return body


def plan(
    out: Path, offers: Sequence[PackOffer], new_files: Sequence[Path]
) -> list[Upload]:
    """What goes where: the new files first, then the list - one file with
    its signature, so it never names a file not there yet, and is never
    read half old, half new."""
    uploads = [
        Upload(path, FILES + path.name, "application/gzip") for path in new_files
    ]
    uploads.append(Upload(out / FOLDER / LIST_NAME, FOLDER + LIST_NAME, "text/plain"))
    return uploads


def wrangler_environment() -> dict[str, str]:
    """This environment for wrangler, without the signing key: it has no
    business with it, and a child process's environment is easily seen."""
    keep = {k: v for k, v in os.environ.items() if k != KEY_VARIABLE}
    return {**keep, "MSYS_NO_PATHCONV": "1"}


def upload(uploads: Sequence[Upload], bucket: str) -> None:
    """Each file into the bucket, in order, with wrangler (logged in by
    `npx wrangler login`; the credentials are wrangler's, never ours)."""
    npx = shutil.which("npx")  # Windows has npx.cmd, which a bare name misses
    if npx is None:
        raise SystemExit("npx isn't on the PATH: wrangler runs through it")
    for item in uploads:
        command = [
            npx,
            "wrangler",
            "r2",
            "object",
            "put",
            f"{bucket}/{item.key}",
            "--file",
            str(item.path),
            "--remote",
            "--content-type",
            item.content_type,
        ]
        print("  npx " + " ".join(command[1:6]))
        subprocess.run(command, check=True, env=wrangler_environment())


def check_live(expected: bytes, get: Callable[[str], bytes]) -> None:
    """The list as the live address serves it: ours, signed by the key the
    app holds."""
    address = LIVE + FOLDER + LIST_NAME
    whole = get(address)
    if whole != expected:
        raise SystemExit("the live list isn't the one just uploaded (a cache?)")
    signature, data = split_signed_list(whole)
    verify(signed_list_message(data), signature, app_keys())
    print(f"  {address}: ours, signed by main.FEED_KEYS' key")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.publish_packs")
    parser.add_argument("languages", nargs="*", help="the packs to publish: ru es")
    parser.add_argument(
        "--built-in",
        action="append",
        default=[],
        choices=sorted(BUILT_IN),
        help="a dictionary built into the app whose recorded words (in --audio) "
        "and meanings files (in --meanings) go up as its riders",
    )
    parser.add_argument(
        "--packs", type=Path, default=REPO / "build" / "dictionaries" / "packs"
    )
    parser.add_argument("--build", action="store_true", help="build the packs first")
    today = dt.datetime.now(dt.UTC).date()  # a label, never compared to a clock
    parser.add_argument(
        "--version",
        default=f"{today.year}.{today.month}.{today.day}",
        help="the packs' version (default: today's date in UTC, 2026.11.14)",
    )
    parser.add_argument("--min-app", default=MIN_APP)
    parser.add_argument(
        "--audio",
        type=Path,
        help="a folder of recorded words (<dictionary>.audio): each language's "
        "goes up as its pack's rider",
    )
    parser.add_argument("--rider-min-app", default=RIDER_MIN_APP)
    parser.add_argument(
        "--meanings",
        type=Path,
        help="a folder of meanings files (<dictionary>-<language>.meanings): "
        "each goes up as its dictionary's rider (decision 0234)",
    )
    parser.add_argument("--meanings-min-app", default=MEANINGS_MIN_APP)
    parser.add_argument(
        "--fonts",
        type=Path,
        help="caption faces built by tools.caption_fonts --packs: their files "
        "go up as riders of the list's fonts",
    )
    parser.add_argument("--font-min-app", default=FONT_MIN_APP)
    parser.add_argument(
        "--riders-only",
        action="store_true",
        help="the riders beside the packs published at --version: no pack "
        "is stamped or uploaded again",
    )
    parser.add_argument(
        "--previous",
        help="the list now published, a list.signed file (default: the live one)",
    )
    parser.add_argument("--out", type=Path, default=REPO / "build" / "packs-publish")
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument(
        "--upload", action="store_true", help="really upload (Claude, at a release)"
    )
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    mins = (args.min_app, args.rider_min_app, args.meanings_min_app, args.font_min_app)
    if any(version_key(v) is None for v in (args.version, *mins)):
        print("--version and the min apps are dotted numbers", file=sys.stderr)
        return 2
    no_riders = args.audio is None and args.meanings is None
    if args.riders_only and (no_riders or args.build):
        print(
            "--riders-only needs --audio or --meanings, and builds no pack",
            file=sys.stderr,
        )
        return 2
    if not args.languages and not args.built_in and args.fonts is None:
        print("name the packs to publish, or --built-in, or --fonts", file=sys.stderr)
        return 2
    if args.built_in and no_riders:
        print("--built-in needs --audio or --meanings", file=sys.stderr)
        return 2

    if args.build:
        from tools.dictionaries import packs

        if packs.main([*args.languages, "--out", str(args.packs)]):
            print("a pack failed its check: nothing published", file=sys.stderr)
            return 1

    encoded = os.environ.get(KEY_VARIABLE, "")
    if not encoded:
        print(f"No signing key: set {KEY_VARIABLE} (the feed's key)", file=sys.stderr)
        return 1
    key = private_key_from(encoded)

    out_files = args.out / FILES
    out_list = args.out / FOLDER
    if args.out.exists() and any(args.out.iterdir()):
        if not (args.out / OUT_MARK).is_file():
            print(
                f"{args.out} isn't empty and isn't an earlier run's: not emptied",
                file=sys.stderr,
            )
            return 1
        shutil.rmtree(args.out)
    out_files.mkdir(parents=True)
    out_list.mkdir(parents=True)
    (args.out / OUT_MARK).write_text("made by tools.package.publish_packs\n")
    from tools.dictionaries.packs import PACKS

    previous, serial, built_in, faces = previous_list(args.previous, _get)
    new: list[PackOffer] = []
    new_files: list[Path] = []
    said_by: dict[str, dict[str, str]] = {}  # each audio file's info
    for language in args.languages:
        pack = PACKS[language]
        riders: tuple[Rider, ...] = ()
        if args.audio is not None:
            rider, path, said_by[pack.name] = stamp_audio(
                args.audio, pack.name, out_files, args.version, args.rider_min_app
            )
            riders = (rider,)
            new_files.append(path)
        if args.meanings is not None:
            for rider, path in stamp_meanings(
                args.meanings, pack.name, out_files, args.version, args.meanings_min_app
            ):
                riders += (rider,)
                new_files.append(path)
        if args.riders_only:
            published = [
                o
                for o in previous
                if o.dictionary == pack.name and o.version == args.version
            ]
            if not published:
                print(
                    f"no {language} pack is published at {args.version}",
                    file=sys.stderr,
                )
                return 1
            new += [replace(o, riders=riders) for o in published]
            continue
        for built in built_files(args.packs, pack.name, pack.meanings):
            if not built.is_file():
                print(f"{built} isn't built: run with --build", file=sys.stderr)
                return 1
            offer, path = stamp(built, out_files, args.version, args.min_app)
            new.append(replace(offer, riders=riders))
            new_files.append(path)

    new_built_in: list[BuiltIn] = []
    for dictionary in dict.fromkeys(args.built_in):
        found: list[tuple[Rider, Path]] = []
        if (
            args.audio is not None
            and (args.audio / f"{dictionary}{AUDIO_SUFFIX}").is_file()
        ):
            rider, path, said_by[dictionary] = stamp_audio(
                args.audio, dictionary, out_files, args.version, args.rider_min_app
            )
            found.append((rider, path))
        if args.meanings is not None:
            found += stamp_meanings(
                args.meanings,
                dictionary,
                out_files,
                args.version,
                args.meanings_min_app,
            )
        if not found:
            print(
                f"no riders for {dictionary} in --audio or --meanings", file=sys.stderr
            )
            return 1
        riders = tuple(rider for rider, _ in found)
        new_built_in.append(BuiltIn(dictionary, BUILT_IN[dictionary], riders))
        new_files += [path for _, path in found]
    clash_built_in = [
        r.file
        for old in built_in
        for o in new_built_in
        for r in o.riders
        if {x.file: x.sha256 for x in old.riders}.get(r.file, r.sha256) != r.sha256
    ]
    if clash_built_in:
        print(
            f"{clash_built_in[0]} is published already with other bytes: "
            "give this build another --version",
            file=sys.stderr,
        )
        return 1
    built_in = tuple(new_built_in) + tuple(
        b for b in built_in if b.dictionary not in {n.dictionary for n in new_built_in}
    )
    for old in previous:
        theirs = {r.file: r.sha256 for r in old.riders}
        clash = [o.file for o in new if o.file == old.file and o.sha256 != old.sha256]
        clash += [
            r.file
            for o in new
            for r in o.riders
            if theirs.get(r.file, r.sha256) != r.sha256
        ]
        if clash:
            print(
                f"{clash[0]} is published already with other bytes: "
                "give this build another --version",
                file=sys.stderr,
            )
            return 1
    new_faces: list[FontOffer] = []
    if args.fonts is not None:
        new_faces, face_files = stamp_fonts(args.fonts, out_files, args.font_min_app)
        face_shas = {r.file: r.sha256 for old in faces for r in old.riders}
        clash_faces = [
            r.file
            for face in new_faces
            for r in face.riders
            if face_shas.get(r.file, r.sha256) != r.sha256
        ]
        if clash_faces:
            print(
                f"{clash_faces[0]} is published already with other bytes: "
                "give the faces another version (caption_fonts.PACK_VERSION)",
                file=sys.stderr,
            )
            return 1
        new_files += face_files
    renamed = {face.font for face in new_faces}
    faces = tuple(new_faces) + tuple(f for f in faces if f.font not in renamed)
    offers = merged(new, previous)
    data = list_bytes(offers, serial + 1, built_in, faces)
    signed = sign_list(data, key)
    (out_list / LIST_NAME).write_bytes(signed)

    uploads = plan(args.out, offers, new_files)
    print(
        f"The list: serial {serial + 1}, {len(offers)} packs"
        f" (public key {public_key_text(key)})"
    )
    for o in offers:
        mark = "new" if o in new else "kept"
        print(
            f"  {mark:4} {o.language}/{o.meanings} {o.version} format {o.format} "
            f"{o.split} from app {o.min_app}: {o.download} {o.gz_size / 1e6:.1f} MB "
            f"({o.size / 1e6:.1f} MB unpacked) sha256 {o.gz_sha256[:12]}"
        )
        for r in o.riders:
            print(
                f"         with {r.kind}{' ' + r.meanings if r.meanings else ''} "
                f"format {r.format} from app {r.min_app}: "
                f"{r.download} {r.gz_size / 1e6:.1f} MB ({r.size / 1e6:.1f} MB "
                f"unpacked) sha256 {r.gz_sha256[:12]}"
            )
    for entry in built_in:
        mark = "new" if entry in new_built_in else "kept"
        for r in entry.riders:
            print(
                f"  {mark:4} built-in {entry.dictionary} ({entry.language}): "
                f"{r.kind}{' ' + r.meanings if r.meanings else ''} "
                f"format {r.format} from app {r.min_app}: {r.download} "
                f"{r.gz_size / 1e6:.1f} MB ({r.size / 1e6:.1f} MB unpacked) "
                f"sha256 {r.gz_sha256[:12]}"
            )
    for face in faces:
        mark = "new" if face in new_faces else "kept"
        size = sum(r.gz_size for r in face.riders)
        print(
            f"  {mark:4} face {face.font} ({face.family}): {len(face.riders)} files, "
            f"{size / 1e6:.2f} MB, from app {face.riders[0].min_app}"
        )
    for name, info in said_by.items():
        print(f"  {name}'s words: {info.get('words')}, said by {info.get('voice')}")
        print(f"    credit: {info.get('licence')}")
    print(
        f"{'Uploading' if args.upload else 'Would upload'}, in this order, to {args.bucket}:"
    )
    for item in uploads:
        print(f"  {item.key}  <-  {item.path}  ({item.path.stat().st_size:,} bytes)")
    if not args.upload:
        print("Dry run: nothing uploaded. --upload puts them in the bucket.")
        return 0
    upload(uploads, args.bucket)
    check_live(signed, _get)
    return 0


if __name__ == "__main__":
    sys.exit(main())
