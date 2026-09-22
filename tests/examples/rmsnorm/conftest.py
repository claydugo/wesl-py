from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from struct import pack
from typing import TYPE_CHECKING, Any

import pytest
import wesl

if TYPE_CHECKING:
    import wgpu


@pytest.fixture(params=[False, True], ids=["plain", "residual"])
def wesl_features(request: pytest.FixtureRequest) -> wesl.Features:
    return wesl.Features(flags={"residual": request.param})


@pytest.fixture
def wesl_root_directory() -> Path:
    return Path(__file__).parents[3]


@pytest.fixture
def wesl_resources(
    wesl_features: wesl.Features,
    wesl_device: "wgpu.GPUDevice",
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    wgpu = pytest.importorskip("wgpu")
    with ExitStack() as stack:
        buffer = wesl_device.create_buffer_with_data(
            data=pack("<2f", 2, -2),
            usage=wgpu.BufferUsage.STORAGE,
        )
        stack.callback(buffer.destroy)
        entries = [{"binding": 0, "resource": {"buffer": buffer}}]
        if wesl_features.flags["residual"]:
            buffer = wesl_device.create_buffer_with_data(
                data=pack("<2f", 1, -1),
                usage=wgpu.BufferUsage.STORAGE,
            )
            stack.callback(buffer.destroy)
            entries.append({"binding": 1, "resource": {"buffer": buffer}})
        yield {0: entries}


@pytest.fixture
def wesl_constants() -> dict[str, float]:
    return {"0": 2, "1": 0.25}
