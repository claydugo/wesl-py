from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import wesl
from wesl.testing import ShaderTestDisabledError, run_test_cpu

if TYPE_CHECKING:
    from functools import partial


def test_override_conversion_preserves_valid_values(shader_runner: partial) -> None:
    shader_runner(
        {
            "package::main": """
                alias Count = u32;
                const initial = 1u;
                override unsigned_fraction: u32;
                override unsigned_negative_fraction: u32;
                override signed_minimum: i32;
                override signed_maximum: i32;
                override signed_fraction: i32;
                override nan_flag: bool;
                override infinite_flag: bool;
                override negative_zero_flag: bool;
                @id(5) override numbered: Count;
                override inferred = initial;
                override offset: u32 = 0u;
                @test fn selected() {
                    wgsl_test::expectEq(unsigned_fraction, 4294967295u);
                    wgsl_test::expectEq(unsigned_negative_fraction, 0u);
                    wgsl_test::expect(signed_minimum == (-2147483647i - 1i));
                    wgsl_test::expect(signed_maximum == 2147483647i);
                    wgsl_test::expect(signed_fraction == -7i);
                    wgsl_test::expect(!nan_flag && infinite_flag);
                    wgsl_test::expect(!negative_zero_flag);
                    wgsl_test::expectEq(numbered, 4294967295u);
                    wgsl_test::expectEq(inferred, 7u);
                    wgsl_test::expectEq(offset, 7u);
                    wgsl_test::expectEq(library::read(), 19u);
                }
            """,
            "library": """
                override offset: u32 = 19u;
                fn read() -> u32 { return offset; }
            """,
        },
        "selected",
        constants={
            "unsigned_fraction": 4294967295.5,
            "unsigned_negative_fraction": -0.5,
            "signed_minimum": -2147483648.5,
            "signed_maximum": 2147483647.5,
            "signed_fraction": -7.5,
            "nan_flag": float("nan"),
            "infinite_flag": float("inf"),
            "negative_zero_flag": -0.0,
            "5": 4294967295,
            "inferred": 7,
            "offset": 7,
        },
    )


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("u32", 4294967296),
        ("u32", -1),
        ("i32", 2147483648),
        ("i32", -2147483649),
        ("f32", 3.5e38),
        ("u32", float("nan")),
        ("i32", float("inf")),
        ("f32", float("-inf")),
    ],
)
def test_override_conversion_rejects_invalid_values(
    shader_runner: partial, value_type: str, value: float
) -> None:
    if shader_runner.func is run_test_cpu:
        error_type = ValueError
    else:
        error_type = pytest.importorskip("wgpu").GPUValidationError
    with pytest.raises(error_type):
        shader_runner(
            {
                "package::main": f"""
                    override value: {value_type};
                    @test fn selected() {{
                        wgsl_test::expect(value == {value_type}(0));
                    }}
                """,
            },
            "selected",
            constants={"value": value},
        )


def test_cpu_runs_native_assertion_tests() -> None:
    root_directory = Path(__file__).parents[1]
    path = root_directory / "tests/runner/assertions.test.wesl"
    module = "package::tests::runner::assertions_test"
    run_test_cpu(
        {module: path.read_text(encoding="utf-8")},
        "assertions_pass_in_every_scope",
        root=module,
        filenames={module: path},
        root_directory=root_directory,
        options=wesl.TestOptions(visibility=True),
    )


def test_cpu_executes_example_library_dependency() -> None:
    run_test_cpu(
        {
            "package::main": """
                import sdf::primitives::{sphere, smooth_union};
                @test fn distances() {
                    wgsl_test::expectNear(sphere(vec3f(0.0), 2.0), -2.0);
                    wgsl_test::expectNear(sphere(vec3f(3.0, 4.0, 0.0), 2.0), 3.0);
                    wgsl_test::expectNear(smooth_union(0.0, 0.0, 0.4), -0.1);
                    wgsl_test::expectNear(smooth_union(0.0, 0.2, 0.4), -0.025);
                }
            """,
        },
        "distances",
        dependencies={"sdf": Path(__file__).parents[1] / "examples/sdf"},
        options=wesl.TestOptions(visibility=True),
    )


def test_cpu_resets_private_state_and_skips_disabled_tests() -> None:
    for _ in range(2):
        run_test_cpu(
            {
                "package::main": """
                    var<private> count = 0u;
                    @test fn selected() {
                        count += 1u;
                        wgsl_test::expectEq(count, 1u);
                    }
                """,
            },
            "selected",
        )
    with pytest.raises(ShaderTestDisabledError):
        run_test_cpu(
            {
                "package::main": """
                    import missing::value;
                    @if(enabled) @test fn selected() { value(); }
                """,
            },
            "selected",
        )


@pytest.mark.parametrize(
    ("source", "error_type", "message"),
    [
        (
            "@test @workgroup_size(2) fn selected() {}",
            NotImplementedError,
            "builtin parameters",
        ),
        (
            "@test fn selected(@builtin(local_invocation_index) index: u32) {}",
            NotImplementedError,
            "builtin parameters",
        ),
        (
            "@group(0) @binding(1) var<storage, read> value: u32;",
            ValueError,
            "user resources or workgroup variables",
        ),
        (
            "@group(0) @binding(1) var<uniform> value: u32;",
            ValueError,
            "user resources or workgroup variables",
        ),
        (
            "@group(0) @binding(1) var value: texture_2d<f32>;",
            ValueError,
            "user resources or workgroup variables",
        ),
        (
            "var<workgroup> value: u32;",
            ValueError,
            "user resources or workgroup variables",
        ),
    ],
    ids=[
        "workgroup-size",
        "builtin-parameter",
        "storage",
        "uniform",
        "texture",
        "workgroup-variable",
    ],
)
def test_cpu_rejects_gpu_only_tests(
    source: str, error_type: type[Exception], message: str
) -> None:
    if "@test" not in source:
        source += " @test fn selected() {}"
    with pytest.raises(error_type, match=message):
        run_test_cpu(
            {"package::main": source},
            "selected",
            options=wesl.TestOptions(strip=False),
        )
