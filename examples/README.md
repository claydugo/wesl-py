# Examples

Run these commands from the repository root.
Graphics and compute examples require a WebGPU adapter.

| Example | Purpose | Run | Output |
| --- | --- | --- | --- |
| [SDF playground](sdf/README.md) | Share geometry between rendering and particle collisions. | `pixi run -e examples python -m examples.sdf` | Interactive scene |
| [Multiscale fluorescence](multiscale/README.md) | Share convolution across directions, scales, and implementations. | `pixi run -e examples python -m examples.multiscale` | Original and enhanced images |
| [Parallel sorting](sorting/README.md) | Substitute a key module into three sort kernels and a bar renderer. | `pixi run -e examples python -m examples.sorting` | Animated sorts |
| [Optimizer comparison](optimizers/README.md) | Share a network between training and rendering, substitute update rules, and reload shaders live. | `pixi run -e examples python -m examples.optimizers` | Live decision boundaries |
| [Third-party imports](imports.py) | Fetch and import an upstream shader module. Needs internet access but no GPU. | `pixi run python examples/imports.py` | Compiled WGSL |
| [Residual RMSNorm](rmsnorm/README.md) | Select input logic and resource bindings through a feature flag. | `pixi run -e gpu python -m examples.rmsnorm` | Numerical verification |
| [Stable compaction (advanced)](compaction/README.md) | Share a predicate across a hierarchical scan and scatter. | `pixi run -e gpu python -m examples.compaction` | Exact verification |
| [FP16 convolution and pooling](convolution/README.md) | Reuse compute operators in parameterized native tests. Needs `shader-f16`. | `pixi run -e gpu python -m examples.convolution` | Numerical verification |

Start with SDF for graphics or RMSNorm for compute.

Examples and tests resolve `package::examples` from the repository root.

## Shader tests

The [testing examples](../tests/examples/testing/README.md) cover compilation,
WESL assertions, compute, rendering, and snapshots without a window.
