from __future__ import annotations

import pickle
import subprocess
import sys
from collections import UserDict
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from zipfile import Path as ZipPath
from zipfile import ZipFile

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


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


def test_compile_source_returns_emitted_names_and_dependencies() -> None:
    result = wesl.compile_source(
        """
            import package::helper::value;
            @compute @workgroup_size(1) fn main() { let result = value(); }
        """,
        modules={
            "package::helper": "fn value() -> u32 { return 7u; }",
            "package::unused": "fn broken( }",
        },
        options=wesl.CompileOptions(mangle_main=True),
    )
    assert isinstance(result, wesl.CompileResult)
    assert result.modules == ("package::main", "package::helper")
    assert result.entry_points == ("package_main_main",)
    assert "fn package_main_main(" in result.wgsl
    assert str(result) == result.wgsl
    assert pickle.loads(pickle.dumps(result)) == result  # noqa: S301
    with pytest.raises(AttributeError):
        result.wgsl = "changed"


def test_named_packages_resolve_local_and_external_dependencies() -> None:
    result = wesl.compile_source(
        "import noise::lib::value; fn main() -> u32 { return value(); }",
        modules={
            "noise::lib": """
                import package::settings::enabled;
                import arithmetic::one;
                fn value() -> u32 { return enabled + one; }
            """,
            "noise::settings": "const enabled = 2u;",
            "noise/arithmetic": "const one = 1u;",
        },
        options=wesl.CompileOptions(keep=["main"]),
    )
    assert result.modules[0] == "package::main"
    assert set(result.modules) == {
        "package::main",
        "noise::lib",
        "noise::settings",
        "noise/arithmetic",
    }


def test_named_package_local_imports_allow_package_visibility() -> None:
    result = wesl.compile_source(
        "@compute @workgroup_size(1) fn main() { library::value(); }",
        modules={
            "library": "import package::helper::value as helper; "
            "fn value() { helper(); }",
            "library::helper": "fn value() {}",
        },
    )
    assert "fn library_helper_value(" in result.wgsl


def test_compile_file_resolves_nested_imports_and_wgsl(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    root = tmp_path / "nested" / "main.wesl"
    root.write_text(
        "import super::super::helper::value; fn main() -> u32 { return value(); }"
    )
    (tmp_path / "helper.wgsl").write_text("fn value() -> u32 { return 7u; }")
    (tmp_path / "unused.wesl").write_text("fn broken( }")
    result = wesl.compile_file(
        root, root_directory=tmp_path, options=wesl.CompileOptions(keep=["main"])
    )
    assert result.modules == ("package::nested::main", "package::helper")
    assert "7u" in result.wgsl
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 3u; }")
    assert (
        "3u"
        in wesl.compile_file(
            root, root_directory=tmp_path, options=wesl.CompileOptions(keep=["main"])
        ).wgsl
    )
    result = wesl.compile_file(
        root,
        root_directory=tmp_path,
        modules={"package::helper": "fn value() -> u32 { return 1u; }"},
        options=wesl.CompileOptions(keep=["main"]),
    )
    assert "1u" in result.wgsl


@pytest.mark.skipif(
    sys.platform == "win32", reason="File symlinks require Windows privileges."
)
def test_compile_file_preserves_symlink_imports(tmp_path: Path) -> None:
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


@pytest.mark.parametrize(
    ("filename", "root_directory"),
    [("shaders/../shaders/main.wesl", "."), ("shaders/main.wesl", "shaders/..")],
)
def test_compile_file_accepts_parent_components(
    tmp_path: Path, filename: str, root_directory: str
) -> None:
    (tmp_path / "shaders").mkdir()
    (tmp_path / "shaders/main.wesl").write_text(
        "@compute @workgroup_size(1) fn main() {}"
    )
    result = wesl.compile_file(
        tmp_path / filename, root_directory=tmp_path / root_directory
    )
    assert result.modules == ("package::shaders::main",)
    assert result.entry_points == ("main",)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Directory symlinks require Windows privileges."
)
def test_compile_file_reads_parent_components_after_symlinks(tmp_path: Path) -> None:
    (tmp_path / "actual/nested").mkdir(parents=True)
    (tmp_path / "link").symlink_to(tmp_path / "actual/nested", target_is_directory=True)
    (tmp_path / "main.wesl").write_text("fn wrong() {}")
    (tmp_path / "actual/main.wesl").write_text(
        "import package::helper::value; "
        "@compute @workgroup_size(1) fn main() { value(); }"
    )
    (tmp_path / "actual/helper.wesl").write_text("fn value() {}")
    result = wesl.compile_file(tmp_path / "link/../main.wesl")
    assert result.entry_points == ("main",)
    assert result.modules == ("package::main", "package::helper")
    assert result.sources["package::helper"].text == "fn value() {}"


def test_compile_file_defaults_to_parent_and_reports_import_filenames(
    tmp_path: Path,
) -> None:
    root = tmp_path / "main.wesl"
    root.write_text("import package::helper::value; fn main() { value(); }")
    helper = tmp_path / "helper.wesl"
    helper.write_text("fn value( }")
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_file(root, options=wesl.CompileOptions(keep=["main"]))
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.filename == str(helper)
    assert diagnostic.module == "package::helper"
    assert diagnostic.source == helper.read_text()
    assert diagnostic.line == 1
    assert str(helper) in str(caught.value)
    with pytest.raises(FileNotFoundError):
        wesl.compile_file(tmp_path / "missing.wesl")
    (tmp_path / "other").mkdir()
    with pytest.raises(ValueError, match="not in the subpath"):
        wesl.compile_file(root, root_directory=tmp_path / "other")


def test_compilation_labels_sources_without_mutating_mappings(tmp_path: Path) -> None:
    source = "import package::helper::value; fn main() { value(); }"
    modules = UserDict({"package::helper": "fn value( }"})
    filenames = UserDict({"package::helper": tmp_path / "generated.wesl"})
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_source(
            source,
            modules=modules,
            filenames=filenames,
            options=wesl.CompileOptions(keep=["main"]),
        )
    assert caught.value.diagnostics[0].filename == str(tmp_path / "generated.wesl")
    assert modules == {"package::helper": "fn value( }"}
    assert filenames == {"package::helper": tmp_path / "generated.wesl"}
    assert not (tmp_path / "generated.wesl").exists()
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_source("fn main(")
    assert caught.value.diagnostics[0].filename == "<string>"
    with pytest.raises(ValueError, match="already present"):
        wesl.compile_source(source, modules={"package::main": source})


def test_compile_file_preserves_source_bytes_in_diagnostics(tmp_path: Path) -> None:
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


def test_result_metadata_follows_selected_features_and_declarations() -> None:
    result = wesl.compile_source(
        """
            @if(enabled) @compute @workgroup_size(1) fn first() {}
            @if(!enabled) @compute @workgroup_size(1) fn second() {}
            fn unused() {}
        """,
        options=wesl.CompileOptions(
            keep=["first"],
            features=wesl.Features(default=wesl.Feature.Error, flags={"enabled": True}),
        ),
    )
    assert result.entry_points == ("first",)
    assert result.modules == ("package::main",)


def test_bundled_assertions_need_no_registration() -> None:
    result = wesl.compile_source(
        "import wgsl_test::expectEq; "
        "@compute @workgroup_size(1) fn main() { expectEq(7u, 7u); }"
    )
    assert {"wgsl_test", "wgsl_test::TestResult"} <= set(result.modules)
    assert "fn expectEq(" in result.sources["wgsl_test"].text


def test_directory_dependencies_follow_imports_and_reload(tmp_path: Path) -> None:
    library = tmp_path / "library"
    (library / "nested").mkdir(parents=True)
    (library / "package.wesl").write_text(
        "import library::nested::operations::value; "
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
        dependencies={"library": library, "shared": str(shared)},
    )
    result = compiler.compile_file("main.wesl")
    assert set(result.modules) == {
        "package::main",
        "library",
        "library::nested::operations",
        "library::nested::settings",
        "shared",
    }
    assert result.sources["library"].filename == str(library / "package.wesl")
    assert result.sources["library::nested::settings"].filename == str(
        library / "nested/settings.wgsl"
    )
    (shared / "package.wesl").write_text("const factor = 11u;")
    result = compiler.compile_source(source)
    assert result.sources["shared"].text == "const factor = 11u;"


def test_directory_dependencies_preserve_scoped_overrides(tmp_path: Path) -> None:
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
        "import shared::helpers::number; fn value() -> u32 { return number; }"
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


def test_directory_dependency_diagnostics(tmp_path: Path) -> None:
    source = "fn value() -> u32 {\n    return absent;\n}"
    filename = tmp_path / "value.wesl"
    filename.write_text(source, newline="\n")
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_source(
            "@compute @workgroup_size(1) fn main() { "
            "let value = library::value::value(); }",
            dependencies={"library": tmp_path},
        )
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.module == "library::value"
    assert diagnostic.filename == str(filename)
    assert diagnostic.source == source
    assert diagnostic.span == (source.index("absent"), source.index("absent") + 6)


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
    with ZipFile(tmp_path / "resources.zip", "a") as archive:
        archive.writestr("nested::helper.wesl", "fn ambiguous() {}")
    with (
        ZipFile(tmp_path / "resources.zip") as archive,
        pytest.raises(ValueError, match="duplicate module"),
    ):
        wesl.load_modules(ZipPath(archive), namespace="imaging")


def test_source_records_preserve_text_and_filenames(tmp_path: Path) -> None:
    root = tmp_path / "main.wesl"
    root.write_text("import package::helper::value; fn main() { value(); }")
    helper = tmp_path / "helper.wgsl"
    helper.write_text("fn value() {}")
    result = wesl.compile_file(root, options=wesl.CompileOptions(keep=["main"]))
    assert result.sources["package::main"].filename == str(root)
    assert result.sources["package::helper"].filename == str(helper)
    generated = wesl.compile_source(
        "fn main() {}", filename=root, options=wesl.CompileOptions(keep=["main"])
    )
    assert generated.sources["package::main"].filename == str(root)
    result.sources.clear()
    assert result.sources["package::helper"].text == "fn value() {}"
    with pytest.raises(AttributeError):
        result.sources["package::helper"].text = "changed"


def test_source_metadata_is_owned_across_concurrent_calls() -> None:
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


def test_package_dependencies_do_not_share_a_flat_namespace() -> None:
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


def test_source_mapping_can_be_disabled() -> None:
    source = (
        "import package::helper::value; "
        "@compute @workgroup_size(1) fn main() { value(); }"
    )
    modules = {"package::helper": "fn value() {}"}
    mapped = wesl.compile_source(source, modules=modules)
    unmapped = wesl.compile_source(
        source, modules=modules, options=wesl.CompileOptions(sourcemap=False)
    )
    assert unmapped.wgsl == mapped.wgsl
    assert unmapped.modules == mapped.modules
    assert unmapped.entry_points == mapped.entry_points
    assert unmapped.sources == {}
