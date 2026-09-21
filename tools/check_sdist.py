import argparse
import os
import tarfile
import tempfile
import tomllib
from email import message_from_bytes
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("archive", type=Path)
arguments = parser.parse_args()
arguments.archive = arguments.archive.resolve(strict=True)
project_directory = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="wesl-sdist-") as temporary_directory:
    directory = Path(temporary_directory)
    with tarfile.open(arguments.archive) as archive:
        archive.extractall(directory, filter="data")
    (source,) = directory.iterdir()
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    package = tomllib.loads((source / "Cargo.toml").read_text())["package"]
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        assert os.environ["GITHUB_REF_NAME"] == f"v{package['version']}"
    assert (
        package["version"]
        == tomllib.loads((project_directory / "Cargo.toml").read_text())["package"][
            "version"
        ]
    )
    for filename in (
        "Cargo.lock",
        "pyproject.toml",
        "wesl.toml",
        "tools/fetch_test_shaders.py",
        *(
            path.relative_to(project_directory)
            for path in project_directory.glob("python/wesl/*.py")
        ),
        "python/wesl/_native.pyi",
        "python/wesl/py.typed",
        "python/wesl/shaders/wgsl_test/package.wesl",
        "python/wesl/shaders/wgsl_test/TestResult.wesl",
        "python/wesl/shaders/wgsl_test/wesl.toml",
        *project["license-files"],
        *(
            path.relative_to(project_directory)
            for directory in ("tests", "examples")
            for pattern in ("**/*.py", "**/*.wesl", "**/*.npz", "**/*.md", "**/*.toml")
            for path in (project_directory / directory).glob(pattern)
        ),
    ):
        assert (source / filename).read_bytes() == (
            project_directory / filename
        ).read_bytes(), filename
    for path in source.rglob("*"):
        assert path.name not in {
            ".git",
            ".pixi",
            ".wesl",
            "target",
            "vendor",
            "third_party",
            "patches",
            "__pycache__",
        }
        assert path.suffix not in {".so", ".pyd", ".pyc"}
    metadata = message_from_bytes((source / "PKG-INFO").read_bytes())
    assert metadata["Name"] == project["name"]
    assert metadata["Version"] == package["version"]
    assert metadata["Requires-Python"] == project["requires-python"]
    assert metadata["License-Expression"] == project.get("license")
    assert set(metadata.get_all("License-File", [])) == set(project["license-files"])
