from typing import Self, final

__all__ = [
    "CompileError",
    "CompileResult",
    "Diagnostic",
    "__version__",
    "_build_metadata",
    "check_syntax",
    "compile",
    "compiler_version",
    "validate",
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
class CompileResult:
    def __new__(
        cls,
        wgsl: str,
        modules: list[str] | tuple[str, ...],
        entry_points: list[str] | tuple[str, ...],
        declarations: dict[str, tuple[str, str]],
    ) -> Self: ...
    @property
    def wgsl(self) -> str: ...
    @property
    def modules(self) -> tuple[str, ...]: ...
    @property
    def entry_points(self) -> tuple[str, ...]: ...
    @property
    def declarations(self) -> dict[str, tuple[str, str]]: ...

__version__: str
compiler_version: str
_build_metadata: str

def compile(
    modules: dict[str, str],
    root: str,
    features: dict[str, bool],
    strip: bool,
    keep_root: bool,
    mangle_root: bool,
    keep: list[str] | None,
    missing_features: str,
    filenames: dict[str, str],
    root_directory: str | None,
) -> CompileResult: ...
def check_syntax(source: str, filename: str) -> None: ...
def validate(source: str, filename: str) -> None: ...
