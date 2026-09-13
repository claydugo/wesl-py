import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pefile
from elftools.elf.elffile import ELFFile
from packaging.utils import parse_wheel_filename

parser = argparse.ArgumentParser()
parser.add_argument("wheels", nargs="+", type=Path)
arguments = parser.parse_args()

for wheel_path in arguments.wheels:
    wheel = wheel_path.resolve(strict=True)
    _, _, _, tags = parse_wheel_filename(wheel.name)
    (platform_tag,) = {tag.platform for tag in tags}
    with zipfile.ZipFile(wheel) as archive:
        extensions = {
            filename: archive.read(filename)
            for filename in archive.namelist()
            if filename.endswith((".so", ".pyd", ".dll", ".dylib"))
        }
        assert extensions, wheel
        if sys.platform == "linux":
            report = json.loads(
                subprocess.check_output(
                    ["auditwheel", "show", "--json", str(wheel)], text=True
                )
            )
            assert platform_tag.startswith("manylinux_"), platform_tag
            assert report["overall_tag"].startswith("manylinux_"), report
            assert tuple(map(int, report["overall_tag"].split("_")[1:3])) <= tuple(
                map(int, platform_tag.split("_")[1:3])
            ), report
            assert not report["external_libs"], report
            assert not report["unsupported_isa"], report
            for filename, content in extensions.items():
                binary = ELFFile(io.BytesIO(content))
                for entry in binary.get_section_by_name(".dynamic").iter_tags():
                    if entry.entry.d_tag in {"DT_RPATH", "DT_RUNPATH"}:
                        paths = getattr(
                            entry, entry.entry.d_tag.removeprefix("DT_").lower()
                        )
                        assert all(
                            not Path(path).is_absolute() for path in paths.split(":")
                        ), (filename, paths)
            continue

        with tempfile.TemporaryDirectory(prefix="wesl-native-") as temporary_directory:
            if sys.platform == "darwin":
                subprocess.run(["delocate-listdeps", "--all", str(wheel)], check=True)
                command = [
                    "delocate-wheel",
                    "--require-archs",
                    "arm64",
                    "--wheel-dir",
                    temporary_directory,
                    str(wheel),
                ]
            else:
                assert sys.platform == "win32", sys.platform
                for filename, content in extensions.items():
                    with pefile.PE(data=content) as binary:
                        assert (
                            binary.FILE_HEADER.Machine
                            == pefile.MACHINE_TYPE["IMAGE_FILE_MACHINE_AMD64"]
                        ), filename
                        dependencies = {
                            entry.dll.decode().lower()
                            for entry in binary.DIRECTORY_ENTRY_IMPORT
                        }
                        assert (
                            "python3t.dll"
                            if any(tag.abi == "abi3t" for tag in tags)
                            else "python3.dll"
                        ) in dependencies, (filename, dependencies)
                subprocess.run(["delvewheel", "show", str(wheel)], check=True)
                command = [
                    "delvewheel",
                    "repair",
                    "--wheel-dir",
                    temporary_directory,
                    str(wheel),
                ]
            subprocess.run(
                command,
                check=True,
                env={**os.environ, "MACOSX_DEPLOYMENT_TARGET": "11.0"}
                if sys.platform == "darwin"
                else None,
            )
            (repaired_wheel,) = Path(temporary_directory).glob("*.whl")
            with zipfile.ZipFile(repaired_wheel) as repaired:
                assert {
                    entry.filename
                    for entry in repaired.infolist()
                    if not entry.is_dir()
                } == {
                    entry.filename for entry in archive.infolist() if not entry.is_dir()
                }, wheel
                for filename, content in extensions.items():
                    assert repaired.read(filename) == content, filename
