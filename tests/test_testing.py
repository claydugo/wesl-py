import tracemalloc
from pathlib import Path
from struct import pack, unpack

import pytest
import wesl

wgpu = pytest.importorskip("wgpu")
from wesl.testing import (
    ShaderAssertionError,
    ShaderTestDisabledError,
    run_test,
)

pytestmark = pytest.mark.gpu


def test_run_test_rejects_compile_options(wesl_device: wgpu.GPUDevice) -> None:
    with pytest.raises(TypeError, match="options must be TestOptions or None"):
        run_test(
            wesl_device,
            {"package::main": "@test fn selected() {}"},
            "selected",
            options=wesl.CompileOptions(),
        )


@pytest.mark.parametrize("workgroup", ["", "@workgroup_size(2)"])
def test_shader_test_visibility(wesl_device: wgpu.GPUDevice, workgroup: str) -> None:
    modules = {
        "package::main": (
            "import library::value; import wgsl_test::expectEq; "
            f"@test {workgroup} fn selected() {{ expectEq(value(), 7u); }}"
        ),
        "library": "fn value() -> u32 { return 7u; }",
    }
    run_test(wesl_device, modules, "selected")
    options = wesl.TestOptions(visibility=True)
    with pytest.raises(wesl.CompileError, match="visibility"):
        run_test(wesl_device, modules, "selected", options=options)
    modules["library"] = "public fn value() -> u32 { return 7u; }"
    run_test(wesl_device, modules, "selected", options=options)


@pytest.mark.parametrize("override", [False, True])
def test_run_test_reuses_project_dependencies(
    wesl_device: wgpu.GPUDevice, tmp_path: Path, *, override: bool
) -> None:
    (tmp_path / "wesl.toml").write_text(
        'edition = "2026_pre"\nroot = "."\n[dependencies]\n'
        'alpha = { path = "common" }\nbeta = { path = "common" }\n'
    )
    common = tmp_path / "common"
    common.mkdir()
    (common / "wesl.toml").write_text('edition = "2026_pre"\nroot = "."\n')
    (common / "package.wesl").write_text(
        "var<private> counter: u32 = 0u; "
        "fn next() -> u32 { counter += 1u; return counter; }"
    )
    compiler = wesl.Compiler.from_project(tmp_path)
    (tmp_path / "wesl.toml").unlink()
    (common / "wesl.toml").unlink()
    modules = {
        "package::main": "@test fn selected() { "
        "wgsl_test::expectEq(alpha::next(), 1u); "
        "wgsl_test::expectEq(beta::next(), 2u); }"
    }
    if override:
        modules["beta"] = (common / "package.wesl").read_text()
    run_test(
        wesl_device,
        modules,
        "selected",
        dependencies=compiler.dependencies,
    )
    if override:
        run_test(
            wesl_device,
            {
                "beta::tests": "@test fn selected() { "
                "wgsl_test::expectEq(package::next(), 1u); "
                "wgsl_test::expectEq(package::next(), 2u); }",
                "beta": modules["beta"],
            },
            "selected",
            root="beta::tests",
            dependencies=compiler.dependencies,
        )


def test_assertions_and_imports(wesl_device: wgpu.GPUDevice) -> None:
    run_test(
        wesl_device,
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


@pytest.mark.parametrize("lower", [False, True])
def test_failure_in_imported_helper(
    wesl_device: wgpu.GPUDevice, *, lower: bool
) -> None:
    source = (
        "import wgsl_test::expectEq;\nfn verify() {\n"
        "    expectEq(4294967295u, 4294967294u);\n"
        "    expectEq(1u, 2u);\n}"
    )
    with pytest.raises(ShaderAssertionError) as captured:
        run_test(
            wesl_device,
            {
                "package::main": (
                    "import library::verify; @test fn failure() { verify(); }"
                ),
                "library": source,
            },
            "failure",
            filenames={"library": "library.wesl"},
            options=wesl.TestOptions(lower=lower),
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


@pytest.mark.parametrize("lower", [False, True])
def test_assertion_wrapper_avoids_parameter_collisions(
    wesl_device: wgpu.GPUDevice, *, lower: bool
) -> None:
    source = "@test fn failure() { wgsl_test::expectEq(7u, 9u); }"
    with pytest.raises(ShaderAssertionError) as captured:
        run_test(
            wesl_device,
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
            options=wesl.TestOptions(lower=lower),
        )
    assert captured.value.actual == 7
    assert captured.value.expected == 9
    assert captured.value.failures == 1
    assert captured.value.checks == 1
    assert captured.value.diagnostic.source == source


@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        ("", ""),
        ("@if(true) {", "}"),
        ("@if(false) {} @else { @if(true) {", "}}"),
    ],
)
@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize("cooperative", [False, True])
def test_result_instrumentation(  # noqa: PLR0913
    wesl_device: wgpu.GPUDevice,
    wgsl_test: Path,
    prefix: str,
    suffix: str,
    *,
    lower: bool,
    cooperative: bool,
) -> None:
    result_source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    result_source = (
        result_source.replace("@binding(0)", "@binding(\n0\n)")
        .replace("passed: u32,\n  failCount: u32,", "failCount: u32,\n  passed: u32,")
        .replace("failCount: u32,", "failCount :\n u32 ,")
        .replace("expected: vec4f,", "@align(64) @size(64) expected : vec4<f32> ,")
    )
    result_source = prefix + "\n" + result_source + "\n" + suffix
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
                options=wesl.TestOptions(lower=lower),
                resources={0: [{"binding": 0, "resource": {"buffer": buffer}}]},
            )
        assert captured.value.actual == 7
        assert captured.value.expected == 9
        assert captured.value.failures == (8 if cooperative else 1)
        assert captured.value.checks == (8 if cooperative else 1)
    finally:
        buffer.destroy()


@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize(
    "body",
    [
        """
        {
            if (testResult.failCount == 0u) {
                testResult.actual = actual;
                testResult.expected = expected;
            }
        }
        testResult.failCount += 1u;
        """,
        """
        if (testResult.failCount == 0u) {
            testResult.actual = actual;
            testResult.expected = expected;
        }
        if (true) { testResult.failCount += 1u; }
        """,
    ],
)
def test_failure_recording_preserves_control_flow(
    wesl_device: wgpu.GPUDevice, body: str, *, lower: bool
) -> None:
    with pytest.raises(ShaderAssertionError) as captured:
        run_test(
            wesl_device,
            {
                "package::main": """
                    @test fn failure() {
                        wgsl_test::expectEq(4294967295u, 4294967294u);
                        wgsl_test::expectEq(3u, 4u);
                    }
                """,
                "wgsl_test": (
                    "import package::TestResult::testResult;\n"
                    "fn recordFailure(actual: vec4f, expected: vec4f) {\n"
                    "    testResult.passed = 0u;\n"
                    f"{body}\n"
                    "}\n"
                    "fn expectEq(actual: u32, expected: u32) {\n"
                    "    if (actual != expected) {\n"
                    "        recordFailure(vec4f(f32(actual)), vec4f(f32(expected)));\n"
                    "    }\n"
                    "}\n"
                ),
            },
            "failure",
            options=wesl.TestOptions(lower=lower),
        )
    assert captured.value.actual == 4294967295
    assert captured.value.expected == 4294967294
    assert captured.value.failures == 2
    assert captured.value.checks == 2


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        (
            "@if(enabled) @test fn selected() { expect(true); } "
            "@else @test fn fallback() { expect(true); }"
        ),
        (
            "@if(enabled) { @test fn selected() { expect(true); } } "
            "@else { @test fn fallback() { expect(true); } }"
        ),
    ],
)
def test_conditional_test(
    wesl_device: wgpu.GPUDevice, source: str, *, enabled: bool
) -> None:
    modules = {
        "package::main": f"import wgsl_test::expect; {source}",
    }
    options = wesl.TestOptions(features=wesl.Features(flags={"enabled": enabled}))
    run_test(
        wesl_device, modules, "selected" if enabled else "fallback", options=options
    )
    with pytest.raises(ShaderTestDisabledError):
        run_test(
            wesl_device, modules, "fallback" if enabled else "selected", options=options
        )


@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize(
    ("statement", "checks", "failures"),
    [
        pytest.param("{ expectEq(1u, 2u); }", 3, 2, id="block"),
        pytest.param("if true { expectEq(1u, 2u); }", 3, 2, id="if"),
        pytest.param(
            "if false {} else if true { expectEq(1u, 2u); }", 3, 2, id="else-if"
        ),
        pytest.param("if false {} else { expectEq(1u, 2u); }", 3, 2, id="else"),
        pytest.param(
            "for (var index = 0u; index < 3u; index++) { "
            "if index < 2u { expectEq(1u, 2u); } }",
            4,
            3,
            id="for",
        ),
        pytest.param(
            "var index = 0u; while index < 2u { expectEq(1u, 2u); index++; }",
            4,
            3,
            id="while",
        ),
        pytest.param("loop { expectEq(1u, 2u); break; }", 3, 2, id="loop"),
        pytest.param(
            "loop { continuing { expectEq(1u, 2u); break if true; } }",
            3,
            2,
            id="continuing",
        ),
        pytest.param(
            "switch 1u { case 1u: { expectEq(1u, 2u); } default: {} }",
            3,
            2,
            id="switch-case",
        ),
        pytest.param(
            "switch 1u { case 0u: {} default: { expectEq(1u, 2u); } }",
            3,
            2,
            id="switch-default",
        ),
        pytest.param("for (expectEq(1u, 2u); false;) {}", 3, 2, id="for-initializer"),
        pytest.param(
            "var index = 0u; for (; index < 1u; expectEq(1u, 2u)) { index++; }",
            3,
            2,
            id="for-update",
        ),
    ],
)
def test_assertions_in_control_flow(
    wesl_device: wgpu.GPUDevice,
    statement: str,
    checks: int,
    failures: int,
    *,
    lower: bool,
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
        run_test(
            wesl_device,
            {"package::main": source},
            "loops",
            filenames={"package::main": "control_flow.wesl"},
            options=wesl.TestOptions(lower=lower),
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
    ("assertion", "actual", "expected"),
    [
        ("expect(false)", False, True),
        ("expectEq(4294967295u, 4294967294u)", 4294967295, 4294967294),
        ("expectNear(1.0, 2.0)", 1.0, 2.0),
        (
            "expectNearVec2(vec2f(1.0, 0.0), vec2f(2.0, 0.0))",
            (1.0, 0.0),
            (2.0, 0.0),
        ),
        (
            "expectNearVec3(vec3f(1.0, 0.0, 0.0), vec3f(2.0, 0.0, 0.0))",
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
        ),
        (
            "expectNearVec4(vec4f(1.0), vec4f(2.0))",
            (1.0, 1.0, 1.0, 1.0),
            (2.0, 2.0, 2.0, 2.0),
        ),
        ("expectWithin(1.0, 1.25, 0.0, 0.125)", 1.0, 1.25),
        ("expectUlp(1.0, 2.0, 2u)", 1.0, 2.0),
        (
            "expectUlpVec2(vec2f(1.0, 0.0), vec2f(2.0, 0.0), 2u)",
            (1.0, 0.0),
            (2.0, 0.0),
        ),
        (
            "expectUlpVec3(vec3f(1.0, 0.0, 0.0), vec3f(2.0, 0.0, 0.0), 2u)",
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
        ),
        (
            "expectUlpVec4(vec4f(1.0, 0.0, 0.0, 0.0), vec4f(2.0, 0.0, 0.0, 0.0), 2u)",
            (1.0, 0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0, 0.0),
        ),
    ],
)
@pytest.mark.parametrize("lower", [False, True])
def test_failure_values(
    wesl_device: wgpu.GPUDevice,
    assertion: str,
    actual: float | tuple[float, ...],
    expected: float | tuple[float, ...],
    *,
    lower: bool,
) -> None:
    with pytest.raises(ShaderAssertionError) as captured:
        run_test(
            wesl_device,
            {"package::main": f"@test fn failure() {{ wgsl_test::{assertion}; }}"},
            "failure",
            options=wesl.TestOptions(lower=lower),
        )
    assert captured.value.actual == actual
    assert captured.value.expected == expected
    assert type(captured.value.actual) is type(actual)
    assert type(captured.value.expected) is type(expected)


@pytest.mark.parametrize(
    ("parameter_type", "assertion", "values"),
    [
        ("bool", "expect(false)", (False, True)),
        ("u32", "expectEq(4294967295u, 4294967294u)", (4294967295, 4294967294)),
        (
            "vec3<f32>",
            "expectNearVec3(vec3f(1.0, 0.0, 0.0), vec3f(2.0, 0.0, 0.0))",
            ((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        ),
    ],
)
def test_failure_values_with_type_aliases(
    wesl_device: wgpu.GPUDevice,
    wgsl_test: Path,
    parameter_type: str,
    assertion: str,
    values: tuple[bool | int | tuple[float, ...], bool | int | tuple[float, ...]],
) -> None:
    source = (wgsl_test / "package.wesl").read_text(encoding="utf-8")
    source = source.replace("vec3f", "vec3<f32>")
    for lower in (False, True):
        with pytest.raises(ShaderAssertionError) as captured:
            run_test(
                wesl_device,
                {
                    "package::main": (
                        f"@test fn failure() {{ wgsl_test::{assertion}; }}"
                    ),
                    "wgsl_test": "import package::types::Value;\n"
                    + source.replace(f": {parameter_type}", ": Value"),
                    "wgsl_test::types": (
                        f"alias Value = Base; alias Base = {parameter_type};"
                    ),
                },
                "failure",
                options=wesl.TestOptions(lower=lower),
            )
        actual, expected = values
        assert captured.value.actual == actual
        assert captured.value.expected == expected
        assert type(captured.value.actual) is type(actual)
        assert type(captured.value.expected) is type(expected)


@pytest.mark.parametrize(
    ("include_newline", "ending"),
    [
        (False, "  | |______^ expectEq failed\n"),
        (True, "6 | | }\n  | |_^ expectEq failed\n"),
    ],
)
def test_failure_source_span(
    tmp_path: Path, ending: str, *, include_newline: bool
) -> None:
    source = (
        "fn vérify() {\r\n\twgsl_test::expectEq(\r\n"
        "\t\t3u + 4u,\r\n\t\t8u,\r\n\t);\r\n}"
    )
    start = source.encode().index(b"wgsl_test")
    end = source.encode().index(b");") + (4 if include_newline else 2)
    filename = tmp_path / "shaders" / "math.test.wesl"
    error = ShaderAssertionError(
        wesl.Diagnostic(
            "expectEq", filename=str(filename), source=source, span=(start, end)
        ),
        actual=7,
        expected=8,
        failures=1,
        checks=1,
        root_directory=tmp_path,
    )
    assert str(error) == (
        "error: expectEq failed\n"
        f" --> {filename.relative_to(tmp_path)}:2:2\n"
        "  |\n"
        "2 | /     wgsl_test::expectEq(\n"
        "3 | |         3u + 4u,\n"
        "4 | |         8u,\n"
        "5 | |     );\n"
        f"{ending}"
        "  |\n"
        f"  = note: in {filename.relative_to(tmp_path)}\n\n"
        "  actual:   7u\n"
        "  expected: 8u\n\n"
        "1 of 1 assertions failed"
    )
    assert error.diagnostic.filename == str(filename)


def test_failure_without_source() -> None:
    error = ShaderAssertionError(
        wesl.Diagnostic("expect", module="package::main"),
        actual=False,
        expected=True,
        failures=2,
        checks=3,
    )
    assert str(error) == (
        "error: expect failed (first failure)\n"
        "  |\n"
        "  = note: in package::main\n\n"
        "  actual:   false\n"
        "  expected: true\n\n"
        "2 of 3 assertions failed"
    )


@pytest.mark.parametrize("span", [(1, 2), (0, 1), (3, 2), (0, 99)])
def test_failure_with_invalid_source_span(span: tuple[int, int]) -> None:
    error = ShaderAssertionError(
        wesl.Diagnostic("expect", source="éx", span=span),
        actual=False,
        expected=True,
        failures=1,
        checks=1,
    )
    assert "expect failed" in str(error)
    assert "-->" not in str(error)
    assert error.diagnostic.span == span


@pytest.mark.parametrize(
    "line_break", ["\n", "\r\n", "\r", "\v", "\f", "\x85", "\u2028", "\u2029"]
)
def test_failure_with_unicode_line_breaks(line_break: str) -> None:
    source = f"fn café() {{{line_break}    wgsl_test::expect(false);{line_break}}}"
    start = source.encode().index(b"wgsl_test")
    end = source.encode().index(b";") + 1
    error = ShaderAssertionError(
        wesl.Diagnostic(
            "expect", filename="shader.wesl", source=source, span=(start, end)
        ),
        actual=False,
        expected=True,
        failures=1,
        checks=1,
    )
    assert (error.diagnostic.line, error.diagnostic.column) == (2, 5)
    assert "--> shader.wesl:2:5" in str(error)
    assert "2 |     wgsl_test::expect(false);\n" in str(error)
    assert error.diagnostic.source == source
    assert error.diagnostic.span == (start, end)


@pytest.mark.parametrize(
    "function",
    [
        "fn invalid(value: f32) {}",
        "fn invalid() -> f32 { return 1.0; }",
        "@compute @workgroup_size(1) fn invalid() {}",
    ],
)
def test_invalid_signature(wesl_device: wgpu.GPUDevice, function: str) -> None:
    with pytest.raises(wesl.CompileError, match="@test requires a function"):
        run_test(wesl_device, {"package::main": "@test " + function}, "invalid")


def test_named_and_numeric_overrides(wesl_device: wgpu.GPUDevice) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                override offset: u32 = 0u;
                @id(3) override scale: u32 = 1u;
                @test fn overrides() {
                    wgsl_test::expectEq(offset, 7u);
                    wgsl_test::expectEq(scale, 2u);
                    wgsl_test::expectEq(library::read(), 19u);
                }
            """,
            "library": """
                override offset: u32 = 19u;
                fn read() -> u32 { return offset; }
            """,
        },
        "overrides",
        constants={"offset": 7, "3": 2},
    )


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("strip", [False, True])
def test_conditional_non_test_definition(
    wesl_device: wgpu.GPUDevice, *, enabled: bool, strip: bool
) -> None:
    modules = {
        "package::main": """
            @if(enabled) @test fn selected() { wgsl_test::expect(true); }
            @else fn selected(value: u32) -> u32 { return value; }
        """,
    }
    options = wesl.TestOptions(
        strip=strip, features=wesl.Features(flags={"enabled": enabled})
    )
    if enabled:
        run_test(wesl_device, modules, "selected", options=options)
    else:
        with pytest.raises(ShaderTestDisabledError):
            run_test(wesl_device, modules, "selected", options=options)


def test_inactive_test_signature(wesl_device: wgpu.GPUDevice) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                @if(true) @test fn selected() { wgsl_test::expect(true); }
                @else @test fn selected(value: u32) -> u32 { return value; }
            """,
        },
        "selected",
    )


def test_requires_test_attribute(wesl_device: wgpu.GPUDevice) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        run_test(wesl_device, {"package::main": "fn helper() {}"}, "helper")


@pytest.mark.parametrize(
    ("import_source", "call"),
    [
        ("import library::wesl_test_entry;", "wesl_test_entry()"),
        ("import library::verify as wesl_test_entry;", "wesl_test_entry()"),
        (
            "import library::{helpers::{verify as wesl_test_entry}};",
            "wesl_test_entry()",
        ),
        (
            "import library::helpers as wesl_test_entry;",
            "wesl_test_entry::verify()",
        ),
    ],
)
def test_entry_name_avoids_imports(
    wesl_device: wgpu.GPUDevice, import_source: str, call: str
) -> None:
    with pytest.raises(ShaderAssertionError, match="expect failed"):
        run_test(
            wesl_device,
            {
                "package::main": (
                    f"{import_source}\n"
                    "fn wesl_test_entry_() {}\n"
                    f"@test fn selected() {{ {call}; }}"
                ),
                "library": (
                    "fn wesl_test_entry() { wgsl_test::expect(false); }\n"
                    "fn verify() { wgsl_test::expect(false); }"
                ),
                "library::helpers": "fn verify() { wgsl_test::expect(false); }",
            },
            "selected",
        )


@pytest.mark.parametrize(
    ("group", "exception"),
    [(-1, OverflowError), (100_000, wgpu.GPUValidationError)],
)
def test_invalid_bind_groups(
    wesl_device: wgpu.GPUDevice, group: int, exception: type[Exception]
) -> None:
    tracemalloc.start()
    try:
        with pytest.raises(exception):
            run_test(
                wesl_device,
                {"package::main": "@test fn selected() { wgsl_test::expect(true); }"},
                "selected",
                resources={group: []},
            )
        assert tracemalloc.get_traced_memory()[1] < 4_000_000
    finally:
        tracemalloc.stop()


@pytest.mark.parametrize("group", [-1, 100_000])
def test_invalid_layout_groups(wesl_device: wgpu.GPUDevice, group: int) -> None:
    with pytest.raises(ValueError, match="layout group index"):
        run_test(
            wesl_device,
            {"package::main": "@test fn selected() { wgsl_test::expect(true); }"},
            "selected",
            layouts={group: []},
        )


def test_native_bindings_and_ownership(wesl_device: wgpu.GPUDevice) -> None:
    uniform = wesl_device.create_buffer_with_data(
        data=pack("<4I", 3, 0, 0, 0),
        usage=wgpu.BufferUsage.UNIFORM,
    )
    values = wesl_device.create_buffer_with_data(
        data=bytes(256) + pack("<I", 7),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        resources = {
            0: [{"binding": 0, "resource": {"buffer": uniform}}],
            2: [
                {"binding": 1, "resource": {"buffer": values, "offset": 256, "size": 4}}
            ],
        }
        source = """
            @group(0) @binding(0) var<uniform> increment: vec4u;
            @group(2) @binding(1) var<storage, read_write> value: u32;
            override expected: u32 = 0u;
            @test fn mutate() {
                value += increment.x;
                wgsl_test::expectEq(value, expected);
            }
        """
        for expected in (10, 13):
            assert (
                run_test(
                    wesl_device,
                    {"package::main": source},
                    "mutate",
                    resources=resources,
                    constants={"expected": expected},
                )
                is None
            )
        assert len(resources[0]) == 1
        assert unpack(
            "<I", wesl_device.queue.read_buffer(values, buffer_offset=256, size=4)
        ) == (13,)
    finally:
        values.destroy()
        uniform.destroy()


def test_texture_bindings(wesl_device: wgpu.GPUDevice) -> None:
    texture = wesl_device.create_texture(
        size=(1, 1, 1),
        format="rgba8unorm",
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    try:
        wesl_device.queue.write_texture(
            {"texture": texture},
            bytes((255, 0, 0, 255)),
            {"bytes_per_row": 4},
            (1, 1, 1),
        )
        run_test(
            wesl_device,
            {
                "package::main": """
                @group(2) @binding(0) var image: texture_2d<f32>;
                @group(2) @binding(1) var nearest: sampler;
                @test fn sample() {
                    wgsl_test::expectNearVec4(
                        textureSampleLevel(image, nearest, vec2f(0.5), 0.0),
                        vec4f(1.0, 0.0, 0.0, 1.0),
                    );
                }
            """
            },
            "sample",
            resources={
                2: [
                    {"binding": 0, "resource": texture.create_view()},
                    {"binding": 1, "resource": wesl_device.create_sampler()},
                ]
            },
        )
        assert texture.create_view() is not None
    finally:
        texture.destroy()


@pytest.mark.parametrize("group", [0, 2])
@pytest.mark.parametrize(
    ("texture_format", "channel_count"), [("r32float", 1), ("rgba32float", 4)]
)
def test_float32_texture_bindings(
    wesl_device: wgpu.GPUDevice, group: int, texture_format: str, channel_count: int
) -> None:
    assert "float32-filterable" not in wesl_device.features
    texture = wesl_device.create_texture(
        size=(1, 1, 1),
        format=texture_format,
        usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST,
    )
    try:
        wesl_device.queue.write_texture(
            {"texture": texture},
            pack("<f", 1.0000009536743164) * channel_count,
            {"bytes_per_row": 4 * channel_count},
            (1, 1, 1),
        )
        resources = {
            group: [
                {"binding": 0, "resource": texture.create_view()},
                {
                    "binding": 1,
                    "resource": wesl_device.create_sampler(
                        mag_filter="nearest",
                        min_filter="nearest",
                        mipmap_filter="nearest",
                    ),
                },
            ]
        }
        layouts = {
            group: [
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "texture": {"sample_type": "unfilterable-float"},
                },
                {
                    "binding": 1,
                    "visibility": wgpu.ShaderStage.COMPUTE,
                    "sampler": {"type": "non-filtering"},
                },
            ]
        }
        run_test(
            wesl_device,
            {
                "package::main": f"""
                    @group({group}) @binding(0) var image: texture_2d<f32>;
                    @group({group}) @binding(1) var nearest: sampler;
                    @test fn sample() {{
                        wgsl_test::expectUlp(
                            textureSampleLevel(image, nearest, vec2f(0.5), 0.0).x,
                            1.0000009536743164,
                            0u,
                        );
                    }}
                """
            },
            "sample",
            resources=resources,
            layouts=layouts,
        )
        assert len(resources[group]) == 2
        assert len(layouts[group]) == 2
        assert set(layouts) == {group}
    finally:
        texture.destroy()


@pytest.mark.parametrize(
    "source",
    [
        "@test fn selected() { let value = sqrt(1u); }",
        """
            @group(1) @binding(0) var<storage, read> value: u32;
            @test fn selected() { wgsl_test::expectEq(value, 1u); }
        """,
        """
            @group(0) @binding(0) var<storage, read> value: u32;
            @test fn selected() { wgsl_test::expectEq(value, 1u); }
        """,
    ],
)
def test_gpu_validation_errors(wesl_device: wgpu.GPUDevice, source: str) -> None:
    with pytest.raises(wgpu.GPUValidationError):
        run_test(wesl_device, {"package::main": source}, "selected")
    run_test(
        wesl_device,
        {"package::main": "@test fn selected() { wgsl_test::expectEq(3u + 4u, 7u); }"},
        "selected",
    )


@pytest.mark.parametrize("workgroup_size", [1, 8, 32])
def test_cooperative_barriers_and_builtin_parameters(
    wesl_device: wgpu.GPUDevice, workgroup_size: int
) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                import wgsl_test::expectEq;
                override width: u32 = 1u;
                var<workgroup> values: array<u32, 32>;
                @test @workgroup_size(width)
                fn cooperative(@builtin(local_invocation_index) lane: u32) {
                    values[lane] = lane + 1u;
                    workgroupBarrier();
                    expectEq(values[(lane + 1u) % width], (lane + 1u) % width + 1u);
                    if lane != 0u { return; }
                    var total = 0u;
                    for (var index = 0u; index < width; index++) {
                        total += values[index];
                    }
                    expectEq(total, width * (width + 1u) / 2u);
                }
            """
        },
        "cooperative",
        constants={"width": workgroup_size},
    )


@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        """
            @test
            fn selected(@builtin(local_invocation_index) selected: u32) {
                wgsl_test::expectEq(selected, 0u);
            }
        """,
        """
            const width = 2u;
            @test @workgroup_size(width)
            fn selected(@builtin(local_invocation_index) width: u32) {
                wgsl_test::expect(width < 2u);
            }
        """,
    ],
    ids=["test_name", "workgroup_size"],
)
def test_cooperative_parameters_do_not_shadow_globals(
    wesl_device: wgpu.GPUDevice, source: str, *, lower: bool
) -> None:
    run_test(
        wesl_device,
        {"package::main": source},
        "selected",
        options=wesl.TestOptions(visibility=True, lower=lower),
    )


@pytest.mark.parametrize("lower", [False, True])
def test_cooperative_qualified_workgroup_size(
    wesl_device: wgpu.GPUDevice, *, lower: bool
) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                @if(enabled)
                @test @workgroup_size(package::configuration::width)
                fn selected(
                    @builtin(local_invocation_index)
                    invocation: package::configuration::Index,
                ) {
                    wgsl_test::expect(invocation < package::configuration::width);
                }
            """,
            "package::configuration": "const width = 2u; alias Index = u32;",
        },
        "selected",
        options=wesl.TestOptions(
            visibility=True,
            lower=lower,
            features=wesl.Features(flags={"enabled": True}),
        ),
    )


def test_cooperative_three_dimensional_builtins(wesl_device: wgpu.GPUDevice) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                import wgsl_test::{expect, expectEq};
                @test @workgroup_size(2, 3, 4)
                fn coordinates(
                    @builtin(local_invocation_id) position: vec3u,
                    @builtin(global_invocation_id) global_position: vec3u,
                    @builtin(num_workgroups) workgroups: vec3u,
                ) {
                    expect(all(position == global_position));
                    expect(all(workgroups == vec3u(1u)));
                    expectEq(position.x + 2u * position.y + 6u * position.z,
                             global_position.x + 2u * global_position.y
                             + 6u * global_position.z);
                }
            """
        },
        "coordinates",
    )


@pytest.mark.parametrize("failed_lanes", [1, 16, 32])
def test_cooperative_failures_retain_counts_and_source(
    wesl_device: wgpu.GPUDevice, failed_lanes: int
) -> None:
    source = (
        "import wgsl_test::expectEq;\n"
        "fn verify(lane: u32) {\n"
        "    expectEq(lane, lane + 1u);\n"
        "    expectEq(lane, lane + 2u);\n}"
    )
    with pytest.raises(ShaderAssertionError) as captured:
        run_test(
            wesl_device,
            {
                "package::main": """
                    import wgsl_test::expect;
                    import package::helper::verify;
                    override failed_lanes: u32 = 1u;
                    @test @workgroup_size(32)
                    fn failures(@builtin(local_invocation_index) lane: u32) {
                        expect(true);
                        if lane >= 32u - failed_lanes { verify(lane); }
                        workgroupBarrier();
                        expect(true);
                    }
                """,
                "package::helper": source,
            },
            "failures",
            filenames={"package::helper": "cooperative/helper.wesl"},
            constants={"failed_lanes": failed_lanes},
        )
    error = captured.value
    assert error.failures == failed_lanes * 2
    assert error.checks == 64 + failed_lanes * 2
    assert error.invocation in range(32 - failed_lanes, 32)
    assert error.actual == error.invocation
    assert error.expected == error.invocation + 1
    assert error.diagnostic.filename == "cooperative/helper.wesl"
    assert error.diagnostic.source == source
    assert "expectEq(lane, lane + 1u)" in str(error)
    assert f"invocation: {error.invocation}" in str(error)


def test_cooperative_test_without_parameters_or_assertions(
    wesl_device: wgpu.GPUDevice,
) -> None:
    run_test(
        wesl_device,
        {"package::main": "@test @workgroup_size(32) fn empty() {}"},
        "empty",
    )


def test_cooperative_wrapper_preserves_other_entry_points(
    wesl_device: wgpu.GPUDevice,
) -> None:
    run_test(
        wesl_device,
        {
            "package::main": """
                import wgsl_test::expectEq;
                @compute @workgroup_size(8)
                fn unrelated(@builtin(local_invocation_index) lane: u32) {
                    let unused = lane;
                }
                @if(enabled) {
                    @test
                    fn selected(@builtin(local_invocation_index) lane: u32) {
                        expectEq(lane, 0u);
                    }
                }
            """
        },
        "selected",
        options=wesl.TestOptions(
            strip=False, features=wesl.Features(flags={"enabled": True})
        ),
    )


def test_cooperative_generated_names_avoid_user_declarations(
    wesl_device: wgpu.GPUDevice, wgsl_test: Path
) -> None:
    result_source = (wgsl_test / "TestResult.wesl").read_text(encoding="utf-8")
    result_source += """
        @if(true) {
            fn wesl_test_collect() {}
            fn wesl_test_collect__output() {}
            fn wesl_test_collect___result() {}
        }
    """
    run_test(
        wesl_device,
        {
            "package::main": """
                import package::configuration::width as wesl_test_entry_parameter_0;
                const wesl_test_entry_parameter_0_ = 1u;
                @test
                @workgroup_size(
                    wesl_test_entry_parameter_0 * wesl_test_entry_parameter_0_
                )
                fn wesl_test_entry_invocation(
                    @builtin(local_invocation_id) position: vec3u,
                ) {
                    wgsl_test::expect(all(position < vec3u(8u, 1u, 1u)));
                }
            """,
            "package::configuration": "const width = 8u;",
            "wgsl_test::TestResult": result_source,
        },
        "wesl_test_entry_invocation",
    )
