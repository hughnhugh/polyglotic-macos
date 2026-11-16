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
FROM_SOURCE = "0.0.0"
"""The version an app run from source has (`connection.app`): it reads
every pack its formats and word splits allow, whatever `min_app` says."""


class PackListError(ValueError):
    """The list can't be read as a list at all (not its shape, or a newer
    list format). Says which, never the contents."""


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

    @property
    def key(self) -> tuple[str, str]:
        return self.language, self.meanings

    @property
    def download(self) -> str:
        """The file to download: the pack, gzipped."""
        return self.file + ".gz"


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
class Reader:
    """What this app reads: the file formats, the word splits it has, and
    its version (`FROM_SOURCE`: any `min_app`)."""

    formats: frozenset[str]
    splits: frozenset[str]
    app_version: str

    def reads(self, offer: PackOffer) -> bool:
        if offer.format not in self.formats or offer.split not in self.splits:
            return False
        if self.app_version == FROM_SOURCE:
            return True
        app = version_key(self.app_version)
        needed = version_key(offer.min_app)
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
    return bool(found) and not any(reader.reads(o) for o in found)


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
