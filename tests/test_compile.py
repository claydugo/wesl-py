from __future__ import annotations

import re
from collections import UserDict
from concurrent.futures import ThreadPoolExecutor
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(("enabled", "expected"), [(False, 3), (True, 7)])
def test_imports_conditions_and_root_bindings(
    modules: dict[str, str], *, enabled: bool, expected: int
) -> None:
    result = wesl.compile(modules, features={"enabled": enabled}).wgsl
    assert isinstance(result, str)
    assert "package_settings_value" in result
    assert "fn main(" in result
    assert "@group(0)" in result
    assert "@binding(0)" in result
    assert re.search(rf"return\s+{expected}u\s*;", result)
    assert "@if" not in result
    assert "import " not in result


@pytest.mark.parametrize(("enabled", "expected"), [(False, 3), (True, 7)])
def test_conditional_statements(*, enabled: bool, expected: int) -> None:
    result = wesl.compile(
        {
            "package::main": """
                fn value() -> u32 {
                    @if(enabled) return 7u;
                    @if(!enabled) return 3u;
                }
            """
        },
        features={"enabled": enabled},
        strip=False,
    ).wgsl
    assert re.search(rf"return\s+{expected}u\s*;", result)
    assert result.count("return") == 1


def test_unspecified_features_are_disabled_per_call(modules: dict[str, str]) -> None:
    assert "7u" in wesl.compile(modules, features={"enabled": True}).wgsl
    assert "3u" in wesl.compile(modules).wgsl
    assert "3u" in wesl.compile(modules, features={"unrelated": True}).wgsl


def test_stripping_root_preservation_and_mangling() -> None:
    modules = {"package::main": "fn value() -> u32 { return 7u; }"}
    assert wesl.compile(modules).wgsl.strip() == ""
    assert "fn value(" in wesl.compile(modules, keep_root=True).wgsl
    assert "fn value(" in wesl.compile(modules, strip=False).wgsl
    assert (
        wesl.compile(modules, strip=False).wgsl
        == wesl.compile(modules, strip=False, keep_root=True).wgsl
    )
    assert (
        "fn package_main_value("
        in wesl.compile(modules, strip=False, mangle_root=True).wgsl
    )


def test_keep_selects_declarations_and_their_dependencies() -> None:
    modules = {
        "package::main": """
            import package::helper::value;
            fn exported() -> u32 { return value(); }
            @compute @workgroup_size(1) fn first() { let result = exported(); }
            @compute @workgroup_size(1) fn second() {}
        """,
        "package::helper": "fn value() -> u32 { return 7u; }",
    }
    result = wesl.compile(modules, keep=["first"]).wgsl
    assert "fn first(" in result
    assert "fn exported(" in result
    assert "fn package_helper_value(" in result
    assert "fn second(" not in result
    result = wesl.compile(modules, keep=("exported",)).wgsl
    assert "fn exported(" in result
    assert "@compute" not in result
    assert not wesl.compile(modules, keep=[]).wgsl.strip()


def test_missing_feature_policy() -> None:
    modules = {"package::main": "@if(enabled) @compute @workgroup_size(1) fn main() {}"}
    with pytest.raises(wesl.CompileError, match="unexpected feature flag"):
        wesl.compile(modules, features={"enabeld": True}, missing_features="error")
    assert not wesl.compile(
        modules, features={"enabled": False}, missing_features="error"
    ).wgsl.strip()
    assert (
        "fn main("
        in wesl.compile(
            modules, features={"enabled": True}, missing_features="error"
        ).wgsl
    )
    with pytest.raises(ValueError, match="missing_features"):
        wesl.compile(modules, missing_features="invalid")
    with pytest.raises(TypeError, match="keep"):
        wesl.compile(modules, keep="main")


@pytest.mark.parametrize("options", [{"strip": False}, {"keep_root": True}])
def test_unused_helpers_resolve_imports_when_preserved(
    options: dict[str, bool],
) -> None:
    modules = {
        "package::main": """
            import package::missing::value;
            fn helper() -> u32 { return value(); }
            @compute @workgroup_size(1) fn main() {}
        """
    }
    assert "fn main(" in wesl.compile(modules).wgsl
    with pytest.raises(wesl.CompileError):
        wesl.compile(modules, **options)


def test_unused_imports_and_unresolved_sources_are_not_validated() -> None:
    modules = {
        "package::main": "import package::missing::value; fn main() {}",
        "package::unused": "fn broken( }",
    }
    assert "fn main(" in wesl.compile(modules, strip=False).wgsl


def test_imported_names_collide_with_preserved_root_names() -> None:
    modules = {
        "package::main": """
            import package::helper::value;
            fn package_helper_value() -> u32 { return 1u; }
            fn main() -> u32 { return value(); }
        """,
        "package::helper": "fn value() -> u32 { return 2u; }",
    }
    with pytest.raises(wesl.CompileError, match="duplicate declaration"):
        wesl.compile(modules, strip=False)
    assert (
        "fn package_main_main("
        in wesl.compile(modules, strip=False, mangle_root=True).wgsl
    )


def test_imports_can_read_root_bindings() -> None:
    result = wesl.compile(
        {
            "package::main": """
                import package::helper::value;
                struct Settings { value: u32, }
                @group(0) @binding(0) var<uniform> settings: Settings;
                fn main() -> u32 { return value(); }
            """,
            "package::helper": """
                import package::main::settings;
                fn value() -> u32 { return settings.value; }
            """,
        },
        strip=False,
    ).wgsl
    assert "settings.value" in result
    assert "package_main_settings" not in result
    assert "@binding(0)" in result


def test_relative_imports_stay_in_the_package() -> None:
    result = wesl.compile(
        {
            "package::main": """
                import package::nested::helper::value;
                fn main() -> u32 { return value(); }
            """,
            "package::nested::helper": """
                import super::super::settings::answer;
                fn value() -> u32 { return answer; }
            """,
            "package::settings": "const answer = 7u;",
        },
        strip=False,
    ).wgsl
    assert "package_settings_answer" in result


@pytest.mark.parametrize("name", ["café", "fn", "async"])
def test_module_names_follow_upstream_path_grammar(name: str) -> None:
    modules = {f"package::{name}": "fn value() -> u32 { return 1u; }"}
    assert (
        "fn value(" in wesl.compile(modules, root=f"package::{name}", strip=False).wgsl
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "self::main",
        "super::main",
        "alpha/beta::main",
        "package::",
        "package::::main",
        "package::main::",
        "package::bad-name",
        "package::9bad",
        "package::bad?",
        "package:: main",
        "package::main/*comment*/",
        "package::else",
    ],
)
def test_module_keys_and_root_reject_invalid_paths(path: str) -> None:
    with pytest.raises(ValueError, match="invalid module path") as caught:
        wesl.compile({path: ""})
    assert path in str(caught.value)
    with pytest.raises(ValueError, match="invalid module path") as caught:
        wesl.compile({"package::main": ""}, root=path)
    assert path in str(caught.value)


@pytest.mark.parametrize(
    ("modules", "options"),
    [
        ([], {}),
        ({"package::main": 1}, {}),
        ({1: ""}, {}),
        ({"package::main": ""}, {"root": 1}),
        ({"package::main": ""}, {"features": []}),
        ({"package::main": ""}, {"features": {"enabled": 1}}),
        ({"package::main": ""}, {"features": {"enabled": "false"}}),
        ({"package::main": ""}, {"features": {1: True}}),
        ({"package::main": ""}, {"strip": 1}),
        ({"package::main": ""}, {"keep_root": None}),
        ({"package::main": ""}, {"mangle_root": "false"}),
    ],
)
def test_invalid_argument_types(modules: object, options: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        wesl.compile(modules, **options)


def test_general_mappings_remain_unchanged(modules: dict[str, str]) -> None:
    original = modules.copy()
    features = UserDict({"enabled": True})
    assert "7u" in wesl.compile(MappingProxyType(modules), features=features).wgsl
    assert "7u" in wesl.compile(UserDict(modules), features=features).wgsl
    assert modules == original
    assert features == {"enabled": True}


def test_missing_modules_never_use_the_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.wesl").write_text("fn main() {}")
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 1u; }")
    with pytest.raises(wesl.CompileError):
        wesl.compile({})
    with pytest.raises(wesl.CompileError):
        wesl.compile(
            {
                "package::main": """
                    import package::helper::value;
                    fn main() -> u32 { return value(); }
                """
            },
            strip=False,
        )


def test_named_package_imports_raise_compiler_errors() -> None:
    with pytest.raises(wesl.CompileError):
        wesl.compile(
            {
                "package::main": """
                    import alpha::helper::value;
                    fn main() -> u32 { return value(); }
                """
            },
            strip=False,
        )


def test_validation_limits() -> None:
    for source in [
        "fn main() { let value: u32 = true; }",
        "fn consume(value: u32) {} fn main() { consume(); }",
    ]:
        assert wesl.compile({"package::main": source}, strip=False).wgsl


def test_concurrent_feature_state_isolation(modules: dict[str, str]) -> None:
    def compile_feature(enabled: bool) -> str:  # noqa: FBT001
        return wesl.compile(modules, features={"enabled": enabled}).wgsl

    enabled = [False, True] * 32
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(compile_feature, enabled))
    for feature, result in zip(enabled, results, strict=True):
        assert ("7u" if feature else "3u") in result
