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
from ._project import ProjectDependencies, absolute_path, load_project
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
    strip: bool = True
    lower: bool = False
    validate: bool = True
    sourcemap: bool = True
    mangler: ManglerKind = ManglerKind.Escape
    mangle_root: bool = False
    keep: Sequence[str] | None = None
    keep_root: bool = False
    features: Features = field(default_factory=Features)


@dataclass(kw_only=True)
class TestOptions:
    __test__ = False

    strip: bool = True
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
    keep_root: bool | None = None,
    strip: bool | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    dependencies: Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    if not isinstance(modules, Mapping):
        raise TypeError("modules must be a mapping")
    if filenames is not None and not isinstance(filenames, Mapping):
        raise TypeError("filenames must be a mapping or None")
    if dependencies is not None and not isinstance(dependencies, Mapping):
        raise TypeError("dependencies must be a mapping or None")
    if options is not None and not isinstance(options, CompileOptions):
        raise TypeError("options must be CompileOptions or None")
    if options is not None and not isinstance(options.mangler, ManglerKind):
        raise TypeError("mangler must be ManglerKind")
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
        keep_root=options.keep_root if keep_root is None else keep_root,
        strip=options.strip if strip is None else strip,
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
                if dependencies is None
                else {name: os.fspath(path) for name, path in dependencies.items()}
            ),
        },
        dependencies.aliases if isinstance(dependencies, ProjectDependencies) else None,
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
    keep_root: bool | None = None,
    strip: bool | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    dependencies: Mapping[str, str | os.PathLike[str]] | None = None,
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
        features=features,
        constant_modules=constant_modules,
        keep=keep,
        keep_root=keep_root,
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
    keep_root: bool | None = None,
    strip: bool | None = None,
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    dependencies: Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    path = absolute_path(Path(filename))
    project = load_project(path.parent)
    directory = (
        (path.parent if project is None else project.root_directory)
        if root_directory is None
        else absolute_path(Path(root_directory))
    )
    relative_path = path.relative_to(directory)
    root = "package::" + "::".join(relative_path.with_suffix("").parts)
    return compile_source(
        path.read_bytes().decode("utf-8"),
        modules=modules,
        root=root,
        filename=path,
        options=options,
        features=features,
        constant_modules=constant_modules,
        keep=keep,
        keep_root=keep_root,
        strip=strip,
        filenames=filenames,
        root_directory=directory,
        dependencies=dependencies
        if project is None
        else project.load_dependencies(dependencies),
    )


@dataclass(kw_only=True)
class Compiler:
    options: CompileOptions = field(default_factory=CompileOptions)
    features: Features | Mapping[str, bool | Feature] | None = None
    keep: Sequence[str] | _Unset | None = _Unset.Value
    keep_root: bool | None = None
    strip: bool | None = None
    modules: Mapping[str, str] = field(default_factory=dict)
    filenames: Mapping[str, str | os.PathLike[str]] = field(default_factory=dict)
    root_directory: str | os.PathLike[str] | None = None
    dependencies: Mapping[str, str | os.PathLike[str]] = field(default_factory=dict)

    @classmethod
    def from_project(  # noqa: D102
        cls,
        directory: str | os.PathLike[str],
        *,
        options: CompileOptions | None = None,
        features: Features | Mapping[str, bool | Feature] | None = None,
        keep: Sequence[str] | _Unset | None = _Unset.Value,
        keep_root: bool | None = None,
        strip: bool | None = None,
        modules: Mapping[str, str] | None = None,
        filenames: Mapping[str, str | os.PathLike[str]] | None = None,
        root_directory: str | os.PathLike[str] | None = None,
        dependencies: Mapping[str, str | os.PathLike[str]] | None = None,
    ) -> Self:
        project = load_project(Path(directory))
        if project is None:
            raise FileNotFoundError("no wesl.toml found")
        return cls(
            options=CompileOptions() if options is None else options,
            features=features,
            keep=keep,
            keep_root=keep_root,
            strip=strip,
            modules={} if modules is None else modules,
            filenames={} if filenames is None else filenames,
            root_directory=project.root_directory
            if root_directory is None
            else root_directory,
            dependencies=project.load_dependencies(dependencies),
        )

    def compile_source(  # noqa: D102
        self,
        source: str,
        *,
        root: str = "package::main",
        filename: str | os.PathLike[str] = "<string>",
        features: Features | Mapping[str, bool | Feature] | None = None,
        constant_modules: _ConstantModules | None = None,
        keep: Sequence[str] | _Unset | None = _Unset.Value,
        keep_root: bool | None = None,
        strip: bool | None = None,
    ) -> CompileResult:
        return compile_source(
            source,
            modules=self.modules,
            root=root,
            filename=filename,
            options=self.options,
            features=self.features if features is None else features,
            constant_modules=constant_modules,
            keep=self.keep if keep is _Unset.Value else keep,
            keep_root=self.keep_root if keep_root is None else keep_root,
            strip=self.strip if strip is None else strip,
            filenames=self.filenames,
            root_directory=self.root_directory,
            dependencies=self.dependencies,
        )

    def compile_file(  # noqa: D102
        self,
        filename: str | os.PathLike[str],
        *,
        features: Features | Mapping[str, bool | Feature] | None = None,
        constant_modules: _ConstantModules | None = None,
        keep: Sequence[str] | _Unset | None = _Unset.Value,
        keep_root: bool | None = None,
        strip: bool | None = None,
    ) -> CompileResult:
        path = (
            Path(filename)
            if self.root_directory is None
            else Path(self.root_directory) / filename
        )
        path = absolute_path(path)
        directory = (
            path.parent
            if self.root_directory is None
            else absolute_path(Path(self.root_directory))
        )
        relative_path = path.relative_to(directory)
        root = "package::" + "::".join(relative_path.with_suffix("").parts)
        return compile_source(
            path.read_bytes().decode("utf-8"),
            root=root,
            filename=path,
            modules=self.modules,
            root_directory=directory,
            options=self.options,
            features=self.features if features is None else features,
            constant_modules=constant_modules,
            keep=self.keep if keep is _Unset.Value else keep,
            keep_root=self.keep_root if keep_root is None else keep_root,
            strip=self.strip if strip is None else strip,
            filenames=self.filenames,
            dependencies=self.dependencies,
        )


def check_syntax(source: str, *, filename: str | os.PathLike[str] = "<string>") -> None:
    return _native.check_syntax(source, os.fspath(filename))
