import numpy as np
import wgpu

from .compute import Compactor


def main() -> None:
    random = np.random.default_rng(7)
    values = random.integers(0, 1000, 1_000_003, dtype=np.uint32)
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    try:
        compactor = Compactor(device, threshold=990)
        output = compactor.compact(values)
        expected = values[values >= 990]
        np.testing.assert_array_equal(output, expected)
        print(f"Verified stable compaction on {device.adapter.info['device']}")
        print(f"Selected {len(output)} of {len(values)} values in input order")
    finally:
        device.destroy()


if __name__ == "__main__":
    main()
