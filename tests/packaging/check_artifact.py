import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from email import message_from_bytes
from pathlib import Path

import tomli_w
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.tags import parse_tag
from packaging.utils import canonicalize_name, parse_wheel_filename

project_directory = Path(__file__).resolve().parents[2]
project = tomllib.loads((project_directory / "pyproject.toml").read_text())["project"]
parser = argparse.ArgumentParser()
parser.add_argument("wheel", type=Path)
parser.add_argument("--python", default="3.12")
parser.add_argument("--extra", choices=project.get("optional-dependencies", {}))
parser.add_argument("--stubtest", action="store_true")
parser.add_argument("--compute", action="store_true")
parser.add_argument("--find-links", type=Path)
parser.add_argument("--abi-tag", default="cp312-abi3")
parser.add_argument("--platform-tag")
arguments = parser.parse_args()
python_version = arguments.python.removesuffix("t")
wheel = arguments.wheel.resolve(strict=True)
cargo = tomllib.loads((project_directory / "Cargo.toml").read_text())
package = cargo["package"]
name, version, _, tags = parse_wheel_filename(wheel.name)
assert name == canonicalize_name(project["name"])
assert str(version) == package["version"]
assert {(tag.interpreter, tag.abi) for tag in tags} == {
    (tag.interpreter, tag.abi) for tag in parse_tag(f"{arguments.abi_tag}-any")
}
if arguments.platform_tag:
    assert {tag.platform for tag in tags} == {arguments.platform_tag}
with zipfile.ZipFile(wheel) as archive:
    (metadata_path,) = (
        name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
    )
    metadata_directory = metadata_path.rsplit("/", 1)[0]
    metadata = message_from_bytes(archive.read(metadata_path))
    assert metadata["Name"] == project["name"]
    assert metadata["Version"] == package["version"]
    assert metadata["Requires-Python"] == project["requires-python"]
    assert metadata["License-Expression"] == project.get("license")
    assert set(metadata.get_all("Provides-Extra", [])) == {
        canonicalize_name(extra) for extra in project.get("optional-dependencies", {})
    }
    requirements = {Requirement(value) for value in project.get("dependencies", [])}
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        for value in dependencies:
            requirement = Requirement(value)
            marker = f'extra == "{canonicalize_name(extra)}"'
            requirement.marker = Marker(
                f"({requirement.marker}) and {marker}" if requirement.marker else marker
            )
            requirements.add(requirement)
    assert {
        Requirement(value) for value in metadata.get_all("Requires-Dist", [])
    } == requirements
    assert set(metadata.get_all("License-File", [])) == set(project["license-files"])
    for filename in project["license-files"]:
        assert (
            archive.read(f"{metadata_directory}/licenses/{filename}")
            == (project_directory / filename).read_bytes()
        ), filename
    sbom = json.loads(
        archive.read(f"{metadata_directory}/sboms/{package['name']}.cyclonedx.json")
    )
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["metadata"]["component"]["name"] == package["name"]
    assert sbom["metadata"]["component"]["version"] == package["version"]
    assert cargo["dependencies"].keys() <= {
        component["name"] for component in sbom["components"]
    }
    for filename in (
        "py.typed",
        *(
            path.relative_to(project_directory / "python/wesl").as_posix()
            for path in (project_directory / "python/wesl/wgsl_test").glob("*.wesl")
        ),
        *(path.name for path in (project_directory / "python/wesl").glob("*.py*")),
    ):
        assert f"wesl/{filename}" in archive.namelist(), filename
        if not filename.endswith(".py"):
            assert (
                archive.read(f"wesl/{filename}")
                == (project_directory / "python" / "wesl" / filename).read_bytes()
            ), filename
    wheel_metadata = message_from_bytes(archive.read(f"{metadata_directory}/WHEEL"))
    (extension_path,) = (
        name
        for name in archive.namelist()
        if name.startswith("wesl/_native.") and name.endswith((".so", ".pyd"))
    )
    extension_hash = hashlib.sha256(archive.read(extension_path)).hexdigest()
    assert wheel_metadata["Root-Is-Purelib"] == "false"
    assert (
        set().union(*(parse_tag(tag) for tag in wheel_metadata.get_all("Tag", [])))
        == tags
    )
platform = json.loads(subprocess.check_output(["pixi", "info", "--json"], text=True))[
    "platform"
]

with tempfile.TemporaryDirectory(prefix="wesl-artifact-") as temporary_directory:
    directory = Path(temporary_directory)
    manifest = {
        "workspace": {
            "name": "wesl-artifact",
            "channels": ["conda-forge"],
            "platforms": [platform],
        },
        "dependencies": {"python": f"{python_version}.*", "pytest": "*"},
        "pypi-dependencies": {"wesl-py": {}},
    }
    if arguments.python.endswith("t"):
        manifest["dependencies"]["python-freethreading"] = "*"
    elif python_version != "3.12":
        manifest["dependencies"]["python-gil"] = "*"
    if arguments.stubtest:
        manifest["dependencies"]["mypy"] = "*"
    if arguments.extra == "testing":
        manifest["dependencies"].update(
            {"numpy": ">=1.26", "pytest-regressions": "*", "pytest-xdist": "*"}
        )
    if arguments.find_links:
        manifest["pypi-dependencies"]["wesl-py"]["version"] = f"=={version}"
        manifest["pypi-options"] = {
            "no-build": ["wesl-py"],
            "find-links": [
                {"path": arguments.find_links.resolve(strict=True).as_posix()}
            ],
        }
    else:
        manifest["pypi-dependencies"]["wesl-py"]["path"] = wheel.as_posix()
    if arguments.extra:
        manifest["pypi-dependencies"]["wesl-py"]["extras"] = [arguments.extra]
    if python_version == "3.15":
        manifest["workspace"]["channels"].append("conda-forge/label/python_rc")
    (directory / "pixi.toml").write_text(tomli_w.dumps(manifest))
    (directory / "installation.json").write_text(
        json.dumps(
            {
                "kind": "wheel",
                "version": str(version),
                "python": python_version,
                "freethreading": arguments.python.endswith("t"),
                "tags": wheel_metadata.get_all("Tag"),
                "extension_hash": extension_hash,
                "extra": arguments.extra,
                "compute": arguments.compute,
            }
        )
    )
    shutil.copyfile(project_directory / "pyproject.toml", directory / "pyproject.toml")
    shutil.copytree(
        project_directory / "tests",
        directory / "tests",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    if arguments.extra:
        shutil.copytree(
            project_directory / "examples",
            directory / "examples",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    subprocess.run(
        [
            "pixi",
            "run",
            "python",
            "-m",
            "pytest",
            "tests/packaging/test_installed.py",
            "--installation=installation.json",
            "-q",
        ],
        cwd=directory,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        check=True,
    )
    if arguments.stubtest:
        subprocess.run(
            [
                "pixi",
                "run",
                "python",
                "-m",
                "mypy.stubtest",
                "wesl._native",
                "--concise",
            ],
            cwd=directory,
            check=True,
        )
    test_paths = []
    if arguments.extra == "examples":
        test_paths.extend(
            [
                "tests/examples/test_multiscale.py",
                "tests/examples/test_example_render.py",
                "tests/examples/test_sdf.py",
            ]
        )
    if arguments.extra == "testing":
        test_paths.extend(
            [
                "tests/test_testing.py",
                "tests/test_pytest_plugin.py",
                "tests/examples/test_rmsnorm.py",
                "tests/examples/test_compaction.py",
                "tests/shaders",
                "tests/examples/rmsnorm",
                "tests/examples/compaction",
                "tests/examples/testing",
            ]
        )
    if arguments.compute:
        test_paths.append("tests/test_compute.py")
    if arguments.extra is None:
        test_paths.extend(
            [
                "tests/test_compile.py",
                "tests/test_check_syntax.py",
                "tests/test_threading.py",
                "tests/test_diagnostics.py",
                "tests/test_sources.py",
            ]
        )
    if test_paths:
        subprocess.run(
            ["pixi", "run", "python", "-m", "pytest", *test_paths, "-q"],
            cwd=directory,
            check=True,
        )
