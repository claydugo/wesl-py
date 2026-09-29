# Tests

Start with [the shader testing examples](examples/testing/README.md).
They follow one exposure adjustment through compilation, shader assertions,
compute dispatch, rendering, and snapshots.

## Compiler and Python API

| File | Contract |
| --- | --- |
| [test_check_syntax.py](test_check_syntax.py) | Parse source without resolving imports or checking types. Preserve filename labels. |
| [test_compile.py](test_compile.py) | Select features and declarations. Resolve imports. Apply options without changing stored settings. |
| [test_constants.py](test_constants.py) | Convert Python scalars to WESL constants. Reject lossy values. Scope each injection to one call. |
| [test_sources.py](test_sources.py) | Resolve files and virtual modules. Preserve source records and dependency scopes. |
| [test_resources.py](test_resources.py) | Load directories and ZIP resources. Select WESL over WGSL. Reject aliases and directory cycles. |
| [test_project.py](test_project.py) | Load manifests. Preserve dependency identity, scoped overrides, and manifest snapshots. |
| [test_diagnostics.py](test_diagnostics.py) | Preserve errors, byte spans, Unicode positions, and diagnostic ownership. |
| [test_threading.py](test_threading.py) | Match version metadata. Preserve the GIL state and import without GPU packages. Compile shader tests concurrently without mixing diagnostics. |
| [upstream.rs](upstream.rs) | Compare emitted WGSL directly with the pinned Rust compiler. |

Run selected compiler tests without GPU dependencies:

```bash
pixi run -e test python -m pytest tests/test_compile.py tests/test_sources.py -q
```

## Shader execution and pytest integration

| File | Contract |
| --- | --- |
| [test_compute.py](test_compute.py) | Execute injected constants in resource bindings, workgroup sizes, and typed expressions. |
| [test_shader_compilation.py](test_shader_compilation.py) | Transform native shader tests. Preserve error locations. Reject invalid assertion layouts without a GPU. |
| [test_testing.py](test_testing.py) | Run shader tests with options, project dependencies, buffer and texture bindings. Preserve resources across calls. |
| [test_shader_assertions.py](test_shader_assertions.py) | Preserve assertion values, component order, source locations, and counts through instrumentation. |
| [test_shader_workgroups.py](test_shader_workgroups.py) | Execute cooperative barriers. Record every invocation in three dimensions. Preserve failure counts and builtin arguments. |
| [test_shader_errors.py](test_shader_errors.py) | Render shader failures without requesting a device. Handle invalid spans and Unicode line breaks. |
| [test_pytest_plugin.py](test_pytest_plugin.py) | Collect shader tests. Apply fixtures, hooks, selection, project settings, and adapter policy. |
| [test_pytest_reporting.py](test_pytest_reporting.py) | Preserve locations, exception chains, notes, and JUnit reports in serial and xdist runs. |

Run the plugin contracts with GPU dependencies:

```bash
pixi run -e testing python -m pytest \
  tests/test_pytest_plugin.py tests/test_pytest_reporting.py -q
```

Use `-e testing-oldest` for the same command to verify pytest 8.2.
Use `-e test` for `test_pytest_plugin.py` to exercise missing dependencies.
These environments cover different contracts. A skip does not verify a contract.

The checked package-visibility case is a strict expected failure.
[The upstream notes](../docs/upstream.md#package-visibility-inside-named-packages)
describe the defect. An unexpected pass requires removal of the marker.

## Numerical examples

| File or directory | Reference or behavior |
| --- | --- |
| [test_compaction.py](examples/test_compaction.py) | NumPy selection through the public API. Cover empty inputs, recursion, and partial workgroups. |
| [test_rmsnorm.py](examples/test_rmsnorm.py) | Float64 normalization, residual inputs, strided arrays, and epsilon limits. |
| [test_operators.py](examples/convolution/test_operators.py) | Separate NumPy convolution, pooling, and resize references. Precision variants apply only to convolution. |
| [operators.wesl](examples/convolution/operators.wesl) and [test_activation.py](examples/convolution/test_activation.py) | Compare each operator with its reference. Check every output guard exactly. Test activation functions separately. |
| [test_multiscale.py](examples/test_multiscale.py) | NumPy Gaussian convolution on single pixels, impulses, and nonsquare images. |
| [test_multiscale_analysis.py](examples/test_multiscale_analysis.py) | Local covariance, distance to boundaries, polar coordinates, and profile reductions. |
| [test_sdf.py](examples/test_sdf.py) | Particle collisions, geometry changes, reset, and resize. |
| [test_example_render.py](examples/test_example_render.py) | Viewer modes, settings, and offscreen rendering. |
| [Native example tests](examples) and [SDF primitives](shaders/sdf.test.wesl) | Small shader contracts with imported functions and local fixture overrides. |

Numerical tests use fixed inputs or seeded generators and explicit tolerances.
The operator tests keep each NumPy reference beside its input cases.
They share GPU setup and a native assertion shader through `assert_operator`.
The shader checks output guards by index, including the padding for odd lengths.
The [snapshot example](examples/testing/test_snapshot.py) keeps two small float32
baselines. Its README explains how to inspect and update them.

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

Each case covers a distinct contract or boundary. Related assertions share a
compilation or dispatch. Stateful tests keep consecutive calls together when
they verify mutation, reloads, or resource reuse.
Vector failures use distinct components and place the mismatch in the last
component. The workgroup tests read every recorded coordinate back to Python.
Numerical tables select dimensions, precision, and feature flags together.
They retain algorithm boundaries without repeating every combination.

```bash
pixi run -e testing python -m pytest tests/examples/test_compaction.py -k recursive -v
pixi run -e testing python -m pytest tests/test_shader_errors.py -m 'not gpu' -v
```

The named cases use pytest's [parameter IDs](https://docs.pytest.org/en/stable/example/parametrize.html#different-options-for-test-ids).
The compiler tests describe WESL translation. GPU tests verify WGSL type checking
and execution. Successful compilation alone does not establish either property.
