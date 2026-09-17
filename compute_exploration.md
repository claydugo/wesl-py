# Compute exploration

## Scope and sources

This work inspects tinygrad before implementing two compute examples.
The local checkout points to `ab447fd111d99fbc5fb27b70300bab80cd0d4c46`.
Its path is `/home/clay/git/upstream/tinygrad`.
Research covers the runtime, renderer, normalization, export code, and commit history.
The linked pull requests supply the authors' written reasoning.
The work installs no tinygrad, pydawn, or additional runtime package.

## What tinygrad does

The [WebGPU runtime](https://github.com/tinygrad/tinygrad/blob/ab447fd111d99fbc5fb27b70300bab80cd0d4c46/tinygrad/runtime/ops_webgpu.py)
creates a Dawn instance through generated C bindings.
It requests supported `ShaderF16` and `TimestampQuery` features.
It creates shader modules, storage and uniform bindings, compute pipelines, and passes.
The queue uploads inputs and copies outputs to buffers for mapping.
Optional timestamp queries surround a compute pass.
Python wrappers wait for Dawn futures to expose synchronous operations.

The [WGSL renderer](https://github.com/tinygrad/tinygrad/blob/ab447fd111d99fbc5fb27b70300bab80cd0d4c46/tinygrad/renderer/wgsl.py)
lowers tinygrad operations into WGSL.
It emits workgroup memory, barriers, invocation indices, and typed buffer accesses.
It packs small integer types into u32 words and uses atomic operations for packed stores.
It enables f16 when the generated kernel uses it.
The renderer and scheduler carry the ML logic.
Dawn executes the generated compute kernels.

The [RMSNorm implementation](https://github.com/tinygrad/tinygrad/blob/ab447fd111d99fbc5fb27b70300bab80cd0d4c46/tinygrad/nn/__init__.py#L281)
reduces squared inputs along the last axis, applies an inverse square root, and scales channels.
It calculates normalization in float32 before casting back to the input type.
This motivates a small fused residual RMSNorm example with a reduction in shared memory.

The [model exporter](https://github.com/tinygrad/tinygrad/blob/ab447fd111d99fbc5fb27b70300bab80cd0d4c46/extra/export_model.py#L115)
emits WGSL kernels and JavaScript that creates pipelines and dispatches them.
Its exported model uses GPU buffers for weights and intermediate tensors.
This separates Python compilation from browser execution.
WESL can compose shader sources without recreating tinygrad's tensor compiler.

## Commit and pull-request findings

| Commit and discussion | Written reasoning | Effect on these examples |
| --- | --- | --- |
| `133cacadd`, [#8646](https://github.com/tinygrad/tinygrad/pull/8646) | The author switches to Chrome's Dawn runtime for browser behavior and an f16 follow-up. The discussion identifies historical buffer-count and aliasing differences. Review asks to generate bindings inside tinygrad to remove Python dependencies. | Use current wgpu-py and core WebGPU operations. Keep bindings distinct and within default limits. Do not interpret historical complaints as current wgpu-py limitations. |
| `916d5e7f0`, [#8653](https://github.com/tinygrad/tinygrad/pull/8653) | The follow-up adds f16. Review finds a type mismatch in NaN handling and asks for transcendental tests. The author reports numerical differences between Vulkan and Metal. | Verify actual computations. Use finite f32 inputs and numerical tolerances. Probe f16 separately. |
| `01f7a4fad`, [#9274](https://github.com/tinygrad/tinygrad/pull/9274) | Browser Llama export uses int8 weights and float32 scales. It streams weight chunks to reduce memory overhead on phones. It also supports symbolic values in exported models. | Keep the ML example self-contained with synthetic data. Keep intermediate data on the GPU. |
| `35eb4d357`, [#10530](https://github.com/tinygrad/tinygrad/pull/10530) | A packed load inside a loop misses a renderer rewrite. The resulting atomic load reads the word without extracting the intended byte. | Test strided and partial workgroups. Check the intermediate scan results as well as final outputs. |
| `9169dcfb4`, [#10510](https://github.com/tinygrad/tinygrad/pull/10510) | The scheduler limits kernel inputs to backend capacity. The author also discusses obtaining limits without opening devices. | RMSNorm uses at most four storage bindings. Compaction uses at most three per pass. |

The pydawn [project description](https://github.com/wpmed92/pydawn)
distinguishes generated bindings from its small compute convenience API.
Its examples request f16 and timestamp features.
Current tinygrad uses its own generated bindings and Dawn binaries associated with pydawn.
It does not call pydawn's convenience API in `ops_webgpu.py`.
The local CI configuration also points to pydawn release binaries.

## wgpu-py capability check

Verification uses wgpu-py 0.32.0 on Linux with an NVIDIA GeForce RTX 4090.
The adapter uses Vulkan and reports driver 610.57.04.
The [wgpu-py API](https://wgpu-py.readthedocs.io/en/stable/wgpu.html)
exposes synchronous device creation, compute pipelines, buffers, and queue readback.
Its installed API also exposes timestamp writes in compute passes and query resolution.

An executed probe requests `shader-f16` and `timestamp-query` together.
It compiles WESL containing f16 multiplication and reads back the expected f32 value `3.0`.
Timestamp queries return two increasing u64 values around the same dispatch.
The examples exercise storage buffers, shared memory, barriers, overrides, multiple passes,
queue uploads, and readback through wgpu-py.
The checks find no missing core capability for these workloads.
This result applies to the checked operations and adapter.

One concrete gap concerns Dawn's experimental extensions to WGSL.
Pydawn's [matrix example](https://github.com/wpmed92/pydawn/blob/main/examples/experimental/subgroup_matrix.py)
uses `enable chromium_experimental_subgroup_matrix` and subgroup matrix operations.
The installed wgpu-py backend rejects that enable directive with
`unknown enable-extension` during shader creation.
The adapter advertises `cooperative-matrix`, but that does not make Dawn's syntax portable.

This check identifies a difference in accepted source for the experimental extension.
It does not establish whether other APIs expose equivalent hardware operations.
Neither example requires that extension.

## Implemented examples

### Fused residual RMSNorm

The [RMSNorm example](examples/rmsnorm/README.md) implements a transformer normalization primitive.
One workgroup reduces each row with 64 invocations.
Residual addition stays inside the loads used by reduction and output.
It does not allocate a combined tensor or a squared tensor.
The output uses learned-weight semantics with synthetic weights for the demonstration.

WESL imports keep input access and normalization separate from work distribution.
A feature removes residual access and its binding from the plain variant.
Numeric override IDs specialize width and epsilon after import renaming.
Native shader tests reuse the imported functions and receive buffers from Python fixtures.

The example prioritizes a readable kernel over a tuned transformer implementation.
It uses finite f32 inputs and assumes intermediate arithmetic stays within the f32 range.
Subnormal inputs or intermediate results can flush to zero on some backends.
The device buffer limits and dispatch limits constrain input sizes.

### Stable stream compaction

The [compaction example](examples/compaction/README.md) filters u32 values into a dense output.
A scan in shared memory computes positions within each block.
The same source scans block totals recursively.
Subsequent passes propagate offsets down the hierarchy and scatter selected values.
The default input contains 1,000,003 elements and needs three scan levels.
Intermediate arrays remain on the GPU until all passes finish.

The initial scan and scatter import the same predicate.
WESL selects either `< threshold` or `>= threshold` for both passes.
Internal scans strip the predicate and its override.
This gives source composition a correctness role: selection bits and scatter decisions agree.

The algorithm preserves order without global atomic appends.
Each local scan uses logarithmic strides and prioritizes clarity over optimal work count.
The output reserves input capacity, and device limits still apply.

Both examples use wesl, wgpu, and NumPy at runtime.
NumPy removes Python loops from input generation and reference calculations.
The drivers upload contiguous arrays and return NumPy arrays.
RMSNorm preserves a two-dimensional shape.
Compaction operates on a one-dimensional array.

The GPU environment now declares NumPy explicitly.
Pytest remains a test dependency.

## Verification

Run both examples without a display:

```bash
pixi run -e gpu python -m examples.rmsnorm
pixi run -e gpu python -m examples.compaction
```

The RMSNorm run verifies every output against a float64 NumPy reference.
RMSNorm differs from the reference by at most `4.29e-7` for 32 rows of width 1025.
Compaction selects 9,947 values and exactly matches the reference order.
Printed times include source compilation, uploads, dispatches, and readback.
They do not support a kernel speedup claim.

Compiler probes confirm that the plain RMSNorm variant removes binding one.
The internal scan variant also removes the threshold declaration.

Run only the new tests:

```bash
pixi run -e testing python -m pytest tests/test_rmsnorm.py tests/test_compaction.py examples/rmsnorm examples/compaction --wesl-gpu=required -q
```

The final targeted run passes 68 tests with no skips on the RTX 4090.
The same tests also pass on llvmpipe with LLVM 21.1.8 and Mesa 26.0.8.

RMSNorm tests cover widths 1, 63, 64, 65, and 1025, all-zero rows, signed weights,
three accepted epsilon values, both feature variants, driver execution, and invalid input dimensions.
NaN output sentinels detect missed writes.
Compaction tests compare local prefixes and block totals with NumPy.
Driver tests cover hierarchy boundaries, partial blocks, stable order, empty input,
all-selected and none-selected inputs, and threshold extremes.
Four native WESL cases demonstrate feature fixtures, resource fixtures, and overrides.

The driver checks include transposed RMSNorm inputs, sliced weights, and reversed compaction inputs.
They verify output dtypes and reject incorrect shapes or an incorrect compaction dtype.

Native tests also collect without GPU dependencies:

```bash
pixi run python -m pytest examples/rmsnorm examples/compaction --collect-only -q
```

This command collects four tests.
Targeted Ruff and ty checks pass for the new Python files.
Ruff also verifies formatting.
The existing artifact test job now selects both Python files and both native test directories.
The work does not change compiler APIs, testing APIs, or Git history.

## Adversarial reviews

Two independent `gpt-5.6-sol` agents review the implementation after the initial tests pass.
The first reviews shader correctness, numerical behavior, and resource lifetimes.
The second reviews test coverage, WESL composition, standalone execution, and report claims.
Both reviewers also verify compaction with `128**3 + 1` inputs.
That probe crosses into a fourth scan level and matches the exact stable reference.

The correctness review finds one numerical contract issue.
A subnormal epsilon can flush to zero on the GPU.
An all-zero RMSNorm row then produces NaNs.
The driver now requires epsilon to be at least `2**-126`, the smallest normal f32.
Two regression cases reject `2**-149` and verify an all-zero row at the accepted boundary.

The review also measures the effect of a subnormal square.
For input `1e-19`, weight one, and epsilon `2**-126`, the tested GPU returns about `0.92233717`.
A float64 reference for the rounded input gives about `0.67798645`.
The result is consistent with the GPU flushing the squared input to zero.
The README now states that subnormal inputs and intermediate results depend on the backend.
The example does not promise full IEEE-754 behavior for that range.

The coverage review finds two ambiguous descriptions.
The documentation now says “all-zero rows” and “both predicate variants.”
The review also verifies the small integration change to the artifact test job.

## Proposed third example

FFT-based phase correlation would estimate translation between two generated images.
The [scikit-image registration example](https://scikit-image.org/docs/stable/auto_examples/registration/plot_register_translation.html)
describes this use of correlation in Fourier space.
The proposed example would calculate forward FFTs, normalize the cross-power spectrum,
apply an inverse FFT, and locate the correlation peak on the GPU.
It would verify the recovered integer translation and intermediate arrays with NumPy.

WESL would share complex arithmetic and FFT butterfly code between both axes and transform directions.
Features would select forward or inverse transforms and row or column access.
This adds a spectral algorithm with multiple stages to the reduction and scan examples.
An initial version can use power-of-two image dimensions and integer translations.
It would run without a viewer or downloaded data.
This is a proposal, not an implemented example.
