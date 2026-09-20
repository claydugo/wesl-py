import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from email import message_from_bytes
from pathlib import Path

import tomli_w

parser = argparse.ArgumentParser()
parser.add_argument("archive", type=Path)
arguments = parser.parse_args()
arguments.archive = arguments.archive.resolve(strict=True)
project_directory = Path(__file__).resolve().parents[2]
platform = json.loads(subprocess.check_output(["pixi", "info", "--json"], text=True))[
    "platform"
]

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
        "build.rs",
        "wesl.toml",
        *(
            path.relative_to(project_directory)
            for path in project_directory.glob("python/wesl/*.py")
        ),
        "python/wesl/_native.pyi",
        "python/wesl/py.typed",
        *(
            path.relative_to(project_directory)
            for path in project_directory.glob("python/wesl/wgsl_test/*.wesl")
        ),
        *project["license-files"],
        *(
            path.relative_to(project_directory)
            for pattern in ("**/*.py", "**/*.wesl", "**/*.npz", "**/*.md")
            for path in (project_directory / "tests").glob(pattern)
        ),
    ):
        assert (source / filename).read_bytes() == (
            project_directory / filename
        ).read_bytes(), filename
    for path in source.rglob("*"):
        assert path.name not in {
            ".git",
            ".pixi",
            "target",
            "vendor",
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
    (directory / "pixi.toml").write_text(
        tomli_w.dumps(
            {
                "workspace": {
                    "name": "wesl-sdist",
                    "channels": ["conda-forge"],
                    "platforms": [platform],
                },
                "dependencies": {
                    "python": "3.12.*",
                    "rust": "==" + package["rust-version"],
                    "pytest": "*",
                },
                "pypi-dependencies": {
                    "wesl-py": {"path": arguments.archive.as_posix()}
                },
                "target": {
                    "linux-64": {
                        "activation": {
                            "env": {
                                "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER": "cc"
                            }
                        }
                    }
                },
            }
        )
    )
    (directory / "installation.json").write_text(
        json.dumps(
            {
                "kind": "sdist",
                "version": package["version"],
                "python": "3.12",
                "freethreading": False,
                "extra": None,
                "compute": False,
            }
        )
    )
    for filename in ("conftest.py", "test_installed.py"):
        shutil.copyfile(Path(__file__).with_name(filename), directory / filename)
    subprocess.run(
        [
            "pixi",
            "run",
            "python",
            "-m",
            "pytest",
            "test_installed.py",
            "--installation=installation.json",
            "-q",
        ],
        cwd=directory,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        check=True,
    )
