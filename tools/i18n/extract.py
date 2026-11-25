"""Every interface string in the app's code, read from the source (decision
0034).

`pyside6-lupdate` can't see most of our strings: each module translates
through a small wrapper (`_tr("Start listening")` calls
`QApplication.translate("Home", text)`), and lupdate gives a call outside a
class no context, or the class's name inside one - not the wrapper's. This
reads the code the way it runs instead:

- a module-level wrapper - a function whose body is
  `return <anything>.translate("Context", <its first argument>)`, with a
  fourth argument for a count - makes calls to it messages in that context
  (`_tr`, `_tr_app`, and the plural ones, `_trn`);
- `self.tr("text")` is a message in the enclosing class's context (what
  PySide6 looks up); `box.tr("text")` on any other object is a problem:
  PySide6 looks it up under that object's class (a QMessageBox's), where
  our translations never are (polyglotic-hq 184: the sign-out question);
- `<anything>.translate("Context", "text")` and `tr("Context", "text")`
  (`tr = QCoreApplication.translate`) name their context;
- `QT_TRANSLATE_NOOP("Context", "text")` and `QT_TR_NOOP("text")` mark text
  translated later.

What it can't translate is a problem, listed so a test can fail on it: an
f-string or a joined string handed to a translation call (a translator
can't see it, and the text isn't in any translation file), and a call that
runs at import - at module or class level - which runs before `main`
installs the interface's language, so it would stay English. Text built
from a variable (`_tr(name)`) is left alone: it's translated where it was
marked.
"""

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "src" / "polyglotic_desktop"
SKIPPED = ("harness.py", "perf")  # developer tools: their text is for us
COUNT = re.compile("%L?n")  # where a count goes: %n, or %Ln with its digits grouped


@dataclass(frozen=True)
class Message:
    """One string to translate, where it's first used."""

    context: str
    source: str
    comment: str = ""  # Qt's disambiguation: the same text, meant differently
    numerus: bool = False  # a count: "%n caption(s)"
    file: str = ""  # relative to the repo, with forward slashes
    line: int = 0
    note: str = ""  # for the translator: a `#:` comment just above the call
    end_line: int = 0  # last line of the call, inclusive
    column: int = 0  # byte offset of the call on its first line

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.context, self.source, self.comment)


@dataclass
class Found:
    messages: list[Message] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Wrapper:
    context: str
    numerus: bool  # its second argument is the count


def _text(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _constants(tree: ast.Module) -> dict[str, str]:
    """The module's string constants (`_CONTEXT = "Languages"`)."""
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and (text := _text(node.value)) is not None:
                found[target.id] = text
    return found


def _context(node: ast.expr, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return _text(node)


def _is_param(node: ast.expr, name: str) -> bool:
    """`text`, or `str(text)`."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        node = node.args[0]
    return isinstance(node, ast.Name) and node.id == name


def _wrappers(tree: ast.Module, constants: dict[str, str]) -> dict[str, _Wrapper]:
    """The module's translation wrappers, by name."""
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.args.args:
            continue
        body = [n for n in node.body if not isinstance(n, ast.Expr)]  # docstring
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            continue
        call = body[0].value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "translate"
            and len(call.args) >= 2
        ):
            continue
        context = _context(call.args[0], constants)
        if context is None or not _is_param(call.args[1], node.args.args[0].arg):
            continue
        found[node.name] = _Wrapper(context, numerus=len(call.args) >= 4)
    return found


class _Reader(ast.NodeVisitor):
    def __init__(self, file: str, lines: list[str], tree: ast.Module) -> None:
        self.file = file
        self.lines = lines
        self.constants = _constants(tree)
        self.wrappers = _wrappers(tree, self.constants)
        self.classes: list[str] = []
        self.functions = 0  # how deep in functions: 0 runs at import
        self.found = Found()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)
        self.classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._inside(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._inside(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._inside(node)

    def _inside(self, node: ast.AST) -> None:
        self.functions += 1
        self.generic_visit(node)
        self.functions -= 1

    def visit_Call(self, node: ast.Call) -> None:
        self._read(node)
        self.generic_visit(node)

    def _read(self, node: ast.Call) -> None:
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        attr = func.attr if isinstance(func, ast.Attribute) else None
        args = node.args
        translating = (
            name in self.wrappers
            or attr == "tr"
            or ((attr == "translate" or name == "tr") and len(args) >= 2)
        )
        if translating and not self.functions:
            self._problem(
                node,
                "translated at import, before the interface's language is "
                "installed: mark it with QT_TRANSLATE_NOOP and translate it in a function",
            )
        if name in self.wrappers:
            wrapper = self.wrappers[name]
            self._add(
                node, wrapper.context, args[0] if args else None, None, wrapper.numerus
            )
        elif attr == "tr" and isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in ("self", "cls"):
                context = self.classes[-1] if self.classes else None
                if context is None:
                    self._problem(node, "self.tr() outside a class")
                    return
                numerus = len(args) >= 3 or any(k.arg == "n" for k in node.keywords)
                comment = args[1] if len(args) >= 2 else None
                self._add(node, context, args[0] if args else None, comment, numerus)
            elif args and (
                _text(args[0]) is not None or isinstance(args[0], ast.JoinedStr)
            ):
                self._problem(
                    node,
                    "<object>.tr() is looked up under that object's class (a"
                    ' QMessageBox\'s: "QMessageBox"), where our translations'
                    " aren't: use the module's _tr",
                )
        elif attr == "translate" or name == "tr" or name == "QT_TRANSLATE_NOOP":
            if len(args) < 2:
                return  # str.translate(table)
            context = _context(args[0], self.constants)
            if context is None:
                if _text(args[1]) is not None or isinstance(args[1], ast.JoinedStr):
                    self._problem(node, "a translation whose context isn't written out")
                return
            numerus = len(args) >= 4
            comment = args[2] if len(args) >= 3 else None
            self._add(node, context, args[1], comment, numerus)
        elif name == "QT_TR_NOOP":
            if not self.classes:
                self._problem(node, "QT_TR_NOOP outside a class: use QT_TRANSLATE_NOOP")
                return
            self._add(node, self.classes[-1], args[0] if args else None, None, False)

    def _add(
        self,
        node: ast.Call,
        context: str,
        text_node: ast.expr | None,
        comment_node: ast.expr | None,
        numerus: bool,
    ) -> None:
        if isinstance(text_node, ast.JoinedStr):
            self._problem(node, 'an f-string to translate: use "...{name}...".format()')
            return
        if isinstance(text_node, ast.BinOp):
            self._problem(node, "a joined string to translate: write it as one")
            return
        text = _text(text_node)
        if text is None:
            return  # a variable: translated where it was marked
        comment = _text(comment_node) or ""
        if numerus and not COUNT.search(text):
            self._problem(node, f"a count without %n: {text!r}")
        if not numerus and COUNT.search(text):
            self._problem(node, f"%n without a count: {text!r}")
        if "(s)" in text and not numerus:
            self._problem(node, f"'(s)' outside a plural: {text!r} (use _trn)")
        self.found.messages.append(
            Message(
                context,
                text,
                comment,
                numerus,
                self.file,
                node.lineno,
                self._note(node),
                node.end_lineno or node.lineno,
                node.col_offset,
            )
        )

    def _note(self, node: ast.Call) -> str:
        """`#: a note for the translator` on the lines just above the call."""
        notes: list[str] = []
        line = node.lineno - 2
        while line >= 0 and self.lines[line].strip().startswith("#:"):
            notes.insert(0, self.lines[line].strip()[2:].strip())
            line -= 1
        return " ".join(notes)

    def _problem(self, node: ast.Call, what: str) -> None:
        self.found.problems.append(f"{self.file}:{node.lineno}: {what}")


def read_file(path: Path) -> Found:
    name = path.relative_to(REPO) if path.is_relative_to(REPO) else path
    return read_text(path.read_text(encoding="utf-8"), name.as_posix())


def read_text(text: str, file: str) -> Found:
    tree = ast.parse(text, filename=file)
    reader = _Reader(file, text.splitlines(), tree)
    reader.visit(tree)
    return reader.found


def source_files(root: Path = SOURCE) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).parts
        if relative[0] not in SKIPPED:
            yield path


def read(files: Iterable[Path] | None = None) -> Found:
    """Every message in the code, each once (where it's first used), and
    every problem."""
    found = Found()
    seen: dict[tuple[str, str, str], Message] = {}
    for path in source_files() if files is None else files:
        one = read_file(path)
        found.problems += one.problems
        for message in one.messages:
            first = seen.get(message.key)
            if first is None:
                seen[message.key] = message
                found.messages.append(message)
            elif first.numerus != message.numerus:
                found.problems.append(
                    f"{message.file}:{message.line}: {message.source!r} is used both "
                    "with and without a count"
                )
    return found
