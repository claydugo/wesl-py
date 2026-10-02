# Microscopy image and shared shaders

[Multiscale fluorescence](../multiscale/README.md) uses this microscopy image
and the WESL library in this directory.

## Sample image

`load_colony()` in [common.py](../multiscale/common.py) loads a microscopy image
of a bacterial colony from `imageio:bacterial_colony.tif` with the tifffile plugin.
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

## Shared operations

These modules provide image operations for compute kernels.
The multiscale example keeps its entry points in [shaders](../multiscale/shaders)
and schedules passes in [compute.py](../multiscale/compute.py).

Import convolution or its Gaussian parameters:

```wesl
import package::examples::imaging::gaussian::convolve;
```

```wesl
import package::examples::imaging::gaussian::{radius, weights};
```

Compile these kernels with the repository as the root directory.
WESL resolves `package::examples::imaging` relative to that root.
The compiler removes unused declarations, including resource bindings.
Correlation uses its own accumulation without importing the convolution buffer.

Sampling and convolution share a planar channel buffer at binding zero.
Convolution reads Gaussian weights at binding two.
Python sets the radius through override ID zero.
The `horizontal` feature selects the axis for convolution.
Clamping, statistics, and coordinate conversion do not need resource bindings.

`sum_workgroup` requires a workgroup of 256 invocations.
Every invocation must call it at the same point in control flow.
Each supplies a `vec4<f32>` and its local invocation index.
The function uses workgroup memory and barriers to return the componentwise sum.

## GPU compositing

`composite()` in [common.py](../multiscale/common.py) connects the composite shader
to a pygfx texture.

The final pass applies LUTs and sums channel colors into a display clipped to
`[0, 1]`. Gain and enhancement controls affect visualization.

Intermediate arrays and display textures stay on the GPU.
The verification script reads results back to compare them with NumPy.
The viewer uses pygfx's experimental `ComputeShader` helper.
The helper consumes `CompileResult.wgsl` and manages wgpu pipelines and bindings.
