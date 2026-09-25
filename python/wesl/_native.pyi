from collections.abc import Mapping
from typing import Self, final

from . import CompileOptions as _CompileOptions
from . import Features as _Features
from . import TestOptions as _TestOptions

__all__ = [
    "CompileError",
    "CompileResult",
    "Diagnostic",
    "Source",
    "__version__",
    "check_syntax",
    "compile",
    "compile_test",
    "constant_module",
    "discover_tests",
    "render_diagnostic",
]

@final
class Diagnostic:
    def __new__(
        cls,
        message: str,
        module: str | None = None,
        filename: str | None = None,
        source: str | None = None,
        span: tuple[int, int] | None = None,
    ) -> Self: ...
    @property
    def message(self) -> str: ...
    @property
    def module(self) -> str | None: ...
    @property
    def filename(self) -> str | None: ...
    @property
    def source(self) -> str | None: ...
    @property
    def span(self) -> tuple[int, int] | None: ...
    @property
    def line(self) -> int | None: ...
    @property
    def column(self) -> int | None: ...
    @property
    def end_line(self) -> int | None: ...
    @property
    def end_column(self) -> int | None: ...

class CompileError(Exception):
    diagnostics: tuple[Diagnostic, ...]

@final
class Source:
    def __new__(cls, text: str, filename: str | None = None) -> Self: ...
    @property
    def text(self) -> str: ...
    @property
    def filename(self) -> str | None: ...

@final
class CompileResult:
    def __new__(
        cls,
        wgsl: str,
        modules: list[str] | tuple[str, ...],
        entry_points: list[str] | tuple[str, ...],
        sources: dict[str, Source],
    ) -> Self: ...
    @property
    def wgsl(self) -> str: ...
    @property
    def modules(self) -> tuple[str, ...]: ...
    @property
    def entry_points(self) -> tuple[str, ...]: ...
    @property
    def sources(self) -> dict[str, Source]: ...

__version__: str

def compile(
    modules: Mapping[str, str],
    root: str,
    options: _CompileOptions | None,
    filenames: dict[str, str],
    root_directory: str | None,
    dependencies: dict[str, str],
    dependency_aliases: dict[str, str] | None = None,
) -> CompileResult: ...
def check_syntax(source: str, filename: str) -> None: ...
def constant_module(
    module: str, constants: Mapping[str, bool | int | float]
) -> str: ...
def render_diagnostic(diagnostic: Diagnostic) -> str: ...
def discover_tests(
    source: str, filename: str, features: _Features | None = None
) -> list[tuple[str, int, int]]: ...
def compile_test(
    modules: Mapping[str, str],
    root: str,
    test_name: str,
    options: _TestOptions,
    filenames: dict[str, str],
    root_directory: str | None,
    result_binding: int,
    dependencies: dict[str, str],
    dependency_aliases: dict[str, str] | None = None,
) -> tuple[str, str, list[Diagnostic], dict[str, str]] | None: ...
