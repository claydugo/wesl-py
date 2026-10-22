from pathlib import Path
from struct import pack, unpack

import pytest
import wesl

wgpu = pytest.importorskip("wgpu")
from wesl.testing import ShaderAssertionError, run_test

pytestmark = pytest.mark.gpu


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
            wesl.Compiler(
                modules={
                    "package::main": """
                    import wgsl_test::expect;
                    import package::helper::verify;
                    @test @workgroup_size(32)
                    fn failures(@builtin(local_invocation_index) lane: u32) {
                        expect(true);
                        if lane >= 32u - constants::failed_lanes { verify(lane); }
                        workgroupBarrier();
                        expect(true);
                    }
                """,
                    "package::helper": source,
                },
                filenames={"package::helper": "cooperative/helper.wesl"},
            ),
            "failures",
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
            wesl.Compiler(
                modules={
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
                }
            ),
            "wesl_test_entry_invocation",
            resources={0: [{"binding": 0, "resource": {"buffer": output}}]},
        )
        assert unpack("<8I", wesl_device.queue.read_buffer(output)) == tuple(range(8))
    finally:
        output.destroy()
