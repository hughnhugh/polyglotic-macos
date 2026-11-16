"""Signing the update feed (decisions 0019 and 0020): the release workflow's half.

    python -m tools.package.sign_feed generate
        A new key pair: the private key for the `release` environment's
        secret FEED_SIGNING_KEY, the public key for main.FEED_KEYS. Run it
        on a trusted machine; keep the private key only in that secret and
        the password manager.

    python -m tools.package.sign_feed check BUILT SERVED
        Whether SERVED - the feed the update storage serves after `vpk
        upload` merged it with what was there - is a merge of BUILT, the
        feed `vpk pack` wrote, and not a tamper: every asset built is in it
        unchanged, and nothing in it is as new as this release or newer
        unless it was built here. Exit 1, saying which check failed,
        otherwise.

    FEED_SIGNING_KEY=... python -m tools.package.sign_feed sign SERVED --channel CHANNEL --built BUILT
        The same check, then SERVED.sig beside it: base64 of the Ed25519
        signature of the channel's name and the feed's exact bytes
        (`signed_feed.signed_message`), checked with the app's own
        verifier. Nothing is signed if the check fails.

    python -m tools.package.sign_feed verify FEED --channel CHANNEL --key PUBLIC
        Whether FEED.sig is a signature of FEED for CHANNEL by the public
        key PUBLIC, as the app checks it: before a public key goes into
        main.FEED_KEYS, check the published feed with it.

The private key is read from the environment, never from an argument or a
file in the repo, and never printed by `sign`. Ed25519 is libsodium's,
through PyNaCl, as in the app.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nacl.signing import SigningKey

from polyglotic_desktop.adapters.signed_feed import (
    FeedNotTrusted,
    public_keys,
    signed_message,
    verify,
)

KEY_VARIABLE = "FEED_SIGNING_KEY"
COMPARED = ("PackageId", "Version", "Type", "FileName", "SHA1", "SHA256", "Size")
"""An asset's fields that must be the same in the served feed as built."""


class NotOurMerge(Exception):
    """The served feed isn't the built feed merged with older releases.
    Says which check failed and the file name concerned, never more."""


def private_key_from(encoded: str) -> SigningKey:
    """The private key from its base64 (Ed25519's 32-byte seed); a line
    break or spaces around it, as a pasted secret may have, are ignored."""
    return SigningKey(base64.b64decode(encoded.strip(), validate=True))


def public_key_text(key: SigningKey) -> str:
    return base64.b64encode(key.verify_key.encode()).decode()


def _assets(feed: bytes, which: str) -> list[dict[str, object]]:
    try:
        assets = json.loads(feed)["Assets"]
    except (ValueError, KeyError, TypeError):
        raise NotOurMerge(f"the {which} feed can't be read") from None
    if not isinstance(assets, list) or not all(isinstance(a, dict) for a in assets):
        raise NotOurMerge(f"the {which} feed can't be read")
    return assets


def _version(asset: dict[str, object]) -> tuple[int, ...]:
    """MAJOR.MINOR.PATCH as numbers; releases have no other shape
    (decision 0015), so anything else is refused."""
    text = str(asset.get("Version", ""))
    parts = text.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise NotOurMerge(f"{asset.get('FileName')}: a version that isn't ours")
    return tuple(int(part) for part in parts)


def _same(built: dict[str, object], served: dict[str, object]) -> bool:
    return all(
        str(built.get(field, "")).lower() == str(served.get(field, "")).lower()
        for field in COMPARED
    )


def check_merge(built: bytes, served: bytes) -> None:
    """Nothing if `served` is `built` merged with older releases, as `vpk
    upload` merges it (Velopack's `_ObjectStore.cs`: the built assets
    first, then the storage's, one per file name, the oldest pruned);
    NotOurMerge otherwise. The served feed is what gets signed, so this
    stands between whatever the storage held and our signature:
    - every built asset is served, with the same fields (above all the
      SHA-256 and size);
    - nothing served is this release's version or newer unless it was
      built here - so the newest full package, the one the app takes, is
      ours, and nobody's newer one rides on our signature.
    Older releases the storage already had are kept as they are: the app
    never installs them (it takes the newest full package)."""
    built_assets = _assets(built, "built")
    served_assets = _assets(served, "served")
    full = [a for a in built_assets if str(a.get("Type", "")).lower() == "full"]
    if not full:
        raise NotOurMerge("the built feed has no full package")
    release = max(_version(a) for a in full)
    served_by_name: dict[str, dict[str, object]] = {}
    for asset in served_assets:
        name = str(asset.get("FileName", ""))
        if name in served_by_name:
            raise NotOurMerge(f"{name}: served twice")
        served_by_name[name] = asset
    for asset in built_assets:
        name = str(asset.get("FileName", ""))
        if name not in served_by_name:
            raise NotOurMerge(f"{name}: built, not served")
        if not _same(asset, served_by_name[name]):
            raise NotOurMerge(f"{name}: served, but not as built")
    built_names = {str(a.get("FileName", "")) for a in built_assets}
    for asset in served_assets:
        name = str(asset.get("FileName", ""))
        if name not in built_names and _version(asset) >= release:
            raise NotOurMerge(f"{name}: as new as this release, not built here")


def sign(feed: Path, channel: str, key: SigningKey) -> Path:
    """Writes `<feed>.sig` - the signature of `channel`'s name and the
    feed's bytes - and checks it as the app will."""
    message = signed_message(channel, feed.read_bytes())
    signature = base64.b64encode(key.sign(message).signature) + b"\n"
    verify(message, signature, [key.verify_key])
    out = feed.with_name(feed.name + ".sig")
    out.write_bytes(signature)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.package.sign_feed")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generate", help="make a new key pair")
    checking = commands.add_parser("check", help="is the served feed our merge?")
    checking.add_argument("built", type=Path)
    checking.add_argument("served", type=Path)
    signing = commands.add_parser(
        "sign", help=f"check, then sign the served feed with ${KEY_VARIABLE}"
    )
    signing.add_argument("served", type=Path)
    signing.add_argument("--channel", required=True)
    signing.add_argument("--built", type=Path, required=True)
    verifying = commands.add_parser("verify", help="check a feed's .sig")
    verifying.add_argument("feed", type=Path)
    verifying.add_argument("--channel", required=True)
    verifying.add_argument("--key", required=True, help="the public key, base64")
    args = parser.parse_args(argv)

    if args.command == "generate":
        key = SigningKey.generate()
        private = base64.b64encode(bytes(key)).decode()
        print(f"private (the secret {KEY_VARIABLE}): {private}")
        print(f"public (main.FEED_KEYS):              {public_key_text(key)}")
        return 0

    if args.command == "verify":
        feed = args.feed.read_bytes()
        signature = args.feed.with_name(args.feed.name + ".sig").read_bytes()
        try:
            verify(
                signed_message(args.channel, feed),
                signature,
                public_keys([args.key]),
            )
        except FeedNotTrusted as e:
            print(f"Not signed for {args.channel} by that key: {e}", file=sys.stderr)
            return 1
        print(f"{args.feed.name}: signed for {args.channel} by that key")
        return 0

    try:
        check_merge(args.built.read_bytes(), args.served.read_bytes())
    except NotOurMerge as e:
        print(f"The served feed isn't a merge of ours: {e}", file=sys.stderr)
        return 1
    if args.command == "check":
        print(f"{args.served.name}: a merge of the built feed")
        return 0

    encoded = os.environ.get(KEY_VARIABLE, "")
    if not encoded:
        print(f"No signing key: set {KEY_VARIABLE}", file=sys.stderr)
        return 1
    key = private_key_from(encoded)
    out = sign(args.served, args.channel, key)
    print(
        f"Signed {args.served.name} for {args.channel} -> {out.name}"
        f" (public key {public_key_text(key)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
