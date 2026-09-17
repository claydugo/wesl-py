from collections.abc import Mapping
from typing import Self, final

from . import CompileOptions as _CompileOptions

__all__ = [
    "CompileError",
    "CompileResult",
    "Diagnostic",
    "Source",
    "__version__",
    "_build_metadata",
    "_compile_test",
    "_discover_tests",
    "build_revision",
    "check_syntax",
    "compile",
    "compiler_version",
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
build_revision: str | None
compiler_version: str
_build_metadata: str

def compile(
    modules: Mapping[str, str],
    root: str,
    options: _CompileOptions | None,
    mangler: str,
    use_sourcemap: bool,
    filenames: dict[str, str],
    root_directory: str | None,
) -> CompileResult: ...
def check_syntax(source: str, filename: str) -> None: ...
def _discover_tests(source: str, filename: str) -> list[tuple[str, int, int]]: ...
def _compile_test(
    modules: Mapping[str, str],
    root: str,
    test_name: str,
    options: _CompileOptions,
    filenames: dict[str, str],
    root_directory: str | None,
    result_binding: int,
) -> tuple[str, str, list[Diagnostic], dict[str, str]] | None: ...
