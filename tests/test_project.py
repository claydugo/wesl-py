from contextlib import chdir
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
        compiled = wesl.compile_file(filename)
        compiler = wesl.Compiler.from_project(shaders / "nested")
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


def test_project_loading_is_explicit_for_memory_sources(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"wesl\.toml"):
        wesl.Compiler.from_project(tmp_path)
    (tmp_path / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (tmp_path / "settings.wesl").write_text("const value = 7u;")
    source = (
        "import package::settings::value; "
        "@compute @workgroup_size(1) fn main() { let result = value; }"
    )
    with chdir(tmp_path), pytest.raises(wesl.CompileError):
        wesl.compile_source(source)


@pytest.mark.parametrize(
    "dependencies",
    [
        'dependencies = "auto"',
        "[dependencies]\nlibrary = {}",
        '[dependencies]\nlibrary = { package = "library" }',
    ],
)
def test_project_reports_unsupported_dependencies(
    tmp_path: Path, dependencies: str
) -> None:
    (tmp_path / "wesl.toml").write_text(
        f'edition = "2026_pre"\nroot = "."\n{dependencies}\n'
    )
    with pytest.raises(NotImplementedError, match="path dependencies"):
        wesl.Compiler.from_project(tmp_path)


def test_project_rejects_dependency_cycles(tmp_path: Path) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\nrecursive = { path = "." }\n'
    )
    with pytest.raises(ValueError, match="cycle"):
        wesl.Compiler.from_project(tmp_path)


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
    result = wesl.Compiler.from_project(tmp_path).compile_source(
        "@group(0) @binding(1) var<storage, read_write> output: array<u32>; "
        "@compute @workgroup_size(1) fn main() { "
        "output[0] = alpha::next(); output[1] = beta::next(); }"
    )
    assert result.wgsl.count("@binding(0)") == 1
    output = compute_with_buffers(
        {0: b"\x07\x00\x00\x00"}, {1: (2, "I")}, result.wgsl, n=1
    )
    assert list(output[1]) == [8, 9]


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
    assert "7u" in wesl.compile_file(filename).wgsl


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


@pytest.mark.parametrize("sourcemap", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        "fn value() -> u32 { return beta::value(); }",
        "import beta::value as imported; fn value() -> u32 { return imported(); }",
        "import {beta::value as imported}; fn value() -> u32 { return imported(); }",
    ],
)
def test_project_rejects_undeclared_dependency_imports(
    tmp_path: Path, source: str, *, sourcemap: bool
) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "alpha" }\nbeta = { path = "beta" }\n'
    )
    for name in ("alpha", "beta"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (tmp_path / "alpha/package.wesl").write_text(source)
    (tmp_path / "beta/package.wesl").write_text("fn value() -> u32 { return 7u; }")
    compiler = wesl.Compiler.from_project(
        tmp_path, options=wesl.CompileOptions(sourcemap=sourcemap)
    )
    with pytest.raises(wesl.CompileError, match="beta"):
        compiler.compile_source(
            "@compute @workgroup_size(1) fn main() { let result = alpha::value(); }"
        )


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


def test_scoped_overrides_isolate_shared_package_dependencies(tmp_path: Path) -> None:
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
    compiler = wesl.Compiler.from_project(
        tmp_path, dependencies={"alpha/common": tmp_path / "replacement"}
    )
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
    assert diagnostic.line == 2  # noqa: PLR2004
