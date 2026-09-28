# Shader testing

Follow one exposure adjustment through compilation, native WESL assertions,
compute dispatch, rendering, and snapshots. Python fixtures select feature flags
and supply test data. NumPy provides numerical references.

Run the examples from the repository root:

```bash
pixi run -e testing python -m pytest tests/examples/testing -v
```

Run the compilation tests and collect the native tests without GPU dependencies:

```bash
pixi run -e test python -m pytest tests/examples/testing/test_compilation.py -v
pixi run -e test python -m pytest \
  tests/examples/testing/shaders --collect-only -q
```

The `wesl_compiler` fixture reads the shared compilation configuration.
The `wesl_device` fixture supplies a WebGPU device.
The repository's `wesl.toml` sets the repository as the package root.
Calls to `wesl_compiler.compile_file()` use paths such as
`tests/examples/testing/shaders/combine.wesl` relative to that root.

The `wesl_features` fixture selects clamped and unclamped implementations.
Pytest applies both parameter values to Python compilation tests, compute tests,
fragment tests, and native WESL tests.
The default `wesl_options` and `wesl_test_options` fixtures use these features.

| Test | Behavior |
| --- | --- |
| [Native tests](shaders/levels.test.wesl) | Import a shared function and select conditional test definitions. |
| [Native buffers](shaders/buffers/exposure.test.wesl) | Combine native buffers, pipeline overrides, and feature flags through Python fixtures. |
| [Compilation tests](test_compilation.py) | Compile imports and verify an expected error without a GPU. |
| [Compute test](test_compute.py) | Verify a single element, a full workgroup, and partial workgroups with two input buffers and two output buffers. |
| [Fragment test](test_fragment.py) | Bind a texture, sampler, and uniform buffer. Compare square, wide, and tall images with NumPy. |
| [Two passes](test_pipeline.py) | Write a storage texture in compute, then sample it in a fragment shader. |
| [Snapshot test](test_snapshot.py) | Compare float32 pixels with a stored baseline for each feature value. |
| [Failure demo](shaders/failure_demo.wesl) | Inspect an assertion failure in the terminal and in a JUnit report. Run this file explicitly. |

## Native tests and Python fixtures

Start with [levels.test.wesl](shaders/levels.test.wesl).
Each `@test` function becomes a pytest item.
The root [conftest.py](conftest.py) selects the `linear` and `clamped` variants.
Conditional definitions give each variant its own expected result.
The `negative_values_clamp_to_zero` test skips for the linear variant.

Next, run the tests that use Python resources:

```bash
pixi run -e testing python -m pytest tests/examples/testing/shaders/buffers -v
```

The local [conftest.py](shaders/buffers/conftest.py) supplies two buffers through
`wesl_resources`. One contains input values. The other contains the NumPy reference.
The fixture yields native bind-group entries and destroys its buffers after each
test.

Its `wesl_constants` fixture selects two values for the shader's `gain` override.
These values combine with both feature variants to produce four named cases.
The shader compares every input with its reference through `expectNear()`.
These fixture overrides apply only to this directory.

## Numerical checks

The fragment test computes its expected image from the input pixels.
It does not maintain snapshot files.
Each fixture or Python test creates and releases its resources.

The compute cases contain 1, 4, and 9 elements with four invocations per
workgroup. Output buffers start with NaNs so an unwritten element fails the test.
The fragment cases use images of size 2 by 2, 4 by 2, and 2 by 4.
Run only these numerical checks with:

```bash
pixi run -e testing python -m pytest \
  tests/examples/testing/test_compute.py \
  tests/examples/testing/test_fragment.py -v
```

The [pipeline test](test_pipeline.py) joins compute and rendering:

```bash
pixi run -e testing python -m pytest tests/examples/testing/test_pipeline.py -v
```

The test creates a texture and binds it in both passes.
Compute writes an exposure gradient. The fragment shader samples that texture
and applies a tint. The intermediate image stays on the GPU.
The test compares the final image with NumPy and releases resources through `ExitStack`.
This demonstrates ownership when a test supplies a GPU resource.

## Stored baselines

The snapshot test uses the optional `pytest-regressions` package.
The repository's `testing` environment includes it.
Baselines in `test_snapshot/` preserve float32 values, including values outside
the range from zero to one. The fixture compares each value with explicit
relative and absolute tolerances. It reports differences by array index.

Update only the selected snapshots after an intentional change:

```bash
pixi run -e testing python -m pytest tests/examples/testing/test_snapshot.py --force-regen
pixi run -e testing python -m pytest tests/examples/testing/test_snapshot.py
```

The first command updates mismatched baselines and fails those tests.
Review the changed `.npz` files, then run the second command to verify them.
Load the `pixels` array with `numpy.load()` to inspect the stored values.
Keep the baseline files in version control.

## Inspect a failure

The [failure demo](shaders/failure_demo.wesl) uses a deliberately incorrect
reference value. Its filename does not end in `.test.wesl`.
Select the file explicitly to see the shader location, actual value, expected
value and assertion count:

```bash
pixi run -e testing python -m pytest \
  tests/examples/testing/shaders/failure_demo.wesl \
  -k clamped -v --junitxml=failure.xml
pixi run -e testing python -m pytest \
  tests/examples/testing/shaders/failure_demo.wesl -k clamped --tb=line
```

Both commands fail intentionally. The first command also records the assertion
details in `failure.xml`. The second command shows concise terminal output.

## Select cases and report results

Use normal pytest selection and reporting:

```bash
pixi run -e testing python -m pytest tests/examples/testing -k clamped -v
pixi run -e testing python -m pytest \
  tests/examples/testing/shaders/buffers -k double_gain -v
pixi run -e testing python -m pytest tests/examples/testing -m wesl -v
pixi run -e testing python -m pytest tests/examples/testing -n 2 --junitxml=results.xml
```
