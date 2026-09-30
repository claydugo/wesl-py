import os
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Self, SupportsFloat

from . import _native
from ._constants import add_constant_modules
from ._native import (
    CompileError,
    CompileResult,
    Diagnostic,
    Source,
    __version__,
)
from ._project import Dependencies, absolute_path, load_project
from ._resources import LoadedModules, load_modules, module_name

__all__ = [
    "CompileError",
    "CompileOptions",
    "CompileResult",
    "Compiler",
    "Dependencies",
    "Diagnostic",
    "Feature",
    "Features",
    "LoadedModules",
    "ManglerKind",
    "Source",
    "TestOptions",
    "__version__",
    "check_syntax",
    "compile",
    "compile_file",
    "compile_source",
    "load_modules",
]


type _ConstantModules = Mapping[str, Mapping[str, SupportsFloat]]


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


class _Unset(Enum):
    Value = "unset"


@dataclass(kw_only=True)
class Features:
    default: Feature = Feature.Disable
    flags: MutableMapping[str, bool | Feature] = field(default_factory=dict)


@dataclass(kw_only=True)
class CompileOptions:
    imports: bool = True
    condcomp: bool = True
    visibility: bool = False
    strip: bool = True
    lower: bool = False
    validate: bool = True
    sourcemap: bool = True
    mangler: ManglerKind = ManglerKind.Escape
    mangle_main: bool = False
    keep: Sequence[str] | None = None
    keep_main: bool = False
    features: Features = field(default_factory=Features)


@dataclass(kw_only=True)
class TestOptions:
    __test__ = False

    strip: bool = True
    visibility: bool = False
    lower: bool = False
    validate: bool = True
    features: Features = field(default_factory=Features)


def compile(
    modules: Mapping[str, str],
    *,
    root: str = "package::main",
    options: CompileOptions | None = None,
    features: Features | Mapping[str, bool | Feature] | None = None,
    constant_modules: _ConstantModules | None = None,
    keep: Sequence[str] | _Unset | None = _Unset.Value,
    keep_main: bool | None = None,
    strip: bool | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    dependencies: Dependencies | Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    if not isinstance(modules, Mapping):
        message = "modules must be a mapping"
        raise TypeError(message)
    if filenames is not None and not isinstance(filenames, Mapping):
        message = "filenames must be a mapping or None"
        raise TypeError(message)
    if dependencies is not None and not isinstance(
        dependencies, (Dependencies, Mapping)
    ):
        message = "dependencies must be Dependencies, a mapping, or None"
        raise TypeError(message)
    if options is not None and not isinstance(options, CompileOptions):
        message = "options must be CompileOptions or None"
        raise TypeError(message)
    if options is not None and not isinstance(options.mangler, ManglerKind):
        message = "mangler must be ManglerKind"
        raise TypeError(message)
    if constant_modules is not None:
        modules = add_constant_modules(modules, constant_modules)
    options = CompileOptions() if options is None else options
    options = replace(
        options,
        features=options.features
        if features is None
        else Features(flags=dict(features))
        if isinstance(features, Mapping)
        else features,
        keep=options.keep if keep is _Unset.Value else keep,
        keep_main=options.keep_main if keep_main is None else keep_main,
        strip=options.strip if strip is None else strip,
    )
    directories = (
        dependencies.directories
        if isinstance(dependencies, Dependencies)
        else dependencies
    )
    return _native.compile(
        modules,
        root,
        options,
        {}
        if filenames is None
        else {name: os.fspath(path) for name, path in filenames.items()},
        None if root_directory is None else os.fspath(root_directory),
        {
            "wgsl_test": str(Path(__file__).parent / "shaders/wgsl_test"),
            **(
                {}
                if directories is None
                else {name: os.fspath(path) for name, path in directories.items()}
            ),
        },
        dict(dependencies.aliases) if isinstance(dependencies, Dependencies) else None,
    )


def compile_source(
    source: str,
    *,
    modules: Mapping[str, str] | None = None,
    root: str = "package::main",
    filename: str | os.PathLike[str] = "<string>",
    options: CompileOptions | None = None,
    features: Features | Mapping[str, bool | Feature] | None = None,
    constant_modules: _ConstantModules | None = None,
    keep: Sequence[str] | _Unset | None = _Unset.Value,
    keep_main: bool | None = None,
    strip: bool | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    dependencies: Dependencies | Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    if modules is not None and not isinstance(modules, Mapping):
        message = "modules must be a mapping or None"
        raise TypeError(message)
    copied_modules = {} if modules is None else dict(modules)
    if root in copied_modules:
        message = "root module is already present in modules"
        raise ValueError(message)
    copied_modules[root] = source
    if filenames is not None and not isinstance(filenames, Mapping):
        message = "filenames must be a mapping or None"
        raise TypeError(message)
    copied_filenames = {} if filenames is None else dict(filenames)
    copied_filenames[root] = filename
    return compile(
        copied_modules,
        root=root,
        options=options,
        features=features,
        constant_modules=constant_modules,
        keep=keep,
        keep_main=keep_main,
        strip=strip,
        filenames=copied_filenames,
        root_directory=root_directory,
        dependencies=dependencies,
    )


def compile_file(
    filename: str | os.PathLike[str],
    *,
    modules: Mapping[str, str] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    options: CompileOptions | None = None,
    features: Features | Mapping[str, bool | Feature] | None = None,
    constant_modules: _ConstantModules | None = None,
    keep: Sequence[str] | _Unset | None = _Unset.Value,
    keep_main: bool | None = None,
    strip: bool | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    dependencies: Dependencies | Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    path = absolute_path(Path(filename))
    directory = (
        path.parent if root_directory is None else absolute_path(Path(root_directory))
    )
    relative_path = path.relative_to(directory)
    root = module_name(relative_path.with_suffix("").parts, namespace="package")
    return compile_source(
        path.read_bytes().decode("utf-8"),
        modules=modules,
        root=root,
        filename=path,
        options=options,
        features=features,
        constant_modules=constant_modules,
        keep=keep,
        keep_main=keep_main,
        strip=strip,
        filenames=filenames,
        root_directory=directory,
        dependencies=dependencies,
    )


@dataclass(kw_only=True)
class Compiler:
    options: CompileOptions = field(default_factory=CompileOptions)
    modules: Mapping[str, str] = field(default_factory=dict)
    filenames: Mapping[str, str | os.PathLike[str]] = field(default_factory=dict)
    root_directory: str | os.PathLike[str] | None = None
    dependencies: Dependencies | Mapping[str, str | os.PathLike[str]] = field(
        default_factory=dict
    )

    @classmethod
    def from_project(
        cls,
        directory: str | os.PathLike[str],
        *,
        options: CompileOptions | None = None,
        modules: Mapping[str, str] | None = None,
        filenames: Mapping[str, str | os.PathLike[str]] | None = None,
        root_directory: str | os.PathLike[str] | None = None,
        dependencies: Mapping[str, str | os.PathLike[str]] | None = None,
    ) -> Self:
        project = load_project(Path(directory))
        if project is None:
            message = "no wesl.toml found"
            raise FileNotFoundError(message)
        return cls(
            options=CompileOptions() if options is None else options,
            modules={} if modules is None else modules,
            filenames={} if filenames is None else filenames,
            root_directory=project.root_directory
            if root_directory is None
            else absolute_path(Path(root_directory)),
            dependencies=project.load_dependencies(dependencies),
        )

    def compile_source(
        self,
        source: str,
        *,
        root: str = "package::main",
        filename: str | os.PathLike[str] = "<string>",
        features: Features | Mapping[str, bool | Feature] | None = None,
        constant_modules: _ConstantModules | None = None,
        keep: Sequence[str] | _Unset | None = _Unset.Value,
        keep_main: bool | None = None,
        strip: bool | None = None,
    ) -> CompileResult:
        return compile_source(
            source,
            modules=self.modules,
            root=root,
            filename=filename,
            options=self.options,
            features=features,
            constant_modules=constant_modules,
            keep=keep,
            keep_main=keep_main,
            strip=strip,
            filenames=self.filenames,
            root_directory=self.root_directory,
            dependencies=self.dependencies,
        )

    def compile_file(
        self,
        filename: str | os.PathLike[str],
        *,
        features: Features | Mapping[str, bool | Feature] | None = None,
        constant_modules: _ConstantModules | None = None,
        keep: Sequence[str] | _Unset | None = _Unset.Value,
        keep_main: bool | None = None,
        strip: bool | None = None,
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
            features=features,
            constant_modules=constant_modules,
            keep=keep,
            keep_main=keep_main,
            strip=strip,
            filenames=self.filenames,
            dependencies=self.dependencies,
        )


def check_syntax(source: str, *, filename: str | os.PathLike[str] = "<string>") -> None:
    return _native.check_syntax(source, os.fspath(filename))
