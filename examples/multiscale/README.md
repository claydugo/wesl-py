# Multiscale fluorescence

```bash
pixi run -e examples python -m examples.multiscale
```

The viewer enhances GFP and RFP structures at an adjustable spatial scale.
Brightfield stays unchanged.
The [sample image](../imaging/README.md#sample-image) shows a bacterial colony
in brightfield and two fluorescence channels.
For each fluorescence channel, it computes

```text
fine = Gaussian(image, sigma)
coarse = Gaussian(image, 2 * sigma)
enhanced = clip(image + strength * (fine - coarse), 0, 1)
```

Start with [convolution.wesl](convolution.wesl) to read the filter.
Its loop uses imported coefficients, indexing, and boundary handling.
Then read [compute.py](compute.py) to see how Python generates coefficients
and compiles the same filter for two directions and two scales.
The viewer in `__main__.py` connects that computation to the controls and display.
`enhance()` and `composite()` use pygfx's shared GPU device for their resources.

The scale slider sets `sigma` in source pixels.
Each Gaussian uses a radius of `ceil(3 * sigma)`.
The filters repeat the nearest pixel at the image boundary.
Scale and strength changes update the result while you drag.
Channel gains and visibility update the display separately.

| File | Responsibility |
| --- | --- |
| `compute.py` | Generate Gaussian coefficients and schedule the passes. |
| `filter.wesl` | Select the filter direction and write each output pixel. |
| `convolution.wesl` | Sample and accumulate a one-dimensional convolution. |
| `boundary.wesl` | Clamp sample coordinates to the image. |
| `tiled.wesl` | Load a tile and its halo into workgroup memory. |
| `enhancement.wesl` | Combine the two scales with the original channels. |

Python calculates Gaussian coefficients and uploads them to a storage buffer.
[coefficients.wesl](coefficients.wesl) defines the weights and a pipeline constant
for the radius. The convolution modules import that interface.
The radius uses override ID zero so Python can set it after WESL renames imports.

WESL feature flags select horizontal or vertical filtering and direct or
tiled sampling. The same source serves both directions and both scales.
The compiler strips the unused implementation.

The tiled variant shares samples between 64 invocations.
All invocations reach the workgroup barrier, including those beyond an image edge.
It produces the same result as the direct variant.
Its performance depends on the adapter and filter radius.

wgsl-analyzer currently reports the array length in `tiled.wesl` as an error.
Its [array-size inference test](https://github.com/wgsl-analyzer/wgsl-analyzer/blob/main/crates/hir_ty/src/tests/simple.rs)
also rejects a named constant as an array length.
WESL compilation, GPU validation, and the numerical reference accept this shader.

Disable brightfield and one fluorescence channel to inspect the remaining signal.
Set its gain to one, zoom into the branches, and change the scale.
The strength controls how much of that spatial detail returns to the original.
Toggle the tiled implementation to compare the same calculation with shared samples.

[test_multiscale.py](../../tests/examples/test_multiscale.py) compares both variants with separable NumPy convolution.
It checks each Gaussian result and the final enhancement.
Inputs include single pixels, edge impulses, separate channel signals,
and random arrays with dimensions that do not divide the workgroup size.
