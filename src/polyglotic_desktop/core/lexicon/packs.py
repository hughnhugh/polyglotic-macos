"""Dictionary packs as an installed app gets them (decision 0122): the
signed list of the packs that exist, which one this app can read for a
language, and whether the one on this PC is older.

The list (`packs/v1/list.json` beside the update feed) names, for each
language and meanings language, every version published: its file, size
and SHA-256, the file's format, the word split it needs, the oldest app
that reads it, its licence and its credits. Old versions stay listed when
a new format comes, so an app never needs a pack it can't read: it takes
the newest one *it* reads (`best_offer`) and leaves the rest
(`needs_newer_app` says when there are only those).

A pack may have **riders** (decision 0133): files that go with it - its
commonest words recorded (`audio`), and its meanings in one more language
each (`meanings`, decision 0234). The list names them inside their pack's
own entry (`riders`), which an app from before them doesn't read: it takes
the pack as it always did; an app from before a kind of rider leaves that
kind out. A rider has its own `min_app` (decision 0192), so one can be
added to a pack already published without hiding the pack from an app
that can't read it. An app takes the riders it reads and wants
(`riders_wanted`): the recordings, and the meanings in the learner's
language only.

A **caption face** (polyglotic-hq 482, decision 0223) has no pack either:
the list's `fonts` names each face its riders bring (`read_fonts`), which
an app from before them doesn't read.

A dictionary **built into the app** (CC-CEDICT, ECDICT) has no pack, so its riders
have an entry of their own (`built_in`, decision 0197): the dictionary's
name, its language, and its riders. An app from before them doesn't read
it, and the packs are read as before (`read_built_in`).

Plain Python: bytes in, choices out. Fetching the list, its signature,
the download and the files are `adapters.dictionary_packs`'.
"""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

LIST_FORMAT = 1
"""The list's own format: its address says it (`packs/v1/`). A list an
older app can't read goes to a new address; the old one stays."""
PLAIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
"""A pack's file name in the list: a bare name, never a path."""
DICTIONARY_NAME = re.compile(r"[a-z][a-z0-9_]*")
"""A dictionary's name (`wiktru`): the start of its entry IDs and of its
files' names."""
WINDOWS_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{n}" for n in range(10)}
    | {f"lpt{n}" for n in range(10)}
)
"""Names Windows takes for a device whatever follows the first dot
(`nul.sqlite` is the null device on older Windows): never a file's."""
PACK_SUFFIX = ".sqlite"
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
CODE = re.compile(r"[a-z]{2,3}")
"""A learned language's code, or a meanings language's: `ru`, `zh`, `yue`."""
RIDER_LOCALES = frozenset({"zh_TW"})
"""The languages a meanings rider may be in beyond a bare code (`CODE`):
Taiwan's Traditional Chinese, JMdict's drafts for it (polyglotic-hq 915)."""
FROM_SOURCE = "0.0.0"
"""The version an app run from source has (`connection.app`): it reads
every pack its formats and word splits allow, whatever `min_app` says."""


RIDER_SUFFIXES: dict[str, tuple[str, ...]] = {
    "audio": (".audio",),
    "meanings": (".meanings",),
    "font": (".ttf", ".otf", ".txt"),
}
"""Each kind of rider this code knows, and how its files' names end; a
kind it doesn't know is left out of a pack's riders (a newer list's). A
`font`'s are its faces and their licence text (polyglotic-hq 482)."""


class PackListError(ValueError):
    """The list can't be read as a list at all (not its shape, or a newer
    list format). Says which, never the contents."""


@dataclass(frozen=True)
class Rider:
    """A file that goes with one published pack (decision 0133): `kind` is
    `audio` (its commonest words recorded) or `meanings` (its meanings in
    the language `meanings`, decision 0234). Its version is its pack's; its
    `min_app` its own (decision 0192): the first app that reads it."""

    kind: str
    format: str
    """The rider file's own format (`adapters.audio_file.FORMAT`,
    `adapters.meanings_file.FORMAT`)."""
    min_app: str
    file: str
    size: int
    sha256: str
    gz_size: int
    gz_sha256: str
    meanings: str = ""
    """A meanings rider's language (`es`); "" for any other kind."""

    @property
    def download(self) -> str:
        return self.file + ".gz"


@dataclass(frozen=True)
class PackOffer:
    """One published version of a language's pack, as the list names it."""

    language: str
    """The learned language it serves (`ru`)."""
    meanings: str
    """The language its meanings are in (`en`; `zh` has Chinese where the
    Chinese edition of Wiktionary has it, else English)."""
    dictionary: str
    """The dictionary's name, the start of its entry IDs (`wiktru`)."""
    version: str
    """The pack's own version, `2026.11.14` (dotted numbers, compared as
    numbers)."""
    format: str
    """The file's format (`adapters.sqlite_dictionary.FORMAT`)."""
    split: str
    """The word split it needs: `spaced` (letters and simplemma) or
    `japanese` (Sudachi)."""
    min_app: str
    """The oldest app version that reads it."""
    file: str
    """Its name on this PC, and the start of its download's (`download`)."""
    size: int
    sha256: str
    """The file as it is on this PC, once unpacked: checked before it opens."""
    gz_size: int
    gz_sha256: str
    """The download, `<file>.gz` (gzip: Russian's 62.4 MB comes down as
    13.3), checked whole before it's unpacked."""
    licence: str
    credits: str
    """One line: whose data it is, under what licence - said on Learning."""
    credits_text: str = ""
    """The pack's credits in full (Markdown), written beside its file."""
    riders: tuple[Rider, ...] = ()
    """The files that go with this version of the pack (decision 0133)."""

    @property
    def key(self) -> tuple[str, str]:
        return self.language, self.meanings

    @property
    def download(self) -> str:
        """The file to download: the pack, gzipped."""
        return self.file + ".gz"


def rider_language(text: str) -> bool:
    """Whether a meanings rider can be in `text`: a code (`es`) or one of
    `RIDER_LOCALES` (`zh_TW`)."""
    return bool(CODE.fullmatch(text)) or text in RIDER_LOCALES


def version_key(text: str) -> tuple[int, ...] | None:
    """`2026.11.14` -> (2026, 11, 14); None if it isn't dotted numbers."""
    try:
        parts = tuple(int(part) for part in text.split("."))
    except ValueError:
        return None
    return parts if all(p >= 0 for p in parts) else None


def newer(candidate: str, than: str) -> bool:
    """Whether version `candidate` is after `than` (unreadable: never)."""
    a, b = version_key(candidate), version_key(than)
    return a is not None and b is not None and a > b


def safe_file_name(name: str) -> bool:
    """Whether `name` is one this PC may write: a plain name (no path), no
    `..`, not ending in a dot or a space (Windows drops them, so two names
    would be one file), and not a Windows device's (`nul`, `com1`, ...)."""
    return (
        PLAIN_NAME.fullmatch(name) is not None
        and ".." not in name
        and not name.endswith((".", " "))
        and name.split(".")[0].lower() not in WINDOWS_DEVICES
    )


def list_serial(data: bytes) -> int:
    """A list's serial: one more at every publish (signed with it), so an
    older list served again can be told from the newest (`PackList`).
    PackListError if it has none."""
    try:
        serial = json.loads(data).get("serial")
    except (ValueError, UnicodeDecodeError, AttributeError):
        raise PackListError("the list isn't JSON") from None
    if not isinstance(serial, int) or isinstance(serial, bool) or serial < 1:
        raise PackListError("the list has no serial")
    return serial


def read_pack_list(data: bytes) -> tuple[tuple[PackOffer, ...], int]:
    """The offers in a list's bytes, and how many entries were left out for
    being malformed (a list we signed holds none: each would be our bug,
    and leaving one out keeps the others). PackListError if the whole
    isn't a list of this format, or has no serial (`list_serial`)."""
    try:
        whole = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise PackListError("the list isn't JSON") from None
    if not isinstance(whole, dict) or not isinstance(whole.get("packs"), list):
        raise PackListError("the list has no packs")
    if whole.get("list") != LIST_FORMAT:
        raise PackListError("the list is another format")
    list_serial(data)
    offers, left_out = [], 0
    for raw in whole["packs"]:
        offer = _offer(raw)
        if offer is None:
            left_out += 1
        else:
            offers.append(offer)
    return tuple(offers), left_out


def _offer(raw: object) -> PackOffer | None:
    if not isinstance(raw, dict):
        return None
    texts = (
        "language",
        "meanings",
        "dictionary",
        "version",
        "format",
        "split",
        "min_app",
        "file",
        "sha256",
        "gz_sha256",
        "licence",
        "credits",
    )
    if not all(isinstance(raw.get(name), str) for name in texts):
        return None
    sizes = {name: raw.get(name) for name in ("size", "gz_size")}
    if not all(
        isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in sizes.values()
    ):
        return None
    credits_text = raw.get("credits_text", "")
    if not isinstance(credits_text, str):
        return None
    offer = PackOffer(
        **{name: raw[name] for name in texts},
        size=int(raw["size"]),
        gz_size=int(raw["gz_size"]),
        credits_text=credits_text,
        riders=_riders(raw.get("riders"), raw["dictionary"]),
    )
    if not (
        CODE.fullmatch(offer.language)
        and CODE.fullmatch(offer.meanings)
        and DICTIONARY_NAME.fullmatch(offer.dictionary)
        and offer.dictionary not in WINDOWS_DEVICES
        and safe_file_name(offer.file)
        and offer.file.endswith(PACK_SUFFIX)
        and offer.file.startswith(f"{offer.dictionary}-{offer.meanings}-")
        and SHA256_HEX.fullmatch(offer.sha256)
        and SHA256_HEX.fullmatch(offer.gz_sha256)
        and version_key(offer.version) is not None
        and version_key(offer.min_app) is not None
    ):
        return None
    return offer


@dataclass(frozen=True)
class BuiltIn:
    """The riders of a dictionary built into the app (decision 0197):
    `dictionary` is its name (`cedict`), `language` the one it's learned
    for (`zh`)."""

    dictionary: str
    language: str
    riders: tuple[Rider, ...]


def read_built_in(data: bytes) -> tuple[BuiltIn, ...]:
    """The built-in dictionaries' riders a list names (`built_in`): an
    entry that is malformed is left out, as are its riders that are
    (`_riders`). Only for a list `read_pack_list` has read: anything else
    has none."""
    try:
        whole = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return ()
    raw = whole.get("built_in") if isinstance(whole, dict) else None
    found = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict):
            continue
        dictionary, language = item.get("dictionary"), item.get("language")
        if not (
            isinstance(dictionary, str)
            and isinstance(language, str)
            and DICTIONARY_NAME.fullmatch(dictionary)
            and CODE.fullmatch(language)
        ):
            continue
        riders = _riders(item.get("riders"), dictionary)
        if riders:
            found.append(BuiltIn(dictionary, language, riders))
    return tuple(found)


@dataclass(frozen=True)
class FontOffer:
    """A caption face published for download (polyglotic-hq 482, decision
    0223): `font` is its name in the list - the start of its files' names,
    and the app's name for it (`ui_next.fonts.PACKED`) - `family` the
    family its files hold, `credits` one line: whose face, under what
    licence; its files are its riders (kind `font`: its faces and their
    licence text)."""

    font: str
    family: str
    credits: str
    riders: tuple[Rider, ...]

    def size(self, reader: "Reader") -> int:
        """What comes down for this app: its riders' downloads."""
        return sum(rider.gz_size for rider in riders_wanted(self, reader))


def read_fonts(data: bytes) -> tuple[FontOffer, ...]:
    """The caption faces a list offers (`fonts`): an entry that is
    malformed, or has no face this code reads, is left out. Fields a newer
    list adds are ignored. Only for a list `read_pack_list` has read:
    anything else has none."""
    try:
        whole = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return ()
    raw = whole.get("fonts") if isinstance(whole, dict) else None
    found = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict):
            continue
        font, family, credits = (
            item.get("font"),
            item.get("family"),
            item.get("credits"),
        )
        if not (
            isinstance(font, str)
            and isinstance(family, str)
            and isinstance(credits, str)
            and DICTIONARY_NAME.fullmatch(font)
            and 0 < len(family) <= 100
        ):
            continue
        riders = tuple(
            rider for rider in _riders(item.get("riders"), font) if rider.kind == "font"
        )
        if any(rider.file.endswith((".ttf", ".otf")) for rider in riders):
            found.append(FontOffer(font, family, credits, riders))
    return tuple(found)


def _riders(raw: object, dictionary: str) -> tuple[Rider, ...]:
    """A pack's riders as its entry lists them: one that is malformed, or of
    a kind this code doesn't know, is left out - the pack and its other
    riders stay. Fields a newer list adds are ignored."""
    found = []
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict):
            continue
        texts = ("kind", "format", "min_app", "file", "sha256", "gz_sha256")
        sizes = [item.get("size"), item.get("gz_size")]
        if not all(isinstance(item.get(name), str) for name in texts) or not all(
            isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in sizes
        ):
            continue
        language = item.get("meanings") if item["kind"] == "meanings" else ""
        rider = Rider(
            **{name: item[name] for name in texts},
            size=int(item["size"]),
            gz_size=int(item["gz_size"]),
            meanings=language if isinstance(language, str) else "",
        )
        suffix = RIDER_SUFFIXES.get(rider.kind)
        if (
            suffix is not None
            and safe_file_name(rider.file)
            and rider.file.endswith(suffix)
            and rider.file.startswith(f"{dictionary}-")
            and version_key(rider.min_app) is not None
            and SHA256_HEX.fullmatch(rider.sha256)
            and SHA256_HEX.fullmatch(rider.gz_sha256)
            and (
                rider.kind != "meanings"
                or rider_language(rider.meanings)
                and rider.file.startswith(f"{dictionary}-{rider.meanings}-")
            )
        ):
            found.append(rider)
    return tuple(found)


@dataclass(frozen=True)
class Reader:
    """What this app reads: the file formats, the word splits it has, its
    version (`FROM_SOURCE`: any `min_app`), and the riders' kinds and
    formats (`riders`: `("audio", "1")`)."""

    formats: frozenset[str]
    splits: frozenset[str]
    app_version: str
    riders: frozenset[tuple[str, str]] = frozenset()

    def reads(self, offer: PackOffer) -> bool:
        if offer.format not in self.formats or offer.split not in self.splits:
            return False
        return self.new_enough(offer.min_app)

    def new_enough(self, min_app: str) -> bool:
        """Whether this app is `min_app` or newer (from source: always)."""
        if self.app_version == FROM_SOURCE:
            return True
        app = version_key(self.app_version)
        needed = version_key(min_app)
        return app is not None and needed is not None and app >= needed


def _for(offers: Iterable[PackOffer], language: str, meanings: str) -> list[PackOffer]:
    """`language`'s offers in `meanings`, or in English if there are none in
    `meanings` (every pack has an English file)."""
    found = [o for o in offers if o.language == language]
    wanted = [o for o in found if o.meanings == meanings]
    return wanted or [o for o in found if o.meanings == "en"]


def best_offer(
    offers: Sequence[PackOffer], language: str, meanings: str, reader: Reader
) -> PackOffer | None:
    """The pack this app gets for `language`: the newest version it reads,
    meanings in `meanings` (else English). None: none it reads."""
    readable = [o for o in _for(offers, language, meanings) if reader.reads(o)]
    if not readable:
        return None
    return max(readable, key=lambda o: version_key(o.version) or ())


def needs_newer_app(
    offers: Sequence[PackOffer], language: str, meanings: str, reader: Reader
) -> bool:
    """`language` has packs, but only ones this app can't read: a newer
    Polyglotic reads them (say so; never offer them)."""
    found = _for(offers, language, meanings)
    compatible = [
        o for o in found if o.format in reader.formats and o.split in reader.splits
    ]
    return bool(compatible) and not any(
        reader.new_enough(o.min_app) for o in compatible
    )


def needs_meanings_rider(dictionary: str, own: str | None, requested: str) -> bool:
    """Whether the dictionary may use a rider in the learner's language."""
    # JMdict's Chinese pack still has English fallbacks for these drafts.
    return requested != own or (dictionary == "jmdict" and requested == "zh")


def riders_wanted(
    offer: PackOffer | BuiltIn | FontOffer,
    reader: Reader,
    explained_in: str | None = None,
) -> list[Rider]:
    """The riders of `offer` (a pack's, a built-in dictionary's or a caption
    face's) this app takes: those of a kind and format it reads, and whose
    `min_app` it is - of the meanings, only those in `explained_in` (the
    learner's language; None: none), when the dictionary can use a rider in that language."""
    own = offer.meanings if isinstance(offer, PackOffer) else None
    dictionary = offer.dictionary if isinstance(offer, PackOffer) else ""
    return [
        rider
        for rider in offer.riders
        if (rider.kind, rider.format) in reader.riders
        and reader.new_enough(rider.min_app)
        and (
            rider.kind != "meanings"
            or (
                rider.meanings == explained_in
                and needs_meanings_rider(dictionary, own, rider.meanings)
            )
        )
    ]


@dataclass(frozen=True)
class InstalledPack:
    """A pack on this PC, as its file's own `info` says."""

    language: str
    meanings: str
    dictionary: str
    version: str
    file: str
    size: int


def update_for(
    installed: InstalledPack, offers: Sequence[PackOffer], reader: Reader
) -> PackOffer | None:
    """A newer version of `installed` this app reads, in its meanings
    language - None if it's the newest (or the list has no newer one it
    reads: an app too old for the next format keeps the pack it has)."""
    best = best_offer(offers, installed.language, installed.meanings, reader)
    if best is None or best.meanings != installed.meanings:
        return None
    return best if newer(best.version, installed.version) else None
