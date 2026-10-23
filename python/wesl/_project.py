from pathlib import Path

from . import _native


def absolute_path(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts:
        index = len(path.parts) - path.parts[::-1].index("..")
        path = Path(*path.parts[:index]).resolve() / Path(*path.parts[index:])
    return path


class Project:
    def __init__(self, manifest: Path) -> None:
        root, dependencies = _native.project(manifest.read_bytes().decode("utf-8"))
        self.root_directory = absolute_path(manifest.parent / root)
        self.dependencies = {
            name: absolute_path(manifest.parent / dependency)
            for name, dependency in dependencies.items()
        }


def load_project(directory: Path) -> Project | None:
    directory = absolute_path(directory)
    for parent in (directory, *directory.parents):
        manifest = parent / "wesl.toml"
        if manifest.is_file():
            return Project(manifest)
    return None
