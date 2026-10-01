import builtins
import collections.abc
import os
import pathlib
import typing

import wesl

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
    "project_root",
    "render_diagnostic",
]

__version__: builtins.str

class CompileError(builtins.Exception):
    diagnostics: tuple[Diagnostic, ...]

@typing.final
class CompileResult:
    @property
    def wgsl(self) -> builtins.str: ...
    @property
    def sources(self) -> builtins.dict[builtins.str, Source]: ...
    @property
    def modules(self) -> tuple[str, ...]: ...
    @property
    def entry_points(self) -> tuple[str, ...]: ...
    def __eq__(self, other: builtins.object, /) -> builtins.bool: ...
    def __new__(
        cls,
        wgsl: builtins.str,
        modules: typing.Sequence[builtins.str],
        entry_points: typing.Sequence[builtins.str],
        sources: typing.Mapping[builtins.str, Source],
    ) -> CompileResult: ...
    def __reduce__(self) -> tuple[type, tuple]: ...

@typing.final
class Diagnostic:
    @property
    def message(self) -> builtins.str: ...
    @property
    def module(self) -> builtins.str | None: ...
    @property
    def filename(self) -> builtins.str | None: ...
    @property
    def span(self) -> tuple[builtins.int, builtins.int] | None: ...
    @property
    def source(self) -> builtins.str | None: ...
    @property
    def line(self) -> builtins.int | None: ...
    @property
    def column(self) -> builtins.int | None: ...
    @property
    def end_line(self) -> builtins.int | None: ...
    @property
    def end_column(self) -> builtins.int | None: ...
    def __eq__(self, other: builtins.object, /) -> builtins.bool: ...
    def __hash__(self) -> builtins.int: ...
    def __new__(
        cls,
        message: builtins.str,
        module: builtins.str | None = None,
        filename: builtins.str | None = None,
        source: builtins.str | None = None,
        span: tuple[builtins.int, builtins.int] | None = None,
    ) -> Diagnostic: ...
    def __reduce__(self) -> tuple[type, tuple]: ...

@typing.final
class Source:
    @property
    def text(self) -> builtins.str: ...
    @property
    def filename(self) -> builtins.str | None: ...
    def __eq__(self, other: builtins.object, /) -> builtins.bool: ...
    def __hash__(self) -> builtins.int: ...
    def __new__(
        cls, text: builtins.str, filename: builtins.str | None = None
    ) -> Source: ...
    def __reduce__(self) -> tuple[type, tuple[builtins.str, builtins.str | None]]: ...

@typing.final
class TestLayout:
    @property
    def buffer_size(self) -> builtins.int: ...
    def decode(self, data: collections.abc.Buffer) -> TestResult: ...

@typing.final
class TestResult:
    @property
    def passed(self) -> builtins.int: ...
    @property
    def failures(self) -> builtins.int: ...
    @property
    def site(self) -> builtins.int: ...
    @property
    def completed(self) -> builtins.int: ...
    @property
    def checks(self) -> builtins.int: ...
    @property
    def invocations(self) -> builtins.int: ...
    @property
    def invocation(self) -> builtins.int | None: ...
    @property
    def values(
        self,
    ) -> tuple[
        bool | int | float | tuple[float, ...], bool | int | float | tuple[float, ...]
    ]: ...

def check_syntax(source: builtins.str, filename: builtins.str) -> None: ...
def compile(
    modules: collections.abc.Mapping[str, str],
    root: builtins.str,
    options: wesl.CompileOptions,
    filenames: typing.Mapping[builtins.str, builtins.str],
    root_directory: builtins.str | os.PathLike | pathlib.Path | None,
    dependencies: typing.Mapping[
        builtins.str, builtins.str | os.PathLike | pathlib.Path
    ],
) -> CompileResult: ...
def compile_test(
    modules: collections.abc.Mapping[str, str],
    root: builtins.str,
    test_name: builtins.str,
    options: wesl.TestOptions,
    filenames: typing.Mapping[builtins.str, builtins.str],
    root_directory: builtins.str | os.PathLike | pathlib.Path | None,
    result_binding: builtins.int,
    dependencies: typing.Mapping[
        builtins.str, builtins.str | os.PathLike | pathlib.Path
    ],
) -> (
    tuple[
        builtins.str,
        builtins.str,
        builtins.list[Diagnostic],
        builtins.dict[builtins.str, builtins.str],
        TestLayout,
    ]
    | None
): ...
def constant_module(
    module: builtins.str, constants: collections.abc.Mapping[str, bool | int | float]
) -> builtins.str: ...
def discover_tests(
    source: builtins.str, filename: builtins.str
) -> builtins.list[tuple[builtins.str, builtins.int, builtins.int]]: ...
def project_root(source: builtins.str) -> builtins.str: ...
def render_diagnostic(diagnostic: Diagnostic) -> builtins.str: ...
