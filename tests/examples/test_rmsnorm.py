from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import wgpu

np = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
normalize = import_module("examples.rmsnorm.compute").normalize


@pytest.mark.gpu
@pytest.mark.parametrize("residual_enabled", [False, True], ids=["plain", "residual"])
def test_normalization_accepts_strided_inputs(
    wesl_device: wgpu.GPUDevice, *, residual_enabled: bool
) -> None:
    random = np.random.default_rng(7)
    values = random.normal(size=(65, 3)).astype(np.float32).T
    values[0] = 0
    weights = np.linspace(-1, 2, 130, dtype=np.float32)[::2]
    residual = (
        random.normal(size=(65, 3)).astype(np.float32).T if residual_enabled else None
    )
    if residual is not None:
        residual[0] = 0
    epsilon = 0.25 if residual_enabled else 2**-126
    output = normalize(wesl_device, values, weights, residual=residual, epsilon=epsilon)
    combined = values.astype(np.float64)
    if residual is not None:
        combined += residual
    expected = (
        combined
        / np.sqrt(np.mean(combined**2, axis=1, keepdims=True) + epsilon)
        * weights
    )
    assert output.dtype == np.float32
    np.testing.assert_allclose(output, expected, rtol=2e-5, atol=2e-6)
