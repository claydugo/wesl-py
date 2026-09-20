import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from email import message_from_bytes
from pathlib import Path

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
        "_assertions.wesl",
        *(path.name for path in (project_directory / "python/wesl").glob("*.py*")),
    ):
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
    (directory / "pixi.toml").write_text(
        '[workspace]\nname = "wesl-artifact"\nchannels = ["conda-forge"]\n'
        "platforms = [" + json.dumps(platform) + "]\n"
        "[dependencies]\npython = "
        + json.dumps(f"{python_version}.*")
        + '\npytest = "*"\n'
        + (
            'python-freethreading = "*"\n'
            if arguments.python.endswith("t")
            else ('python-gil = "*"\n' if python_version != "3.12" else "")
        )
        + ('mypy = "*"\n' if arguments.stubtest else "")
        + (
            'pytest-regressions = "*"\npytest-xdist = "*"\n'
            if arguments.extra == "testing"
            else ""
        )
        + "[pypi-dependencies]\nwesl-py = { "
        + (
            "version = " + json.dumps(f"=={version}")
            if arguments.find_links
            else "path = " + json.dumps(wheel.as_posix())
        )
        + (", extras = " + json.dumps([arguments.extra]) if arguments.extra else "")
        + " }\n"
        + (
            '[pypi-options]\nno-build = ["wesl-py"]\nfind-links = [{ path = '
            + json.dumps(arguments.find_links.resolve(strict=True).as_posix())
            + " }]\n"
            if arguments.find_links
            else ""
        )
        + (
            '[feature.prerelease]\nchannels = ["conda-forge", '
            '"conda-forge/label/python_rc"]\n'
            '[environments]\ndefault = { features = ["prerelease"] }\n'
            if python_version == "3.15"
            else ""
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
            "-c",
            (
                "import hashlib, json, os, sys, sysconfig; from pathlib import Path; "
                "from email import message_from_string; "
                "from importlib.metadata import distribution, version; "
                "from importlib.util import find_spec; "
                "assert sys.version_info[:2] == "
                "tuple(map(int, sys.argv[2].split('.'))); "
                "assert bool(sysconfig.get_config_var('Py_GIL_DISABLED')) "
                "== (sys.argv[3] == 'true'); "
                "assert sys.argv[3] != 'true' or 'PYTHON_GIL' not in os.environ; "
                "assert sys.argv[3] != 'true' or not sys._is_gil_enabled(); "
                "import wesl; "
                "assert sys.argv[3] != 'true' or not sys._is_gil_enabled(); "
                "from wesl import _native; "
                "assert hashlib.sha256(Path(_native.__file__).read_bytes())"
                ".hexdigest() == sys.argv[6]; "
                "assert set(message_from_string(distribution('wesl-py').read_text("
                "'WHEEL')).get_all('Tag')) == set(json.loads(sys.argv[4])); "
                "assert wesl.__version__ == version('wesl-py') == sys.argv[1]; "
                "assert Path(_native.__file__).is_relative_to(sys.prefix); "
                "assert Path(wesl.__file__).is_relative_to(sys.prefix); "
                "assert Path(wesl.__file__).with_name('py.typed').is_file(); "
                "assert Path(wesl.__file__).with_name('_native.pyi').is_file(); "
                "assert 'wgpu' not in sys.modules; "
                "assert (find_spec('wgpu') is None) == (sys.argv[5] == 'true'); "
                "assert not list((Path(sys.prefix) / 'conda-meta')"
                ".glob('rust-*.json')); "
                "print(json.dumps({'python': sys.version, "
                "'extension': _native.__file__, "
                "'binding': wesl.__version__, 'compiler': wesl.compiler_version}))"
            ),
            str(version),
            python_version,
            json.dumps(arguments.python.endswith("t")),
            json.dumps(wheel_metadata.get_all("Tag")),
            json.dumps(arguments.extra is None),
            extension_hash,
        ],
        cwd=directory,
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
    if arguments.extra == "examples":
        subprocess.run(
            [
                "pixi",
                "run",
                "python",
                "-c",
                (
                    "import imageio, numpy, wgpu; "
                    "import imgui_bundle, glfw, pygfx, rendercanvas, tifffile"
                ),
            ],
            cwd=directory,
            check=True,
        )
    if arguments.extra == "examples":
        subprocess.run(
            [
                "pixi",
                "run",
                "python",
                "-m",
                "pytest",
                "tests/examples/test_multiscale.py",
                "tests/examples/test_example_render.py",
                "tests/examples/test_sdf.py",
                "-q",
            ],
            cwd=directory,
            check=True,
        )
    if arguments.extra == "testing":
        subprocess.run(
            [
                "pixi",
                "run",
                "python",
                "-m",
                "pytest",
                "tests/test_testing.py",
                "tests/test_pytest_plugin.py",
                "tests/examples/test_rmsnorm.py",
                "tests/examples/test_compaction.py",
                "tests/shaders",
                "tests/examples/rmsnorm",
                "tests/examples/compaction",
                "tests/examples/testing",
                "-q",
            ],
            cwd=directory,
            check=True,
        )
    if arguments.compute:
        subprocess.run(
            [
                "pixi",
                "run",
                "python",
                "-c",
                (
                    "import wgpu; "
                    "adapter = wgpu.gpu.request_adapter_sync(); "
                    "assert adapter.info['adapter_type'] == 'CPU'; "
                    "assert adapter.info['backend_type'] == 'Vulkan'; "
                    "print(adapter.info)"
                ),
            ],
            cwd=directory,
            check=True,
        )
        subprocess.run(
            ["pixi", "run", "python", "-m", "pytest", "tests/test_compute.py", "-q"],
            cwd=directory,
            check=True,
        )
    if arguments.extra is None:
        for filename in (
            "test_compile.py",
            "test_check_syntax.py",
            "test_threading.py",
            "test_diagnostics.py",
            "test_sources.py",
        ):
            subprocess.run(
                ["pixi", "run", "python", "-m", "pytest", f"tests/{filename}", "-q"],
                cwd=directory,
                check=True,
            )
