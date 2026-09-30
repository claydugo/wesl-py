import numpy as np
import wgpu

from .compute import compact


def main() -> None:
    random = np.random.default_rng(7)
    values = random.integers(0, 1000, 1_000_003, dtype=np.uint32)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        output = compact(device, values, threshold=990)
        expected = values[values >= 990]
        np.testing.assert_array_equal(output, expected)
        print(f"Verified stable compaction on {device.adapter.info['device']}")
        print(f"Selected {len(output)} of {len(values)} values in input order")
    finally:
        device.destroy()


if __name__ == "__main__":
    main()
