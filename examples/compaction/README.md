# Stable stream compaction

This advanced example schedules a hierarchy of GPU passes.
Start with [RMSNorm](../rmsnorm/README.md) for a single compute kernel.

Run from the repository root on Linux x86-64:

```bash
pixi run -e gpu python -m examples.compaction
```

Filter 1,000,003 generated u32 values and preserve their input order.
The example checks the entire result against NumPy boolean indexing.
It does not need a window or an external dataset.

Compaction turns a sparse selection into a dense buffer.
It can collect threshold detections, active particles, or work for a later kernel.
Atomic appends can produce different orders between runs.
This example gives each selected value a unique output position with a prefix scan.

1. [scan.wesl](scan.wesl) converts values to selection bits and scans blocks of 128.
   It writes an exclusive prefix for each element and a total for each block.
2. The same shader scans the block totals with `select_values=False`.
   [compute.py](compute.py) repeats this step until one block remains.
3. [offsets.wesl](offsets.wesl) adds parent prefixes from the top level down.
4. [scatter.wesl](scatter.wesl) writes selected values to their prefix positions.

All intermediate buffers stay on the GPU.
Each level uses a separate compute pass in one command submission.
Only the final count and selected values return to Python.
Partial blocks load zero for missing elements and still execute every barrier.
The local scan uses shared memory and logarithmic strides.
It prioritizes readable code over a tuned scan implementation.

WESL shares [predicate.wesl](predicate.wesl) between the initial scan and scatter.
The `keep_below` feature selects `< threshold` or `>= threshold`.
Both passes use the same rule, including equality at the boundary.
Threshold uses numeric override ID zero, which survives import renaming.
The internal scans compile without the predicate or threshold.

Call `compact(device, values, threshold=500, keep_below=False)` to use other inputs.
Values use a one-dimensional NumPy array with dtype `uint32`.
Uploads make noncontiguous views contiguous.
The result is a one-dimensional `uint32` array. Threshold must fit u32.

Empty input returns an empty array without a dispatch.
An output buffer has capacity for every input element.
Input size remains subject to the device buffer limits and dispatch limits.
The first level needs `ceil(element_count / 128)` workgroups on the x axis.

## Tests

```bash
pixi run -e testing python -m pytest tests/examples/test_compaction.py tests/examples/compaction -q
```

The tests compare prefixes and selected values with NumPy across hierarchy boundaries.

Pytest discovers [predicate.test.wesl](../../tests/examples/compaction/predicate.test.wesl) as native shader tests.
[conftest.py](../../tests/examples/compaction/conftest.py) supplies both predicate variants and the threshold override.

Collect the native tests without GPU dependencies:

```bash
pixi run -e test python -m pytest tests/examples/compaction --collect-only -q
```
