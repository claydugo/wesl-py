# ruff: noqa: PLR2004, T201

from time import perf_counter

import numpy
import wgpu

from .compute import compact


def main() -> None:
    random = numpy.random.default_rng(7)
    values = random.integers(0, 1000, 1_000_003, dtype=numpy.uint32)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        start = perf_counter()
        output = compact(device, values, threshold=990)
        elapsed = perf_counter() - start
        expected = values[values >= 990]
        numpy.testing.assert_array_equal(output, expected)
        print(f"Verified stable compaction on {device.adapter.info['device']}")
        print(f"Selected {len(output)} of {len(values)} values in input order")
        print(f"Compile, upload, dispatches, readback: {elapsed * 1000:.1f} ms")
    finally:
        device.destroy()


if __name__ == "__main__":
    main()
