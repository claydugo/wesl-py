from __future__ import annotations

import re
from collections import UserDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import chdir
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def test_keep_selects_declarations_and_their_dependencies() -> None:
    options = wesl.CompileOptions(keep_main=True, strip=False)
    result = wesl.compile_source(
        """
            import package::helper::value;
            fn exported() -> u32 { return value(); }
            @compute @workgroup_size(1) fn first() { let result = exported(); }
            @compute @workgroup_size(1) fn second() {}
        """,
        modules={"package::helper": "fn value() -> u32 { return 7u; }"},
        options=options,
        keep=["first"],
        keep_main=False,
        strip=True,
    )
    assert set(re.findall(r"fn (\w+)\(", result.wgsl)) == {
        "first",
        "exported",
        "package_helper_value",
    }
    assert result.entry_points == ("first",)
    assert options.keep_main
    assert not options.strip


@pytest.mark.parametrize(
    ("source", "keep"),
    [
        ("@compute @workgroup_size(1) fn main() {}", ["mian"]),
        ("@if(enabled) @compute @workgroup_size(1) fn main() {}", ["main"]),
    ],
    ids=["unknown", "disabled"],
)
def test_keep_rejects_unknown_and_disabled_declarations(
    source: str, keep: list[str]
) -> None:
    with pytest.raises(wesl.CompileError, match="has no declaration"):
        wesl.compile_source(source, options=wesl.CompileOptions(keep=keep))


@pytest.mark.parametrize(
    "features",
    [
        pytest.param(
            wesl.Features(default=wesl.Feature.Error, flags={"enabeld": True}),
            id="misspelled-flag",
        ),
        pytest.param(
            wesl.Features(flags={"enabled": wesl.Feature.Error}),
            id="explicit-error",
        ),
    ],
)
def test_unknown_features_can_be_errors(features: wesl.Features) -> None:
    with pytest.raises(wesl.CompileError, match="unexpected feature flag"):
        wesl.compile_source(
            "@if(enabled) @compute @workgroup_size(1) fn main() {}",
            features=features,
        )


@pytest.mark.parametrize(
    "path",
    [
        "super::main",
        "package::::main",
    ],
)
def test_module_keys_and_root_reject_invalid_paths(path: str) -> None:
    with pytest.raises(ValueError, match="invalid module path") as caught:
        wesl.compile({path: ""})
    assert path in str(caught.value)
    with pytest.raises(ValueError, match="invalid module path") as caught:
        wesl.compile({"package::main": ""}, root=path)
    assert path in str(caught.value)


def test_missing_modules_never_use_the_filesystem(tmp_path: Path) -> None:
    (tmp_path / "main.wesl").write_text("fn main() {}")
    (tmp_path / "helper.wesl").write_text("fn value() -> u32 { return 1u; }")
    with chdir(tmp_path), pytest.raises(wesl.CompileError):
        wesl.compile({})
    with chdir(tmp_path), pytest.raises(wesl.CompileError):
        wesl.compile(
            {
                "package::main": """
                    import package::helper::value;
                    fn main() -> u32 { return value(); }
                """
            },
            options=wesl.CompileOptions(strip=False),
        )


def test_concurrent_feature_state_isolation(modules: dict[str, str]) -> None:
    def compile_feature(enabled: bool) -> str:
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
        assert ("3u" if feature else "7u") not in result


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
    assert result.wgsl.count("fn same(") == 2


@pytest.mark.parametrize(
    "modifier", ["", "private ", "public "], ids=["package", "private", "public"]
)
def test_external_visibility_is_optional(modifier: str) -> None:
    modules = {
        "package::main": "import library::value; fn main() -> u32 { return value(); }",
        "library": f"{modifier}fn value() -> u32 {{ return 7u; }}",
    }
    options = wesl.CompileOptions(keep=["main"])
    result = wesl.compile(modules, options=options)
    assert "return 7u;" in result.wgsl
    assert "public " not in result.wgsl
    assert "private fn" not in result.wgsl
    options.visibility = True
    if modifier == "public ":
        assert wesl.compile(modules, options=options).wgsl == result.wgsl
    else:
        with pytest.raises(wesl.CompileError, match="visibility"):
            wesl.compile(modules, options=options)


def test_lowering_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="lowering is not supported"):
        wesl.compile_source(
            "alias Number = u32; const amount = 3u; "
            "fn value() -> Number { return amount; }",
            options=wesl.CompileOptions(lower=True, keep=["value"]),
        )


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


def test_disabled_imports_preserve_the_root_entry_point() -> None:
    result = wesl.compile_source(
        "@compute @workgroup_size(1) fn main() {}",
        options=wesl.CompileOptions(imports=False),
    )
    assert "fn main(" in result.wgsl


@pytest.mark.parametrize(
    "features",
    [
        pytest.param({}, id="empty-mapping"),
        pytest.param(MappingProxyType({"enabled": False}), id="read-only-mapping"),
    ],
)
def test_feature_mappings_and_call_overrides(
    modules: dict[str, str], features: Mapping[str, bool]
) -> None:
    flags = UserDict({"enabled": True})
    options = wesl.CompileOptions(features=wesl.Features(flags=flags))
    assert "7u" in wesl.compile(modules, options=options).wgsl
    assert "3u" in wesl.compile(modules, options=options, features=features).wgsl
    assert options.features.flags is flags
    assert flags == {"enabled": True}
    assert "7u" in wesl.compile(modules, options=options).wgsl


@pytest.mark.parametrize("method", ["compile_source", "compile_file"])
def test_compiler_call_options_preserve_stored_settings(
    tmp_path: Path,
    method: str,
) -> None:
    source = (
        "@if(enabled) fn selected() -> u32 { return 7u; } "
        "@else fn selected() -> u32 { return 3u; } "
        "fn other() {} @compute @workgroup_size(1) fn main() {}"
    )
    (tmp_path / "main.wesl").write_text(source)
    options = wesl.CompileOptions(
        features=wesl.Features(flags={"enabled": True}),
        keep=["selected"],
    )
    compiler = wesl.Compiler(root_directory=tmp_path, options=options)
    argument = source if method == "compile_source" else "main.wesl"
    compile_shader = partial(getattr(compiler, method), argument)
    stored = compile_shader()
    assert set(re.findall(r"fn (\w+)\(", stored.wgsl)) == {"selected"}
    assert "7u" in stored.wgsl
    assert stored.entry_points == ()

    result = compile_shader(features={}, keep=[], keep_main=True, strip=False)
    assert set(re.findall(r"fn (\w+)\(", result.wgsl)) == {"selected", "other", "main"}
    assert "3u" in result.wgsl
    assert compiler.options is options
    assert compile_shader() == stored
    assert compile_shader(keep=None).entry_points == ("main",)

    options.features.flags["enabled"] = False
    options.keep = ["other"]
    assert set(re.findall(r"fn (\w+)\(", compile_shader().wgsl)) == {"other"}
    options.keep_main = True
    assert "3u" in compile_shader().wgsl
    assert "selected" not in compile_shader(keep_main=False).wgsl
    assert options.keep_main
