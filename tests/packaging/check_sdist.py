import argparse
import json
import os
import subprocess
import tarfile
import tempfile
import tomllib
from email import message_from_bytes
from pathlib import Path

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
        "ci/pixi.toml",
        "ci/pixi.lock",
        "wesl.toml",
        "TODO.md",
        "ROADMAP.md",
        *(
            path.relative_to(project_directory)
            for path in project_directory.glob("python/wesl/*.py")
        ),
        "python/wesl/_native.pyi",
        "python/wesl/py.typed",
        "python/wesl/_assertions.wesl",
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
        '[workspace]\nname = "wesl-sdist"\nchannels = ["conda-forge"]\n'
        "platforms = [" + json.dumps(platform) + "]\n"
        '[dependencies]\npython = "3.12.*"\nrust = '
        + json.dumps("==" + package["rust-version"])
        + "\n[pypi-dependencies]\nwesl-py = { path = "
        + json.dumps(arguments.archive.as_posix())
        + " }\n[target.linux-64.activation.env]\n"
        'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER = "cc"\n'
    )
    subprocess.run(
        [
            "pixi",
            "run",
            "python",
            "-c",
            (
                "import sys, wesl; from pathlib import Path; "
                "from importlib.metadata import version; "
                "from importlib.util import find_spec; "
                "assert Path(wesl.__file__).is_relative_to(sys.prefix); "
                "assert wesl.__version__ == version('wesl-py') == sys.argv[1]; "
                "assert find_spec('maturin') is None; "
                "result = wesl.compile_source("
                "'@compute @workgroup_size(1) fn main() {}'); "
                "assert 'fn main(' in result.wgsl"
            ),
            package["version"],
        ],
        cwd=directory,
        check=True,
    )
