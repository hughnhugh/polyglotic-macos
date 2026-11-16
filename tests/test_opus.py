"""Speech as Ogg Opus (platform.opus), on synthetic audio."""

import io

import numpy as np
import soundfile as sf

from polyglotic_desktop.platform.opus import _crc32, _trim_tags, encode_ogg_opus

SR = 16000


def tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (
        0.3 * np.sin(2 * np.pi * 440 * t) * (1 + np.sin(2 * np.pi * 3 * t)) / 2
    ).astype(np.float32)


def pages(ogg: bytes) -> list[tuple[bytes, bytes]]:
    """(header, body) of each Ogg page."""
    out, i = [], 0
    while i < len(ogg):
        assert ogg[i : i + 4] == b"OggS"
        segments = ogg[i + 26]
        header_len = 27 + segments
        body_len = sum(ogg[i + 27 : i + header_len])
        out.append(
            (ogg[i : i + header_len], ogg[i + header_len : i + header_len + body_len])
        )
        i += header_len + body_len
    return out


def crc_ok(header: bytes, body: bytes) -> bool:
    blank = header[:22] + b"\0\0\0\0" + header[26:]
    return _crc32(blank + body) == int.from_bytes(header[22:26], "little")


def test_round_trip_decodes_alone_at_16khz() -> None:
    audio = tone(2.0)
    decoded, rate = sf.read(io.BytesIO(encode_ogg_opus(audio)), dtype="float32")
    assert rate == SR and len(decoded) == len(audio)
    assert np.corrcoef(audio, decoded)[0, 1] > 0.9


def test_page_checksums_match_libsndfiles() -> None:
    out = io.BytesIO()
    sf.write(out, tone(1.0), SR, format="OGG", subtype="OPUS")
    assert all(crc_ok(h, b) for h, b in pages(out.getvalue()))


def test_tag_padding_is_trimmed_and_the_stream_stays_valid() -> None:
    out = io.BytesIO()
    sf.write(out, tone(1.0), SR, format="OGG", subtype="OPUS")
    original = out.getvalue()
    trimmed = _trim_tags(original)
    before, after = pages(original), pages(trimmed)
    assert len(before[1][1]) > 700 and len(after[1][1]) < 64
    assert after[1][1].startswith(b"OpusTags")
    assert all(crc_ok(h, b) for h, b in after)
    assert [p for i, p in enumerate(after) if i != 1] == [
        p for i, p in enumerate(before) if i != 1
    ]
    decoded, _ = sf.read(io.BytesIO(trimmed), dtype="float32")
    reference, _ = sf.read(io.BytesIO(original), dtype="float32")
    assert np.array_equal(decoded, reference)


def test_higher_bitrate_is_bigger() -> None:
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.1, SR * 3).astype(np.float32)
    assert len(encode_ogg_opus(noise, 16_000)) < len(encode_ogg_opus(noise, 32_000))


def test_stream_is_mono_16khz_opus() -> None:
    head = pages(encode_ogg_opus(tone(0.5)))[0][1]
    assert head[:8] == b"OpusHead" and head[9] == 1  # one channel
    assert int.from_bytes(head[12:16], "little") == SR  # input sample rate
