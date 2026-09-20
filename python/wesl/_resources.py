import os
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import NamedTuple


class LoadedModules(NamedTuple):
    modules: dict[str, str]
    filenames: dict[str, str]


def load_modules(
    directory: str | os.PathLike[str] | Traversable, *, namespace: str
) -> LoadedModules:
    root = Path(directory) if isinstance(directory, (str, os.PathLike)) else directory
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    selected: dict[str, tuple[tuple[str, ...], str, Traversable]] = {}
    directories: list[tuple[tuple[str, ...], Traversable, frozenset[Path]]] = [
        ((), root, frozenset())
    ]
    while directories:
        parts, resource, ancestors = directories.pop()
        resolved = resource.resolve() if isinstance(resource, Path) else None
        if resolved is not None and resolved in ancestors:
            raise ValueError("resource directory contains a cycle")
        ancestors = ancestors | {resolved} if resolved is not None else ancestors
        for child in sorted(resource.iterdir(), key=lambda child: child.name):
            if child.is_dir():
                directories.append(((*parts, child.name), child, ancestors))
                continue
            filename = PurePosixPath(child.name)
            if filename.suffix not in {".wesl", ".wgsl"}:
                continue
            module_path = (*parts, filename.stem)
            name = namespace + "::" + "::".join(module_path)
            previous = selected.get(name)
            if previous is not None and (
                module_path != previous[0] or filename.suffix == previous[1]
            ):
                raise ValueError(f"duplicate module: {name}")
            if previous is None or filename.suffix == ".wesl":
                selected[name] = (module_path, filename.suffix, child)
    modules = {}
    filenames = {}
    for name, (_, _, resource) in sorted(selected.items()):
        modules[name] = resource.read_bytes().decode("utf-8")
        filenames[name] = (
            str(resource.resolve())
            if isinstance(resource, Path)
            else name + (".wesl" if resource.name.endswith(".wesl") else ".wgsl")
        )
    return LoadedModules(modules, filenames)
