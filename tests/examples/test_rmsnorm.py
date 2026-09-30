from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

import pytest
import wesl

if TYPE_CHECKING:
    import wgpu

np = pytest.importorskip("numpy")
pytest.importorskip("wgpu")
RMSNorm = import_module("examples.rmsnorm.compute").RMSNorm


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
    normalizer = RMSNorm(
        wesl_device, weights.size, residual=residual_enabled, epsilon=epsilon
    )
    output = normalizer.normalize(values, weights, residual=residual)
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


@pytest.mark.gpu
def test_prepared_normalization_accepts_new_inputs(
    wesl_device: wgpu.GPUDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    normalizer = RMSNorm(wesl_device, 256)
    monkeypatch.setattr(wesl, "compile_file", None)
    monkeypatch.setattr(wesl_device, "create_shader_module", None)
    monkeypatch.setattr(wesl_device, "create_compute_pipeline", None)
    weights = np.linspace(1, 2, 256, dtype=np.float32)
    for value in (1, -2):
        values = np.full((3, 256), value, dtype=np.float32)
        output = normalizer.normalize(values, weights)
        expected = values / np.sqrt(np.mean(values**2, axis=1, keepdims=True) + 1e-6)
        np.testing.assert_allclose(output, expected * weights, rtol=2e-5, atol=2e-6)
