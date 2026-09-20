from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    import wesl
    import wgpu


@pytest.fixture(params=[0.5, 2.0], ids=["half_gain", "double_gain"])
def wesl_constants(request: pytest.FixtureRequest) -> dict[str, float]:
    return {"gain": request.param}


@pytest.fixture
def wesl_resources(
    wesl_options: wesl.CompileOptions,
    wesl_constants: dict[str, float],
    wesl_device: wgpu.GPUDevice,
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    import numpy as np  # noqa: PLC0415
    import wgpu  # noqa: PLC0415

    values = np.array([-0.25, 0.0, 0.25, 0.75, 1.0], dtype=np.float32)
    expected = values * 2
    if wesl_options.features.flags["clamped"]:
        expected = np.clip(expected, 0, 1)
    expected *= wesl_constants["gain"]
    with ExitStack() as stack:
        entries = []
        for binding, data in enumerate((values, expected)):
            buffer = wesl_device.create_buffer_with_data(
                data=data,
                usage=wgpu.BufferUsage.STORAGE,
            )
            stack.callback(buffer.destroy)
            entries.append({"binding": binding, "resource": {"buffer": buffer}})
        yield {0: entries}
