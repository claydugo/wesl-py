# Examples

| Example | Demonstrates |
| --- | --- |
| [Height to surface](heightfield/README.md) | Share a gradient across edges, normals, and animated lighting. |
| [Mandelbrot and Julia](fractal/README.md) | Select between two fractals with conditional compilation. |
| [Multiscale fluorescence](multiscale/README.md) | Share a convolution across directions and scales. |
| [Adaptive local contrast](clahe/README.md) | Combine tile histograms and interpolated contrast curves. |

Start with [fractal](fractal/README.md) for a small introduction to imports and
conditional compilation. Continue with the microscopy viewers for algorithms
that use multiple compute passes.

## Render images

Run these commands from the repository root.
The repository's `wesl.toml` sets `examples/` as the shader root for editor tooling.
The Python examples pass that root to `compile_file()` for the same
`package::` namespace.

Render the height field and its relighting animation:

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

## Explore microscopy

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

Both viewers use a microscopy image of a bacterial colony.
Imageio downloads and caches the TIFF on first use.
See [the image and shared shaders](imaging/README.md) for its channels,
source, and GPU compositing code.

## Verify and export

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

## Minimal compute example

[compute.py](compute.py) compiles two feature variants and checks their GPU output:

```bash
pixi run -e gpu python examples/compute.py
```
