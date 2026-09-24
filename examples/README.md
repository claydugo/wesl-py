# Examples

Run these commands from the repository root.
The Pixi environments below support Linux x86-64.
Graphics and compute examples require a WebGPU adapter.

| Example | Purpose | Run | Output |
| --- | --- | --- | --- |
| [SDF playground](sdf/README.md) | Share geometry between rendering and particle collisions. | `pixi run -e examples python -m examples.sdf` | Interactive scene |
| [Multiscale fluorescence](multiscale/README.md) | Share convolution across directions, scales, and implementations. | `pixi run -e examples python -m examples.multiscale` | Original and enhanced images |
| [Third-party imports](imports.py) | Fetch and import an upstream shader module. | `pixi run python examples/imports.py` | Compiled WGSL |
| [Residual RMSNorm](rmsnorm/README.md) | Select input logic and resource bindings through a feature flag. | `pixi run -e gpu python -m examples.rmsnorm` | Numerical verification |
| [Stable compaction (advanced)](compaction/README.md) | Share a predicate across a hierarchical scan and scatter. | `pixi run -e gpu python -m examples.compaction` | Exact verification |

Start with the SDF playground.
Change the surface while particles bounce off it.
One distance function defines the rendered surface and its collisions.
The tunnel feature compiles into both shaders from the same scene module.

Continue with multiscale fluorescence for image processing across multiple passes.
One convolution serves both image axes and both Gaussian scales.
A WESL feature selects the filter direction.
The viewer downloads and caches a sample microscopy TIFF on first use.
See [the sample image](imaging/README.md) for its source and channels.

The [imports example](imports.py) downloads one module from a pinned Lygia revision.
It registers a temporary directory with `dependencies={"lygia": directory}`.
The shader imports `lygia::math::mod289::mod289` and compiles to ordinary WGSL.
This example needs internet access but no GPU or optional dependencies:

```bash
pixi run python examples/imports.py
```

RMSNorm and compaction generate their own inputs and run without a window.
Start with RMSNorm for compute. Compaction adds a hierarchy of GPU passes.

The Pixi `examples` environment provides the graphics and image dependencies.
The repository's `wesl.toml` sets `examples/` as the shader root for editor tooling.
The examples pass that root to `compile_file()` for the same `package::` namespace.

Each example's README includes its verification command.

## Shader tests

The [testing examples](../tests/examples/testing/README.md) use pytest without an interactive window.
They cover compilation, native WESL tests, compute dispatch, and fragment images.
The tour also covers resources from Python fixtures, a texture shared between
compute and rendering, stored baselines, and an explicit failure demo.

```bash
pixi run -e testing python -m pytest tests/examples/testing -v
```
