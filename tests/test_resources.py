import subprocess
import sys
from pathlib import Path
from zipfile import Path as ZipPath
from zipfile import ZipFile

import pytest
import wesl


@pytest.mark.skipif(
    sys.platform == "win32", reason="Directory symlinks require Windows privileges."
)
def test_resource_loader_rejects_directory_cycles(tmp_path: Path) -> None:
    (tmp_path / "main.wesl").write_text("fn main() {}")
    (tmp_path / "first").symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "second").symlink_to(tmp_path, target_is_directory=True)
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            "import sys, wesl; wesl.load_modules(sys.argv[1], namespace='package')",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode != 0
    assert "ValueError: resource directory contains a cycle" in result.stderr


@pytest.mark.skipif(
    sys.platform == "win32", reason="Directory symlinks require Windows privileges."
)
def test_resource_loader_accepts_shared_directories_without_cycles(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "helper.wesl").write_text("fn value() {}")
    root = tmp_path / "root"
    root.mkdir()
    (root / "first").symlink_to(shared, target_is_directory=True)
    (root / "second").symlink_to(shared, target_is_directory=True)
    loaded = wesl.load_modules(root, namespace="package")
    assert loaded.modules == {
        "package::first::helper": "fn value() {}",
        "package::second::helper": "fn value() {}",
    }


@pytest.mark.parametrize(
    "suffixes", [("wesl", "wgsl"), ("wgsl", "wesl"), ("wesl", "wesl")]
)
def test_resource_loader_rejects_path_aliases(
    tmp_path: Path, suffixes: tuple[str, str]
) -> None:
    with ZipFile(tmp_path / "resources.zip", "w") as archive:
        archive.writestr(f"a::b.{suffixes[0]}", "fn first() {}")
        archive.writestr(f"a/b.{suffixes[1]}", "fn second() {}")
    with (
        ZipFile(tmp_path / "resources.zip") as archive,
        pytest.raises(ValueError, match="duplicate module"),
    ):
        wesl.load_modules(ZipPath(archive), namespace="package")


def test_resource_loader_preserves_bytes_and_module_names(tmp_path: Path) -> None:
    directory = tmp_path / "shaders"
    (directory / "nested").mkdir(parents=True)
    (directory / "nested" / "helper.wesl").write_bytes(
        "fn café() -> u32 {\r\n    return 2u;\r\n}".encode(),
    )
    (directory / "nested" / "helper.wgsl").write_text("fn ignored() {}")
    (directory / "notes.txt").write_text("not a shader")
    loaded = wesl.load_modules(directory, namespace="imaging")
    with ZipFile(tmp_path / "resources.zip", "w") as archive:
        for path in directory.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(directory))
    with ZipFile(tmp_path / "resources.zip") as archive:
        packaged = wesl.load_modules(ZipPath(archive), namespace="imaging")
    assert loaded.modules == packaged.modules
    assert list(loaded.modules) == ["imaging::nested::helper"]
    assert "\r\n" in loaded.modules["imaging::nested::helper"]
    assert loaded.filenames["imaging::nested::helper"] == str(
        directory / "nested" / "helper.wesl",
    )
    assert (
        packaged.filenames["imaging::nested::helper"] == "imaging::nested::helper.wesl"
    )
    result = wesl.compile_source(
        "import imaging::nested::helper::café; fn main() -> u32 { return café(); }",
        modules={
            **packaged.modules,
            "imaging::nested::helper": "fn café() -> u32 { return 7u; }",
        },
        options=wesl.CompileOptions(keep=["main"]),
    )
    assert "7u" in result.wgsl


def test_resource_loader_compiles_package_roots(tmp_path: Path) -> None:
    source = "fn value() -> u32 { return package::helper::value(); }"
    (tmp_path / "package.wesl").write_text(source)
    (tmp_path / "package.wgsl").write_text("fn ignored() {}")
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 7u; }")
    (tmp_path / "math.test.wesl").write_text("@test fn unfinished(")
    loaded = wesl.load_modules(tmp_path, namespace="library")
    assert loaded.modules["library"] == source
    assert loaded.filenames["library"] == str(tmp_path / "package.wesl")
    with ZipFile(tmp_path / "resources.zip", "w") as archive:
        for filename in (
            "package.wesl",
            "package.wgsl",
            "helper.wesl",
            "math.test.wesl",
        ):
            archive.write(tmp_path / filename, filename)
    with ZipFile(tmp_path / "resources.zip") as archive:
        packaged = wesl.load_modules(ZipPath(archive), namespace="library")
    assert packaged.modules == loaded.modules
    shader = "@compute @workgroup_size(1) fn main() { let value = library::value(); }"
    assert (
        wesl.compile_source(shader, modules=packaged.modules).wgsl
        == wesl.compile_source(shader, dependencies={"library": tmp_path}).wgsl
    )
