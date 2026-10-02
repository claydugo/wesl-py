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

[conftest.py](conftest.py) selects linear and clamped feature variants for Python
and native tests. `wesl_compiler` uses the repository root from `wesl.toml`.
`wesl_device` supplies the GPU device.

## Native tests and Python fixtures

Each `@test` function in [levels.test.wesl](shaders/levels.test.wesl) becomes a
pytest item. Conditional definitions select expected values for each feature variant.
`negative_values_clamp_to_zero` skips for the linear variant.

[Buffer tests](shaders/buffers/exposure.test.wesl) combine resources, overrides,
and features. Their [fixtures](shaders/buffers/conftest.py) provide inputs and NumPy
references through `wesl_resources`, then destroy the buffers after each test.
`wesl_constants` selects two gains, producing four cases with the feature variants.

```bash
pixi run -e testing python -m pytest tests/examples/testing/shaders/buffers -v
```

## Numerical checks

Compute tests cover single elements, full workgroups, and partial workgroups.
NaN output initialization detects unwritten elements.
Fragment tests compare square, wide, and tall images with NumPy.
The [pipeline test](test_pipeline.py) shares a texture between compute and rendering.
Tests release their GPU resources.

```bash
pixi run -e testing python -m pytest \
  tests/examples/testing/test_compute.py \
  tests/examples/testing/test_fragment.py \
  tests/examples/testing/test_pipeline.py -v
```

## Stored baselines

The `testing` environment includes `pytest-regressions`.
Baselines in `test_snapshot/` retain float32 values, including pixels outside
`[0, 1]`.
Comparisons use explicit tolerances and report differences by array index.

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

Both commands fail intentionally. `failure.xml` retains assertion details.

## Select cases and report results

Use normal pytest selection and reporting:

```bash
pixi run -e testing python -m pytest tests/examples/testing -k clamped -v
pixi run -e testing python -m pytest \
  tests/examples/testing/shaders/buffers -k double_gain -v
pixi run -e testing python -m pytest tests/examples/testing -m wesl -v
pixi run -e testing python -m pytest tests/examples/testing -n 2 --junitxml=results.xml
```
