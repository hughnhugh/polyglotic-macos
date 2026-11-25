"""The separately delivered data file used by SudachiPy's Japanese split."""

from polyglotic_desktop.core.lexicon.packs import Rider

OBJECT_NAME = "packs/v1/sudachidict-small-20261015.system.dic.gz"
"""Stable update-storage object name; pinned because it is not in the signed list."""
FILE_NAME = "sudachidict-small-20261015.system.dic"
SIZE_BYTES = 115_306_595
SHA256 = "c5e2bb9988cc88b05c37734d985eac59c9c4b35353187f068c605f3d3908716a"
GZIP_SIZE_BYTES = 42_439_181
GZIP_SHA256 = "6a47afe552095c4f54c61252bdde2bf4cd31e98fe4c65ab1d4aac74ca107fec3"
"""Pinned sizes and hashes verify both the compressed upload and usable dictionary."""

RIDER = Rider(
    kind="japanese-dictionary",
    format="sudachi-small-20261015",
    min_app="0.1.12",
    file=FILE_NAME,
    size=SIZE_BYTES,
    sha256=SHA256,
    gz_size=GZIP_SIZE_BYTES,
    gz_sha256=GZIP_SHA256,
)
