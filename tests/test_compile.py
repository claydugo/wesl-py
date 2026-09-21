from __future__ import annotations

import pickle
import re
import subprocess
import sys
from collections import UserDict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import make_dataclass
from multiprocessing import get_context
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


def test_long_expression_compiles_without_ast_serialization(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import wesl; "
                "source = 'fn main() -> u32 { return ' "
                "+ ' + '.join(['1u'] * 10000) + '; }'; "
                "result = wesl.compile_source(source, "
                "options=wesl.CompileOptions(strip=False)); "
                "assert 'fn main(' in result.wgsl; print('compiled')"
            ),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == "compiled"


@pytest.mark.parametrize(("enabled", "expected"), [(False, 3), (True, 7)])
def test_imports_conditions_and_root_bindings(
    modules: dict[str, str], *, enabled: bool, expected: int
) -> None:
    result = wesl.compile(
        modules,
        options=wesl.CompileOptions(features=wesl.Features(flags={"enabled": enabled})),
    ).wgsl
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
        options=wesl.CompileOptions(
            strip=False, features=wesl.Features(flags={"enabled": enabled})
        ),
    ).wgsl
    assert re.search(rf"return\s+{expected}u\s*;", result)
    assert result.count("return") == 1


def test_unspecified_features_are_disabled_per_call(modules: dict[str, str]) -> None:
    assert (
        "7u"
        in wesl.compile(
            modules,
            options=wesl.CompileOptions(
                features=wesl.Features(flags={"enabled": True})
            ),
        ).wgsl
    )
    assert "3u" in wesl.compile(modules).wgsl
    assert (
        "3u"
        in wesl.compile(
            modules,
            options=wesl.CompileOptions(
                features=wesl.Features(flags={"unrelated": True})
            ),
        ).wgsl
    )


def test_stripping_root_preservation_and_mangling() -> None:
    modules = {"package::main": "fn value() -> u32 { return 7u; }"}
    assert wesl.compile(modules).wgsl.strip() == ""
    assert (
        "fn value("
        in wesl.compile(modules, options=wesl.CompileOptions(keep_main=True)).wgsl
    )
    assert (
        "fn value("
        in wesl.compile(modules, options=wesl.CompileOptions(strip=False)).wgsl
    )
    assert (
        wesl.compile(modules, options=wesl.CompileOptions(strip=False)).wgsl
        == wesl.compile(modules, options=wesl.CompileOptions(keep_main=True)).wgsl
    )
    assert (
        "fn package_main_value("
        in wesl.compile(
            modules, options=wesl.CompileOptions(strip=False, mangle_main=True)
        ).wgsl
    )
    assert (
        "fn value("
        in wesl.compile(modules, options=wesl.CompileOptions(keep=[], strip=False)).wgsl
    )
    assert (
        "fn value("
        in wesl.compile(
            modules, options=wesl.CompileOptions(keep=["missing"], keep_main=True)
        ).wgsl
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
    result = wesl.compile(modules, options=wesl.CompileOptions(keep=["first"])).wgsl
    assert "fn first(" in result
    assert "fn exported(" in result
    assert "fn package_helper_value(" in result
    assert "fn second(" not in result
    result = wesl.compile(modules, options=wesl.CompileOptions(keep=("exported",))).wgsl
    assert "fn exported(" in result
    assert "@compute" not in result
    assert not wesl.compile(modules, options=wesl.CompileOptions(keep=[])).wgsl.strip()


@pytest.mark.parametrize(
    ("source", "keep"),
    [
        ("@compute @workgroup_size(1) fn main() {}", ["mian"]),
        ("@if(enabled) @compute @workgroup_size(1) fn main() {}", ["main"]),
    ],
)
def test_keep_ignores_unknown_and_disabled_declarations(
    source: str, keep: list[str]
) -> None:
    result = wesl.compile_source(source, options=wesl.CompileOptions(keep=keep))
    assert not result.wgsl.strip()


def test_feature_error_policy() -> None:
    modules = {"package::main": "@if(enabled) @compute @workgroup_size(1) fn main() {}"}
    with pytest.raises(wesl.CompileError, match="unexpected feature flag"):
        wesl.compile(
            modules,
            options=wesl.CompileOptions(
                features=wesl.Features(
                    default=wesl.Feature.Error, flags={"enabeld": True}
                )
            ),
        )
    assert not wesl.compile(
        modules,
        options=wesl.CompileOptions(
            features=wesl.Features(default=wesl.Feature.Error, flags={"enabled": False})
        ),
    ).wgsl.strip()
    assert (
        "fn main("
        in wesl.compile(
            modules,
            options=wesl.CompileOptions(
                features=wesl.Features(
                    default=wesl.Feature.Error, flags={"enabled": True}
                )
            ),
        ).wgsl
    )
    with pytest.raises(wesl.CompileError, match="unexpected feature flag"):
        wesl.compile(
            modules,
            options=wesl.CompileOptions(
                features=wesl.Features(flags={"enabled": wesl.Feature.Error})
            ),
        )


@pytest.mark.parametrize(
    "options",
    [
        wesl.CompileOptions(strip=False),
        wesl.CompileOptions(keep_main=True),
    ],
)
def test_unused_helpers_resolve_imports_when_preserved(
    options: wesl.CompileOptions,
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
        wesl.compile(modules, options=options)


def test_unused_imports_and_unresolved_sources_are_not_validated() -> None:
    modules = {
        "package::main": "import package::missing::value; fn main() {}",
        "package::unused": "fn broken( }",
    }
    assert (
        "fn main("
        in wesl.compile(modules, options=wesl.CompileOptions(strip=False)).wgsl
    )


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
        wesl.compile(modules, options=wesl.CompileOptions(strip=False))
    assert (
        "fn package_main_main("
        in wesl.compile(
            modules, options=wesl.CompileOptions(strip=False, mangle_main=True)
        ).wgsl
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
        options=wesl.CompileOptions(strip=False),
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
        options=wesl.CompileOptions(strip=False),
    ).wgsl
    assert "package_settings_answer" in result


@pytest.mark.parametrize("name", ["café", "fn", "async"])
def test_module_names_follow_upstream_path_grammar(name: str) -> None:
    modules = {f"package::{name}": "fn value() -> u32 { return 1u; }"}
    assert (
        "fn value("
        in wesl.compile(
            modules, root=f"package::{name}", options=wesl.CompileOptions(strip=False)
        ).wgsl
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "self::main",
        "super::main",
        "alpha//beta::main",
        "alpha::beta/main",
        "package/beta::main",
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
        ({"package::main": ""}, {"options": {"strip": False}}),
    ],
)
def test_invalid_argument_types(modules: object, options: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        wesl.compile(modules, **options)


def test_general_mappings_remain_unchanged(modules: dict[str, str]) -> None:
    original = modules.copy()
    features = UserDict({"enabled": True})
    assert (
        "7u"
        in wesl.compile(
            MappingProxyType(modules),
            options=wesl.CompileOptions(features=wesl.Features(flags=features)),
        ).wgsl
    )
    assert (
        "7u"
        in wesl.compile(
            UserDict(modules),
            options=wesl.CompileOptions(features=wesl.Features(flags=features)),
        ).wgsl
    )
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
            options=wesl.CompileOptions(strip=False),
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
            options=wesl.CompileOptions(strip=False),
        )


def test_validation_limits() -> None:
    for source in [
        "fn main() { let value: u32 = true; }",
        "fn consume(value: u32) {} fn main() { consume(); }",
    ]:
        assert wesl.compile(
            {"package::main": source}, options=wesl.CompileOptions(strip=False)
        ).wgsl


def test_concurrent_feature_state_isolation(modules: dict[str, str]) -> None:
    def compile_feature(enabled: bool) -> str:  # noqa: FBT001
        return wesl.compile(
            modules,
            options=wesl.CompileOptions(
                features=wesl.Features(flags={"enabled": enabled})
            ),
        ).wgsl

    enabled = [False, True] * 32
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(compile_feature, enabled))
    for feature, result in zip(enabled, results, strict=True):
        assert ("7u" if feature else "3u") in result


def test_incremental_conditional_translation() -> None:
    source = """
        @if(enabled) @compute @workgroup_size(1) fn main() {}
        @if(pending) fn deferred() {}
    """
    partial = wesl.compile_source(
        source,
        options=wesl.CompileOptions(
            keep_main=True,
            features=wesl.Features(
                default=wesl.Feature.Enable, flags={"pending": wesl.Feature.Keep}
            ),
        ),
    )
    assert "@if(enabled)" not in partial.wgsl
    assert "@if(pending)" in partial.wgsl
    assert partial.entry_points == ("main",)
    complete = wesl.compile_source(partial.wgsl)
    assert "@if" not in complete.wgsl
    assert "deferred" not in complete.wgsl
    preserved = wesl.compile_source(
        source,
        options=wesl.CompileOptions(
            keep_main=True, features=wesl.Features(default=wesl.Feature.Keep)
        ),
    )
    disabled = wesl.compile_source(
        source, options=wesl.CompileOptions(keep_main=True, condcomp=False)
    )
    assert disabled.wgsl == preserved.wgsl


def test_import_resolution_can_be_disabled() -> None:
    source = "import package::missing::value; fn main() { value(); }"
    with pytest.raises(wesl.CompileError, match="module not found"):
        wesl.compile_source(source, options=wesl.CompileOptions(strip=False))
    result = wesl.compile_source(
        source, options=wesl.CompileOptions(imports=False, strip=False)
    )
    assert "import " not in result.wgsl
    assert "value();" in result.wgsl


def test_validation_can_be_disabled() -> None:
    source = "fn same() {} fn same() {}"
    with pytest.raises(wesl.CompileError, match="duplicate declaration"):
        wesl.compile_source(source, options=wesl.CompileOptions(strip=False))
    result = wesl.compile_source(
        source, options=wesl.CompileOptions(validate=False, strip=False)
    )
    assert result.wgsl.count("fn same(") == 2  # noqa: PLR2004


def test_lowering_inlines_aliases_and_constants() -> None:
    result = wesl.compile_source(
        "alias Number = u32; const amount = 3u; "
        "fn value() -> Number { return amount; }",
        options=wesl.CompileOptions(lower=True, keep=["value"]),
    )
    assert "alias " not in result.wgsl
    assert "const " not in result.wgsl
    assert "-> u32" in result.wgsl
    assert "return (3u);" in result.wgsl


@pytest.mark.parametrize(
    ("mangler", "expected"),
    [
        (wesl.ManglerKind.Escape, r"package_helper_value"),
        (wesl.ManglerKind.Hash, r"value_[0-9]+"),
        (wesl.ManglerKind.Unicode, r"package::helper::value"),
        (wesl.ManglerKind.None_, r"value"),
    ],
)
def test_manglers_rename_imported_functions(
    mangler: wesl.ManglerKind, expected: str
) -> None:
    result = wesl.compile_source(
        "import package::helper::value; "
        "@compute @workgroup_size(1) fn main() { value(); }",
        modules={"package::helper": "fn value() {}"},
        options=wesl.CompileOptions(mangler=mangler),
    )
    declaration = re.search(rf"fn ({expected})\(", result.wgsl)
    assert declaration is not None
    assert f"{declaration[1]}();" in result.wgsl


@pytest.mark.parametrize(
    "options",
    [
        {"strip": 1},
        {"keep": "main"},
        {"features": {}},
        {"mangler": "escape"},
        {"sourcemap": "false"},
    ],
)
def test_compile_options_reject_invalid_types(options: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        wesl.compile_source("", options=wesl.CompileOptions(**options))


@pytest.mark.parametrize("flags", [[], {"enabled": 1}, {"enabled": "false"}, {1: True}])
def test_features_reject_invalid_types(flags: object) -> None:
    with pytest.raises(TypeError):
        wesl.compile_source(
            "", options=wesl.CompileOptions(features=wesl.Features(flags=flags))
        )


def test_compile_options_preserve_all_fields_through_pickle() -> None:
    options = wesl.CompileOptions(
        imports=False,
        condcomp=False,
        strip=False,
        lower=True,
        validate=False,
        sourcemap=False,
        mangler=wesl.ManglerKind.Hash,
        mangle_main=True,
        keep=["main"],
        keep_main=True,
        features=wesl.Features(
            default=wesl.Feature.Error,
            flags={
                "enabled": wesl.Feature.Enable,
                "disabled": wesl.Feature.Disable,
                "pending": wesl.Feature.Keep,
                "unexpected": wesl.Feature.Error,
            },
        ),
    )
    restored = pickle.loads(pickle.dumps(options))  # noqa: S301
    assert restored == options
    assert restored is not options
    assert pickle.loads(pickle.dumps(wesl.ManglerKind.None_)) is wesl.ManglerKind.None_  # noqa: S301


def test_features_retain_supplied_flags() -> None:
    flags: dict[str, bool | wesl.Feature] = {"enabled": False}
    features = wesl.Features(flags=flags)
    source = "@if(enabled) @compute @workgroup_size(1) fn main() {}"
    options = wesl.CompileOptions(features=features)
    assert wesl.compile_source(source, options=options).entry_points == ()
    flags["enabled"] = True
    assert wesl.compile_source(source, options=options).entry_points == ("main",)
    flags["enabled"] = wesl.Feature.Disable
    assert wesl.compile_source(source, options=options).entry_points == ()


def test_features_dataclass_subclass_preserves_defaults() -> None:
    features = make_dataclass("DerivedFeatures", [], bases=(wesl.Features,))()
    assert features.default is wesl.Feature.Disable
    assert features.flags == {}


def test_compile_options_apply_mutations_without_sharing_defaults() -> None:
    options = wesl.CompileOptions()
    independent_options = wesl.CompileOptions()
    source = "@if(enabled) @compute @workgroup_size(1) fn main() {}"
    disabled = wesl.compile_source(source, options=options)
    options.features.flags["enabled"] = True
    options.mangle_main = True
    enabled = wesl.compile_source(source, options=options)
    assert disabled.entry_points == ()
    assert enabled.entry_points == ("package_main_main",)
    assert independent_options.features.flags == {}


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="WESL 0.4.4 strips the root entry point when imports are disabled",
)
def test_disabled_imports_preserve_the_root_entry_point() -> None:
    result = wesl.compile_source(
        "@compute @workgroup_size(1) fn main() {}",
        options=wesl.CompileOptions(imports=False),
    )
    assert "fn main(" in result.wgsl


def test_compiler_options_cross_process_boundaries() -> None:
    source = "@if(enabled) @compute @workgroup_size(1) fn main() {}"
    options = wesl.CompileOptions(
        mangle_main=True,
        mangler=wesl.ManglerKind.Hash,
        features=wesl.Features(default=wesl.Feature.Error, flags={"enabled": True}),
    )
    expected = wesl.compile_source(source, options=options)
    with ProcessPoolExecutor(
        max_workers=1, mp_context=get_context("spawn")
    ) as executor:
        result = executor.submit(wesl.compile_source, source, options=options).result(
            timeout=10
        )
    assert result == expected
