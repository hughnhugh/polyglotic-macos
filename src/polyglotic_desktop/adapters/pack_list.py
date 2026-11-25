"""The dictionary packs' list, checked against our own signature
(decision 0122) - the same keys and the same check as the update feed's
(decision 0019), so there is one trust path, not two.

The list is one file, `packs/v1/list.signed` on the update storage: a
line of base64 - an Ed25519 signature, by the feed's key, of
`SIGNED_PREFIX` and the list's exact bytes - then the list itself. One
file, so a publish replaces both at once: no app can read a new
signature beside an old list, or the other way round. The prefix is the
list's own, so a feed's signature can never pass for a list's, nor a
list's for a feed's.

The list carries a serial, one more at every publish. A list that passes
is kept on this PC (`kept`), so Learning can say a pack's size offline,
and checked again when read; a list with a lower serial than the one kept
- an old, genuinely signed list served again - is refused, so it can't
hide a newer pack. (A PC that has never read a list can't tell; what an
old list offers is still a pack we signed, checked whole.)

Each pack's file is checked whole against the list's size and SHA-256
before anything opens it (`adapters.pack_downloads`): whoever holds the
storage or the domain can stop packs arriving, never change one. Where
they come from is `https://` on the list's own host (a loopback `http://`
stand-in only for tests and a developer's runs).
"""

import binascii
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import urlsplit

from nacl.signing import VerifyKey

from polyglotic_desktop.adapters.signed_feed import FeedNotTrusted, fetch, verify
from polyglotic_desktop.core.lexicon.packs import (
    LIST_FORMAT,
    BuiltIn,
    FontOffer,
    PackListError,
    PackOffer,
    Rider,
    list_serial,
    read_built_in,
    read_fonts,
    read_pack_list,
)

log = logging.getLogger(__name__)

FOLDER = f"packs/v{LIST_FORMAT}/"
"""Where the list is, under the update storage's address."""
LIST_NAME = "list.signed"
FILES = "packs/files/"
"""Where every pack's file is, under the update storage's address: one
name per version, never replaced, so a download carried on from is always
the same file."""
LIST_BYTES_MAX = 4_000_000  # a list is tens of KB: anything this big is wrong
SIGNED_PREFIX = b"Polyglotic dictionary packs 1\n"
"""What every signed list starts with: what it is, and the signing format's
number - a signature over anything else can't pass for a list's."""
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class PackListNotTrusted(Exception):
    """The list or its signature isn't what we signed, can't be read, or
    is older than the one kept. Says which check failed, never the
    contents."""


def signed_list_message(data: bytes) -> bytes:
    """What the publishing command signs and the app checks: the prefix,
    then the list's exact bytes."""
    return SIGNED_PREFIX + data


def signed_list_file(signature: bytes, data: bytes) -> bytes:
    """The one file published: the signature's base64 on a line, then the
    list."""
    return signature.strip() + b"\n" + data


def split_signed_list(whole: bytes) -> tuple[bytes, bytes]:
    """`signed_list_file` read back: (signature, list)."""
    signature, newline, data = whole.partition(b"\n")
    if not newline:
        raise PackListNotTrusted("the list has no signature")
    return signature, data


def signed_data(whole: bytes) -> bytes:
    """A signed list file's list, its signature set aside: only for one
    `PackList._checked` has passed."""
    return split_signed_list(whole)[1]


def storage_address(base: str) -> str:
    """`base` if packs may come from it - `https://`, or a loopback
    `http://` stand-in - with a trailing slash. ValueError otherwise."""
    parts = urlsplit(base)
    secure = parts.scheme == "https" and bool(parts.hostname)
    stand_in = parts.scheme == "http" and parts.hostname in LOOPBACK
    if not (secure or stand_in):
        raise ValueError("packs come over https only")
    return base if base.endswith("/") else base + "/"


class PackList:
    """The signed list at `base` (the update storage's `https://` address),
    checked, and its last good copy kept in `kept` (a folder)."""

    def __init__(
        self,
        base: str,
        keys: Sequence[VerifyKey],
        kept: Path,
        get: Callable[[str], bytes] = fetch,
    ) -> None:
        if not keys:
            raise ValueError("the packs' list needs at least one public key")
        self.base = storage_address(base)
        self._keys = keys
        self._kept = kept
        self._get = get
        self.built_in: tuple[BuiltIn, ...] = ()
        """The built-in dictionaries' riders (decision 0197) of the list
        last fetched or kept (`fetch`, `kept`)."""
        self.fonts: tuple[FontOffer, ...] = ()
        """The caption faces it offers (polyglotic-hq 482), the same way."""

    @property
    def address(self) -> str:
        return self.base + FOLDER + LIST_NAME

    def file_address(self, offer: PackOffer | Rider) -> str:
        """Where `offer`'s download is - its file, gzipped (a plain name: the
        list's reader refused any other), on the list's own host."""
        if isinstance(offer, Rider) and offer.kind == "japanese-dictionary":
            from polyglotic_desktop.adapters.japanese_dictionary import OBJECT_NAME

            return self.base + OBJECT_NAME
        return self.base + FILES + offer.download

    def fetch(self) -> tuple[PackOffer, ...]:
        """The list, fetched and checked, then kept. Raises
        PackListNotTrusted if a check fails or it's older than the one kept
        (the kept copy stays as it was), and the fetch's own OSError if it
        can't be fetched."""
        whole = self._get(self.address)
        offers, serial, built_in = self._checked(whole)
        kept = self._kept_serial()
        if kept is not None and serial < kept:
            raise PackListNotTrusted("the list is older than the one kept")
        self._kept.mkdir(parents=True, exist_ok=True)
        part = self._kept / (LIST_NAME + ".part")
        part.write_bytes(whole)
        part.replace(self._kept / LIST_NAME)  # one file, one rename: never half
        self.built_in = built_in
        self.fonts = read_fonts(signed_data(whole))
        return offers

    def kept(self) -> tuple[PackOffer, ...] | None:
        """The list as last fetched, checked again - None if there's none,
        or it doesn't pass now (a key retired since, a file changed)."""
        try:
            whole = (self._kept / LIST_NAME).read_bytes()
            offers, _, self.built_in = self._checked(whole)
            self.fonts = read_fonts(signed_data(whole))
            return offers
        except (OSError, PackListNotTrusted) as e:
            if not isinstance(e, FileNotFoundError):
                log.info("kept packs list not used (%s)", type(e).__name__)
            return None

    def _kept_serial(self) -> int | None:
        try:
            return self._checked((self._kept / LIST_NAME).read_bytes())[1]
        except (OSError, PackListNotTrusted):
            return None

    def _checked(
        self, whole: bytes
    ) -> tuple[tuple[PackOffer, ...], int, tuple[BuiltIn, ...]]:
        if len(whole) > LIST_BYTES_MAX:
            raise PackListNotTrusted("the list is too big")
        signature, data = split_signed_list(whole)
        try:
            verify(signed_list_message(data), signature, self._keys)
        except (FeedNotTrusted, binascii.Error) as e:
            message = str(e) if isinstance(e, FeedNotTrusted) else "not base64"
            raise PackListNotTrusted(message.replace("feed", "list")) from None
        try:
            offers, left_out = read_pack_list(data)
            serial = list_serial(data)
        except PackListError as e:
            raise PackListNotTrusted(str(e)) from None
        if left_out:
            log.warning("packs list: %d entries can't be read, left out", left_out)
        return offers, serial, read_built_in(data)
