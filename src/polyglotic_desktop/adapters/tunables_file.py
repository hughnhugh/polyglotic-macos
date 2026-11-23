"""Read desktop tunables from TOML. The common file-free start skips the parser."""

from pathlib import Path


def read(path: Path, *, optional: bool = False) -> dict[str, object]:
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        if optional:
            return {}
        raise
    with stream:
        import tomllib

        raw = tomllib.load(stream)

    values: dict[str, object] = {}

    def flatten(prefix: str, table: dict[str, object]) -> None:
        for key, value in table.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flatten(name, value)
            elif name in values:
                raise ValueError(f"duplicate tunable {name}")
            else:
                values[name] = value

    flatten("", raw)
    return values
