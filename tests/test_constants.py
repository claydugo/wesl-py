from __future__ import annotations

import os
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
        "const width = 64;",
        "const scale = 1.0;",
        "const enabled = true;",
    }
    assert result.sources["package::config"].filename == "generated.wesl"
    assert list(modules) == ["package::main"]
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
        root_directory=tmp_path, modules=modules, features={"selected": False}
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
    assert result.sources["package::config"].text == "const width = 64;"
    restored = getattr(compiler, method)(argument, features={"selected": True})
    assert restored.sources["package::config"].text == "const width = 1;"
    assert compiler.modules is modules
    assert modules == {"package::unused": "fn unused() {}"}
    assert compiler.features == {"selected": False}
    assert getattr(compiler, method)(argument).entry_points == ()


@pytest.mark.parametrize(
    ("value", "initializer"),
    [
        (False, "false"),
        (True, "true"),
        (-1, "-1"),
        (2**32 - 1, "4294967295"),
        (2**63 - 1, "9223372036854775807"),
        (1.0, "1.0"),
        (-0.0, "-0.0"),
        (5e-324, "5e-324"),
        (sys.float_info.max, "1.7976931348623157e308"),
        (Fraction(1, 2), "0.5"),
    ],
)
def test_constant_scalar_representations(value: object, initializer: str) -> None:
    result = wesl.compile_source(
        "fn main() { let value = package::config::value; }",
        constant_modules={"package::config": {"value": value}},
        keep=["main"],
    )
    assert result.sources["package::config"].text == f"const value = {initializer};"


def test_constant_modules_report_upstream_minimum_integer_parse_error() -> None:
    with pytest.raises(wesl.CompileError) as caught:
        wesl.compile_source(
            "fn main() { let value = package::config::value; }",
            constant_modules={"package::config": {"value": -(2**63)}},
            keep=["main"],
        )
    assert caught.value.diagnostics[0].module == "package::config"
    assert caught.value.diagnostics[0].source == "const value = -9223372036854775808;"


@pytest.mark.parametrize(
    ("constant_modules", "message"),
    [
        ([], "constant_modules must be a mapping"),
        ({1: {}}, "constant module names must be strings"),
        ({"package::config": []}, "package::config.*constants must be a mapping"),
        (
            {"package::config": {1: 1}},
            "package::config.*constant names must be strings",
        ),
    ],
)
def test_constant_modules_reject_invalid_mapping_types(
    constant_modules: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        wesl.compile_source("", constant_modules=constant_modules)


@pytest.mark.parametrize("value", [None, "1u", b"1", 1j, [1], {"value": 1}])
def test_constant_modules_reject_non_scalar_values(value: object) -> None:
    with pytest.raises(TypeError, match=r"package::config::value.*scalar"):
        wesl.compile_source("", constant_modules={"package::config": {"value": value}})


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (float("nan"), "finite"),
        (float("inf"), "finite"),
        (-float("inf"), "finite"),
        (2**63, "signed 64-bit range"),
        (-(2**63) - 1, "signed 64-bit range"),
        (Fraction(1, 10), "loses precision"),
        (Fraction(10**400, 1), "finite float range"),
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
        "",
        "_",
        "__reserved",
        "fn",
        "class",
        "two words",
        "value = 0; const other",
        "value: i32",
        "value/*comment*/",
    ],
)
def test_constant_modules_validate_unused_names(name: str) -> None:
    with pytest.raises(ValueError, match=r"package::config::.*invalid WGSL identifier"):
        wesl.compile_source(
            "",
            constant_modules={"package::config": {name: 1}},
            options=wesl.CompileOptions(validate=False),
        )


def test_constant_modules_accept_unicode_names() -> None:
    result = wesl.compile_source(
        "fn main() -> u32 { return package::config::café; }",
        constant_modules={"package::config": {"café": 1}},
        keep=["main"],
    )
    assert result.sources["package::config"].text == "const café = 1;"


@pytest.mark.parametrize("module", ["super::config", "package::::config"])
def test_constant_modules_use_existing_module_path_validation(module: str) -> None:
    with pytest.raises(ValueError, match="invalid module path"):
        wesl.compile_source("", constant_modules={module: {}})


@pytest.mark.parametrize("module", ["package::main", "package::config"])
def test_constant_modules_reject_source_collisions(module: str) -> None:
    compiler = wesl.Compiler(modules={"package::config": "const value = 1;"})
    with pytest.raises(
        ValueError, match="present in both modules and constant_modules"
    ):
        compiler.compile_source("", constant_modules={module: {}})


def test_constant_modules_replace_whole_files(tmp_path: Path) -> None:
    (tmp_path / "config.wesl").write_text("const width = 1; const height = 2;")
    with pytest.raises(wesl.CompileError, match="height"):
        wesl.compile_source(
            "@compute @workgroup_size(package::config::height) fn main() {}",
            root_directory=tmp_path,
            constant_modules={"package::config": {"width": 64}},
        )


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
    assert result.sources["library/settings"].text == "const scale = 0.5;"


@pytest.mark.parametrize(
    ("dtype", "value", "initializer"),
    [
        ("int64", -1, "-1"),
        ("uint64", 2**32 - 1, "4294967295"),
        ("float16", 0.5, "0.5"),
        ("float32", 0.1, "0.10000000149011612"),
        ("float64", 1.0, "1.0"),
    ],
)
def test_constant_modules_normalize_numpy_scalars(
    dtype: str, value: float, initializer: str
) -> None:
    numpy = pytest.importorskip("numpy")
    result = wesl.compile_source(
        "fn main() { let value = package::config::value; }",
        constant_modules={"package::config": {"value": getattr(numpy, dtype)(value)}},
        keep=["main"],
    )
    assert result.sources["package::config"].text == f"const value = {initializer};"


@pytest.mark.parametrize(("duration", "unit"), [(1000, "ns"), (1, "us")])
def test_constant_modules_reject_numpy_durations(duration: int, unit: str) -> None:
    numpy = pytest.importorskip("numpy")
    with pytest.raises(
        TypeError, match="package::config::duration: expected an integer"
    ):
        wesl.compile_source(
            "",
            constant_modules={
                "package::config": {"duration": numpy.timedelta64(duration, unit)},
            },
        )


def test_constant_modules_reject_lossy_numpy_conversion() -> None:
    numpy = pytest.importorskip("numpy")
    if numpy.finfo(numpy.longdouble).nmant <= numpy.finfo(float).nmant:
        pytest.skip("longdouble has no additional precision")
    with pytest.raises(ValueError, match=r"package::config::value.*loses precision"):
        wesl.compile_source(
            "", constant_modules={"package::config": {"value": numpy.longdouble("0.1")}}
        )


@pytest.mark.parametrize("shape", [(), (1,)])
def test_constant_modules_reject_numpy_arrays(shape: tuple[int, ...]) -> None:
    numpy = pytest.importorskip("numpy")
    with pytest.raises(TypeError, match=r"package::config::value.*scalar"):
        wesl.compile_source(
            "", constant_modules={"package::config": {"value": numpy.ones(shape)}}
        )


@pytest.mark.gpu
def test_constant_modules_create_render_pipeline() -> None:
    wgpu = pytest.importorskip("wgpu")
    try:
        adapter = wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(str(error))
    result = wesl.compile_source(
        """
        import package::config::{location_number, scale};
        @vertex fn vertex_main() -> @builtin(position) vec4f {
            return vec4f(0.0, 0.0, 0.0, 1.0);
        }
        @fragment fn fragment_main() -> @location(location_number) vec4f {
            return vec4f(scale);
        }
        """,
        constant_modules={"package::config": {"location_number": 0, "scale": 0.5}},
    )
    device = adapter.request_device_sync()
    try:
        shader = device.create_shader_module(code=result.wgsl)
        pipeline = device.create_render_pipeline(
            layout="auto",
            vertex={"module": shader, "entry_point": "vertex_main"},
            fragment={
                "module": shader,
                "entry_point": "fragment_main",
                "targets": [{"format": "rgba8unorm"}],
            },
        )
        assert isinstance(pipeline, wgpu.GPURenderPipeline)
    finally:
        device.destroy()
