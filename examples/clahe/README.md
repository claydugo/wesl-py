# Adaptive local contrast

```bash
pixi run -e examples python -m examples.clahe
```

The viewer applies contrast-limited adaptive histogram equalization (CLAHE)
independently to brightfield, GFP, and RFP.
The [sample image](../imaging/README.md#sample-image) shows a bacterial colony
in those three channels.
The tile size controls the spatial extent of each contrast calculation.
The clip limit controls how much each histogram bin can contribute before
redistribution. Slider changes update the result while you drag.

| File | Responsibility |
| --- | --- |
| `compute.py` | Schedule histogram construction, equalization, and interpolation. |
| `histogram.wesl` | Build a 256-bin histogram per tile and channel with workgroup atomics. |
| `equalize.wesl` | Clip histograms, redistribute counts, and compute cumulative sums. |
| `interpolation.wesl` | Sample four neighboring contrast curves. |
| `apply.wesl` | Apply the interpolated curve to each pixel. |

Each histogram uses 256 invocations and local workgroup memory.
The equalization pass reduces the clipped counts and performs a parallel
inclusive scan. Bilinear interpolation joins the curves at tile centers.
The final shared shader applies the channel LUTs and combines their colors.

The input remains in its original 8-bit intensity bins.
Partial tiles repeat the nearest edge pixel to fill the tile.
For a tile with `tile_size ** 2` samples, the histogram count limit is
`max(1, floor(clip_limit * tile_size ** 2 / 256))`.
Clipped counts spread evenly across all bins.
The remaining counts go to bins spaced by `floor(256 / remainder)`.
Contrast curves use floating point values and end at one.

`verify.py` constructs independent NumPy histograms, contrast curves,
and interpolated images. It checks constant channels, intensity ramps,
random inputs, partial tiles, and tile sizes that are not powers of two.
The reference uses the edge and redistribution rules above.
