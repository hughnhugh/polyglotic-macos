"""Report growth in unregistered literals per file. CI starts in warning mode."""

import argparse
import ast
import io
import json
import re
import subprocess
import tokenize
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

PACKAGE = Path("src/polyglotic_desktop")
BASELINE = Path("tools/literals_baseline.json")
AREAS = ("core", "ui_next", "ui", "connection")
EXEMPT = {"connection/protocol.py", "connection/tls.py"}
COMMON = {-1, 0, 0.5, 1, 2, 100}


class Finding(NamedTuple):
    line: int
    value: str
    scope: str


def number(node: ast.AST) -> float | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (float, int))
        and not isinstance(node.value, bool)
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = number(node.operand)
        return None if value is None else -value
    return None


def findings(source: str) -> list[Finding]:
    marked = {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
        and re.match(r"#\s*constant:\s*\S", token.string)
    }
    found: list[Finding] = []

    class Scan(ast.NodeVisitor):
        scope = ""

        def record(self, node: ast.expr) -> None:
            if node.lineno not in marked and node.end_lineno not in marked:
                found.append(
                    Finding(node.lineno, ast.unparse(node), self.scope or "module")
                )

        def visit_FunctionDef(
            self, node: ast.FunctionDef | ast.AsyncFunctionDef
        ) -> None:
            before, self.scope = self.scope, node.name
            self.generic_visit(node)
            self.scope = before

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            # The class's methods still count; class attributes are outside this check.
            for child in node.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    self.visit(child)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "tunable":
                return
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign | ast.AnnAssign) -> None:
            value = node.value
            if value is not None and not self.scope:
                colour = (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and re.fullmatch(
                        r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})",
                        value.value,
                    )
                )
                numbers = (
                    isinstance(value, ast.Tuple)
                    and bool(value.elts)
                    and all(number(n) is not None for n in value.elts)
                )
                if number(value) is not None or colour or numbers:
                    self.record(value)
                    return
            self.generic_visit(node)

        visit_AnnAssign = visit_Assign

        def visit_Constant(self, node: ast.Constant) -> None:
            value = number(node)
            if self.scope and value is not None and value not in COMMON:
                self.record(node)

        def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
            value = number(node)
            if value is None:
                self.generic_visit(node)
            elif self.scope and value not in COMMON:
                self.record(node)

    Scan().visit(ast.parse(source))
    return found


def survey() -> dict[str, list[Finding]]:
    files = [PACKAGE / "main.py"]
    for area in AREAS:
        files.extend((PACKAGE / area).rglob("*.py"))
    result = {}
    for path in sorted(files):
        name = path.relative_to(PACKAGE).as_posix()
        if (
            name.startswith("core/lexicon/")
            or path.name == "glyphs.py"
            or name in EXEMPT
        ):
            continue
        if found := findings(path.read_text(encoding="utf-8")):
            result[name] = found
    return result


def at_base(base: str, paths: set[str]) -> dict[str, list[Finding]]:
    """Actual counts on the PR base catch a raised baseline or a missed reduction."""
    changed = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", base, "--", PACKAGE.as_posix()],
        text=True,
        encoding="utf-8",
    )
    previous = {}
    for path in changed.splitlines():
        name = Path(path).relative_to(PACKAGE).as_posix()
        if name in paths:
            read = subprocess.run(
                ["git", "show", f"{base}:{path}"], capture_output=True, check=False
            )
            previous[name] = (
                findings(read.stdout.decode("utf-8")) if read.returncode == 0 else []
            )
    return previous


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true", help="lower the recorded counts"
    )
    parser.add_argument(
        "--warn", action="store_true", help="report growth without failing CI"
    )
    parser.add_argument("--base", help="compare changed files with the PR base commit")
    args = parser.parse_args(argv)
    before: dict[str, int] = json.loads(BASELINE.read_text(encoding="utf-8"))
    now = survey()
    previous = at_base(args.base, set(now)) if args.base else {}
    grew = False
    for name, items in now.items():
        old = before.get(name, 0)
        if name in previous:
            old = min(old, len(previous[name]))
        if len(items) <= old:
            continue
        grew = True
        print(
            f"::warning file={PACKAGE.as_posix()}/{name}::{len(items)} literals, baseline {old}. Candidates:"
        )
        existing = Counter((row.value, row.scope) for row in previous.get(name, ()))
        for line, value, scope in items:
            if existing[value, scope]:
                existing[value, scope] -= 1
                continue
            print(
                f"  {name}:{line}: {value} in {scope}. Use tunable(...) or # constant: <reason>."
            )
    if args.update:
        lowered = {
            name: min(count, len(now[name]))
            for name, count in before.items()
            if name in now and count
        }
        BASELINE.write_text(
            json.dumps(lowered, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return int(grew and not args.warn)


if __name__ == "__main__":
    raise SystemExit(main())
