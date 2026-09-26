import collections.abc
from collections.abc import Sequence
from os import PathLike
from typing import Final, final

import wesl

__version__: Final[str]

@final
class CompileResult:
    def __eq__(self, value: object, /) -> bool: ...
    def __ne__(self, value: object, /) -> bool: ...
    def __new__(
        cls,
        /,
        wgsl: str,
        modules: Sequence[str],
        entry_points: Sequence[str],
        sources: dict[str, Source],
    ) -> CompileResult: ...
    def __reduce__(self, /) -> tuple[type, tuple]: ...
    @property
    def entry_points(self, /) -> tuple[str, ...]: ...
    @property
    def modules(self, /) -> tuple[str, ...]: ...
    @property
    def sources(self, /) -> dict[str, Source]: ...
    @property
    def wgsl(self, /) -> str: ...

@final
class Diagnostic:
    def __eq__(self, value: object, /) -> bool: ...
    def __hash__(self, /) -> int: ...
    def __ne__(self, value: object, /) -> bool: ...
    def __new__(
        cls,
        /,
        message: str,
        module: str | None = None,
        filename: str | None = None,
        source: str | None = None,
        span: tuple[int, int] | None = None,
    ) -> Diagnostic: ...
    def __reduce__(self, /) -> tuple[type, tuple]: ...
    @property
    def column(self, /) -> int | None: ...
    @property
    def end_column(self, /) -> int | None: ...
    @property
    def end_line(self, /) -> int | None: ...
    @property
    def filename(self, /) -> str | None: ...
    @property
    def line(self, /) -> int | None: ...
    @property
    def message(self, /) -> str: ...
    @property
    def module(self, /) -> str | None: ...
    @property
    def source(self, /) -> str | None: ...
    @property
    def span(self, /) -> tuple[int, int] | None: ...

@final
class Source:
    def __eq__(self, value: object, /) -> bool: ...
    def __hash__(self, /) -> int: ...
    def __ne__(self, value: object, /) -> bool: ...
    def __new__(cls, /, text: str, filename: str | None = None) -> Source: ...
    def __reduce__(self, /) -> tuple[type, tuple[str, str | None]]: ...
    @property
    def filename(self, /) -> str | None: ...
    @property
    def text(self, /) -> str: ...

@final
class TestLayout:
    @property
    def buffer_size(self, /) -> int: ...
    def decode(self, /, data: collections.abc.Buffer) -> TestResult: ...

@final
class TestResult:
    @property
    def checks(self, /) -> int: ...
    @property
    def completed(self, /) -> int: ...
    @property
    def failures(self, /) -> int: ...
    @property
    def passed(self, /) -> int: ...
    @property
    def site(self, /) -> int: ...
    @property
    def values(
        self, /
    ) -> tuple[
        bool | int | float | tuple[float, ...], bool | int | float | tuple[float, ...]
    ]: ...

def check_syntax(source: str, filename: str) -> None: ...
def compile(
    modules: collections.abc.Mapping[str, str],
    root: str,
    options: wesl.CompileOptions | None,
    filenames: dict[str, str],
    root_directory: str | PathLike[str] | None,
    dependencies: dict[str, str | PathLike[str]],
    dependency_aliases: dict[str, str] | None = None,
) -> CompileResult: ...
def compile_test(
    modules: collections.abc.Mapping[str, str],
    root: str,
    test_name: str,
    options: wesl.TestOptions,
    filenames: dict[str, str],
    root_directory: str | PathLike[str] | None,
    result_binding: int,
    dependencies: dict[str, str | PathLike[str]],
    dependency_aliases: dict[str, str] | None = None,
) -> tuple[str, str, list[Diagnostic], dict[str, str], TestLayout] | None: ...
def constant_module(
    module: str, constants: collections.abc.Mapping[str, bool | int | float]
) -> str: ...
def discover_tests(
    source: str, filename: str, features: wesl.Features | None = None
) -> list[tuple[str, int, int]]: ...
def render_diagnostic(diagnostic: Diagnostic) -> str: ...

class CompileError(Exception):
    diagnostics: tuple[Diagnostic, ...]

__all__ = [
    "CompileError",
    "CompileResult",
    "Diagnostic",
    "Source",
    "TestLayout",
    "TestResult",
    "__version__",
    "check_syntax",
    "compile",
    "compile_test",
    "constant_module",
    "discover_tests",
    "render_diagnostic",
]
