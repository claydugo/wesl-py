# Compute examples

Run these commands from the repository root.
The repository's `wesl.toml` sets `examples/` as the shader root.
Imports and Python compilation use the same `package::` namespace.
The [heightfield example](heightfield/README.md) turns one height field into edges,
normals, and animated lighting. It shares a gradient across three shader variants.

```bash
pixi run -e compute python -m examples.heightfield --output /tmp/heightfield --show
```

The `compute` environment adds wgpu-py, NumPy, and imageio.
These dependencies also form the optional `compute` extra.
Heightfield and fractal require an explicit `--output` directory to save images.
The heightfield example also saves a relighting GIF.
Omit `--show` to generate files only.
The heightfield verification script compares GPU results with NumPy:

```bash
pixi run -e compute python -m examples.heightfield.verify
```

The [fractal compute shader](fractal/README.md) provides a smaller introduction.
It imports shader modules and compiles Mandelbrot and Julia variants.
It uses wgpu-py to compute pixels, NumPy to view the array, and imageio to save PNGs.

```bash
pixi run -e fractal python -m examples.fractal --output /tmp/fractals --show
```

Read [quadratic.wesl](fractal/quadratic.wesl) for the fractal equation.
Read [render.wesl](fractal/render.wesl) for the compute entry point and imports.

Continue with [multiscale fluorescence](multiscale/README.md) for filter reuse.
One convolution serves both image axes and both Gaussian scales.
Python generates the coefficients, and a WESL feature selects workgroup tiling.
The numerical reference verifies both implementations.

The `examples` environment installs imageio, NumPy, tifffile, wgpu-py,
pygfx, GLFW, and imgui-bundle.
These dependencies also form the optional `examples` extra.

| Example | Run | Compute stages |
| --- | --- | --- |
| [Multiscale fluorescence](multiscale/README.md) | `pixi run -e examples python -m examples.multiscale` | Separable convolution, scale subtraction, LUT compositing. |
| [Adaptive local contrast](clahe/README.md) | `pixi run -e examples python -m examples.clahe` | Tile histograms, clipping, cumulative sums, interpolation, LUT compositing. |

Both viewers compare an original composite with the processed result.
Pan and zoom stay linked between the views.
Sliders control the algorithm and channel gains.
Channel toggles apply to both views.

The microscopy examples load `imageio:bacterial_colony.tif` with the tifffile plugin.
Imageio downloads and caches the image on first use.
The TIFF contains three `uint8` planes with shape `(3, 2048, 2048)`:

1. Transmission brightfield.
2. Fluorescence at 440 nm (GFP).
3. Fluorescence at 590 nm (RFP).

ImageJ metadata supplies the channel labels and RGB lookup tables.
Processing keeps the acquisition channels separate.
The final compute pass applies the LUTs and adds the channel colors.
The display clips the sum to the range `[0, 1]`.
Gain and enhancement controls affect visualization.

See the [image contribution](https://github.com/imageio/imageio-binaries/pull/25)
for acquisition details and the
[imageio integration](https://github.com/imageio/imageio/pull/1115)
for the resource name.

Each example keeps its algorithm in `.wesl` files and schedules passes
in `compute.py`. Both import indexing and color functions from `imaging/`.
`common.py` loads the TIFF and connects the composite shader to a pygfx texture.
Intermediate arrays and display textures stay on the GPU.
The verification scripts read results back to compare them with NumPy.

The viewers use pygfx's experimental `ComputeShader` helper.
The helper consumes `CompileResult.wgsl` and manages wgpu pipelines and bindings.

Run numerical verification without opening a window:

```bash
pixi run -e examples python -m examples.multiscale.verify
pixi run -e examples python -m examples.clahe.verify
```

Add `--image` to verify the full TIFF as well as the synthetic inputs.
Verification requires a WebGPU adapter. Synthetic checks do not download the TIFF.

Save a viewer image without opening a window:

```bash
pixi run -e examples python -m examples.multiscale --screenshot /tmp/multiscale.png
pixi run -e examples python -m examples.clahe --screenshot /tmp/clahe.png
```

The original [compute smoke example](compute.py) remains available:

```bash
pixi run -e gpu python examples/compute.py
```
