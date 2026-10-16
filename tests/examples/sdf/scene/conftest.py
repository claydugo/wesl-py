from __future__ import annotations

from struct import pack
from typing import TYPE_CHECKING, Any

import pytest
import wesl

if TYPE_CHECKING:
    from collections.abc import Iterator

    import wgpu


@pytest.fixture(params=[False, True], ids=["solid", "cutout"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"cutout": request.param})


@pytest.fixture
def wesl_resources(
    wesl_device: wgpu.GPUDevice,
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    wgpu = pytest.importorskip("wgpu")
    parameters = [0.0] * 28
    parameters[4:8] = [0.35, 0.48, 0.7, 0.0]
    buffer = wesl_device.create_buffer_with_data(
        data=pack("<28f", *parameters), usage=wgpu.BufferUsage.UNIFORM
    )
    try:
        yield {0: [{"binding": 0, "resource": {"buffer": buffer}}]}
    finally:
        buffer.destroy()
