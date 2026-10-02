from __future__ import annotations

import re
from struct import pack
from typing import TYPE_CHECKING

import pytest
from wesl.testing import ShaderAssertionError, run_test

if TYPE_CHECKING:
    from functools import partial
    from pathlib import Path

    import wgpu


def test_assertions_pass_in_root_and_imported_functions(
    shader_runner: partial,
) -> None:
    shader_runner(
        {
            "package::main": """
                import library::verify;
                import wgsl_test::{expect, expectEq, expectNear as near};
                @test fn assertions() {
                    verify();
                    expect(true);
                    expectEq(4294967295u, 4294967295u);
                    expect(-2147483647i == -2147483647i);
                    near(1.0, 1.0001);
                }
            """,
            "library": """
                import wgsl_test::{expectWithinVec2, expectNearVec3, expectUlpVec4};
                fn verify() {
                    expectWithinVec2(vec2f(1.0, 2.0), vec2f(1.01, 2.0), 0.02, 0.0);
                    expectNearVec3(vec3f(0.0), vec3f(0.0000001));
                    expectUlpVec4(
                        vec4f(-0.0, 1.0, -1.0, 0.0),
                        vec4f(0.0, 1.0, -1.0, -0.0), 0u,
                    );
                }
            """,
        },
        "assertions",
    )


def test_failure_in_imported_helper(shader_runner: partial) -> None:
    source = (
        "import wgsl_test::expectEq;\nfn verify() {\n"
        "    expectEq(4294967295u, 4294967294u);\n"
        "    expectEq(1u, 2u);\n}"
    )
    with pytest.raises(ShaderAssertionError) as captured:
        shader_runner(
            {
                "package::main": (
                    "import library::verify; @test fn failure() { verify(); }"
                ),
                "library": source,
            },
            "failure",
            filenames={"library": "library.wesl"},
        )
    error = captured.value
    assert error.actual == 4294967295
    assert error.expected == 4294967294
    assert error.failures == 2
    assert error.checks == 2
    assert error.diagnostic.filename == "library.wesl"
    assert error.diagnostic.line == 3
    assert error.diagnostic.column == 5
    assert "4294967295" in str(error)
    assert "expectEq(4294967295u, 4294967294u);" in str(error)
    assert "expectEq failed (first failure)" in str(error)
    assert "2 of 2 assertions failed" in str(error)


@pytest.mark.parametrize(
    "assertions",
    [
        pytest.param(
            "wgsl_test::expectWithin(value, 1.0, 0.0, 0.0); "
            "wgsl_test::expectWithin(1.0, value, 0.0, 0.0);",
            id="scalar",
        ),
        pytest.param(
            "wgsl_test::expectWithinVec2(vec2f(1.0, value), vec2f(1.0), 0.0, 0.0); "
            "wgsl_test::expectWithinVec2(vec2f(1.0), vec2f(1.0, value), 0.0, 0.0);",
            id="vec2f",
        ),
        pytest.param(
            "wgsl_test::expectWithinVec3("
            "vec3f(1.0, 1.0, value), vec3f(1.0), 0.0, 0.0); "
            "wgsl_test::expectWithinVec3("
            "vec3f(1.0), vec3f(1.0, 1.0, value), 0.0, 0.0);",
            id="vec3f",
        ),
        pytest.param(
            "wgsl_test::expectWithinVec4(vec4f(1.0, 1.0, 1.0, value), "
            "vec4f(1.0), 0.0, 0.0); "
            "wgsl_test::expectWithinVec4(vec4f(1.0), "
            "vec4f(1.0, 1.0, 1.0, value), 0.0, 0.0);",
            id="vec4f",
        ),
    ],
)
@pytest.mark.gpu
def test_tolerance_assertions_reject_nan(
    wesl_device: wgpu.GPUDevice, assertions: str
) -> None:
    import wgpu

    buffer = wesl_device.create_buffer_with_data(
        data=pack("<f", float("nan")), usage=wgpu.BufferUsage.STORAGE
    )
    try:
        with pytest.raises(ShaderAssertionError) as captured:
            run_test(
                wesl_device,
                {
                    "package::main": (
                        "@group(0) @binding(0) var<storage, read> value: f32; "
                        f"@test fn failure() {{ {assertions} }}"
                    ),
                },
                "failure",
                resources={0: [{"binding": 0, "resource": {"buffer": buffer}}]},
            )
        assert captured.value.failures == 2
        assert captured.value.checks == 2
    finally:
        buffer.destroy()


def test_assertion_wrapper_avoids_parameter_collisions(
    shader_runner: partial,
) -> None:
    source = "@test fn failure() { wgsl_test::expectEq(7u, 9u); }"
    with pytest.raises(ShaderAssertionError) as captured:
        shader_runner(
            {
                "package::main": source,
                "wgsl_test": """
                    import package::TestResult::testResult;
                    fn expectEq(wesl_test_location: u32, wesl_test_location_: u32) {
                        if (wesl_test_location != wesl_test_location_) {
                            testResult.passed = 0u;
                            testResult.failCount += 1u;
                        }
                    }
                """,
            },
            "failure",
        )
    assert captured.value.actual == 7
    assert captured.value.expected == 9
    assert captured.value.failures == 1
    assert captured.value.checks == 1
    assert captured.value.diagnostic.source == source


@pytest.mark.parametrize(
    "cooperative",
    [
        pytest.param(False, id="single-invocation"),
        pytest.param(True, id="workgroup"),
    ],
)
@pytest.mark.gpu
def test_result_instrumentation_preserves_layout_and_binding(
    wesl_device: wgpu.GPUDevice,
    wgsl_test: Path,
    *,
    cooperative: bool,
) -> None:
    import wgpu

    result_source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    result_source, replacement_count = re.subn(
        r"@binding\s*\(\s*0\s*\)", "@binding(\n0\n)", result_source
    )
    assert replacement_count == 1
    result_source, replacement_count = re.subn(
        r"\bpassed\s*:\s*u32\s*,\s*failCount\s*:\s*u32\s*,",
        "failCount :\n u32 ,\n  passed: u32,",
        result_source,
    )
    assert replacement_count == 1
    result_source, replacement_count = re.subn(
        r"\bexpected\s*:\s*(?:vec4f|vec4\s*<\s*f32\s*>)\s*,",
        "@align(64) @size(64) expected : vec4<f32> ,",
        result_source,
    )
    assert replacement_count == 1
    result_source = "@if(false) {} @else { @if(true) {\n" + result_source + "\n}}"
    buffer = wesl_device.create_buffer_with_data(
        data=pack("<I", 7), usage=wgpu.BufferUsage.STORAGE
    )
    try:
        with pytest.raises(ShaderAssertionError) as captured:
            run_test(
                wesl_device,
                {
                    "package::main": """
                        @group(0) @binding(0) var<storage, read> value: u32;
                        @test fn failure() {
                            wgsl_test::expectEq(value, 9u);
                        }
                    """.replace(
                        "@test fn",
                        "@test @workgroup_size(8) fn" if cooperative else "@test fn",
                    ),
                    "wgsl_test::TestResult": result_source,
                },
                "failure",
                resources={0: [{"binding": 0, "resource": {"buffer": buffer}}]},
            )
        assert captured.value.actual == 7
        assert captured.value.expected == 9
        assert captured.value.failures == (8 if cooperative else 1)
        assert captured.value.checks == (8 if cooperative else 1)
    finally:
        buffer.destroy()


def test_result_layout_constants_preserve_failure_values(
    shader_runner: partial, wgsl_test: Path
) -> None:
    source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    source = source.replace(
        "expected: vec4f,",
        "@align(alignment) @size(alignment) expected: vec4f, extra: array<u32, count>,",
    )
    source += """
        const alignment = base * 2;
        const count = base / 16;
        const base = 32;
    """
    with pytest.raises(ShaderAssertionError) as captured:
        shader_runner(
            {
                "package::main": """
                    @test fn failure() {
                        wgsl_test::expectEq(4294967295u, 4294967294u);
                    }
                """,
                "wgsl_test::TestResult": source,
            },
            "failure",
        )
    assert captured.value.actual == 4294967295
    assert captured.value.expected == 4294967294
    assert captured.value.failures == 1
    assert captured.value.checks == 1


def test_failure_recording_preserves_control_flow(
    shader_runner: partial,
) -> None:
    with pytest.raises(ShaderAssertionError) as captured:
        shader_runner(
            {
                "package::main": """
                    @test fn failure() {
                        wgsl_test::expectEq(4294967295u, 4294967294u);
                        wgsl_test::expectEq(3u, 4u);
                    }
                """,
                "wgsl_test": """
                    import package::TestResult::testResult;
                    fn recordFailure(actual: vec4f, expected: vec4f) {
                        testResult.passed = 0u;
                        {
                            if (testResult.failCount == 0u) {
                                testResult.actual = actual;
                                testResult.expected = expected;
                            }
                        }
                        if (true) { testResult.failCount += 1u; }
                    }
                    fn expectEq(actual: u32, expected: u32) {
                        if (actual != expected) {
                            recordFailure(vec4f(f32(actual)), vec4f(f32(expected)));
                        }
                    }
                """,
            },
            "failure",
        )
    assert captured.value.actual == 4294967295
    assert captured.value.expected == 4294967294
    assert captured.value.failures == 2
    assert captured.value.checks == 2


@pytest.mark.parametrize(
    ("statement", "checks", "failures"),
    [
        pytest.param(
            "{ expectEq(1u, 2u); }\n"
            "if true { expectEq(1u, 2u); }\n"
            "if false {} else if true { expectEq(1u, 2u); }\n"
            "if false {} else { expectEq(1u, 2u); }",
            6,
            5,
            id="blocks-and-branches",
        ),
        pytest.param(
            "for (var index = 0u; index < 3u; index++) { "
            "if index < 2u { expectEq(1u, 2u); } }\n"
            "var index = 0u; while index < 2u { expectEq(1u, 2u); index++; }\n"
            "loop { expectEq(1u, 2u); break; }\n"
            "loop { continuing { expectEq(1u, 2u); break if true; } }",
            8,
            7,
            id="loops",
        ),
        pytest.param(
            "switch 1u { case 1u: { expectEq(1u, 2u); } default: {} }\n"
            "switch 1u { case 0u: {} default: { expectEq(1u, 2u); } }",
            4,
            3,
            id="switch",
        ),
        pytest.param(
            "for (expectEq(1u, 2u); false;) {}\n"
            "var index = 0u; for (; index < 1u; expectEq(1u, 2u)) { index++; }",
            4,
            3,
            id="for-clauses",
        ),
    ],
)
def test_assertions_in_control_flow(
    shader_runner: partial,
    statement: str,
    checks: int,
    failures: int,
) -> None:
    source = (
        "import wgsl_test::expectEq;\n"
        "@test fn loops() {\n"
        "expectEq(0u, 0u);\n"
        f"{statement}\n"
        "expectEq(3u, 4u);\n"
        "}"
    )
    with pytest.raises(ShaderAssertionError) as captured:
        shader_runner(
            {"package::main": source},
            "loops",
            filenames={"package::main": "control_flow.wesl"},
        )
    error = captured.value
    assert error.checks == checks
    assert error.failures == failures
    assert error.actual == 1
    assert error.expected == 2
    assert error.diagnostic.filename == "control_flow.wesl"
    assert error.diagnostic.source == source
    assert error.diagnostic.line == 4
    assert error.diagnostic.column == statement.index("expectEq(1u, 2u)") + 1


@pytest.mark.parametrize(
    ("parameter_type", "assertions", "actual", "expected", "checks"),
    [
        pytest.param("bool", "expect(false);", False, True, 1, id="bool"),
        pytest.param(
            "u32",
            "expectEq(4294967295u, 4294967294u);",
            4294967295,
            4294967294,
            1,
            id="u32",
        ),
        pytest.param(
            "f32",
            "expectNear(-1.25, 2.5);"
            "expectWithin(-1.25, 2.5, 0.0, 0.125);"
            "expectUlp(-1.25, 2.5, 2u);",
            -1.25,
            2.5,
            3,
            id="f32",
        ),
        pytest.param(
            "vec2f",
            "expectNearVec2(vec2f(1.0, -2.5), vec2f(1.0, 16.75));"
            "expectWithinVec2(vec2f(1.0, -2.5), vec2f(1.0, 16.75), 0.0, 0.125);"
            "expectUlpVec2(vec2f(1.0, -2.5), vec2f(1.0, 16.75), 2u);",
            (1.0, -2.5),
            (1.0, 16.75),
            3,
            id="vec2f",
        ),
        pytest.param(
            "vec3f",
            "expectNearVec3(vec3f(1.0, -2.5, 4.25), vec3f(1.0, -2.5, 16.75));"
            "expectWithinVec3(vec3f(1.0, -2.5, 4.25), "
            "vec3f(1.0, -2.5, 16.75), 0.0, 0.125);"
            "expectUlpVec3(vec3f(1.0, -2.5, 4.25), vec3f(1.0, -2.5, 16.75), 2u);",
            (1.0, -2.5, 4.25),
            (1.0, -2.5, 16.75),
            3,
            id="vec3f",
        ),
        pytest.param(
            "vec4f",
            "expectNearVec4(vec4f(1.0, -2.5, 4.25, -8.5), "
            "vec4f(1.0, -2.5, 4.25, 16.75));"
            "expectWithinVec4(vec4f(1.0, -2.5, 4.25, -8.5), "
            "vec4f(1.0, -2.5, 4.25, 16.75), 0.0, 0.125);"
            "expectUlpVec4(vec4f(1.0, -2.5, 4.25, -8.5), "
            "vec4f(1.0, -2.5, 4.25, 16.75), 2u);",
            (1.0, -2.5, 4.25, -8.5),
            (1.0, -2.5, 4.25, 16.75),
            3,
            id="vec4f",
        ),
    ],
)
def test_failures_preserve_scalar_and_vector_values(
    shader_runner: partial,
    wgsl_test: Path,
    parameter_type: str,
    assertions: str,
    checks: int,
    *,
    actual: bool | float | tuple[float, ...],
    expected: bool | float | tuple[float, ...],
) -> None:
    source = (wgsl_test / "package.wesl").read_text(encoding="utf-8")
    source, replacement_count = re.subn(
        rf":\s*{re.escape(parameter_type)}\b", ": Value", source
    )
    assert replacement_count > 0
    with pytest.raises(ShaderAssertionError) as captured:
        shader_runner(
            {
                "package::main": (
                    "import wgsl_test::{expect, expectEq, expectNear, expectWithin, "
                    "expectUlp, expectNearVec2, expectWithinVec2, expectUlpVec2, "
                    "expectNearVec3, expectWithinVec3, expectUlpVec3, "
                    "expectNearVec4, expectWithinVec4, expectUlpVec4}; "
                    f"@test fn failure() {{ {assertions} }}"
                ),
                "wgsl_test": "import package::types::Value;\n" + source,
                "wgsl_test::types": (
                    f"alias Value = Base; alias Base = {parameter_type};"
                ),
            },
            "failure",
        )
    assert captured.value.actual == actual
    assert captured.value.expected == expected
    assert type(captured.value.actual) is type(actual)
    assert type(captured.value.expected) is type(expected)
    assert captured.value.checks == checks
    assert captured.value.failures == checks


def test_entry_name_avoids_imports(shader_runner: partial) -> None:
    with pytest.raises(ShaderAssertionError, match="expect failed") as captured:
        shader_runner(
            {
                "package::main": """
                    import library::wesl_test_entry;
                    import library::verify as wesl_test_entry_;
                    import library::{helpers::{verify as wesl_test_entry__}};
                    import library::helpers as wesl_test_entry___;
                    fn wesl_test_entry____() {}
                    @test fn selected() {
                        wesl_test_entry();
                        wesl_test_entry_();
                        wesl_test_entry__();
                        wesl_test_entry___::verify();
                    }
                """,
                "library": """
                    fn wesl_test_entry() { wgsl_test::expect(false); }
                    fn verify() { wgsl_test::expect(false); }
                """,
                "library::helpers": "fn verify() { wgsl_test::expect(false); }",
            },
            "selected",
        )
    assert captured.value.checks == 4
    assert captured.value.failures == 4
