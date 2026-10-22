from __future__ import annotations

import sys
from collections import UserDict
from fractions import Fraction
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    from pathlib import Path


def test_constant_modules_preserve_inputs_and_source_metadata() -> None:
    modules = UserDict(
        {
            "package::main": (
                "import constants::{width, scale, enabled}; "
                "@if(selected) @compute @workgroup_size(width) fn main() { "
                "let value: f32 = scale; let selected = enabled; }"
            ),
        }
    )
    constants = UserDict(
        {"width": 64, "scale": 1.0, "enabled": True, "center": "vec2f(0.5, 0.75)"}
    )
    filenames = {"constants": "generated.wesl"}
    result = wesl.compile(
        modules,
        features={"selected": True},
        constants=constants,
        filenames=filenames,
    )
    assert result.entry_points == ("main",)
    assert result.modules == ("package::main", "constants")
    assert set(result.sources["constants"].text.splitlines()) == {
        "public const width = 64;",
        "public const scale = 1.0;",
        "public const enabled = true;",
        "public const center = vec2f(0.5, 0.75);",
    }
    assert result.sources["constants"].filename == "generated.wesl"
    assert modules == {
        "package::main": (
            "import constants::{width, scale, enabled}; "
            "@if(selected) @compute @workgroup_size(width) fn main() { "
            "let value: f32 = scale; let selected = enabled; }"
        ),
    }
    assert constants == {
        "width": 64,
        "scale": 1.0,
        "enabled": True,
        "center": "vec2f(0.5, 0.75)",
    }
    assert filenames == {"constants": "generated.wesl"}

    scoped = wesl.compile_source(
        "fn main() -> f32 { return library::value(); }",
        modules={"library": "fn value() -> f32 { return constants::scale; }"},
        constants={"scale": 0.5},
        keep=["main"],
    )
    assert set(scoped.modules) == {"package::main", "library", "constants"}

    compiler = wesl.Compiler(modules={"constants": "const value = 1;"})
    with pytest.raises(
        ValueError, match="in modules and also comes from the constants argument"
    ):
        compiler.compile_source("", constants={"value": 2})


@pytest.mark.parametrize("method", ["compile_source", "compile_file"])
def test_constant_modules_apply_to_one_compilation(method: str, tmp_path: Path) -> None:
    source = (
        "import constants::width; "
        "@if(selected) @compute @workgroup_size(width) fn main() {}"
    )
    filename = tmp_path / "main.wesl"
    filename.write_text(source)
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
        constants={"width": 64},
    )
    assert result == getattr(wesl, method)(
        argument,
        modules=modules,
        root_directory=tmp_path,
        features={"selected": True},
        constants={"width": 64},
    )
    assert result.sources["constants"].text == "public const width = 64;"
    with pytest.raises(wesl.CompileError):
        getattr(compiler, method)(argument, features={"selected": True})
    assert compiler.modules is modules
    assert modules == {"package::unused": "fn unused() {}"}
    assert compiler.options.features.flags == {"selected": False}
    assert getattr(compiler, method)(argument).entry_points == ()


def test_constant_scalar_representations() -> None:
    result = wesl.compile_source(
        "fn main() { let value = constants::café; }",
        constants={
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
        keep=["main"],
    )
    assert set(result.sources["constants"].text.splitlines()) == {
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
    ("constants", "error", "message"),
    [
        pytest.param(
            {"value": "1u; const other = 2u"},
            ValueError,
            "value.*invalid WGSL expression",
            id="injected-expression",
        ),
        pytest.param({"value": 1j}, TypeError, "value.*scalar", id="complex"),
        pytest.param({"value": float("nan")}, ValueError, "value.*finite", id="nan"),
        pytest.param(
            {"value": float("inf")}, ValueError, "value.*finite", id="infinity"
        ),
        pytest.param(
            {"value": 2**63}, ValueError, "value.*signed 64-bit range", id="overflow"
        ),
        pytest.param(
            {"value": -(2**63) - 1},
            ValueError,
            "value.*signed 64-bit range",
            id="underflow",
        ),
        pytest.param(
            {"value": Fraction(1, 10)},
            ValueError,
            "value.*loses precision",
            id="lossy-fraction",
        ),
        pytest.param(
            {"value": Fraction(10**400, 1)},
            ValueError,
            "value.*finite float range",
            id="float-overflow",
        ),
        pytest.param(
            {"fn": 1}, ValueError, ".*invalid WGSL identifier", id="reserved-name"
        ),
        pytest.param(
            {"value = 0; const other": 1},
            ValueError,
            ".*invalid WGSL identifier",
            id="injected-name",
        ),
    ],
)
def test_constant_modules_reject_unrepresentable_values(
    constants: dict[object, object], error: type[Exception], message: str
) -> None:
    for validate in (False, True):
        with pytest.raises(error, match=f"constants::{message}"):
            wesl.compile_source(
                "",
                constants=constants,
                options=wesl.CompileOptions(validate=validate),
            )


def test_constant_modules_normalize_numpy_scalars() -> None:
    np = pytest.importorskip("numpy")
    result = wesl.compile_source(
        "fn main() { let value = constants::signed; }",
        constants={
            "signed": np.int64(-1),
            "unsigned": np.uint64(2**32 - 1),
            "half": np.float16(0.5),
            "single": np.float32(0.1),
            "double": np.float64(1.0),
        },
        keep=["main"],
    )
    assert set(result.sources["constants"].text.splitlines()) == {
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
    with pytest.raises(ValueError, match=r"constants::value.*loses precision"):
        wesl.compile_source("", constants={"value": np.longdouble("0.1")})
