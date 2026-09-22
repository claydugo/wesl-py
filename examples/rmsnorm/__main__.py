# ruff: noqa: T201

import numpy
import wgpu

from .compute import normalize


def main() -> None:
    random = numpy.random.default_rng(7)
    values = random.uniform(-2, 2, (32, 1025)).astype(numpy.float32)
    residual = random.uniform(-1, 1, values.shape).astype(numpy.float32)
    weights = random.uniform(0.5, 1.5, values.shape[1]).astype(numpy.float32)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        output = normalize(device, values, weights, residual=residual)
        combined = (values + residual).astype(numpy.float64)
        expected = (
            combined
            / numpy.sqrt(numpy.mean(combined**2, axis=1, keepdims=True) + 1e-6)
            * weights
        )
        numpy.testing.assert_allclose(output, expected, rtol=2e-5, atol=2e-6)
        print("Verified residual RMSNorm: 32 rows, 1025 columns")
        print(f"Adapter: {device.adapter.info['device']}")
        error = numpy.max(numpy.abs(output - expected))
        print(f"Maximum absolute error: {error:.3g}")
    finally:
        device.destroy()


if __name__ == "__main__":
    main()
