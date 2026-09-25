import tomllib
from collections import deque
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from os import PathLike
from pathlib import Path


def absolute_path(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts:
        index = len(path.parts) - path.parts[::-1].index("..")
        path = Path(*path.parts[:index]).resolve() / Path(*path.parts[index:])
    return path


@dataclass(eq=False)
class ProjectDependencies(Mapping[str, Path]):
    directories: dict[str, Path]
    aliases: dict[str, str]

    def __getitem__(self, name: str) -> Path:
        return self.directories[self.aliases[name]]

    def __iter__(self) -> Iterator[str]:
        return iter(self.aliases)

    def __len__(self) -> int:
        return len(self.aliases)


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
    ) -> ProjectDependencies:
        if overrides is not None and not isinstance(overrides, Mapping):
            raise TypeError("dependencies must be a mapping or None")
        overrides = {} if overrides is None else overrides
        directories: dict[str, Path] = {}
        aliases: dict[str, str] = {}
        identities: dict[tuple[Path, tuple[tuple[str, Path], ...]], str] = {}
        pending: deque[tuple[Project, str, str]] = deque([(self, "", "")])
        while pending:
            project, namespace, scope = pending.popleft()
            configuration = project.dependencies
            if not isinstance(configuration, dict):
                raise NotImplementedError("only WESL path dependencies are supported")
            declared = dict(configuration)
            prefix = f"{scope}/" if scope else ""
            for name in overrides:
                if name.startswith(prefix) and "/" not in name.removeprefix(prefix):
                    declared[name.removeprefix(prefix)] = None
            for name, dependency in declared.items():
                dependency_name = f"{namespace}/{name}" if namespace else name
                dependency_scope = f"{prefix}{name}"
                if dependency_scope in overrides:
                    root = absolute_path(Path(overrides[dependency_scope]))
                    identity = (root.resolve(), ())
                    canonical = identities.setdefault(identity, dependency_name)
                    directories[canonical] = root
                    aliases[dependency_name] = canonical
                    continue
                if (
                    not isinstance(dependency, dict)
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
                manifest = absolute_path(project.manifest.parent / path) / "wesl.toml"
                resolved_dependency = manifest.resolve()
                dependency_prefix = f"{dependency_scope}/"
                identity = (
                    resolved_dependency,
                    tuple(
                        sorted(
                            (name.removeprefix(dependency_prefix), Path(path).resolve())
                            for name, path in overrides.items()
                            if name.startswith(dependency_prefix)
                        )
                    ),
                )
                canonical = identities.setdefault(identity, dependency_name)
                aliases[dependency_name] = canonical
                if canonical in directories:
                    continue
                loaded = Project(manifest)
                directories[canonical] = loaded.root_directory
                pending.append((loaded, canonical, dependency_scope))
        graph: dict[str, set[str]] = {}
        for name, canonical in aliases.items():
            parent = name.rpartition("/")[0]
            graph.setdefault(parent, set()).add(canonical)
        try:
            TopologicalSorter(graph).prepare()
        except CycleError as error:
            raise ValueError("WESL path dependencies contain a cycle") from error
        return ProjectDependencies(directories, aliases)


def load_project(directory: Path) -> Project | None:
    directory = absolute_path(directory)
    for parent in (directory, *directory.parents):
        manifest = parent / "wesl.toml"
        if manifest.is_file():
            return Project(manifest)
    return None
