"""wordfreq's data files, written for the dictionary tools' tests: the
Chinese build's (`test_build`) and the packs' (`test_packs`). Here, not in
either test file, so the packs' tests don't load the Chinese build (the
packs workflow's paths, polyglotic-hq 234)."""


def msgpack(value: object) -> bytes:
    """Just enough MessagePack to write a wordfreq data file."""
    if isinstance(value, int):
        return bytes([value])
    if isinstance(value, str):
        data = value.encode("utf-8")
        return bytes([0xA0 | len(data)]) + data
    if isinstance(value, dict):
        pairs = b"".join(msgpack(k) + msgpack(v) for k, v in value.items())
        return bytes([0x80 | len(value)]) + pairs
    assert isinstance(value, list)
    if len(value) < 16:
        head = bytes([0x90 | len(value)])
    else:
        head = b"\xdc" + len(value).to_bytes(2, "big")
    return head + b"".join(msgpack(v) for v in value)
