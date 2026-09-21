import tracemalloc
from struct import pack, unpack
from unittest.mock import Mock

import pytest
import wesl

wgpu = pytest.importorskip("wgpu")
from wesl.testing import (
    ShaderAssertionError,
    ShaderTestDisabledError,
    run_test,
)

pytestmark = pytest.mark.gpu


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


def test_failure_in_imported_helper(wesl_device: wgpu.GPUDevice) -> None:
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
        )
    error = captured.value
    assert error.actual == (4294967296.0, 0.0, 0.0, 0.0)
    assert error.expected == (4294967296.0, 0.0, 0.0, 0.0)
    assert error.failures == 2
    assert error.checks == 2
    assert error.diagnostic.filename == "library.wesl"
    assert error.diagnostic.line == 3
    assert error.diagnostic.column == 5
    assert "4294967295" in str(error)
    assert "expectEq(4294967295u, 4294967294u);" in str(error)


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
    options = wesl.CompileOptions(features=wesl.Features(flags={"enabled": enabled}))
    run_test(
        wesl_device, modules, "selected" if enabled else "fallback", options=options
    )
    with pytest.raises(ShaderTestDisabledError):
        run_test(
            wesl_device, modules, "fallback" if enabled else "selected", options=options
        )


def test_assertions_in_control_flow(wesl_device: wgpu.GPUDevice) -> None:
    run_test(
        wesl_device,
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
                for (expectEq(count, 1u); count < 2u; expectEq(count, 2u)) {
                    count++;
                }
            }
        """
        },
        "loops",
    )


@pytest.mark.parametrize(
    ("assertion", "actual", "expected"),
    [
        ("expect(false)", [-999.0] * 4, [-999.0] * 4),
        ("expectNear(1.0, 2.0)", [1.0, 0.0, 0.0, 0.0], [2.0, 0.0, 0.0, 0.0]),
        (
            "expectNearVec4(vec4f(1.0), vec4f(2.0))",
            [1.0] * 4,
            [2.0] * 4,
        ),
        (
            "expectWithin(1.0, 1.25, 0.0, 0.125)",
            [1.0, 0.0, 0.0, 0.0],
            [1.25, 0.0, 0.0, 0.0],
        ),
        ("expectUlp(1.0, 2.0, 2u)", [1.0, 0.0, 0.0, 0.0], [2.0, 0.0, 0.0, 0.0]),
    ],
)
def test_failure_values(
    wesl_device: wgpu.GPUDevice,
    assertion: str,
    actual: list[float],
    expected: list[float],
) -> None:
    with pytest.raises(ShaderAssertionError) as captured:
        run_test(
            wesl_device,
            {"package::main": f"@test fn failure() {{ wgsl_test::{assertion}; }}"},
            "failure",
        )
    assert captured.value.actual == tuple(actual)
    assert captured.value.expected == tuple(expected)


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
    options = wesl.CompileOptions(
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


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "assertion",
        "validation",
        "binding",
        "collision",
        "readback",
        "incomplete",
    ],
)
def test_result_buffer_cleanup(
    wesl_device: wgpu.GPUDevice,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    buffer = wesl_device.create_buffer(
        size=64,
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    destroy = Mock(wraps=buffer.destroy)
    monkeypatch.setattr(buffer, "destroy", destroy)
    monkeypatch.setattr(wesl_device, "create_buffer", Mock(return_value=buffer))
    source = "@test fn selected() { wgsl_test::expect(true); }"
    exception = None
    if outcome == "assertion":
        source = "@test fn selected() { wgsl_test::expect(false); }"
        exception = ShaderAssertionError
    elif outcome == "validation":
        source = "@test fn selected() { let value = sqrt(1u); }"
        exception = wgpu.GPUValidationError
    elif outcome == "binding":
        source = """
            @group(1) @binding(0) var<storage, read> value: u32;
            @test fn selected() { wgsl_test::expectEq(value, 1u); }
        """
        exception = wgpu.GPUValidationError
    elif outcome == "collision":
        source = """
            @group(0) @binding(0) var<storage, read> value: u32;
            @test fn selected() { wgsl_test::expectEq(value, 1u); }
        """
        exception = wgpu.GPUValidationError
    elif outcome == "readback":
        monkeypatch.setattr(
            wesl_device.queue,
            "read_buffer",
            Mock(side_effect=RuntimeError("readback failed")),
        )
        exception = RuntimeError
    elif outcome == "incomplete":
        monkeypatch.setattr(
            wesl_device.queue, "read_buffer", Mock(return_value=bytes(64))
        )
        exception = RuntimeError
    try:
        if exception is None:
            run_test(wesl_device, {"package::main": source}, "selected")
        else:
            with pytest.raises(exception):
                run_test(wesl_device, {"package::main": source}, "selected")
        destroy.assert_called_once_with()
    finally:
        if not destroy.called:
            buffer.destroy()
