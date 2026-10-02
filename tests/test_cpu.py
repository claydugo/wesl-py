from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import wesl
from wesl.testing import ShaderTestDisabledError, run_test_cpu

if TYPE_CHECKING:
    from functools import partial


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


@pytest.mark.parametrize(
    ("value_type", "value", "expected"),
    [
        ("u32", 4294967295.5, "4294967295u"),
        ("u32", -0.5, "0u"),
        ("i32", -2147483648.5, "(-2147483647i - 1i)"),
        ("i32", 2147483647.5, "2147483647i"),
        ("u32", 7.5, "7u"),
        ("i32", -7.5, "-7i"),
        ("bool", float("nan"), "false"),
        ("bool", float("inf"), "true"),
        ("bool", -0.0, "false"),
    ],
)
def test_override_conversion_preserves_valid_values(
    shader_runner: partial, value_type: str, value: float, expected: str
) -> None:
    shader_runner(
        {
            "package::main": f"""
                override value: {value_type};
                @test fn selected() {{ wgsl_test::expect(value == {expected}); }}
            """,
        },
        "selected",
        constants={"value": value},
    )


def test_inferred_and_aliased_override_types(shader_runner: partial) -> None:
    shader_runner(
        {
            "package::main": """
                alias Count = u32;
                const initial = 1u;
                override count = initial;
                @id(5) override limit: Count;
                override enabled: bool = false;
                @test fn selected() {
                    wgsl_test::expectEq(count, 7u);
                    wgsl_test::expectEq(limit, 4294967295u);
                    wgsl_test::expect(enabled);
                }
            """,
        },
        "selected",
        constants={"count": 7, "5": 4294967295, "enabled": True},
    )


def test_disabled_cpu_test_does_not_resolve_imports() -> None:
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
    "source",
    [
        "@test @workgroup_size(2) fn selected() {}",
        "@test fn selected(@builtin(local_invocation_index) index: u32) {}",
    ],
)
def test_cpu_rejects_cooperative_tests(source: str) -> None:
    with pytest.raises(NotImplementedError, match="builtin parameters"):
        run_test_cpu({"package::main": source}, "selected")


@pytest.mark.parametrize(
    "declarations",
    [
        "@group(0) @binding(1) var<storage, read> value: u32;",
        "@group(0) @binding(1) var<uniform> value: u32;",
        "@group(0) @binding(1) var value: texture_2d<f32>;",
        "var<workgroup> value: u32;",
    ],
)
def test_cpu_rejects_resources_and_shared_memory(declarations: str) -> None:
    with pytest.raises(ValueError, match="user resources or workgroup variables"):
        run_test_cpu(
            {"package::main": declarations + " @test fn selected() {}"},
            "selected",
            options=wesl.TestOptions(strip=False),
        )


def test_cpu_resets_private_state_between_runs() -> None:
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


def test_cpu_executes_sdf_primitive() -> None:
    run_test_cpu(
        {
            "package::main": """
                import sdf::primitives::sphere;
                @test fn distances() {
                    wgsl_test::expectNear(sphere(vec3f(0.0), 2.0), -2.0);
                    wgsl_test::expectNear(sphere(vec3f(2.0, 0.0, 0.0), 2.0), 0.0);
                    wgsl_test::expectNear(sphere(vec3f(3.0, 0.0, 0.0), 2.0), 1.0);
                }
            """,
        },
        "distances",
        dependencies={"sdf": Path(__file__).parents[1] / "examples/sdf"},
        options=wesl.TestOptions(visibility=True),
    )
