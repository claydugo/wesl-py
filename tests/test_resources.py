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
def test_resource_loader_follows_shared_directories_and_rejects_cycles(
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

    (shared / "loop").symlink_to(shared, target_is_directory=True)
    looped = tmp_path / "looped"
    looped.mkdir()
    (looped / "main.wesl").write_text("fn main() {}")
    (looped / "first").symlink_to(looped, target_is_directory=True)
    (looped / "second").symlink_to(looped, target_is_directory=True)
    for directory in (root, looped):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys, wesl; from pathlib import Path; "
                    "wesl.load_modules(Path(sys.argv[1]), namespace='package')"
                ),
                str(directory),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        assert result.returncode != 0
        assert "ValueError: resource directory contains a cycle" in result.stderr


def test_resource_loader_rejects_path_aliases(tmp_path: Path) -> None:
    for first, second in [("wesl", "wgsl"), ("wgsl", "wesl"), ("wesl", "wesl")]:
        archive_path = tmp_path / f"{first}_{second}.zip"
        with ZipFile(archive_path, "w") as archive:
            archive.writestr(f"a::b.{first}", "fn first() {}")
            archive.writestr(f"a/b.{second}", "fn second() {}")
        with (
            ZipFile(archive_path) as archive,
            pytest.raises(ValueError, match="duplicate module"),
        ):
            wesl.load_modules(ZipPath(archive), namespace="package")


def test_directories_and_archives_load_the_same_modules(tmp_path: Path) -> None:
    directory = tmp_path / "shaders"
    (directory / "nested").mkdir(parents=True)
    helper = "fn café() -> u32 {\r\n    return 2u;\r\n}"
    (directory / "nested/helper.wesl").write_bytes(helper.encode())
    (directory / "nested/helper.wgsl").write_text("fn ignored() {}")
    source = "fn value() -> u32 { return package::nested::helper::café(); }"
    (directory / "package.wesl").write_text(source, encoding="utf-8")
    (directory / "package.wgsl").write_text("fn ignored() {}")
    (directory / "math.test.wesl").write_text("@test fn unfinished(")
    (directory / "notes.txt").write_text("not a shader")
    loaded = wesl.load_modules(directory, namespace="imaging")
    with ZipFile(tmp_path / "resources.zip", "w") as archive:
        for path in directory.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(directory))
    with ZipFile(tmp_path / "resources.zip") as archive:
        packaged = wesl.load_modules(ZipPath(archive), namespace="imaging")
    assert loaded.modules == packaged.modules
    assert loaded.modules == {"imaging": source, "imaging::nested::helper": helper}
    assert loaded.filenames["imaging"] == str(directory / "package.wesl")
    assert loaded.filenames["imaging::nested::helper"] == str(
        directory / "nested/helper.wesl"
    )
    assert (
        packaged.filenames["imaging::nested::helper"] == "imaging::nested::helper.wesl"
    )
    shader = "@compute @workgroup_size(1) fn main() { let value = imaging::value(); }"
    assert (
        wesl.compile_source(shader, modules=packaged.modules).wgsl
        == wesl.compile_source(shader, dependencies={"imaging": directory}).wgsl
    )
