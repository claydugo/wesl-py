from collections.abc import Iterator
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

import pytest
import wesl

if TYPE_CHECKING:
    import wgpu


@pytest.fixture(params=[False, True], ids=["plain", "residual"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"residual": request.param})


@pytest.fixture
def wesl_resources(
    wesl_features: wesl.Features,
    wesl_device: "wgpu.GPUDevice",
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    np = pytest.importorskip("numpy")
    wgpu = pytest.importorskip("wgpu")
    random = np.random.default_rng(11)
    values = random.normal(size=64).astype(np.float32)
    residuals = random.normal(size=64).astype(np.float32)
    combined = values + residuals if wesl_features.flags["residual"] else values
    bindings = {0: values, 2: combined}
    if wesl_features.flags["residual"]:
        bindings[1] = residuals
    with ExitStack() as stack:
        entries = []
        for binding, data in bindings.items():
            buffer = wesl_device.create_buffer_with_data(
                data=data, usage=wgpu.BufferUsage.STORAGE
            )
            stack.callback(buffer.destroy)
            entries.append({"binding": binding, "resource": {"buffer": buffer}})
        yield {0: entries}


@pytest.fixture
def wesl_constants() -> dict[str, float]:
    return {"0": 64, "1": 0.25}
