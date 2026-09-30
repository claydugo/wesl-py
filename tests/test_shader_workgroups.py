from pathlib import Path
from struct import pack, unpack

import pytest
import wesl

wgpu = pytest.importorskip("wgpu")
from wesl.testing import ShaderAssertionError, run_test

pytestmark = pytest.mark.gpu


def test_cooperative_barriers_and_builtin_parameters(
    wesl_device: wgpu.GPUDevice,
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
        constants={"width": 32},
    )


def test_cooperative_parameters_do_not_shadow_globals(
    wesl_device: wgpu.GPUDevice,
) -> None:
    output = wesl_device.create_buffer_with_data(
        data=pack("<2I", *([0xFFFFFFFF] * 2)),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        run_test(
            wesl_device,
            {
                "package::main": """
                @group(0) @binding(0)
                var<storage, read_write> invocations: array<u32>;
                const width = 2u;
                @test @workgroup_size(width)
                fn selected(
                    @builtin(local_invocation_index) selected: u32,
                    @builtin(local_invocation_id) width: vec3u,
                ) {
                    wgsl_test::expectEq(selected, width.x);
                    invocations[selected] = width.x;
                }
            """
            },
            "selected",
            options=wesl.TestOptions(visibility=True),
            resources={0: [{"binding": 0, "resource": {"buffer": output}}]},
        )
        assert unpack("<2I", wesl_device.queue.read_buffer(output)) == (0, 1)
    finally:
        output.destroy()


def test_cooperative_qualified_workgroup_size(wesl_device: wgpu.GPUDevice) -> None:
    output = wesl_device.create_buffer_with_data(
        data=pack("<2I", *([0xFFFFFFFF] * 2)),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        run_test(
            wesl_device,
            {
                "package::main": """
                    @group(0) @binding(0)
                    var<storage, read_write> invocations: array<u32>;
                    @if(enabled)
                    @test @workgroup_size(package::configuration::width)
                    fn selected(
                        @builtin(local_invocation_index)
                        invocation: package::configuration::Index,
                    ) {
                        invocations[invocation] = invocation;
                    }
                """,
                "package::configuration": "const width = 2u; alias Index = u32;",
            },
            "selected",
            options=wesl.TestOptions(
                visibility=True,
                features=wesl.Features(flags={"enabled": True}),
            ),
            resources={0: [{"binding": 0, "resource": {"buffer": output}}]},
        )
        assert unpack("<2I", wesl_device.queue.read_buffer(output)) == (0, 1)
    finally:
        output.destroy()


def test_cooperative_three_dimensional_builtins(wesl_device: wgpu.GPUDevice) -> None:
    output = wesl_device.create_buffer_with_data(
        data=pack("<96I", *([0xFFFFFFFF] * 96)),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        run_test(
            wesl_device,
            {
                "package::main": """
                import wgsl_test::{expect, expectEq};
                @group(0) @binding(0)
                var<storage, read_write> coordinates: array<vec4u>;
                @test @workgroup_size(2, 3, 4)
                fn record_coordinates(
                    @builtin(local_invocation_id) position: vec3u,
                    @builtin(local_invocation_index) invocation: u32,
                    @builtin(global_invocation_id) global_position: vec3u,
                    @builtin(workgroup_id) workgroup: vec3u,
                    @builtin(num_workgroups) workgroups: vec3u,
                ) {
                    expect(all(position == global_position));
                    expect(all(workgroup == vec3u(0u)));
                    expect(all(workgroups == vec3u(1u)));
                    expectEq(position.x + 2u * position.y + 6u * position.z,
                             invocation);
                    coordinates[invocation] = vec4u(position, invocation);
                }
            """
            },
            "record_coordinates",
            resources={0: [{"binding": 0, "resource": {"buffer": output}}]},
        )
        actual = list(unpack("<96I", wesl_device.queue.read_buffer(output)))
        expected = [
            value
            for depth in range(4)
            for row in range(3)
            for column in range(2)
            for value in (column, row, depth, column + 2 * row + 6 * depth)
        ]
        assert actual == expected
    finally:
        output.destroy()


@pytest.mark.parametrize("failed_lanes", [1, 32], ids=["one-failure", "all-fail"])
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
    output = wesl_device.create_buffer_with_data(
        data=pack("<8I", *([0xFFFFFFFF] * 8)),
        usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC,
    )
    try:
        run_test(
            wesl_device,
            {
                "package::main": """
                    import package::configuration::width as wesl_test_entry_parameter_0;
                    @group(0) @binding(0)
                    var<storage, read_write> invocations: array<u32>;
                    const wesl_test_entry_parameter_0_ = 1u;
                    @test
                    @workgroup_size(
                        wesl_test_entry_parameter_0 * wesl_test_entry_parameter_0_
                    )
                    fn wesl_test_entry_invocation(
                        @builtin(local_invocation_id) position: vec3u,
                    ) {
                        invocations[position.x] = position.x;
                    }
                """,
                "package::configuration": "const width = 8u;",
                "wgsl_test::TestResult": result_source,
            },
            "wesl_test_entry_invocation",
            resources={0: [{"binding": 0, "resource": {"buffer": output}}]},
        )
        assert unpack("<8I", wesl_device.queue.read_buffer(output)) == tuple(range(8))
    finally:
        output.destroy()
