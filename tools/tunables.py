"""Inspect, check, or promote a desktop tunables file. Promotion edits the working tree."""

import argparse
import ast
import os
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from polyglotic_desktop.adapters.tunables_file import read
from polyglotic_desktop.core.shared.tunables import Value, declarations
from polyglotic_desktop.tunable_config import configuration

SOURCE = Path(__file__).resolve().parents[1] / "src" / "polyglotic_desktop"


def locations(root: Path) -> Iterator[tuple[str, Path, ast.expr]]:
    for path in sorted(root.rglob("*.py")):
        source = path.read_bytes()
        if b"tunable(" not in source:
            continue
        for call in ast.walk(ast.parse(source)):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "tunable"
            ):
                name, default = call.args[:2]
                if not isinstance(name, ast.Constant) or not isinstance(
                    name.value, str
                ):
                    raise ValueError(
                        f"expected a literal tunable name in {path.name}:{call.lineno}"
                    )
                yield name.value, path, default


def replace_bytes(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        staged = Path(temp.name)
        try:
            temp.write(content)
            temp.close()
            os.chmod(staged, path.stat().st_mode)
            os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)


def promote(root: Path, overrides: Mapping[str, Value]) -> None:
    edits: dict[Path, list[tuple[ast.expr, Value]]] = {}
    remaining = set(overrides)
    for name, path, node in locations(root):
        if name in overrides:
            remaining.remove(name)
            edits.setdefault(path, []).append((node, overrides[name]))
    if remaining:
        raise ValueError("missing declarations: " + ", ".join(sorted(remaining)))
    originals = {}
    replacements = {}
    for path, changes in edits.items():
        content = originals[path] = path.read_bytes()
        # AST columns count UTF-8 bytes. Keep comments, CRLF and all other bytes.
        offsets = [0]
        for line in content.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        for node, value in sorted(
            changes,
            key=lambda change: (change[0].lineno, change[0].col_offset),
            reverse=True,
        ):
            assert node.end_lineno is not None and node.end_col_offset is not None
            start = offsets[node.lineno - 1] + node.col_offset
            end = offsets[node.end_lineno - 1] + node.end_col_offset
            content = content[:start] + repr(value).encode() + content[end:]
        ast.parse(content)
        replacements[path] = content
    written = []
    try:
        for path, content in replacements.items():
            replace_bytes(path, content)
            written.append(path)
    except OSError:
        for path in reversed(written):
            replace_bytes(path, originals[path])
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for action in ("check", "promote"):
        commands.add_parser(action).add_argument("file", type=Path)
    args = parser.parse_args(argv)
    if args.command == "list":
        for name, item in sorted(declarations().items()):
            print(
                f"{name} = {item.default!r}  # {item.unit} {item.bounds}, {item.applies}; {item.source}"
            )
        return 0
    try:
        raw = read(args.file)
        result = configuration({}, raw, {})
        if result.warnings:
            for warning in result.warnings:
                print(warning, file=sys.stderr)
            return 1
        if args.command == "promote":
            promote(
                SOURCE,
                {
                    key: result.values[key]
                    for key in raw
                    if result.values[key] != declarations()[key].default
                },
            )
    except (OSError, ValueError, RecursionError) as error:
        print(
            f"{args.command} failed ({type(error).__name__}): {error}", file=sys.stderr
        )
        return 1
    print(f"{args.command}: {len(raw)} validated values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
