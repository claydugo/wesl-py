import numpy as np
import wgpu

from .compute import RMSNorm


def main() -> None:
    random = np.random.default_rng(7)
    values = random.uniform(-2, 2, (32, 1025)).astype(np.float32)
    residual = random.uniform(-1, 1, values.shape).astype(np.float32)
    weights = random.uniform(0.5, 1.5, values.shape[1]).astype(np.float32)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        normalizer = RMSNorm(device, values.shape[1], residual=True)
        output = normalizer.normalize(values, weights, residual=residual)
        combined = (values + residual).astype(np.float64)
        expected = (
            combined
            / np.sqrt(np.mean(combined**2, axis=1, keepdims=True) + 1e-6)
            * weights
        )
        np.testing.assert_allclose(output, expected, rtol=2e-5, atol=2e-6)
        print("Verified residual RMSNorm: 32 rows, 1025 columns")
        print(f"Adapter: {device.adapter.info['device']}")
        error = np.max(np.abs(output - expected))
        print(f"Maximum absolute error: {error:.3g}")
    finally:
        device.destroy()


if __name__ == "__main__":
    main()
