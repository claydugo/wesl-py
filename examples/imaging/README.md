# Microscopy image and shared shaders

[Multiscale fluorescence](../multiscale/README.md) and
[adaptive local contrast](../clahe/README.md) use the same microscopy image
and color compositing code.

## Sample image

`load_colony()` in [common.py](../common.py) loads a microscopy image of a
bacterial colony from `imageio:bacterial_colony.tif` with the tifffile plugin.
Imageio downloads and caches the image on first use.
The TIFF contains three `uint8` planes with shape `(3, 2048, 2048)`:

1. Transmission brightfield.
2. Fluorescence at 440 nm (GFP).
3. Fluorescence at 590 nm (RFP).

ImageJ metadata supplies the channel labels and RGB lookup tables.
The loader returns the channels and lookup tables as floats in `[0, 1]`,
plus the channel labels.

See the [image contribution](https://github.com/imageio/imageio-binaries/pull/25)
for acquisition details and the
[imageio integration](https://github.com/imageio/imageio/pull/1115)
for the resource name.

## GPU compositing

Each example keeps its algorithm in `.wesl` files and schedules passes
in `compute.py`. Both import indexing and color functions from this directory.
`composite()` in [common.py](../common.py) connects the composite shader
to a pygfx texture.

| File | Responsibility |
| --- | --- |
| [indexing.wesl](indexing.wesl) | Map channel and pixel coordinates to a buffer index. |
| [color.wesl](color.wesl) | Map each channel's intensity through its lookup table. |
| [composite.wesl](composite.wesl) | Apply the channel gains and add the colors into an RGBA texture. |

Processing keeps the acquisition channels separate.
The final compute pass applies the LUTs and adds the channel colors.
The display clips the sum to the range `[0, 1]`.
Gain and enhancement controls affect visualization.

Intermediate arrays and display textures stay on the GPU.
The verification scripts read results back to compare them with NumPy.
The viewers use pygfx's experimental `ComputeShader` helper.
The helper consumes `CompileResult.wgsl` and manages wgpu pipelines and bindings.
