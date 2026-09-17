# Examples

Run these commands from the repository root.
Both examples open interactive windows and require a WebGPU adapter.

| Example | Run | WESL demonstrates |
| --- | --- | --- |
| [SDF playground](sdf/README.md) | `pixi run -e examples python -m examples.sdf` | Share geometry between rendering and particle collisions. |
| [Multiscale fluorescence](multiscale/README.md) | `pixi run -e examples python -m examples.multiscale` | Share convolution across directions, scales, and implementations. |

Start with the SDF playground.
Change the surface while particles bounce off it.
One distance function defines the rendered surface and its collisions.
The tunnel feature compiles into both shaders from the same scene module.

Continue with multiscale fluorescence for image processing across multiple passes.
One convolution serves both image axes and both Gaussian scales.
A WESL feature selects direct or workgroup-tiled sampling.
The viewer downloads and caches a sample microscopy TIFF on first use.
See [the sample image](imaging/README.md) for its source and channels.

The `examples` environment provides the optional `examples` dependencies.
The repository's `wesl.toml` sets `examples/` as the shader root for editor tooling.
The examples pass that root to `compile_file()` for the same `package::` namespace.

## Headless compute

These examples run without a window or downloaded data.
They require `wesl`, `wgpu`, and NumPy at runtime.
Each command verifies its output and prints a result.
Their READMEs describe targeted Python and native WESL tests.

| Example | Run | WESL demonstrates |
| --- | --- | --- |
| [Residual RMSNorm](rmsnorm/README.md) | `pixi run -e gpu python -m examples.rmsnorm` | Fuse an ML normalization and specialize imported input logic. |
| [Stable compaction](compaction/README.md) | `pixi run -e gpu python -m examples.compaction` | Share a predicate across a hierarchical scan and scatter. |

## Verify

Run the SDF checks without opening a window:

```bash
pixi run -e examples python -m pytest tests/test_sdf.py -q
```

Compare the multiscale GPU results with NumPy:

```bash
pixi run -e examples python -m examples.multiscale.verify
```

Add `--image` to verify the full TIFF as well as synthetic inputs.
Synthetic checks do not download the TIFF.

## Shader tests

The [testing examples](testing/README.md) use pytest without an interactive window.
They cover compilation, native WESL tests, compute dispatch, and fragment images.
The tour also covers resources from Python fixtures, a texture shared between
compute and rendering, stored baselines, and an explicit failure demo.

```bash
pixi run -e testing python -m pytest examples/testing -v
```
