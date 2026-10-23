import builtins
import collections.abc
import typing

import wesl

__all__ = [
    "CompileError",
    "CompileResult",
    "Diagnostic",
    "ParsedTestModule",
    "Source",
    "TestLayout",
    "TestResult",
    "__version__",
    "compile",
    "compile_compute",
    "compile_test",
    "constant_module",
    "entry_points",
    "execute_test_cpu",
    "path_layout",
    "project",
    "render_diagnostic",
    "struct_layouts",
    "var_reflection",
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
class ParsedTestModule:
    @property
    def tests(
        self,
    ) -> builtins.list[tuple[builtins.str, builtins.int, builtins.int]]: ...
    def __new__(
        cls, source: builtins.str, filename: builtins.str
    ) -> ParsedTestModule: ...

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
    @property
    def resources(self) -> builtins.list[tuple[builtins.int, builtins.int]]: ...
    @property
    def buffers(self) -> list[dict[str, typing.Any]]: ...
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
        bool | int | float | tuple[bool | int | float, ...],
        bool | int | float | tuple[bool | int | float, ...],
    ]: ...
    @property
    def value_type(self) -> builtins.str: ...

def compile(compiler: wesl.Compiler, root: builtins.str) -> CompileResult: ...
def compile_compute(
    compiler: wesl.Compiler, root: builtins.str
) -> tuple[str, list[dict[str, typing.Any]], dict[str, str]]: ...
def compile_test(
    compiler: wesl.Compiler,
    root: builtins.str,
    test_name: builtins.str,
    options: wesl.TestOptions,
    result_binding: builtins.int,
    reserved: typing.Sequence[builtins.int],
    parsed_module: ParsedTestModule | None = None,
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
    module: builtins.str,
    constants: collections.abc.Mapping[str, bool | int | float | str],
) -> builtins.str: ...
def entry_points(
    compiler: wesl.Compiler, module: builtins.str
) -> builtins.list[
    tuple[
        builtins.str,
        builtins.str,
        tuple[builtins.int, builtins.int, builtins.int] | None,
    ]
]: ...
def execute_test_cpu(
    source: builtins.str, entry_point: builtins.str, layout: TestLayout
) -> builtins.list[builtins.int]: ...
def path_layout(
    compiler: wesl.Compiler, path: builtins.str
) -> builtins.tuple[builtins.bool, builtins.str | builtins.tuple[typing.Any, ...]]: ...
def project(
    source: builtins.str,
) -> tuple[builtins.str, builtins.dict[builtins.str, builtins.str]]: ...
def render_diagnostic(diagnostic: Diagnostic) -> builtins.str: ...
def struct_layouts(
    compiler: wesl.Compiler, module: builtins.str
) -> builtins.list[
    builtins.tuple[builtins.str, builtins.str | builtins.tuple[typing.Any, ...] | None]
]: ...
def var_reflection(
    compiler: wesl.Compiler, path: builtins.str
) -> builtins.tuple[
    builtins.str | None,
    builtins.str | None,
    builtins.int | None,
    builtins.int | None,
    builtins.str | builtins.tuple[typing.Any, ...] | None,
    builtins.int,
]: ...
