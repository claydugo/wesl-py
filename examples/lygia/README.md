# Lygia color mapping

Map a grayscale image to RGBA on the GPU.
The shader imports Lygia's range mapping and heatmap functions without modifying them.
Display limits normalize the intensity. Values outside the limits use the endpoint colors.
The limits must have a finite positive range in `f32` arithmetic.
The output clips RGB channels to `[0, 1]` and sets alpha to one.

Run from the repository root on Linux x86-64:

```bash
pixi run python tools/fetch_test_shaders.py
pixi run -e examples python -m examples.lygia --library .wesl/lygia
```

The window displays a heatmap of two generated Gaussian spots.
Drag to pan. Scroll to zoom.
To use a grayscale TIFF instead:

```bash
pixi run -e examples python -m examples.lygia --library .wesl/lygia --input image.tif --minimum 100 --maximum 2000
```

The setup script fetches the two required Lygia shaders at a pinned revision.
The example registers `--library` with `dependencies={"lygia": library_directory}`.
The compiler resolves normal `import lygia::...` statements from that directory.
The binding does not download files.
See [Lygia's license](https://lygia.xyz/license).

The Python driver accepts a `wgpu.GPUDevice` and a two-dimensional NumPy array:

```python
from pathlib import Path

import numpy
import wgpu

from examples.lygia.compute import colorize

image = numpy.linspace(100, 2000, 64, dtype=numpy.float32).reshape(8, 8)
device = wgpu.gpu.request_adapter_sync().request_device_sync()
try:
    rgba = colorize(
        device, image, library_directory=Path(".wesl/lygia"), minimum=100, maximum=2000
    )
finally:
    device.destroy()
```

## Verify

```bash
pixi run -e testing python -m pytest tests/examples/lygia -q
```

The tests compare GPU output with NumPy and verify display limits and clipping.
