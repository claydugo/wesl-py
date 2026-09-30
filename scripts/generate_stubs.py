import ast
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "maturin",
            "generate-stubs",
            "--locked",
            "--features",
            "stub-gen",
            "--out",
            directory,
        ],
        check=True,
    )
    source = (Path(directory) / "wesl/_native.pyi").read_text(encoding="utf-8")

syntax = ast.parse(source)
syntax.body = [
    statement
    for statement in syntax.body
    if not (
        (isinstance(statement, ast.FunctionDef) and statement.name == "__getattr__")
        or (isinstance(statement, ast.ImportFrom) and statement.module == "_typeshed")
    )
]
for node in ast.walk(syntax):
    if (
        isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        node.body = node.body[1:] or [ast.Expr(value=ast.Constant(value=Ellipsis))]
    if isinstance(node, ast.ClassDef):
        for member in node.body:
            if not isinstance(member, ast.FunctionDef):
                continue
            if node.name == "CompileResult" and member.name in {
                "modules",
                "entry_points",
            }:
                member.returns = ast.parse("tuple[str, ...]", mode="eval").body
            elif node.name == "TestResult" and member.name == "values":
                member.returns = ast.parse(
                    "tuple[bool | int | float | tuple[float, ...], "
                    "bool | int | float | tuple[float, ...]]",
                    mode="eval",
                ).body

syntax.body[:0] = ast.parse("import collections.abc\nimport wesl\n").body
syntax.body.extend(
    ast.parse(
        "class CompileError(Exception):\n    diagnostics: tuple[Diagnostic, ...]\n",
    ).body,
)
exports = sorted(
    ["__version__"]
    + [
        statement.name
        for statement in syntax.body
        if isinstance(statement, (ast.ClassDef, ast.FunctionDef))
    ],
)
syntax.body.extend(ast.parse(f"__all__ = {exports!r}").body)
Path("python/wesl/_native.pyi").write_text(
    ast.unparse(ast.fix_missing_locations(syntax)) + "\n", encoding="utf-8"
)
