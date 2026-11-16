"""Speech compressed for sending: Ogg Opus, mono, 16kHz (decision 0005).

Each live update or finished caption is sent as one complete Ogg Opus
stream (RFC 7845) that decodes on its own: the `OpusHead` and `OpusTags`
headers, then the audio in 20ms Opus frames at about `OPUS_BITRATE`.

Encoded by libsndfile through `soundfile` (libsndfile 1.2.2 with libopus
1.5.2, at complexity 10). libsndfile sets Opus's target bitrate from its
"compression level" q as (1 - q) x 250,000 + 6,000 bit/s per channel
(`ogg_opus.c`, `SFC_SET_COMPRESSION_LEVEL`), and reserves about 760 bytes
of padding in `OpusTags` for tags it might add; `_trim_tags` drops that
padding, which RFC 7845 allows, so a 1.5s live update is ~18% smaller.
"""

import io
import struct

import soundfile as sf

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.platform.speech_detection import Audio

OPUS_BITRATE = 24_000  # target, bits per second (VBR: speech averages ~21k)
_MIN_BITRATE, _BITRATE_RANGE = 6_000, 250_000  # libsndfile's mapping


def encode_ogg_opus(audio: Audio, bitrate: int = OPUS_BITRATE) -> bytes:
    """16kHz mono float audio as one self-contained Ogg Opus stream."""
    out = io.BytesIO()
    level = 1.0 - (bitrate - _MIN_BITRATE) / _BITRATE_RANGE
    sf.write(
        out,
        audio,
        VAD_SAMPLE_RATE,
        format="OGG",
        subtype="OPUS",
        compression_level=level,
    )
    return _trim_tags(out.getvalue())


def _crc32(data: bytes) -> int:
    """Ogg's page checksum: CRC-32, polynomial 0x04C11DB7, not reflected,
    starting at 0, no final XOR."""
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else crc << 1
            crc &= 0xFFFFFFFF
    return crc


def _trim_tags(ogg: bytes) -> bytes:
    """`ogg` with the padding after the `OpusTags` comment list removed.

    The tags are the whole second page (libsndfile writes them so); only
    that page's body, segment table and checksum change."""
    first_len = 27 + ogg[26] + sum(ogg[27 : 27 + ogg[26]])
    page = ogg[first_len:]
    segments = page[26]
    header_len = 27 + segments
    body_len = sum(page[27:header_len])
    body = page[header_len : header_len + body_len]
    if not body.startswith(b"OpusTags") or page[header_len - 1] == 255:
        return ogg  # not the layout we know (or the tags continue): leave it
    end = 8 + 4 + struct.unpack_from("<I", body, 8)[0]  # magic, vendor
    (count,) = struct.unpack_from("<I", body, end)
    end += 4
    for _ in range(count):
        end += 4 + struct.unpack_from("<I", body, end)[0]
    trimmed = body[:end]
    lacing = bytes([255] * (len(trimmed) // 255) + [len(trimmed) % 255])
    header = bytearray(page[:26]) + bytes([len(lacing)]) + lacing
    header[22:26] = b"\0\0\0\0"
    crc = _crc32(bytes(header) + trimmed)
    header[22:26] = crc.to_bytes(4, "little")
    rest = page[header_len + body_len :]
    return ogg[:first_len] + bytes(header) + trimmed + rest
