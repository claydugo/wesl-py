# Tests

Start with [the shader testing examples](examples/testing/README.md).

## Compiler and Python API

Run the Rust regression with `pixi run -e test cargo test --locked --test upstream`.
Run selected Python compiler tests without GPU dependencies:

```bash
pixi run -e test python -m pytest tests/test_compile.py tests/test_sources.py -q
```

The Rust integration test also runs the pinned shared WESL cases through the
Python compiler API. See [fixture provenance](wesl-testsuite/README.md).

Run CPU execution and assertion tests without GPU dependencies:

```bash
pixi run -e test python -m pytest tests/test_cpu.py tests/test_testing.py \
  tests/test_shader_assertions.py tests/test_shader_errors.py -m 'not gpu' -q
```

Pure assertion cases also run on GPU in the `testing` environment.

## Runner self-tests

The [runner](runner) directory tests the shader runner through its own pytest
plugin. The `*.test.wesl` files cover assertions in every scope and control-flow
form, workgroup builtins with pipeline overrides, and resource bindings with
explicit layouts. Fixtures in each directory supply overrides, resources,
and layouts. `test_cpu.py` runs the assertion file on the CPU interpreter as well.

```bash
pixi run -e testing python -m pytest tests/runner -v
```

Python tests keep the contracts that a passing shader cannot show: failure
values, failure counts, diagnostic locations, and rejected configurations.

## Shader execution and pytest integration

Run the plugin contracts with GPU dependencies:

```bash
pixi run -e testing python -m pytest \
  tests/test_pytest_plugin.py tests/test_pytest_reporting.py -q
```

Use `-e test` for `test_pytest_plugin.py` to exercise missing dependencies.
A skip does not verify a contract.

The checked package-visibility case in `test_sources.py` is a strict expected
failure. wesl-rs treats imports within named packages as public.
An unexpected pass requires removal of the marker.

## Native shader tests

The `*.test.wesl` files under [examples](examples) test the example shader
libraries with wgsl-test. Each test runs one workgroup. Each invocation checks
one input, so one test covers a range of inputs.

The tests check properties instead of single values.
Each [example README](../examples/README.md) describes the properties its tests
check.

[random.wesl](examples/random.wesl) gives each invocation reproducible inputs.
It is the PCG hash of Jarzynski and Olano, and it maps a seed to `[0, 1)` with
24-bit resolution. Each invocation uses its own seed range, such as `lane * 8u`
to `lane * 8u + 7u` for eight values.
Each property test also checks one or two exact values.
Fixtures in each directory's `conftest.py` supply buffers, overrides, and
feature variants. Keep tests that need different bindings in separate
directories.

wgpu-native 29 does not zero-initialize workgroup variables, so they can keep
values from earlier dispatches. Write every workgroup element before you read it.
Use `u32` elements instead of `bool` in workgroup arrays: cross-invocation
reads of `bool` arrays return `false` on some NVIDIA drivers.

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
for case selection.
