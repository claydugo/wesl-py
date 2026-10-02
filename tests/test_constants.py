from __future__ import annotations

import sys
from collections import UserDict
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


def test_constant_modules_preserve_inputs_and_source_metadata() -> None:
    modules = UserDict(
        {
            "package::main": (
                "import package::config::{width, scale, enabled}; "
                "@if(selected) @compute @workgroup_size(width) fn main() { "
                "let value: f32 = scale; let selected = enabled; }"
            ),
        }
    )
    constants = UserDict({"width": 64, "scale": 1.0, "enabled": True})
    constant_modules = MappingProxyType({"package::config": constants})
    filenames = {"package::config": "generated.wesl"}
    result = wesl.compile(
        modules,
        features={"selected": True},
        constant_modules=constant_modules,
        filenames=filenames,
    )
    assert result.entry_points == ("main",)
    assert result.modules == ("package::main", "package::config")
    assert set(result.sources["package::config"].text.splitlines()) == {
        "public const width = 64;",
        "public const scale = 1.0;",
        "public const enabled = true;",
    }
    assert result.sources["package::config"].filename == "generated.wesl"
    assert modules == {
        "package::main": (
            "import package::config::{width, scale, enabled}; "
            "@if(selected) @compute @workgroup_size(width) fn main() { "
            "let value: f32 = scale; let selected = enabled; }"
        ),
    }
    assert constant_modules["package::config"] is constants
    assert constants == {"width": 64, "scale": 1.0, "enabled": True}
    assert filenames == {"package::config": "generated.wesl"}


@pytest.mark.parametrize("method", ["compile_source", "compile_file"])
def test_constant_modules_apply_to_one_compilation(method: str, tmp_path: Path) -> None:
    source = (
        "import package::config::width; "
        "@if(selected) @compute @workgroup_size(width) fn main() {}"
    )
    filename = tmp_path / "main.wesl"
    filename.write_text(source)
    (tmp_path / "config.wesl").write_text("const width = 1;")
    modules = {"package::unused": "fn unused() {}"}
    compiler = wesl.Compiler(
        root_directory=tmp_path,
        modules=modules,
        options=wesl.CompileOptions(features=wesl.Features(flags={"selected": False})),
    )
    argument = source if method == "compile_source" else filename
    result = getattr(compiler, method)(
        argument,
        features={"selected": True},
        constant_modules={"package::config": {"width": 64}},
    )
    assert result == getattr(wesl, method)(
        argument,
        modules=modules,
        root_directory=tmp_path,
        features={"selected": True},
        constant_modules={"package::config": {"width": 64}},
    )
    assert result.sources["package::config"].text == "public const width = 64;"
    restored = getattr(compiler, method)(argument, features={"selected": True})
    assert restored.sources["package::config"].text == "const width = 1;"
    assert compiler.modules is modules
    assert modules == {"package::unused": "fn unused() {}"}
    assert compiler.options.features.flags == {"selected": False}
    assert getattr(compiler, method)(argument).entry_points == ()


def test_constant_scalar_representations() -> None:
    result = wesl.compile_source(
        "fn main() { let value = package::config::café; }",
        constant_modules={
            "package::config": {
                "disabled": False,
                "enabled": True,
                "negative": -1,
                "maximum_u32": 2**32 - 1,
                "maximum_i64": 2**63 - 1,
                "whole_float": 1.0,
                "negative_zero": -0.0,
                "subnormal": 5e-324,
                "maximum_float": sys.float_info.max,
                "café": Fraction(1, 2),
            },
        },
        keep=["main"],
    )
    assert set(result.sources["package::config"].text.splitlines()) == {
        "public const disabled = false;",
        "public const enabled = true;",
        "public const negative = -1;",
        "public const maximum_u32 = 4294967295;",
        "public const maximum_i64 = 9223372036854775807;",
        "public const whole_float = 1.0;",
        "public const negative_zero = -0.0;",
        "public const subnormal = 5e-324;",
        "public const maximum_float = 1.7976931348623157e308;",
        "public const café = 0.5;",
    }


@pytest.mark.parametrize(
    "value",
    ["1u", 1j],
    ids=["shader-expression", "complex"],
)
def test_constant_modules_reject_non_scalar_values(value: object) -> None:
    with pytest.raises(TypeError, match=r"package::config::value.*scalar"):
        wesl.compile_source("", constant_modules={"package::config": {"value": value}})


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "finite"),
        (float("inf"), "finite"),
        (2**63, "signed 64-bit range"),
        (-(2**63) - 1, "signed 64-bit range"),
        (Fraction(1, 10), "loses precision"),
        (Fraction(10**400, 1), "finite float range"),
    ],
    ids=[
        "nan",
        "infinity",
        "overflow",
        "underflow",
        "lossy-fraction",
        "float-overflow",
    ],
)
def test_constant_modules_reject_unrepresentable_values(
    value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=f"package::config::value.*{message}"):
        wesl.compile_source("", constant_modules={"package::config": {"value": value}})


@pytest.mark.parametrize(
    "name",
    [
        "fn",
        "value = 0; const other",
    ],
)
def test_constant_modules_validate_unused_names(name: str) -> None:
    with pytest.raises(ValueError, match=r"package::config::.*invalid WGSL identifier"):
        wesl.compile_source(
            "",
            constant_modules={"package::config": {name: 1}},
            options=wesl.CompileOptions(validate=False),
        )


@pytest.mark.parametrize("module", ["package::main", "package::config"])
def test_constant_modules_reject_source_collisions(module: str) -> None:
    compiler = wesl.Compiler(modules={"package::config": "const value = 1;"})
    with pytest.raises(
        ValueError, match="present in both modules and constant_modules"
    ):
        compiler.compile_source("", constant_modules={module: {}})


def test_constant_modules_follow_dependency_scopes() -> None:
    result = wesl.compile_source(
        "fn main() -> f32 { return library::value(); }",
        modules={
            "library": "fn value() -> f32 { return settings::scale; }",
        },
        constant_modules={"library/settings": {"scale": 0.5}},
        keep=["main"],
    )
    assert set(result.modules) == {"package::main", "library", "library/settings"}
    assert result.sources["library/settings"].text == "public const scale = 0.5;"


def test_constant_modules_normalize_numpy_scalars() -> None:
    np = pytest.importorskip("numpy")
    result = wesl.compile_source(
        "fn main() { let value = package::config::signed; }",
        constant_modules={
            "package::config": {
                "signed": np.int64(-1),
                "unsigned": np.uint64(2**32 - 1),
                "half": np.float16(0.5),
                "single": np.float32(0.1),
                "double": np.float64(1.0),
            },
        },
        keep=["main"],
    )
    assert set(result.sources["package::config"].text.splitlines()) == {
        "public const signed = -1;",
        "public const unsigned = 4294967295;",
        "public const half = 0.5;",
        "public const single = 0.10000000149011612;",
        "public const double = 1.0;",
    }


def test_constant_modules_reject_lossy_numpy_conversion() -> None:
    np = pytest.importorskip("numpy")
    if np.finfo(np.longdouble).nmant <= np.finfo(float).nmant:
        pytest.skip("longdouble has no additional precision")
    with pytest.raises(ValueError, match=r"package::config::value.*loses precision"):
        wesl.compile_source(
            "", constant_modules={"package::config": {"value": np.longdouble("0.1")}}
        )
