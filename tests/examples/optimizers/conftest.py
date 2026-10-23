from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from examples.optimizers.layout import create_layout

if TYPE_CHECKING:
    import wgpu


@pytest.fixture
def wesl_constants() -> dict[str, int]:
    return create_layout(16)


@pytest.fixture
def wesl_modules() -> dict[str, str]:
    return {
        "package::examples::optimizers::parameters": (
            Path(__file__).parent / "perturbed.wesl"
        ).read_text(),
    }


@pytest.fixture
def wesl_filenames() -> dict[str, Path]:
    return {
        "package::examples::optimizers::parameters": Path(__file__).parent
        / "perturbed.wesl"
    }


@pytest.fixture
def wesl_resources(
    wesl_device: "wgpu.GPUDevice",
) -> Iterator[dict[int, list[dict[str, Any]]]]:
    np = pytest.importorskip("numpy")
    wgpu = pytest.importorskip("wgpu")
    parameter_count = create_layout(16)["parameter_count"]
    parameters = wesl_device.create_buffer_with_data(
        data=np.random.default_rng(5)
        .normal(0, 0.7, parameter_count)
        .astype(np.float32),
        usage=wgpu.BufferUsage.STORAGE,
    )
    gradients = wesl_device.create_buffer(
        size=parameter_count * 4, usage=wgpu.BufferUsage.STORAGE
    )
    try:
        yield {
            0: [
                {"binding": 0, "resource": {"buffer": parameters}},
                {"binding": 2, "resource": {"buffer": gradients}},
            ]
        }
    finally:
        parameters.destroy()
        gradients.destroy()
