import pytest
import wesl

np = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
from wesl.testing import (
    Buffer,
    ShaderAssertionError,
    ShaderRunner,
    ShaderTestDisabledError,
    Texture,
)

pytestmark = pytest.mark.gpu


def test_assertions_and_imports(wesl_runner: ShaderRunner) -> None:
    result = wesl_runner.run_test(
        {
            "package::main": """
                import library::verify;
                import wgsl_test::{expect, expectEq, expectEqI32, expectNear as near};
                @test fn assertions() {
                    verify();
                    expect(true);
                    expectEq(4294967295u, 4294967295u);
                    expectEqI32(-2147483647i, -2147483647i);
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
    assert result.checks == 7
    assert result.outputs == {}


def test_failure_in_imported_helper(wesl_runner: ShaderRunner) -> None:
    source = (
        "import wgsl_test::expectEq;\nfn verify() {\n"
        "    expectEq(4294967295u, 4294967294u);\n"
        "    expectEq(1u, 2u);\n}"
    )
    with pytest.raises(ShaderAssertionError) as captured:
        wesl_runner.run_test(
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
    assert error.actual.tolist() == [4294967295]
    assert error.expected.tolist() == [4294967294]
    assert error.failures == 2
    assert error.checks == 2
    assert error.diagnostic.filename == "library.wesl"
    assert error.diagnostic.line == 3
    assert error.diagnostic.column == 5
    assert "4294967295" in str(error)
    assert "expectEq(4294967295u, 4294967294u);" in str(error)


@pytest.mark.parametrize("enabled", [False, True])
def test_conditional_test(wesl_runner: ShaderRunner, *, enabled: bool) -> None:
    modules = {
        "package::main": """
            import wgsl_test::expect;
            @if(enabled) @test fn selected() { expect(true); }
            @else @test fn fallback() { expect(true); }
        """,
    }
    options = wesl.CompileOptions(features=wesl.Features(flags={"enabled": enabled}))
    result = wesl_runner.run_test(
        modules, "selected" if enabled else "fallback", options=options
    )
    assert result.checks == 1
    with pytest.raises(ShaderTestDisabledError):
        wesl_runner.run_test(
            modules, "fallback" if enabled else "selected", options=options
        )


def test_assertions_in_control_flow(wesl_runner: ShaderRunner) -> None:
    result = wesl_runner.run_test(
        {
            "package::main": """
            import wgsl_test::expectEq;
            @test fn loops() {
                for (var index = 0u; index < 3u; index++) {
                    if index == 0u { expectEq(index, 0u); }
                    else if index == 1u { expectEq(index, 1u); }
                    else { expectEq(index, 2u); }
                }
                var count = 0u;
                loop {
                    expectEq(count, 0u);
                    continuing { expectEq(count, 0u); break if true; }
                }
                while count < 1u { expectEq(count, 0u); count++; }
                switch count { case 1u: { expectEq(count, 1u); } default: {} }
            }
        """
        },
        "loops",
    )
    assert result.checks == 7


def test_compute_bindings_and_isolation(wesl_runner: ShaderRunner) -> None:
    shader = wesl.compile_source("""
        struct Uniforms { scale: vec4f }
        @group(0) @binding(0) var<uniform> settings: Uniforms;
        @group(2) @binding(1) var<storage, read_write> values: array<f32>;
        override offset: f32 = 0.0;
        @compute @workgroup_size(4)
        fn main(@builtin(global_invocation_id) invocation: vec3u) {
            if invocation.x < arrayLength(&values) {
                values[invocation.x] = values[invocation.x] * settings.scale.x + offset;
            }
        }
    """)
    values = np.arange(7, dtype=np.float32)
    resources = {
        (0, 0): Buffer(data=np.array([3, 0, 0, 0], dtype=np.float32), uniform=True),
        (2, 1): Buffer(data=values),
    }
    for _ in range(2):
        output = wesl_runner.compute(
            shader, resources=resources, workgroups=(2, 1, 1), constants={"offset": 2}
        )
        np.testing.assert_array_equal(output[2, 1], values * 3 + 2)
    np.testing.assert_array_equal(values, np.arange(7, dtype=np.float32))


def test_histogram(wesl_runner: ShaderRunner) -> None:
    shader = wesl.compile_source("""
        @group(0) @binding(0) var image: texture_2d<u32>;
        @group(0) @binding(1) var<storage, read_write> counts: array<atomic<u32>, 4>;
        @compute @workgroup_size(2, 2)
        fn main(@builtin(global_invocation_id) invocation: vec3u) {
            if all(invocation.xy < textureDimensions(image)) {
                let value = textureLoad(image, invocation.xy, 0).r;
                atomicAdd(&counts[value], 1u);
            }
        }
    """)
    values = np.array([[0, 1, 2], [1, 2, 2], [3, 3, 2]], dtype=np.uint32)
    output = wesl_runner.compute(
        shader,
        resources={
            (0, 0): Texture(data=values[..., None], format="r32uint"),
            (0, 1): Buffer(data=np.zeros(4, dtype=np.uint32)),
        },
        workgroups=(2, 2, 1),
    )
    np.testing.assert_array_equal(
        output[0, 1], np.bincount(values.ravel(), minlength=4)
    )


def test_fragment_texture_sampler_and_uniform(wesl_runner: ShaderRunner) -> None:
    shader = wesl.compile(
        {
            "package::main": """
            import package::display::transform;
            @group(0) @binding(0) var image: texture_2d<f32>;
            @group(0) @binding(1) var nearest: sampler;
            @fragment fn main(
                    @builtin(position) position: vec4f,
                ) -> @location(0) vec4f {
                let coordinate = position.xy / vec2f(textureDimensions(image));
                return transform(textureSampleLevel(image, nearest, coordinate, 0.0));
            }
        """,
            "package::display": """
            @group(1) @binding(0) var<uniform> multiplier: vec4f;
            fn transform(color: vec4f) -> vec4f { return color * multiplier; }
        """,
        }
    )
    pixels = np.arange(24, dtype=np.uint8).reshape(2, 3, 4)
    output = wesl_runner.fragment(
        shader,
        size=(3, 2),
        resources={
            (0, 0): Texture(data=pixels, format="rgba8unorm"),
            (0, 1): wesl_runner.device.create_sampler(),
            (1, 0): Buffer(data=np.array([2, 1, 1, 1], dtype=np.float32), uniform=True),
        },
    )
    np.testing.assert_allclose(output, pixels / 255 * [2, 1, 1, 1], rtol=1e-6)
    assert output.dtype == np.float32


def test_storage_texture(wesl_runner: ShaderRunner) -> None:
    shader = wesl.compile_source("""
        @group(0) @binding(0) var output: texture_storage_2d<rgba32float, write>;
        @compute @workgroup_size(1)
        fn main(@builtin(global_invocation_id) invocation: vec3u) {
            textureStore(output, invocation.xy, vec4f(vec2f(invocation.xy), 2.0, 1.0));
        }
    """)
    output = wesl_runner.compute(
        shader,
        workgroups=(3, 2, 1),
        resources={
            (0, 0): Texture(
                data=np.zeros((2, 3, 4), dtype=np.float32),
                format="rgba32float",
                storage=True,
            ),
        },
    )
    np.testing.assert_array_equal(output[0, 0][1, 2], [2, 1, 2, 1])


def test_shader_validation_failure(wesl_runner: ShaderRunner) -> None:
    with pytest.raises(wgpu.GPUValidationError):
        wesl_runner.compute("@compute @workgroup_size(1) fn main() { nonexistent(); }")


@pytest.mark.parametrize(
    ("assertion", "actual", "expected", "tolerance"),
    [
        ("expect(false)", [False], [True], ""),
        ("expectEqI32(-2147483647i, -2147483646i)", [-2147483647], [-2147483646], ""),
        ("expectNear(1.0, 2.0)", [1.0], [2.0], "relative tolerance: 0.001"),
        (
            "expectNearVec4(vec4f(1.0), vec4f(2.0))",
            [1.0] * 4,
            [2.0] * 4,
            "absolute tolerance: 1e-06",
        ),
        (
            "expectWithin(1.0, 1.25, 0.0, 0.125)",
            [1.0],
            [1.25],
            "absolute tolerance: 0.125",
        ),
        ("expectUlp(1.0, 2.0, 2u)", [1.0], [2.0], "maximum ULP distance: 2"),
    ],
)
def test_failure_values(
    wesl_runner: ShaderRunner,
    assertion: str,
    actual: list[float],
    expected: list[float],
    tolerance: str,
) -> None:
    with pytest.raises(ShaderAssertionError) as captured:
        wesl_runner.run_test(
            {"package::main": f"@test fn failure() {{ wgsl_test::{assertion}; }}"},
            "failure",
        )
    assert captured.value.actual.tolist() == actual
    assert captured.value.expected.tolist() == expected
    assert tolerance in str(captured.value)


def test_caller_owned_buffer(wesl_runner: ShaderRunner) -> None:
    buffer = wesl_runner.device.create_buffer_with_data(
        data=np.array([2], dtype=np.uint32),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    shader = wesl.compile_source("""
        @group(0) @binding(0) var<storage, read_write> value: u32;
        @compute @workgroup_size(1) fn main() { value *= 3u; }
    """)
    try:
        wesl_runner.compute(shader, resources={(0, 0): buffer})
        wesl_runner.compute(shader, resources={(0, 0): buffer})
        output = wesl_runner.device.queue.read_buffer(buffer)
        assert np.frombuffer(output, dtype=np.uint32).tolist() == [18]
    finally:
        buffer.destroy()


@pytest.mark.parametrize(
    "function",
    [
        "fn invalid(value: f32) {}",
        "fn invalid() -> f32 { return 1.0; }",
        "@compute @workgroup_size(1) fn invalid() {}",
    ],
)
def test_invalid_signature(wesl_runner: ShaderRunner, function: str) -> None:
    with pytest.raises(wesl.CompileError, match="@test requires a function"):
        wesl_runner.run_test({"package::main": "@test " + function}, "invalid")


def test_named_and_numeric_overrides(wesl_runner: ShaderRunner) -> None:
    result = wesl_runner.run_test(
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
    assert result.checks == 3


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("strip", [False, True])
def test_conditional_non_test_definition(
    wesl_runner: ShaderRunner, *, enabled: bool, strip: bool
) -> None:
    modules = {
        "package::main": """
            @if(enabled) @test fn selected() { wgsl_test::expect(true); }
            @else fn selected(value: u32) -> u32 { return value; }
        """,
    }
    options = wesl.CompileOptions(
        strip=strip, features=wesl.Features(flags={"enabled": enabled})
    )
    if enabled:
        assert wesl_runner.run_test(modules, "selected", options=options).checks == 1
    else:
        with pytest.raises(ShaderTestDisabledError):
            wesl_runner.run_test(modules, "selected", options=options)


def test_inactive_test_signature(wesl_runner: ShaderRunner) -> None:
    result = wesl_runner.run_test(
        {
            "package::main": """
                @if(true) @test fn selected() { wgsl_test::expect(true); }
                @else @test fn selected(value: u32) -> u32 { return value; }
            """,
        },
        "selected",
    )
    assert result.checks == 1


def test_requires_test_attribute(wesl_runner: ShaderRunner) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        wesl_runner.run_test({"package::main": "fn helper() {}"}, "helper")


def test_scalar_buffer_shape(wesl_runner: ShaderRunner) -> None:
    value = np.array(3, dtype=np.float32)
    output = wesl_runner.compute(
        """
            @group(0) @binding(0) var<storage, read_write> value: f32;
            @compute @workgroup_size(1) fn main() { value *= 2.0; }
        """,
        resources={(0, 0): Buffer(data=value)},
    )
    assert output[0, 0].shape == ()
    assert output[0, 0].dtype == np.float32
    assert output[0, 0].item() == 6
    assert value.item() == 3
