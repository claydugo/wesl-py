from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath
from typing import NamedTuple


class LoadedModules(NamedTuple):
    modules: dict[str, str]
    filenames: dict[str, str]


def module_name(parts: tuple[str, ...], *, namespace: str) -> str:
    return namespace if parts == ("package",) else namespace + "::" + "::".join(parts)


def load_modules(directory: Traversable, *, namespace: str) -> LoadedModules:
    root = directory
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
            message = "resource directory contains a cycle"
            raise ValueError(message)
        ancestors = ancestors | {resolved} if resolved is not None else ancestors
        for child in sorted(resource.iterdir(), key=lambda child: child.name):
            if child.is_dir():
                directories.append(((*parts, child.name), child, ancestors))
                continue
            filename = PurePosixPath(child.name)
            if filename.suffix not in {".wesl", ".wgsl"} or child.name.endswith(
                ".test.wesl"
            ):
                continue
            module_path = (*parts, filename.stem)
            name = module_name(module_path, namespace=namespace)
            previous = selected.get(name)
            if previous is not None and (
                module_path != previous[0] or filename.suffix == previous[1]
            ):
                message = f"duplicate module: {name}"
                raise ValueError(message)
            if previous is None or filename.suffix == ".wesl":
                selected[name] = (module_path, filename.suffix, child)
    modules = {}
    filenames = {}
    for name, (_, suffix, resource) in sorted(selected.items()):
        modules[name] = resource.read_bytes().decode("utf-8")
        filenames[name] = (
            str(resource.resolve()) if isinstance(resource, Path) else name + suffix
        )
    return LoadedModules(modules, filenames)
