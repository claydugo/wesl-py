from contextlib import chdir
from copy import copy
from importlib import import_module
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


def test_project_loads_scoped_path_dependencies(tmp_path: Path) -> None:
    (tmp_path / "shaders").mkdir()
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\n[dependencies]\n'
        'alpha = { path = "alpha" }\nbeta = { path = "beta" }\n'
        'shared = { path = "left" }\n'
    )
    for name, dependency in (("alpha", "left"), ("beta", "right")):
        directory = tmp_path / name
        (directory / "src").mkdir(parents=True)
        (directory / "wesl.toml").write_text(
            'edition = "2026_pre"\nroot = "src"\n[dependencies]\n'
            f'common = {{ path = "../{dependency}" }}\n'
        )
        (directory / "src/package.wesl").write_text(
            "fn value() -> u32 { return common::value(); }"
        )
    for name, value in (("left", 1), ("right", 2)):
        directory = tmp_path / name
        (directory / "src").mkdir(parents=True)
        (directory / "wesl.toml").write_text('edition = "2026_pre"\nroot = "src"\n')
        (directory / "src/package.wesl").write_text(
            f"fn value() -> u32 {{ return {value}u; }}"
        )
    source = (
        "@compute @workgroup_size(1) fn main() { "
        "let result = alpha::value() + beta::value() + shared::value(); }"
    )
    (tmp_path / "shaders/main.wesl").write_text(source)
    compiler = wesl.Compiler.from_project(tmp_path)
    result = compiler.compile_file("main.wesl")
    assert set(result.modules) == {
        "package::main",
        "alpha",
        "beta",
        "beta/common",
        "shared",
    }
    assert "1u" in result.wgsl
    assert "2u" in result.wgsl
    (tmp_path / "left/src/package.wesl").write_text("fn value() -> u32 { return 5u; }")
    assert "5u" in compiler.compile_source(source).wgsl
    override = tmp_path / "override"
    override.mkdir()
    (override / "package.wesl").write_text("fn value() -> u32 { return 9u; }")
    compiler = wesl.Compiler.from_project(
        tmp_path, dependencies={"alpha/common": override}
    )
    result = compiler.compile_source(source)
    assert "9u" in result.sources["alpha/common"].text
    assert "2u" in result.sources["beta/common"].text
    assert "5u" in result.sources["shared"].text


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


def test_directory_overrides_retain_child_dependencies(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    library = tmp_path / "library"
    library.mkdir()
    (library / "package.wesl").write_text(
        "fn value() -> u32 { return common::value(); }"
    )
    common = tmp_path / "common"
    common.mkdir()
    (common / "package.wesl").write_text(
        "fn value() -> u32 { return settings::value; }"
    )
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "package.wesl").write_text("const value = 7u;")
    directories = {
        "library": library,
        "library/common": common,
        "library/common/settings": settings,
    }
    source = "@compute @workgroup_size(1) fn main() { let result = library::value(); }"
    expected = wesl.compile_source(source, dependencies=directories)
    compiler = wesl.Compiler.from_project(tmp_path, dependencies=directories)
    assert compiler.compile_source(source) == expected
    assert "7u" in expected.wgsl


@pytest.mark.gpu
def test_project_shares_dependency_state_and_bindings(tmp_path: Path) -> None:
    pytest.importorskip("wgpu", exc_type=ModuleNotFoundError)
    compute_with_buffers = import_module("wgpu.utils.compute").compute_with_buffers
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "alpha" }\nbeta = { path = "beta" }\n'
    )
    for name in ("alpha", "beta"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "wesl.toml").write_text(
            'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
            'common = { path = "../common" }\n'
        )
        (directory / "package.wesl").write_text(
            "fn next() -> u32 { return common::next(); }"
        )
    common = tmp_path / "common"
    common.mkdir()
    (common / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (common / "package.wesl").write_text(
        "@group(0) @binding(0) var<storage, read> values: array<u32>; "
        "var<private> counter: u32 = 0u; "
        "fn next() -> u32 { counter += 1u; return values[0] + counter; }"
    )
    compiler = wesl.Compiler.from_project(tmp_path)
    dependencies = copy(compiler.dependencies)
    result = wesl.compile_source(
        "@group(0) @binding(1) var<storage, read_write> output: array<u32>; "
        "@compute @workgroup_size(1) fn main() { "
        "output[0] = alpha::next(); output[1] = beta::next(); }",
        dependencies=dependencies,
    )
    assert result.wgsl.count("@binding(0)") == 1
    output = compute_with_buffers(
        {0: b"\x07\x00\x00\x00"}, {1: (2, "I")}, result.wgsl, n=1
    )
    assert list(output[1]) == [8, 9]
    assert isinstance(dependencies, wesl.Dependencies)
    with pytest.raises(TypeError):
        dict(dependencies)
    with pytest.raises(TypeError):
        dependencies.directories["alpha"] = tmp_path
    with pytest.raises(TypeError):
        dependencies.aliases["beta/common"] = "beta"


@pytest.mark.gpu
@pytest.mark.parametrize(
    "sourcemap", [False, True], ids=["no-source-map", "source-map"]
)
def test_virtual_overrides_preserve_dependency_identity(
    tmp_path: Path, *, sourcemap: bool
) -> None:
    pytest.importorskip("wgpu", exc_type=ModuleNotFoundError)
    compute_with_buffers = import_module("wgpu.utils.compute").compute_with_buffers
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "library" }\nbeta = { path = "library" }\n'
    )
    library = tmp_path / "library"
    library.mkdir()
    (library / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'common = { path = "../common" }\n'
    )
    source = (
        "var<private> counter: u32 = 0u; "
        "fn next() -> u32 { counter += 1u; return counter + common::offset; }"
    )
    (library / "package.wesl").write_text(source)
    common = tmp_path / "common"
    common.mkdir()
    (common / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (common / "package.wesl").write_text("const offset = 7u;")
    compiler = wesl.Compiler.from_project(
        tmp_path,
        options=wesl.CompileOptions(sourcemap=sourcemap),
        modules={"beta": source},
        filenames={
            "beta": "generated-library.wesl",
            "beta/common": "generated-common.wesl",
        },
    )
    result = compiler.compile_source(
        "@group(0) @binding(0) var<storage, read_write> output: array<u32>; "
        "@compute @workgroup_size(1) fn main() { "
        "output[0] = alpha::next(); output[1] = beta::next(); }",
        constant_modules={"beta/common": {"offset": 9}},
    )
    assert result.modules == ("package::main", "alpha", "alpha/common")
    output = compute_with_buffers({}, {0: (2, "I")}, result.wgsl, n=1)
    assert list(output[0]) == [10, 11]
    if sourcemap:
        assert result.sources["alpha"].filename == "generated-library.wesl"
        assert result.sources["alpha/common"].filename == "generated-common.wesl"
    compiler.modules = {}
    result = compiler.compile_source(source, root="beta", keep=["next"])
    assert result.modules == ("alpha", "alpha/common")
    assert "7u" in result.wgsl
    compiler.modules = {"alpha": source, "beta": source}
    result = compiler.compile_source("fn main() { alpha::next(); }", keep=["main"])
    assert result.modules == ("package::main", "alpha", "alpha/common")
    compiler.modules = {"alpha": source, "beta": "fn next() -> u32 { return 1u; }"}
    with pytest.raises(ValueError, match="conflicting sources for module alpha"):
        compiler.compile_source("fn main() { alpha::next(); }", keep=["main"])
    compiler.modules = {"beta": source}
    compiler.filenames = {"alpha": "first.wesl", "beta": "second.wesl"}
    with pytest.raises(ValueError, match="conflicting filenames for module alpha"):
        compiler.compile_source("fn main() { alpha::next(); }", keep=["main"])


def test_project_compiler_keeps_its_manifest_context(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\n[dependencies]\nambient = { path = "library" }\n'
    )
    (tmp_path / "project").mkdir()
    (tmp_path / "project/wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "../shaders"\n'
    )
    (tmp_path / "library").mkdir()
    (tmp_path / "library/wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (tmp_path / "library/package.wesl").write_text("fn value() -> u32 { return 7u; }")
    (tmp_path / "shaders").mkdir()
    source = "@compute @workgroup_size(1) fn main() { let result = ambient::value(); }"
    filename = tmp_path / "shaders/main.wesl"
    filename.write_text(source)
    compiler = wesl.Compiler.from_project(tmp_path / "project")
    with pytest.raises(wesl.CompileError, match="ambient"):
        compiler.compile_source(source)
    with pytest.raises(wesl.CompileError, match="ambient"):
        compiler.compile_file("main.wesl")
    with pytest.raises(wesl.CompileError, match="ambient"):
        wesl.compile_file(
            filename,
            root_directory=compiler.root_directory,
            dependencies=compiler.dependencies,
        )
    with pytest.raises(wesl.CompileError, match="ambient"):
        wesl.compile_file(filename)
    assert "7u" in wesl.Compiler.from_project(tmp_path).compile_file("main.wesl").wgsl


def test_dependency_snapshots_fix_relative_paths(tmp_path: Path) -> None:
    for name, value in (("first", 1), ("second", 2)):
        directory = tmp_path / name / "library"
        directory.mkdir(parents=True)
        (directory / "package.wesl").write_text(
            f"fn value() -> u32 {{ return {value}u; }}"
        )
    directories = {"library": "library"}
    with chdir(tmp_path / "first"):
        dependencies = wesl.Dependencies(directories)
    directories.clear()
    with chdir(tmp_path / "second"):
        result = wesl.compile_source(
            "@compute @workgroup_size(1) fn main() { let value = library::value(); }",
            dependencies=dependencies,
        )
    assert result.sources["library"].filename == str(
        tmp_path / "first/library/package.wesl"
    )
    assert "1u" in result.wgsl


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


def test_project_snapshots_manifests_but_reloads_shader_sources(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'library = { path = "library" }\n'
    )
    library = tmp_path / "library"
    library.mkdir()
    (library / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'common = { path = "../first" }\n'
    )
    (library / "package.wesl").write_text(
        "fn value() -> u32 { return common::value(); }"
    )
    for name, value in (("first", 1), ("second", 2)):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
        (directory / "package.wesl").write_text(
            f"fn value() -> u32 {{ return {value}u; }}"
        )
    source = "@compute @workgroup_size(1) fn main() { let result = library::value(); }"
    compiler = wesl.Compiler.from_project(tmp_path)
    expected = compiler.compile_source(source)
    (library / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'common = { path = "../second" }\n'
    )
    assert compiler.compile_source(source) == expected
    assert "2u" in wesl.Compiler.from_project(tmp_path).compile_source(source).wgsl
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'library = { path = "second" }\n'
    )
    assert compiler.compile_source(source) == expected
    assert wesl.Compiler.from_project(tmp_path).compile_source(source).modules == (
        "package::main",
        "library",
    )
    (tmp_path / "first/package.wesl").write_text("fn value() -> u32 { return 7u; }")
    assert "7u" in compiler.compile_source(source).wgsl


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


def test_project_rejects_cycles_between_direct_dependencies(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "alpha" }\nbeta = { path = "beta" }\n'
    )
    for name, dependency in (("alpha", "beta"), ("beta", "alpha")):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "wesl.toml").write_text(
            'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
            f'other = {{ path = "../{dependency}" }}\n'
        )
    with pytest.raises(ValueError, match="cycle"):
        wesl.Compiler.from_project(tmp_path)


@pytest.mark.parametrize(
    "override_parents", [False, True], ids=["child-only", "parents-and-child"]
)
def test_scoped_overrides_isolate_shared_package_dependencies(
    tmp_path: Path, *, override_parents: bool
) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "library" }\nbeta = { path = "library" }\n'
    )
    (tmp_path / "library").mkdir()
    (tmp_path / "library/wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'common = { path = "../common" }\n'
    )
    (tmp_path / "library/package.wesl").write_text(
        "fn value() -> u32 { return common::value(); }"
    )
    for name, value in (("common", 1), ("replacement", 2)):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
        (directory / "package.wesl").write_text(
            f"fn value() -> u32 {{ return {value}u; }}"
        )
    directories = {"alpha/common": tmp_path / "replacement"}
    if override_parents:
        directories.update(
            {
                "alpha": tmp_path / "library",
                "beta": tmp_path / "library",
                "beta/common": tmp_path / "common",
            }
        )
    compiler = wesl.Compiler.from_project(tmp_path, dependencies=directories)
    result = compiler.compile_source(
        "@compute @workgroup_size(1) fn main() { "
        "let result = alpha::value() + beta::value(); }"
    )
    assert "2u" in result.sources["alpha/common"].text
    assert "1u" in result.sources["beta/common"].text


def test_project_dependencies_preserve_original_diagnostics(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'library = { path = "library" }\n'
    )
    (tmp_path / "library").mkdir()
    (tmp_path / "library/wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    filename = tmp_path / "library/package.wesl"
    source = "fn value() -> u32 {\n  return missing;\n}"
    filename.write_text(source)
    compiler = wesl.Compiler.from_project(tmp_path)
    with pytest.raises(wesl.CompileError, match="missing") as error:
        compiler.compile_source(
            "@compute @workgroup_size(1) fn main() { let result = library::value(); }"
        )
    (diagnostic,) = error.value.diagnostics
    assert diagnostic.filename == str(filename)
    assert diagnostic.source == source
    assert diagnostic.line == 2
