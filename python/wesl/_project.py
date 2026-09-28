import tomllib
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from os import PathLike
from pathlib import Path
from types import MappingProxyType


def absolute_path(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts:
        index = len(path.parts) - path.parts[::-1].index("..")
        path = Path(*path.parts[:index]).resolve() / Path(*path.parts[index:])
    return path


@dataclass(frozen=True, eq=False, init=False)
class Dependencies:
    directories: Mapping[str, Path]
    aliases: Mapping[str, str]

    def __init__(self, directories: Mapping[str, str | PathLike[str]]) -> None:
        object.__setattr__(
            self,
            "directories",
            MappingProxyType(
                {name: absolute_path(Path(path)) for name, path in directories.items()}
            ),
        )
        object.__setattr__(self, "aliases", MappingProxyType({}))


class Project:
    def __init__(self, manifest: Path) -> None:
        self.manifest = manifest
        with manifest.open("rb") as stream:
            configuration = tomllib.load(stream)
        if configuration.get("edition") != "2026_pre":
            raise ValueError("unsupported WESL edition")
        root = Path(configuration.get("root", "shaders"))
        if root.is_absolute():
            raise ValueError("the WESL root must be relative to its manifest")
        self.root_directory = absolute_path(manifest.parent / root)
        self.dependencies = configuration.get("dependencies", {})

    def load_dependencies(  # noqa: C901
        self, overrides: Mapping[str, str | PathLike[str]] | None = None
    ) -> Dependencies:
        if overrides is not None and not isinstance(overrides, Mapping):
            raise TypeError("dependencies must be a mapping or None")
        overrides = {} if overrides is None else overrides
        directories: dict[str, Path] = {}
        aliases: dict[str, str] = {}
        identities: dict[tuple[Path, tuple[tuple[str, Path], ...]], str] = {}
        pending: deque[tuple[Project | None, str, str]] = deque([(self, "", "")])
        while pending:
            project, namespace, scope = pending.popleft()
            configuration = {} if project is None else project.dependencies
            if not isinstance(configuration, dict):
                raise NotImplementedError("only WESL path dependencies are supported")
            declared = dict(configuration)
            prefix = f"{scope}/" if scope else ""
            declared.update(
                (name.removeprefix(prefix), None)
                for name in overrides
                if name.startswith(prefix) and "/" not in name.removeprefix(prefix)
            )
            for name, dependency in declared.items():
                dependency_name = f"{namespace}/{name}" if namespace else name
                dependency_scope = f"{prefix}{name}"
                dependency_prefix = f"{dependency_scope}/"
                scoped_overrides = tuple(
                    sorted(
                        (name.removeprefix(dependency_prefix), Path(path).resolve())
                        for name, path in overrides.items()
                        if name.startswith(dependency_prefix)
                    )
                )
                if dependency_scope in overrides:
                    path = absolute_path(Path(overrides[dependency_scope]))
                else:
                    if (
                        project is None
                        or not isinstance(dependency, dict)
                        or "path" not in dependency
                        or "package" in dependency
                    ):
                        raise NotImplementedError(
                            "only WESL path dependencies are supported"
                        )
                    path = Path(dependency["path"])
                    if path.is_absolute():
                        raise ValueError(
                            "dependency paths must be relative to their manifest"
                        )
                    path = absolute_path(project.manifest.parent / path) / "wesl.toml"
                identity = (path.resolve(), scoped_overrides)
                canonical = identities.setdefault(identity, dependency_name)
                aliases[dependency_name] = canonical
                if canonical in directories:
                    continue
                loaded = None if dependency_scope in overrides else Project(path)
                directories[canonical] = (
                    path if loaded is None else loaded.root_directory
                )
                pending.append((loaded, canonical, dependency_scope))
        graph: dict[str, set[str]] = {}
        for name, canonical in aliases.items():
            parent = name.rpartition("/")[0]
            graph.setdefault(parent, set()).add(canonical)
        try:
            TopologicalSorter(graph).prepare()
        except CycleError as error:
            raise ValueError("WESL path dependencies contain a cycle") from error
        dependencies = Dependencies(directories)
        object.__setattr__(dependencies, "aliases", MappingProxyType(aliases))
        return dependencies


def load_project(directory: Path) -> Project | None:
    directory = absolute_path(directory)
    for parent in (directory, *directory.parents):
        manifest = parent / "wesl.toml"
        if manifest.is_file():
            return Project(manifest)
    return None
