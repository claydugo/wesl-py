from __future__ import annotations

from pathlib import Path

import pytest
import wesl
from wesl.testing import ShaderTestDisabledError, run_test_cpu


def test_cpu_runs_native_assertion_tests() -> None:
    root_directory = Path(__file__).parents[1]
    path = root_directory / "tests/runner/assertions.test.wesl"
    module = "package::tests::runner::assertions_test"
    run_test_cpu(
        wesl.Compiler(
            modules={module: path.read_text(encoding="utf-8")},
            filenames={module: path},
            root_directory=root_directory,
        ),
        "assertions_pass_in_every_scope",
        root=module,
        options=wesl.TestOptions(visibility=True),
    )


def test_cpu_executes_example_library_dependency() -> None:
    run_test_cpu(
        wesl.Compiler(
            modules={
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
            dependencies={"sdf": Path(__file__).parents[1] / "examples/sdf"},
        ),
        "distances",
        options=wesl.TestOptions(visibility=True),
    )


def test_cpu_resets_private_state_and_skips_disabled_tests() -> None:
    for _ in range(2):
        run_test_cpu(
            wesl.Compiler(
                modules={
                    "package::main": """
                    var<private> count = 0u;
                    @test fn selected() {
                        count += 1u;
                        wgsl_test::expectEq(count, 1u);
                    }
                """,
                }
            ),
            "selected",
        )
    with pytest.raises(ShaderTestDisabledError):
        run_test_cpu(
            wesl.Compiler(
                modules={
                    "package::main": """
                    import missing::value;
                    @if(enabled) @test fn selected() { value(); }
                """,
                }
            ),
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
            wesl.Compiler(modules={"package::main": source}),
            "selected",
            options=wesl.TestOptions(strip=False),
        )
