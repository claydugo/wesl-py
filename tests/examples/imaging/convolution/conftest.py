from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

import pytest
import wesl

if TYPE_CHECKING:
    from collections.abc import Iterator

    import wgpu


@pytest.fixture(params=[False, True], ids=["vertical", "horizontal"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"horizontal": request.param})


@pytest.fixture(params=[1, 3], ids=["radius_1", "radius_3"])
def wesl_constants(request: pytest.FixtureRequest) -> dict[str, int]:
    return {"radius": request.param}


@pytest.fixture
def wesl_resources(
    wesl_constants: dict[str, int],
    wesl_device: wgpu.GPUDevice,
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    np = pytest.importorskip("numpy")
    wgpu = pytest.importorskip("wgpu")
    rows, columns = np.indices((8, 8), dtype=np.float32)
    noise = np.random.default_rng(3).random((8, 8), dtype=np.float32)
    fields = np.stack([np.full((8, 8), 0.75, dtype=np.float32), columns, rows, noise])
    radius = wesl_constants["radius"]
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    weights = np.exp(-0.5 * (3 * offsets / radius) ** 2)
    weights /= weights.sum()
    with ExitStack() as stack:
        entries = []
        for binding, data in ((0, fields), (2, weights.astype(np.float32))):
            buffer = wesl_device.create_buffer_with_data(
                data=data, usage=wgpu.BufferUsage.STORAGE
            )
            stack.callback(buffer.destroy)
            entries.append({"binding": binding, "resource": {"buffer": buffer}})
        yield {0: entries}
