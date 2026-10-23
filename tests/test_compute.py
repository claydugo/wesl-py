import os
from importlib import import_module

import pytest
import wesl

wgpu = pytest.importorskip("wgpu", exc_type=ModuleNotFoundError)
compute_with_buffers = import_module("wgpu.utils.compute").compute_with_buffers

pytestmark = [pytest.mark.gpu, pytest.mark.usefixtures("available_adapter")]


@pytest.fixture(scope="module")
def available_adapter() -> None:
    try:
        wgpu.gpu.request_adapter_sync()
    except RuntimeError as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(str(error))


def test_injected_constant_semantics() -> None:
    result = wesl.compile_source(
        """
        import constants::{binding_number, width, scale, enabled, maximum};
        @group(0) @binding(binding_number)
        var<storage, read_write> output: array<u32>;
        @compute @workgroup_size(width) fn main() {
            let signed_width: i32 = width;
            let unsigned_width: u32 = width;
            let amount: f32 = scale;
            output[0] = u32(signed_width) + unsigned_width;
            output[1] = bitcast<u32>(amount);
            output[2] = select(0u, maximum, enabled);
        }
        """,
        constants={
            "binding_number": 0,
            "width": 1,
            "scale": 1.0,
            "enabled": True,
            "maximum": 2**32 - 1,
        },
    )
    output = compute_with_buffers({}, {0: (3, "I")}, result.wgsl, n=1)
    assert list(output[0]) == [2, 1065353216, 2**32 - 1]
