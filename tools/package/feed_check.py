"""The daily feed check: is each channel's public update feed what we published?

Run by `.github/workflows/feed-check.yml` (polyglotic-hq project 032, D5
item 8; decisions 0018, 0020 and 0044). A tag has one GitHub Release; each
channel the tag's build is published to records on it a
`SHA256SUMS-<channel>` of what it published there: the channel's feed as
the storage served it after the upload merged it, the feed's signature,
the installer and the full package. Anyone who could write the update storage or change the domain's
DNS could serve testers other code; this compares those files as the
public feed serves them now.

**Each channel against its own latest published Release** (project 066,
Low 5): following only the newest Release overall would stop checking the
alpha's feed once a beta release is newest - while alpha testers still run
the alpha. A channel's latest is the highest version whose Release records
that channel - not the latest by date: a promotion adds a channel to an
older tag's Release (decision 0044). A channel with no published Release
yet is skipped; drafts (release.yml's runs before the update storage
existed) published nothing.

    GH_TOKEN=... GH_REPO=owner/repo UPDATE_FEED=https://updates.<domain>/ \\
        python -m tools.package.feed_check

Exits 1 - which emails the repo's owner from Actions - on any difference,
a file not served, a Release that records no feed for its channel, or no
published Release at all. Standard library only: the workflow runs it
without installing the app.
"""

from __future__ import annotations

import base64
import binascii
import fnmatch
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence

CHANNELS = ("win-x64-alpha", "win-x64-beta", "win-x64-stable")
"""The app's Windows update channels (core.releases.updates.CHANNELS'
`win-x64-*`; a test keeps them equal - this runs without the app
installed). Windows' releases only: the Mac's and Linux's channels aren't
published through a tag's Release (polyglotic-hq 580)."""

LINUX_CHANNELS = ("linux-x64-alpha",)
"""Linux update channels checked directly against the public feed (polyglotic-hq
592, 646): Linux isn't published through a GitHub Release, so a 404 feed means
'not published yet', while a present feed must carry a valid signature and its
AppImage and newest full package must answer."""

FEED_KEYS: tuple[str, ...] = ("T9JEreM5nPkehQOMIfPbjUz1+UoZ73pUJ7rslb72xBs=",)
"""The app's Ed25519 feed signing public keys (base64; a test keeps them equal
to `main.FEED_KEYS` since this script runs with the standard library only)."""

SIGNED_PREFIX = b"Polyglotic update feed 1\n"
"""Matches `adapters.signed_feed.SIGNED_PREFIX`."""

PLAIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REQUEST_HEADERS = {"User-Agent": "Polyglotic/0.1 (https://polyglotic.io)"}
"""Matches `core.shared.client.HEADERS` so Cloudflare accepts the check."""
FEED_BYTES_MAX = 4_000_000
SIGNATURE_BYTES = 64
HTTP_TIMEOUT_SEC = 60

COMPARED = ("releases.*.json", "releases.*.json.sig", "*-Setup.exe", "*-full.nupkg")
"""The files compared: the feed, its signature, the installer and the full
package. Velopack's other files (RELEASES-<channel>, assets.<channel>.json,
deltas) aren't what the app reads."""

TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def sums_asset(channel: str) -> str:
    """The asset that records what a channel was published: `SHA256SUMS-win-x64-beta`."""
    return f"SHA256SUMS-{channel}"


def linux_appimage(channel: str) -> str:
    """The AppImage object name on the update host for `channel` (592)."""
    return f"Polyglotic-{channel}.AppImage"


Served = Callable[[str], "str | None"]
"""A URL -> the SHA-256 of what it serves now, or None if it serves nothing."""
FetchBytes = Callable[[str], "tuple[int | None, bytes]"]
"""A URL -> (HTTP status or None if unreachable, body bytes)."""
Answers = Callable[[str], bool]
"""A URL -> True if the object is served (HTTP 200/206 with non-empty content)."""


# -- stdlib Ed25519 verification (RFC 8032 §5.1.7) ---------------------------------
# Runs under `uv run --no-project --python 3.12` without PyNaCl installed;
# cross-checked against `adapters.signed_feed.verify` (PyNaCl) in tests.

_ED_P = 2**255 - 19
_ED_L = 2**252 + 27742317777372353535851937790883648493
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)
_ED_BY = (4 * pow(5, _ED_P - 2, _ED_P)) % _ED_P


def _ed_recover_x(y: int, sign: int) -> int | None:
    if y >= _ED_P:
        return None
    x2 = ((y * y - 1) * pow(_ED_D * y * y + 1, _ED_P - 2, _ED_P)) % _ED_P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_ED_P + 3) // 8, _ED_P)
    if (x * x - x2) % _ED_P != 0:
        x = (x * _ED_I) % _ED_P
    if (x * x - x2) % _ED_P != 0:
        return None
    if (x & 1) != sign:
        x = _ED_P - x
    return x


_ED_BX = _ed_recover_x(_ED_BY, 0)
assert _ED_BX is not None
_ED_B = (_ED_BX, _ED_BY, 1, (_ED_BX * _ED_BY) % _ED_P)
_ED_ID = (0, 1, 1, 0)
_Point = tuple[int, int, int, int]


def _ed_add(p1: _Point, p2: _Point) -> _Point:
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _ED_P
    b = ((y1 + x1) * (y2 + x2)) % _ED_P
    c = (2 * _ED_D * t1 * t2) % _ED_P
    d = (2 * z1 * z2) % _ED_P
    e = (b - a) % _ED_P
    f = (d - c) % _ED_P
    g = (d + c) % _ED_P
    h = (b + a) % _ED_P
    return ((e * f) % _ED_P, (g * h) % _ED_P, (f * g) % _ED_P, (e * h) % _ED_P)


def _ed_mul(scalar: int, point: _Point) -> _Point:
    acc = _ED_ID
    cur = point
    while scalar > 0:
        if scalar & 1:
            acc = _ed_add(acc, cur)
        cur = _ed_add(cur, cur)
        scalar >>= 1
    return acc


def _ed_equal(p1: _Point, p2: _Point) -> bool:
    x1, y1, z1, _ = p1
    x2, y2, z2, _ = p2
    return (x1 * z2 - x2 * z1) % _ED_P == 0 and (y1 * z2 - y2 * z1) % _ED_P == 0


def _ed_decode(raw: bytes) -> _Point | None:
    if len(raw) != 32:
        return None
    value = int.from_bytes(raw, "little")
    y = value & ((1 << 255) - 1)
    sign = value >> 255
    x = _ed_recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, (x * y) % _ED_P)


def _ed25519_verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != SIGNATURE_BYTES:
        return False
    a_pt = _ed_decode(public)
    r_pt = _ed_decode(signature[:32])
    if a_pt is None or r_pt is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _ED_L:
        return False
    h = hashlib.sha512(signature[:32] + public + message).digest()
    k = int.from_bytes(h, "little") % _ED_L
    return _ed_equal(_ed_mul(s, _ED_B), _ed_add(r_pt, _ed_mul(k, a_pt)))


def verify_feed_signature(
    channel: str, feed: bytes, signature: bytes, keys: Sequence[str] = FEED_KEYS
) -> str | None:
    """None if one of `keys` signed `feed` for `channel`, else a reason."""
    if not PLAIN_NAME.fullmatch(channel):
        return "not a channel name"
    try:
        raw_sig = base64.b64decode(signature.strip(), validate=True)
    except binascii.Error:
        return "the signature isn't base64"
    if len(raw_sig) != SIGNATURE_BYTES:
        return "the signature isn't 64 bytes"
    message = SIGNED_PREFIX + channel.encode("ascii") + b"\n" + feed
    for encoded in keys:
        try:
            pub = base64.b64decode(encoded.strip(), validate=True)
        except binascii.Error:
            continue
        if _ed25519_verify(pub, message, raw_sig):
            return None
    return "no key we trust signed this feed"


def _newest_full_package(feed: bytes) -> tuple[dict[str, object] | None, str | None]:
    """The newest full package in `feed`, or `(None, reason)`."""
    try:
        assets = json.loads(feed.decode("utf-8-sig"))["Assets"]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None, "the feed can't be read"
    if not isinstance(assets, list):
        return None, "the feed can't be read"
    full: list[tuple[tuple[int, ...], dict[str, object]]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if str(asset.get("Type", "")).lower() != "full":
            continue
        parts = str(asset.get("Version", "")).split(".")
        if not parts or not all(p.isdigit() for p in parts):
            continue
        full.append((tuple(int(p) for p in parts), asset))
    if not full:
        return None, "the feed has no full package"
    _, newest = max(full, key=lambda item: item[0])
    name, size, sha256 = (
        newest.get("FileName"),
        newest.get("Size"),
        newest.get("SHA256"),
    )
    if not isinstance(name, str) or not PLAIN_NAME.fullmatch(name) or ".." in name:
        return None, "a package's file name isn't a plain name"
    if not isinstance(size, int) or size <= 0 or not isinstance(sha256, str):
        return None, "a package's size or SHA-256 is missing"
    return newest, None


def check_linux_channel(
    channel: str,
    feed: str,
    fetch: FetchBytes,
    answers: Answers,
    keys: Sequence[str] = FEED_KEYS,
) -> list[str]:
    """One Linux channel on the public feed (646):
    - a 404 feed is 'not published yet', not a failure;
    - a present feed must carry a valid signature, a readable newest full
      package, and both its AppImage and newest full package must answer."""
    base = feed.rstrip("/")
    feed_name = f"releases.{channel}.json"
    status, body = fetch(f"{base}/{feed_name}")
    if status == 404:
        print(f"{channel}: not published yet - not checked")
        return []
    if status != 200:
        return [f"{feed_name}: HTTP {status if status is not None else 'unreachable'}"]
    if len(body) > FEED_BYTES_MAX:
        return [f"{feed_name}: the feed is too big"]
    problems: list[str] = []
    sig_name = f"{feed_name}.sig"
    sig_status, sig_body = fetch(f"{base}/{sig_name}")
    if sig_status != 200:
        problems.append(
            f"{sig_name}: {'not served' if sig_status in (404, None) else f'HTTP {sig_status}'}"
        )
    else:
        reason = verify_feed_signature(channel, body, sig_body, keys)
        if reason is not None:
            problems.append(f"{sig_name}: {reason}")
        else:
            print(f"{sig_name}: signature valid for {channel}")
    newest, parse_error = _newest_full_package(body)
    if parse_error is not None:
        problems.append(f"{feed_name}: {parse_error}")
    else:
        assert newest is not None
        pkg = str(newest["FileName"])
        if answers(f"{base}/{pkg}"):
            print(f"{pkg}: answers")
        else:
            problems.append(f"{pkg}: not served")
    appimage = linux_appimage(channel)
    if answers(f"{base}/{appimage}"):
        print(f"{appimage}: answers")
    else:
        problems.append(f"{appimage}: not served")
    return problems


def latest_per_channel(releases: Iterable[Mapping[str, object]]) -> dict[str, str]:
    """Each channel's latest published Release's tag, from `list_releases`
    rows (`tagName`, `isDraft`, `assets`): the highest version that records
    the channel."""
    latest: dict[str, tuple[tuple[int, ...], str]] = {}
    for row in releases:
        tag = str(row.get("tagName") or "")
        if row.get("isDraft") or not TAG.match(tag):
            continue
        version = tuple(int(part) for part in tag[1:].split("."))
        assets = row.get("assets") or ()
        assert isinstance(assets, list | tuple)
        for channel in CHANNELS:
            if sums_asset(channel) in assets and (
                channel not in latest or version > latest[channel][0]
            ):
                latest[channel] = (version, tag)
    return {channel: tag for channel, (_, tag) in latest.items()}


def recorded(sums: str) -> list[tuple[str, str]]:
    """The compared files in a SHA256SUMS (sha256sum's format), as (name,
    SHA-256), in its order."""
    files = []
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix("*")  # sha256sum's binary-mode mark
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in COMPARED):
            files.append((name, digest.lower()))
    return files


def check_channel(channel: str, sums: str, feed: str, served: Served) -> list[str]:
    """What the feed serves for one channel against its Release's
    SHA256SUMS: one line per problem, none if all is as published."""
    files = recorded(sums)
    if f"releases.{channel}.json" not in {name for name, _ in files}:
        return [f"the Release for {channel} records no releases.{channel}.json"]
    problems = []
    for name, published in files:
        actual = served(f"{feed.rstrip('/')}/{name}")
        if actual is None:
            problems.append(f"{name}: not served")
        elif actual != published:
            problems.append(f"{name}: served {actual}, published {published}")
        else:
            print(f"{name}: as published")
    return problems


def run(
    feed: str,
    releases: Iterable[Mapping[str, object]],
    download_sums: Callable[[str, str], str],
    served: Served,
    fetch_bytes: FetchBytes | None = None,
    answers: Answers | None = None,
    keys: Sequence[str] = FEED_KEYS,
) -> int:
    """Every Windows channel with a published Release against its latest one,
    plus each Linux channel directly against the public feed when `fetch_bytes`
    and `answers` are given."""
    latest = latest_per_channel(releases)
    if not latest:
        print("::error::no published Release to compare the feed with")
        return 1
    problems = []
    for channel in CHANNELS:
        if channel not in latest:
            print(f"{channel}: no published Release yet - not checked")
            continue
        tag = latest[channel]
        print(f"{channel}: the feed against {tag}")
        problems += check_channel(channel, download_sums(tag, channel), feed, served)
    if fetch_bytes is not None and answers is not None:
        for channel in LINUX_CHANNELS:
            problems += check_linux_channel(channel, feed, fetch_bytes, answers, keys)
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


API = "https://api.github.com"


def _request(url: str, accept: str) -> urllib.request.Request:
    """A GitHub API request with GH_TOKEN (the Linux runner image has no
    `gh`; this needs only the standard library)."""
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Lets a redirect through as an error, so the download's storage
    address can be fetched without GitHub's token (the storage refuses a
    second credential)."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def api_json(path: str) -> object:
    with urllib.request.urlopen(
        _request(f"{API}{path}", "application/vnd.github+json"), timeout=60
    ) as response:
        return json.load(response)


def list_releases(repo: str) -> list[dict[str, object]]:
    """Every Release of `repo`, in the keys `latest_per_channel` reads: its
    tag, whether it's a draft, and its assets' names."""
    rows: list[dict[str, object]] = []
    page = 1
    while True:
        chunk = api_json(f"/repos/{repo}/releases?per_page=100&page={page}")
        assert isinstance(chunk, list)
        rows += [
            {
                "tagName": r["tag_name"],
                "isDraft": r["draft"],
                "assets": [str(a["name"]) for a in r.get("assets", [])],
            }
            for r in chunk
        ]
        if len(chunk) < 100:
            return rows
        page += 1


def _sums_for(repo: str, tag: str, channel: str) -> str:
    """The Release's SHA256SUMS for `channel`; LookupError if it has none."""
    release = api_json(f"/repos/{repo}/releases/tags/{tag}")
    assert isinstance(release, dict)
    for asset in release.get("assets", []):
        if asset["name"] != sums_asset(channel):
            continue
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(_request(asset["url"], "application/octet-stream"), timeout=60)
        except urllib.error.HTTPError as redirect:
            if redirect.code not in (301, 302, 303, 307, 308):
                raise
            location = redirect.headers["Location"]
        else:
            raise LookupError(f"{tag}: the asset did not redirect")
        with urllib.request.urlopen(location, timeout=60) as response:
            return str(response.read().decode("utf-8"))
    raise LookupError(tag)


def _sums(tag: str, channel: str) -> str:
    """The Release's SHA256SUMS for `channel`; empty, said as an error, if
    it has none (check_channel then fails the channel)."""
    try:
        return _sums_for(os.environ["GH_REPO"], tag, channel)
    except (LookupError, urllib.error.URLError):
        print(f"::error::{tag}: no {sums_asset(channel)} on its Release")
        return ""


def _served(url: str) -> str | None:
    """The SHA-256 of what `url` serves, read in pieces (a full package is
    ~77MB); None for an HTTP error or no answer (curl -f's "not served")."""
    digest = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as response:
            while piece := response.read(1 << 20):
                digest.update(piece)
    except (urllib.error.URLError, TimeoutError):
        return None
    return digest.hexdigest()


def _fetch_bytes(url: str) -> tuple[int | None, bytes]:
    """Fetches a small public file (`releases.*.json`, `.sig`): `(status, body)`.
    `(None, b"")` if unreachable."""
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as response:
            return int(response.status), response.read(FEED_BYTES_MAX + 1)
    except urllib.error.HTTPError as error:
        return int(error.code), b""
    except (urllib.error.URLError, TimeoutError):
        return None, b""


def _answers(url: str) -> bool:
    """Whether `url` answers with non-empty content: HEAD first, falling back
    to a 1-byte ranged GET if HEAD is refused (405)."""
    head = urllib.request.Request(url, headers=REQUEST_HEADERS, method="HEAD")
    try:
        with urllib.request.urlopen(head, timeout=HTTP_TIMEOUT_SEC) as response:
            length = response.headers.get("Content-Length")
            return response.status == 200 and (
                length is None or (length.isdigit() and int(length) > 0)
            )
    except urllib.error.HTTPError as error:
        if error.code != 405:
            return False
    except (urllib.error.URLError, TimeoutError):
        return False
    ranged = urllib.request.Request(
        url, headers={**REQUEST_HEADERS, "Range": "bytes=0-0"}
    )
    try:
        with urllib.request.urlopen(ranged, timeout=HTTP_TIMEOUT_SEC) as response:
            return response.status in (200, 206) and bool(response.read(1))
    except (urllib.error.URLError, TimeoutError):
        return False


def main() -> int:
    feed = os.environ.get("UPDATE_FEED", "")
    if not feed.startswith("https://"):
        print("::error::UPDATE_FEED isn't an https:// address")
        return 1
    releases = list_releases(os.environ["GH_REPO"])
    return run(feed, releases, _sums, _served, _fetch_bytes, _answers)


if __name__ == "__main__":
    sys.exit(main())
