# Tests

Start with [the shader testing examples](examples/testing/README.md).
They follow one exposure adjustment through compilation, shader assertions,
compute dispatch, rendering, and snapshots.

## Compiler and Python API

Run the Rust regression with `pixi run -e test cargo test --locked --test upstream`.
Run selected Python compiler tests without GPU dependencies:

```bash
pixi run -e test python -m pytest tests/test_compile.py tests/test_sources.py -q
```

## Shader execution and pytest integration

Run the plugin contracts with GPU dependencies:

```bash
pixi run -e testing python -m pytest \
  tests/test_pytest_plugin.py tests/test_pytest_reporting.py -q
```

Use `-e test` for `test_pytest_plugin.py` to exercise missing dependencies.
These environments cover different contracts. A skip does not verify a contract.

The checked package-visibility case is a strict expected failure.
[The upstream notes](../docs/upstream.md#package-visibility-inside-named-packages)
describe the defect. An unexpected pass requires removal of the marker.

## Numerical examples

Use fixed inputs or seeded generators and explicit tolerances.
See the [snapshot example](examples/testing/README.md#stored-baselines) for baselines.

Run the numerical file that covers a change:

```bash
pixi run -e testing python -m pytest tests/examples/test_compaction.py -v
```

Convolution tests require `shader-f16`.
These tests verify the available adapter. They do not establish numerical
agreement across GPU vendors.

## Case selection

Keep tests for behavior owned by these bindings, known regressions, and representative
example execution. Test each behavior at the layer that owns it. Do not repeat
upstream compiler semantics, pytest fixture mechanics, or an example kernel already
covered through its public API.

Choose distinct contracts and boundaries. Share compilation or dispatch between
related assertions. Keep consecutive calls together when testing mutation or reuse.

```bash
pixi run -e testing python -m pytest tests/examples/test_compaction.py -k recursive -v
pixi run -e testing python -m pytest tests/test_shader_errors.py -m 'not gpu' -v
```

Use pytest [parameter IDs](https://docs.pytest.org/en/stable/example/parametrize.html#different-options-for-test-ids)
for case selection. GPU tests establish runtime validity and execution.
