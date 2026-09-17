# Fused residual RMSNorm

```bash
pixi run -e gpu python -m examples.rmsnorm
```

Normalize 32 token rows with 1025 channels per row.
The example generates inputs and verifies every output with a NumPy reference.
It requires `wesl`, `wgpu`, and NumPy.
It does not open a window or download weights.

For each row, the shader computes:

```text
combined = values + residual
output = combined * inverse_sqrt(mean(combined * combined) + epsilon) * weights
```

Transformer blocks use residual addition and RMSNorm.
This example uses synthetic weights to demonstrate the operation.

Start with [normalize.wesl](normalize.wesl).
One workgroup handles each row.
Its 64 invocations accumulate strided columns and reduce squares in shared memory.
All invocations reach every barrier, including those with no input columns.
The output pass repeats the load without allocating an intermediate residual tensor.

[input.wesl](input.wesl) owns the input bindings and residual addition.
The `residual` WESL feature selects plain or residual RMSNorm.
Both loads in the kernel use that module.
The compiler removes the residual binding for the plain variant.

[normalization.wesl](normalization.wesl) owns the scale calculation.
Width and epsilon are pipeline overrides with numeric IDs.
Those IDs let Python specialize imported declarations after WESL renames them.
[compute.py](compute.py) passes the feature and constants to the compiler and pipeline.
It uses the same `examples/` package root as the other examples.

Inputs use a nonempty array with shape `(rows, channels)`.
Weights use a one-dimensional array with one value per channel.
Residuals have the same shape as the input.
Uploads convert arrays to contiguous float32 storage.
The result is a float32 array with the same shape as the input.

Use finite f32 inputs and keep intermediate arithmetic within the f32 range.
Epsilon must fit f32 and be at least `2**-126`, the smallest normal f32.
This prevents devices from flushing epsilon to zero for an all-zero row.

Subnormal inputs or intermediate results can flush to zero.
Results in that range depend on the backend.
Each row requires one workgroup and remains subject to device dispatch limits.

The example uses core f32 operations without optional GPU features.
The printed time includes compilation, upload, execution, and readback.
It is not a kernel benchmark.

## Tests

```bash
pixi run -e testing python -m pytest tests/test_rmsnorm.py examples/rmsnorm --wesl-gpu=required -q
```

`ShaderRunner.compute()` compares the shader with a float64 NumPy reference.
Widths 1, 63, 64, 65, and 1025 cover idle invocations and strided tails.
The kernel cases include all-zero rows, signed weights, and both feature variants.
They exercise epsilon values of `1e-6` and `0.25`.
Output buffers start with NaNs to detect missed writes.

Separate tests exercise the Python driver and invalid dimensions.
They also verify transposed inputs and sliced weights.
Boundary tests reject a subnormal epsilon and accept the smallest normal f32 epsilon.

Pytest discovers [test_row.wesl](test_row.wesl) as native shader tests.
[conftest.py](conftest.py) supplies feature variants, buffers, and pipeline constants.
The tests import the same input and scale functions as the compute kernel.

Collect the native tests without GPU dependencies:

```bash
pixi run python -m pytest examples/rmsnorm --collect-only -q
```
