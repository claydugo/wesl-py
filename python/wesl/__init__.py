import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from . import _native
from ._native import (
    CompileError,
    CompileResult,
    Diagnostic,
    __version__,
    compiler_version,
)

__all__ = [
    "CompileError",
    "CompileResult",
    "Diagnostic",
    "__version__",
    "check_syntax",
    "compile",
    "compile_file",
    "compile_source",
    "compiler_version",
    "validate",
]


def compile(
    modules: Mapping[str, str],
    *,
    root: str = "package::main",
    features: Mapping[str, bool] | None = None,
    strip: bool = True,
    keep_root: bool = False,
    mangle_root: bool = False,
    keep: Sequence[str] | None = None,
    missing_features: Literal["disable", "error"] = "disable",
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
) -> CompileResult:
    if not isinstance(modules, Mapping):
        raise TypeError("modules must be a mapping")
    copied_modules = dict(modules)
    if features is None:
        copied_features = {}
    elif isinstance(features, Mapping):
        copied_features = dict(features)
    else:
        raise TypeError("features must be a mapping or None")
    if not all(isinstance(value, bool) for value in copied_features.values()):
        raise TypeError("feature values must be booleans")
    if not all(isinstance(value, bool) for value in (strip, keep_root, mangle_root)):
        raise TypeError("compiler options must be booleans")
    if isinstance(keep, str):
        raise TypeError("keep must be a sequence of declaration names")
    if filenames is not None and not isinstance(filenames, Mapping):
        raise TypeError("filenames must be a mapping or None")
    return _native.compile(
        copied_modules,
        root,
        copied_features,
        strip,
        keep_root,
        mangle_root,
        None if keep is None else list(keep),
        missing_features,
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
    features: Mapping[str, bool] | None = None,
    strip: bool = True,
    keep_root: bool = False,
    mangle_root: bool = False,
    keep: Sequence[str] | None = None,
    missing_features: Literal["disable", "error"] = "disable",
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
        features=features,
        strip=strip,
        keep_root=keep_root,
        mangle_root=mangle_root,
        keep=keep,
        missing_features=missing_features,
        filenames=copied_filenames,
        root_directory=root_directory,
    )


def compile_file(
    filename: str | os.PathLike[str],
    *,
    modules: Mapping[str, str] | None = None,
    root_directory: str | os.PathLike[str] | None = None,
    features: Mapping[str, bool] | None = None,
    strip: bool = True,
    keep_root: bool = False,
    mangle_root: bool = False,
    keep: Sequence[str] | None = None,
    missing_features: Literal["disable", "error"] = "disable",
    filenames: Mapping[str, str | os.PathLike[str]] | None = None,
) -> CompileResult:
    path = Path(filename).resolve(strict=True)
    directory = (
        path.parent
        if root_directory is None
        else Path(root_directory).resolve(strict=True)
    )
    root = "package::" + "::".join(path.relative_to(directory).with_suffix("").parts)
    return compile_source(
        path.read_bytes().decode("utf-8"),
        modules=modules,
        root=root,
        filename=path,
        features=features,
        strip=strip,
        keep_root=keep_root,
        mangle_root=mangle_root,
        keep=keep,
        missing_features=missing_features,
        filenames=filenames,
        root_directory=directory,
    )


def check_syntax(source: str, *, filename: str | os.PathLike[str] = "<string>") -> None:
    return _native.check_syntax(source, os.fspath(filename))


def validate(source: str, *, filename: str | os.PathLike[str] = "<string>") -> None:
    return _native.validate(source, os.fspath(filename))
