import os
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from . import _native
from ._native import (
    CompileError,
    CompileResult,
    Diagnostic,
    Source,
    __version__,
    build_revision,
    compiler_version,
)
from ._resources import LoadedModules, load_modules

__all__ = [
    "CompileError",
    "CompileOptions",
    "CompileResult",
    "Compiler",
    "Diagnostic",
    "Feature",
    "Features",
    "LoadedModules",
    "ManglerKind",
    "Source",
    "__version__",
    "build_revision",
    "check_syntax",
    "compile",
    "compile_file",
    "compile_source",
    "compiler_version",
    "load_modules",
]


class Feature(Enum):
    Enable = "Enable"
    Disable = "Disable"
    Keep = "Keep"
    Error = "Error"


class ManglerKind(Enum):
    Escape = "Escape"
    Hash = "Hash"
    Unicode = "Unicode"
    None_ = "None"


@dataclass(kw_only=True)
class Features:
    default: Feature = Feature.Disable
    flags: MutableMapping[str, bool | Feature] = field(default_factory=dict)


@dataclass(kw_only=True)
class CompileOptions:
    imports: bool = True
    condcomp: bool = True
    strip: bool = True
    lower: bool = False
    validate: bool = True
    sourcemap: bool = True
    mangler: ManglerKind = ManglerKind.Escape
    mangle_main: bool = False
    keep: Sequence[str] | None = None
    keep_main: bool = False
    features: Features = field(default_factory=Features)


def compile(
    modules: Mapping[str, str],
    *,
    root: str = "package::main",
    options: CompileOptions | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
) -> CompileResult:
    if not isinstance(modules, Mapping):
        raise TypeError("modules must be a mapping")
    if filenames is not None and not isinstance(filenames, Mapping):
        raise TypeError("filenames must be a mapping or None")
    if options is not None and not isinstance(options, CompileOptions):
        raise TypeError("options must be CompileOptions or None")
    if options is not None and not isinstance(options.mangler, ManglerKind):
        raise TypeError("mangler must be ManglerKind")
    return _native.compile(
        modules,
        root,
        options,
        {}
        if filenames is None
        else {name: os.fspath(path) for name, path in filenames.items()},
        None if root_directory is None else os.fspath(root_directory),
    )


def compile_source(
    source: str,
    *,
    modules: Mapping[str, str] | None = None,
    root: str = "package::main",
    filename: str | os.PathLike[str] = "<string>",
    options: CompileOptions | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
) -> CompileResult:
    if modules is not None and not isinstance(modules, Mapping):
        raise TypeError("modules must be a mapping or None")
    copied_modules = {} if modules is None else dict(modules)
    if root in copied_modules:
        raise ValueError("root module is already present in modules")
    copied_modules[root] = source
    if filenames is not None and not isinstance(filenames, Mapping):
        raise TypeError("filenames must be a mapping or None")
    copied_filenames = {} if filenames is None else dict(filenames)
    copied_filenames[root] = filename
    return compile(
        copied_modules,
        root=root,
        options=options,
        filenames=copied_filenames,
        root_directory=root_directory,
    )


def compile_file(
    filename: str | os.PathLike[str],
    *,
    modules: Mapping[str, str] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    options: CompileOptions | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    path = Path(filename).absolute()
    directory = (
        path.parent if root_directory is None else Path(root_directory).absolute()
    )
    relative_path = Path(os.path.normpath(path)).relative_to(
        os.path.normpath(directory)
    )
    root = "package::" + "::".join(relative_path.with_suffix("").parts)
    return compile_source(
        path.read_bytes().decode("utf-8"),
        modules=modules,
        root=root,
        filename=path,
        options=options,
        filenames=filenames,
        root_directory=directory,
    )


@dataclass(kw_only=True)
class Compiler:
    options: CompileOptions = field(default_factory=CompileOptions)
    modules: Mapping[str, str] = field(default_factory=dict)
    filenames: Mapping[str, str | os.PathLike[str]] = field(default_factory=dict)
    root_directory: str | os.PathLike[str] | None = None

    def compile_source(  # noqa: D102
        self,
        source: str,
        *,
        root: str = "package::main",
        filename: str | os.PathLike[str] = "<string>",
    ) -> CompileResult:
        return compile_source(
            source,
            modules=self.modules,
            root=root,
            filename=filename,
            options=self.options,
            filenames=self.filenames,
            root_directory=self.root_directory,
        )

    def compile_file(  # noqa: D102
        self,
        filename: str | os.PathLike[str],
    ) -> CompileResult:
        path = (
            Path(filename)
            if self.root_directory is None
            else Path(self.root_directory) / filename
        )
        return compile_file(
            path,
            modules=self.modules,
            root_directory=self.root_directory,
            options=self.options,
            filenames=self.filenames,
        )


def check_syntax(source: str, *, filename: str | os.PathLike[str] = "<string>") -> None:
    return _native.check_syntax(source, os.fspath(filename))
