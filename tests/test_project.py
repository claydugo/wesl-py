from contextlib import chdir
from pathlib import Path

import pytest
import wesl


def test_project_discovers_the_nearest_manifest(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text('edition = "2026_pre"\nroot = "missing"\n')
    project = tmp_path / "project"
    shaders = project / "shaders"
    (shaders / "nested").mkdir(parents=True)
    (project / "wesl.toml").write_text('edition = "2026_pre"\n')
    (shaders / "settings.wesl").write_text("const value = 7u;")
    source = (
        "import package::settings::value; "
        "@compute @workgroup_size(1) fn main() { let result = value; }"
    )
    filename = shaders / "nested/main.wesl"
    filename.write_text(source)
    with chdir(tmp_path):
        compiler = wesl.Compiler.from_project(shaders / "nested")
        compiled = wesl.compile_file(
            filename,
            root_directory=compiler.root_directory,
            dependencies=compiler.dependencies,
        )
        assert compiler.root_directory == shaders
        assert compiler.compile_file("nested/main.wesl") == compiled
        assert "7u" in compiler.compile_source(source).wgsl
    assert compiled.modules == ("package::nested::main", "package::settings")


def test_project_explicit_settings_take_precedence(tmp_path: Path) -> None:
    (tmp_path / "shaders").mkdir()
    (tmp_path / "library").mkdir()
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\n[dependencies]\nlibrary = { path = "unavailable" }\n'
    )
    (tmp_path / "main.wesl").write_text(
        "@compute @workgroup_size(1) fn main() { let result = library::value(); }"
    )
    (tmp_path / "library/package.wesl").write_text("fn value() -> u32 { return 7u; }")
    compiler = wesl.Compiler.from_project(
        tmp_path,
        root_directory=tmp_path,
        dependencies={"library": tmp_path / "library"},
    )
    result = compiler.compile_file("main.wesl")
    assert result.modules == ("package::main", "library")
    assert "7u" in result.wgsl


def test_project_paths_do_not_follow_working_directory_changes(tmp_path: Path) -> None:
    source = "@compute @workgroup_size(1) fn main() { let result = library::value(); }"
    for name, value in (("first", 1), ("second", 2)):
        directory = tmp_path / name
        (directory / "replacement").mkdir(parents=True)
        (directory / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
        (directory / "main.wesl").write_text(source)
        (directory / "replacement/package.wesl").write_text(
            f"fn value() -> u32 {{ return {value}u; }}"
        )
    with chdir(tmp_path / "first"):
        compiler = wesl.Compiler.from_project(
            ".", root_directory=".", dependencies={"library": "replacement"}
        )
        expected = compiler.compile_file("main.wesl")
    with chdir(tmp_path / "second"):
        assert compiler.compile_file("main.wesl") == expected
        assert compiler.compile_source(source).wgsl == expected.wgsl
        assert (
            wesl.compile_source(source, dependencies=compiler.dependencies).wgsl
            == expected.wgsl
        )


def test_project_discovery_normalizes_parent_components(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text('edition = "2026_pre"\n')
    shaders = tmp_path / "shaders"
    (shaders / "nested").mkdir(parents=True)
    (shaders / "nested/wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (shaders / "main.wesl").write_text("@compute @workgroup_size(1) fn main() {}")
    assert wesl.compile_file(shaders / "nested/../main.wesl") == wesl.compile_file(
        shaders / "main.wesl"
    )
    compiler = wesl.Compiler.from_project(shaders / "nested/..")
    assert compiler.root_directory == shaders
    assert compiler.compile_file("nested/../main.wesl").entry_points == ("main",)


def test_project_dependencies_preserve_original_diagnostics(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'library = { path = "library" }\n'
    )
    (tmp_path / "library").mkdir()
    (tmp_path / "library/wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    filename = tmp_path / "library/package.wesl"
    source = "fn value() -> u32 {\n  return missing;\n}"
    filename.write_text(source, newline="\n")
    compiler = wesl.Compiler.from_project(
        tmp_path, dependencies={"library": tmp_path / "library"}
    )
    with pytest.raises(wesl.CompileError, match="missing") as error:
        compiler.compile_source(
            "@compute @workgroup_size(1) fn main() { let result = library::value(); }"
        )
    (diagnostic,) = error.value.diagnostics
    assert diagnostic.filename == str(filename)
    assert diagnostic.source == source
    assert diagnostic.line == 2


def test_project_requires_explicit_dependencies(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'library = { path = "library" }\n'
    )
    library = tmp_path / "library"
    library.mkdir()
    (library / "package.wesl").write_text("fn value() -> u32 { return 7u; }")
    source = "@compute @workgroup_size(1) fn main() { let value = library::value(); }"
    compiler = wesl.Compiler.from_project(tmp_path)
    assert compiler.dependencies == {}
    with pytest.raises(wesl.CompileError, match="library"):
        compiler.compile_source(source)
    compiler = wesl.Compiler.from_project(tmp_path, dependencies={"library": library})
    assert "7u" in compiler.compile_source(source).wgsl
    (library / "package.wesl").write_text("fn value() -> u32 { return 9u; }")
    assert "9u" in compiler.compile_source(source).wgsl


def test_project_uses_upstream_manifest_validation(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text('edition = "2026_pre"\ninclude = 7\n')
    with pytest.raises(ValueError, match="sequence"):
        wesl.Compiler.from_project(tmp_path)
