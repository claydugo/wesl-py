# Examples

Run these commands from the repository root.
The Pixi environments support Linux x86-64, macOS arm64, and Windows x86-64.
Graphics and compute examples require a WebGPU adapter.

| Example | Purpose | Run | Output |
| --- | --- | --- | --- |
| [SDF playground](sdf/README.md) | Share geometry between rendering and particle collisions. | `pixi run -e examples python -m examples.sdf` | Interactive scene |
| [Multiscale fluorescence](multiscale/README.md) | Share convolution across directions, scales, and implementations. | `pixi run -e examples python -m examples.multiscale` | Original and enhanced images |
| [Third-party imports](imports.py) | Fetch and import an upstream shader module. | `pixi run python examples/imports.py` | Compiled WGSL |
| [Residual RMSNorm](rmsnorm/README.md) | Select input logic and resource bindings through a feature flag. | `pixi run -e gpu python -m examples.rmsnorm` | Numerical verification |
| [Stable compaction (advanced)](compaction/README.md) | Share a predicate across a hierarchical scan and scatter. | `pixi run -e gpu python -m examples.compaction` | Exact verification |

Start with SDF for graphics or RMSNorm for compute.
RMSNorm and compaction generate their inputs and need no window.

Multiscale fluorescence downloads and caches a microscopy TIFF on first use.
See [the sample image](imaging/README.md) for its source and channels.

The [imports example](imports.py) downloads one module from a pinned Lygia revision.
It registers a temporary directory with `dependencies={"lygia": directory}`.
It needs internet access but no GPU or optional dependencies.

The Pixi `examples` environment provides the graphics and image dependencies.
Examples and tests use the repository root for imports through `package::examples`.
Both `wesl.toml` and calls to `compile_file()` set this root.

Each example's README includes its verification command.

## Shader tests

The [testing examples](../tests/examples/testing/README.md) cover compilation,
WESL assertions, compute, rendering, and snapshots without a window.
They include Python fixtures, shared textures, and a failure demo.

```bash
pixi run -e testing python -m pytest tests/examples/testing -v
```

[FP16 convolution and pooling](convolution/README.md) demonstrates reusable
compute operators and parameterized native WESL tests. It uses synthetic inputs
and requires an adapter with `shader-f16`.
