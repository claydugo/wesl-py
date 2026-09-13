from __future__ import annotations

import pickle
from collections import UserDict
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


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
        mangle_root=True,
    )
    assert isinstance(result, wesl.CompileResult)
    assert result.modules == ("package::helper", "package::main")
    assert result.entry_points == ("package_main_main",)
    assert result.declarations == {
        "package_helper_value": ("package::helper", "value"),
        "package_main_main": ("package::main", "main"),
    }
    assert "fn package_main_main(" in result.wgsl
    assert str(result) == result.wgsl
    assert pickle.loads(pickle.dumps(result)) == result  # noqa: S301
    result.declarations.clear()
    assert result.declarations["package_main_main"] == ("package::main", "main")
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
            "arithmetic": "const one = 1u;",
        },
        keep=["main"],
    )
    assert result.modules == (
        "arithmetic",
        "noise::lib",
        "noise::settings",
        "package::main",
    )
    assert ("noise::settings", "enabled") in result.declarations.values()
    assert ("arithmetic", "one") in result.declarations.values()
    wesl.validate(result.wgsl)


def test_compile_file_resolves_nested_imports_and_wgsl(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    root = tmp_path / "nested" / "main.wesl"
    root.write_text(
        "import super::super::helper::value; fn main() -> u32 { return value(); }"
    )
    (tmp_path / "helper.wgsl").write_text("fn value() -> u32 { return 7u; }")
    (tmp_path / "unused.wesl").write_text("fn broken( }")
    result = wesl.compile_file(root, root_directory=tmp_path, keep=["main"])
    assert result.modules == ("package::helper", "package::nested::main")
    assert result.declarations["main"] == ("package::nested::main", "main")
    assert "7u" in result.wgsl
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 3u; }")
    assert "3u" in wesl.compile_file(root, root_directory=tmp_path, keep=["main"]).wgsl
    result = wesl.compile_file(
        root,
        root_directory=tmp_path,
        modules={"package::helper": "fn value() -> u32 { return 1u; }"},
        keep=["main"],
    )
    assert "1u" in result.wgsl


def test_compile_file_defaults_to_parent_and_reports_import_filenames(
    tmp_path: Path,
) -> None:
    root = tmp_path / "main.wesl"
    root.write_text("import package::helper::value; fn main() { value(); }")
    helper = tmp_path / "helper.wesl"
    helper.write_text("fn value( }")
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_file(root, keep=["main"])
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
        wesl.compile_source(source, modules=modules, filenames=filenames, keep=["main"])
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
        features={"enabled": True},
        keep=["first"],
        missing_features="error",
    )
    assert result.entry_points == ("first",)
    assert result.declarations == {"first": ("package::main", "first")}
    assert result.modules == ("package::main",)
