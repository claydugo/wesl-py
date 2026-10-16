from __future__ import annotations

import pickle
import sys
from collections import UserDict
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


def test_compile_results_are_owned_values(tmp_path: Path) -> None:
    result = wesl.compile_source(
        """
            import package::helper::value;
            @compute @workgroup_size(1) fn main() { let result = value(); }
        """,
        modules={
            "package::helper": "fn value() -> u32 { return 7u; }",
            "package::unused": "fn broken( }",
        },
        filename=tmp_path / "main.wesl",
        options=wesl.CompileOptions(mangle_main=True),
    )
    assert isinstance(result, wesl.CompileResult)
    assert result.modules == ("package::main", "package::helper")
    assert result.entry_points == ("package_main_main",)
    assert "fn package_main_main(" in result.wgsl
    assert str(result) == result.wgsl
    assert pickle.loads(pickle.dumps(result)) == result
    assert result.sources["package::main"].filename == str(tmp_path / "main.wesl")
    with pytest.raises(AttributeError):
        result.wgsl = "changed"
    result.sources.clear()
    assert result.sources["package::helper"].text == "fn value() -> u32 { return 7u; }"
    with pytest.raises(AttributeError):
        result.sources["package::helper"].text = "changed"

    inputs = [f"fn value() -> u32 {{ return {value}u; }}" for value in range(12)]
    with ThreadPoolExecutor() as executor:
        results = list(
            executor.map(
                lambda source: wesl.compile_source(
                    source, options=wesl.CompileOptions(keep=["value"])
                ),
                inputs,
            )
        )
    assert [result.sources["package::main"].text for result in results] == inputs


@pytest.mark.parametrize(
    "visibility",
    [
        pytest.param(False, id="unchecked"),
        pytest.param(
            True,
            id="checked",
            marks=pytest.mark.xfail(
                strict=True,
                raises=wesl.CompileError,
                reason="wesl-rs treats imports within named packages as public",
            ),
        ),
    ],
)
def test_named_package_local_imports_allow_package_visibility(
    *, visibility: bool
) -> None:
    try:
        result = wesl.compile_source(
            "@compute @workgroup_size(1) fn main() { library::value(); }",
            modules={
                "library": "import package::helper::value as helper; "
                "public fn value() { helper(); }",
                "library::helper": "fn value() {}",
            },
            options=wesl.CompileOptions(visibility=visibility),
        )
    except wesl.CompileError:
        assert visibility
        with pytest.raises(
            wesl.CompileError,
            match=(
                "`library::helper::value` is declared with `package` visibility, "
                "but another declaration imports it with `public` visibility"
            ),
        ):
            raise
        raise
    assert "fn library_helper_value(" in result.wgsl


def test_compile_file_resolves_imports_from_the_file_tree(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    root = tmp_path / "nested" / "main.wesl"
    root.write_text(
        "import super::super::helper::value; fn main() -> u32 { return value(); }"
    )
    helper = tmp_path / "helper.wgsl"
    helper.write_text("fn value() -> u32 { return 7u; }")
    (tmp_path / "unused.wesl").write_text("fn broken( }")
    options = wesl.CompileOptions(keep=["main"])
    result = wesl.compile_file(root, root_directory=tmp_path, options=options)
    assert result.modules == ("package::nested::main", "package::helper")
    assert result.sources["package::nested::main"].filename == str(root)
    assert result.sources["package::helper"].filename == str(helper)
    assert "7u" in result.wgsl
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 3u; }")
    assert (
        "3u" in wesl.compile_file(root, root_directory=tmp_path, options=options).wgsl
    )
    result = wesl.compile_file(
        root,
        root_directory=tmp_path,
        modules={"package::helper": "fn value() -> u32 { return 1u; }"},
        options=options,
    )
    assert "1u" in result.wgsl


@pytest.mark.parametrize("suffix", ["wesl", "wgsl"])
def test_compile_file_uses_the_package_root(tmp_path: Path, suffix: str) -> None:
    (tmp_path / "wesl.toml").write_text('edition = "2026_pre"\nroot = "elsewhere"\n')
    filename = tmp_path / f"package.{suffix}"
    filename.write_text(
        "import package::helper::value; "
        "@compute @workgroup_size(1) fn main() { let result = value(); }"
    )
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 7u; }")
    result = wesl.compile_file(filename)
    assert result.modules == ("package", "package::helper")
    assert result.sources["package"].filename == str(filename)
    assert "7u" in result.wgsl
    assert wesl.compile_file(filename, dependencies={}) == result
    compiler = wesl.Compiler(root_directory=tmp_path)
    assert compiler.compile_file(filename.name) == result
    loaded = wesl.load_modules(tmp_path, namespace="package")
    assert (
        wesl.compile(loaded.modules, root="package", filenames=loaded.filenames)
        == result
    )
    nested = tmp_path / "shaders"
    nested.mkdir()
    (nested / f"main.{suffix}").write_text(filename.read_text())
    (nested / "helper.wesl").write_text("fn value() -> u32 { return 9u; }")
    nested_result = wesl.compile_file(nested / f"main.{suffix}")
    assert nested_result.modules == ("package::main", "package::helper")
    assert "9u" in nested_result.wgsl


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require privileges.")
def test_compile_file_follows_symlinks(tmp_path: Path) -> None:
    directory = tmp_path / "shaders"
    directory.mkdir()
    source = tmp_path / "main.wesl"
    source.write_text(
        "import package::helper::value; "
        "@compute @workgroup_size(1) fn main() { value(); }"
    )
    (directory / "main.wesl").symlink_to(source)
    (directory / "helper.wesl").write_text("fn value() {}")
    expected = wesl.compile({}, root_directory=directory)
    explicit = wesl.compile_file(directory / "main.wesl", root_directory=directory)
    implicit = wesl.compile_file(directory / "main.wesl")
    assert explicit == implicit == expected

    (tmp_path / "actual/nested").mkdir(parents=True)
    (tmp_path / "link").symlink_to(tmp_path / "actual/nested", target_is_directory=True)
    (tmp_path / "actual/main.wesl").write_text(source.read_text())
    (tmp_path / "actual/helper.wesl").write_text("fn value() {}")
    result = wesl.compile_file(tmp_path / "link/../main.wesl")
    assert result.entry_points == ("main",)
    assert result.modules == ("package::main", "package::helper")
    assert result.sources["package::helper"].filename == str(
        tmp_path / "actual/helper.wesl"
    )


def test_diagnostics_label_sources_without_side_effects(tmp_path: Path) -> None:
    modules = UserDict({"package::helper": "fn value( }"})
    filenames = UserDict({"package::helper": tmp_path / "generated.wesl"})
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_source(
            "import package::helper::value; fn main() { value(); }",
            modules=modules,
            filenames=filenames,
            options=wesl.CompileOptions(keep=["main"]),
        )
    assert caught.value.diagnostics[0].filename == str(tmp_path / "generated.wesl")
    assert modules == {"package::helper": "fn value( }"}
    assert filenames == {"package::helper": tmp_path / "generated.wesl"}
    assert not (tmp_path / "generated.wesl").exists()

    source = "fn café() {\r\n    )\r\n}"
    filename = tmp_path / "main.wesl"
    filename.write_bytes(source.encode())
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_file(filename)
    (diagnostic,) = caught.value.diagnostics
    start = source.encode().rindex(b")")
    assert diagnostic.source == source
    assert diagnostic.span == (start, start + 1)
    assert (diagnostic.line, diagnostic.column) == (2, 5)


def test_directory_dependencies_follow_imports_and_reload(tmp_path: Path) -> None:
    library = tmp_path / "library"
    (library / "nested").mkdir(parents=True)
    (library / "package.wesl").write_text(
        "import package::nested::operations::value; "
        "fn compute() -> u32 { return value(); }"
    )
    (library / "nested/operations.wesl").write_text(
        "import super::settings::offset; import shared::factor; "
        "fn value() -> u32 { return offset + factor; }"
    )
    (library / "nested/settings.wgsl").write_text("const offset = 7u;")
    (library / "2D.wesl").write_text("invalid unused shader")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "package.wesl").write_text("const factor = 3u;")
    source = (
        "import library::compute; "
        "@compute @workgroup_size(1) fn main() { let value = compute(); }"
    )
    (tmp_path / "main.wesl").write_text(source)
    compiler = wesl.Compiler(
        root_directory=tmp_path,
        dependencies={"library": library, "library/shared": str(shared)},
    )
    result = compiler.compile_file("main.wesl")
    assert set(result.modules) == {
        "package::main",
        "library",
        "library::nested::operations",
        "library::nested::settings",
        "library/shared",
    }
    assert result.sources["library"].filename == str(library / "package.wesl")
    assert result.sources["library::nested::settings"].filename == str(
        library / "nested/settings.wgsl"
    )
    (shared / "package.wesl").write_text("const factor = 11u;")
    result = compiler.compile_source(source)
    assert result.sources["library/shared"].text == "const factor = 11u;"


def test_scoped_dependencies_do_not_share_a_flat_namespace(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    shared = tmp_path / "shared"
    replacement = tmp_path / "replacement"
    for directory in (left, right, shared, replacement):
        directory.mkdir()
    source = "import shared::value; fn compute() -> u32 { return value(); }"
    (left / "package.wesl").write_text(source)
    (right / "package.wesl").write_text(source)
    (shared / "package.wesl").write_text("fn value() -> u32 { return 3u; }")
    (replacement / "package.wesl").write_text(
        "import package::helpers::number; fn value() -> u32 { return number; }"
    )
    (replacement / "helpers.wesl").write_text("const number = 7u;")
    result = wesl.compile_source(
        "@compute @workgroup_size(1) fn main() { "
        "let first = left::compute(); let second = right::compute(); "
        "let third = shared::value(); }",
        dependencies={
            "left": left,
            "right": right,
            "shared": shared,
            "left/shared": replacement,
        },
        modules={"right/shared": "fn value() -> u32 { return 11u; }"},
    )
    assert result.sources["left/shared"].filename == str(replacement / "package.wesl")
    assert result.sources["left/shared::helpers"].filename == str(
        replacement / "helpers.wesl"
    )
    assert result.sources["shared"].filename == str(shared / "package.wesl")
    assert result.sources["right/shared"].text == "fn value() -> u32 { return 11u; }"

    modules = {
        "package::main": """
            import alpha::value as first;
            import beta::value as second;
            @compute @workgroup_size(1) fn main() { let sum = first() + second(); }
        """,
        "alpha": "import common::value as common_value; "
        "fn value() -> u32 { return common_value(); }",
        "beta": "import common::value as common_value; "
        "fn value() -> u32 { return common_value(); }",
        "alpha/common": "fn value() -> u32 { return 3u; }",
        "beta/common": "fn value() -> u32 { return 7u; }",
        "common": "fn value() -> u32 { return 99u; }",
    }
    result = wesl.compile(modules)
    assert result.modules[0] == "package::main"
    assert set(result.modules) == {
        "package::main",
        "alpha",
        "alpha/common",
        "beta",
        "beta/common",
    }
    assert "3u" in result.wgsl
    assert "7u" in result.wgsl
    assert "99u" not in result.wgsl
    del modules["alpha/common"]
    with pytest.raises(wesl.CompileError, match="alpha/common"):
        wesl.compile(modules)
    result = wesl.compile(
        modules, root="beta/common", options=wesl.CompileOptions(keep=["value"])
    )
    assert result.modules == ("beta/common",)
    assert "7u" in result.wgsl

    for namespace in ["library", "outer/library"]:
        grouped = {
            namespace: "import {library::helper::value}; fn entry() { value(); }",
            f"{namespace}::helper": "fn value() {}",
        }
        result = wesl.compile(
            grouped, root=namespace, options=wesl.CompileOptions(keep=["entry"])
        )
        assert set(result.modules) == {namespace, f"{namespace}::helper"}


@pytest.mark.parametrize(
    "sourcemap", [False, True], ids=["no-source-map", "source-map"]
)
def test_dependency_mappings_use_upstream_scopes(
    tmp_path: Path, *, sourcemap: bool
) -> None:
    common = tmp_path / "common"
    common.mkdir()
    (common / "package.wesl").write_text("fn value() -> u32 { return 7u; }")
    library = tmp_path / "library"
    library.mkdir()
    shader = "@compute @workgroup_size(1) fn main() { let value = library::value(); }"
    options = wesl.CompileOptions(sourcemap=sourcemap)
    for source in [
        "fn value() -> u32 { return common::value(); }",
        "import common::value as imported; fn value() -> u32 { return imported(); }",
        "import {common::value as imported}; fn value() -> u32 { return imported(); }",
    ]:
        (library / "package.wesl").write_text(source)
        directories = {"library": library, "common": common}
        with pytest.raises(wesl.CompileError, match="common"):
            wesl.compile_source(shader, options=options, dependencies=directories)
        directories["library/common"] = common
        result = wesl.compile_source(shader, options=options, dependencies=directories)
        assert "7u" in result.wgsl
        assert set(result.modules) == {"package::main", "library", "library/common"}
