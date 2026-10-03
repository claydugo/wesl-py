# Shader tests

`wesl-py` provides a pytest plugin and bundles assertion shaders from the WESL project's
[wgsl-test](https://github.com/webgpu-tools/wesl-js/tree/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test).
Pytest loads the plugin automatically and collects `*.test.wesl` files.
The `testing` extra installs pytest and wgpu-py.
The base package can collect tests when pytest is installed.
Compilation and collection need no GPU. Execution requires a WebGPU adapter.
This requirement applies to collected WESL tests and the GPU runner.
Python tests can use the CPU interpreter without an adapter.

Use the [checkout setup](../CONTRIBUTING.md#set-up-a-checkout) and `testing`
environment. No `conftest.py` is required.

## WESL tests

Each `@test` function becomes a pytest item.
Save this as `shaders/math.test.wesl`:

```wesl
import wgsl_test::expectEq;

@test
fn addition() {
    expectEq(3u + 4u, 7u);
}
```

```bash
pixi run -e testing python -m pytest shaders/math.test.wesl::addition
pixi run -e testing python -m pytest shaders --collect-only
pixi run -e testing python -m pytest shaders -k addition --junitxml=results.xml
```

A test function has no return value or shader stage attribute.
Without `@workgroup_size`, the runner uses one compute invocation.
A function with no assertions passes when execution completes.

Add `@workgroup_size` and builtin parameters to test cooperative code:

```wesl
import wgsl_test::expectEq;

var<workgroup> values: array<u32, 32>;

@test @workgroup_size(32)
fn neighbors(@builtin(local_invocation_index) lane: u32) {
    values[lane] = lane + 1u;
    workgroupBarrier();
    expectEq(values[(lane + 1u) % 32u], (lane + 1u) % 32u + 1u);
}
```

The runner dispatches one workgroup. All parameters must have a `@builtin` attribute.
Workgroup dimensions can use constants or overrides from `wesl_constants`.
The test can use shared memory, barriers, and enabled subgroup operations.
The `wesl_device` fixture must enable any device features that the shader requires.
Use Python tests for multiple workgroups or fragment shaders.

Counts combine all invocations. Reports identify one failing invocation and its
first failure; GPU scheduling can change which invocation appears.
Early returns still record results. Passing invocations cannot overwrite a failure.

Imports resolve through the existing WESL compiler.
Each test uses the nearest ancestor `wesl.toml` for its shader root.
Register dependency directories through the `wesl_dependencies` fixture.
Use `Compiler.from_project()` to load these settings outside pytest.
Without a manifest, the default package root is the test file's parent directory.
Configure a project root in `wesl.toml`:

```toml
edition = "2026_pre"
root = "shaders"
```

An explicit pytest setting overrides the manifest's root.
This path is relative to pytest's root directory:

```toml
[tool.pytest.ini_options]
wesl_root = "shaders"
```

Keep collected files inside this directory. Their paths determine their
`package::` module names. Dots in a test filename's stem become `_` characters.
Pytest also collects any `.wesl` file that you select explicitly.

`@if`, `@elif`, and `@else` select implementations with `wesl_features`.
Collection includes conditional tests and all fixture parameter variants.
Pytest runs fixture setup before the runner checks WESL conditions.
A disabled test reports a skip during the call phase.
GPU and resource fixtures can run before this skip. Fixture failures remain errors,
even when WESL conditions disable the test.
Multiple conditional definitions of one name produce one item.

### Assertions

Import assertions from `wgsl_test`. The bundled
[upstream shaders](https://github.com/webgpu-tools/wesl-js/tree/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders)
register automatically. Upstream `lib.wesl` becomes `package.wesl` with attribution
and public visibility modifiers. Instrumentation captures typed values, locations,
counts, and completion without changing packaged files.

WESL derives the result buffer layout from the compiled result type and decodes
the buffer. Custom result modules must retain the upstream field names and types.
Arbitrary custom layouts are unsupported. The binding evaluates named and
transitive layout constants. It rejects zero alignment and
cyclic result types. See [integration requirements](upstream.md#local-integration-requirements).

The test runner uses one shared `wgsl_test` package for assertion results.
Shader tests reject scoped overrides such as `alpha/wgsl_test` in `dependencies`
or `modules`. Normal compilation accepts these overrides.

Other libraries use `dependencies` or the `wesl_dependencies` fixture:
Put the fixture in `conftest.py` and replace the path with your library directory:

```python
from pathlib import Path

import pytest


@pytest.fixture
def wesl_dependencies():
    return {"library": Path("path/to/library")}
```

See [library directories](api.md#compile-strings-and-files) and the
[imports example](../examples/imports.py) for registration outside pytest.

- `expect(condition)`: Boolean is true
- `expectEq(actual, expected)`: Exact `u32` equality
- `expectNear(actual, expected)`: `f32` comparison with relative tolerance
  `0.001` and absolute tolerance `0.000001`
- `expectWithin(actual, expected, relative, absolute)`: `f32` comparison with
  explicit tolerances
- `expectUlp(actual, expected, maximum)`: At most `maximum` representable `f32`
  steps apart

The floating-point functions also have `Vec2`, `Vec3`, and `Vec4` suffixes.
For example, `expectNearVec3` accepts two `vec3f` values.
Each component must pass. Near comparisons use
`abs(actual - expected) <= max(absolute, relative * max(abs(actual), abs(expected)))`.
Use finite operands and tolerances. The upstream assertions can accept NaN and
infinity. GPU floating-point behavior still applies.

Failures underline the first failed assertion and show actual and expected values
with failure and assertion counts. Paths are relative to the project root.

Scalar values retain their types. Unsigned integers retain all 32 bits.
Vectors retain their dimensions, including zero components.
Boolean assertions report `false` and `true`.
Use `expect(actual == expected)` to compare signed integers.

Assertions continue after failure. Imported failures point to the helper's source.
Diagnostics use plain text; pytest controls terminal presentation.

## Python tests

Use `run_test_cpu` for shader calculations that need no GPU resources:

```python
from wesl.testing import run_test_cpu


def test_addition():
    run_test_cpu(
        {
            "package::main": """
                @test fn addition() {
                    wgsl_test::expectEq(3u + 4u, 7u);
                }
            """,
        },
        "addition",
    )
```

Run this test in the `test` environment. It needs neither wgpu-py nor an adapter.
The CPU runner supports imports, feature flags, private variables, and override
constants. It uses the same assertions and failure diagnostics as `run_test`.
Each call starts with fresh shader state.

Override conversion follows WebGPU rules. Integer values truncate toward zero.
Values outside the destination type's range raise an error.
Numeric overrides reject NaN and infinity. Boolean overrides convert NaN to false.

CPU tests cannot use user buffers, textures, samplers, workgroup variables,
builtin parameters, or an explicit `@workgroup_size`.
The upstream interpreter is experimental and supports only some WGSL operations.
Keep GPU tests for resource bindings, cooperative execution, and GPU arithmetic.
`run_test_cpu` does not select a backend for collected `*.test.wesl` files.

The `wesl_compiler` fixture shares `wesl_features`, `wesl_modules`, `wesl_dependencies`,
`wesl_filenames`, and `wesl_root_directory` with native WESL tests.
It returns a `wesl.Compiler` and does not request a GPU.
Parametrizing these fixtures also parametrizes Python tests that use the compiler.
`wesl_options` configures this compiler. `wesl_test_options` configures native tests.

Call `wesl_compiler.compile_source(source)` for an inline shader.
Call `wesl_compiler.compile_file("blur.wesl")` for a shader file.
Relative file paths start at `wesl_root_directory`.
Absolute paths must stay inside that directory.

Compile with `wesl.compile`, `compile_source`, or `compile_file` when a test
needs separate configuration. Pass `CompileResult.wgsl` to wgpu-py.
For buffer computations, wgpu-py provides `compute_with_buffers`:
Save this as `test_compute.py`:

```python
from array import array
from wgpu.utils.compute import compute_with_buffers


def test_double(wesl_compiler):
    shader = wesl_compiler.compile_source("""
        @group(0) @binding(0) var<storage, read_write> values: array<f32>;
        @compute @workgroup_size(1)
        fn main(@builtin(global_invocation_id) invocation: vec3u) {
            values[invocation.x] *= 2.0;
        }
    """)
    output = compute_with_buffers(
        {0: array("f", [1, 2, 3])},
        {0: (3, "f")},
        shader.wgsl,
        n=3,
    )
    assert output[0].tolist() == [2.0, 4.0, 6.0]
```

This helper uses wgpu-py's default device and the `main` entry point.
Its `n` argument counts workgroups. `constants` sets override values in the pipeline.
Use the device API directly for other entry points, bind groups, textures, or samplers.
Use pytest parametrization for input and feature matrices.

See the [executable examples](../tests/examples/testing/README.md) for shared
feature flags, compute dispatch, texture sampling, image comparisons, and
compilation failures.

### Resources for WESL tests

`wesl_resources` maps group numbers to wgpu-py bind-group entries.
Resources can be buffer dictionaries (with optional `offset` and `size`), texture
views, or samplers. Save this as `shaders/buffers/conftest.py`:

```python
from struct import pack

import pytest
import wgpu


@pytest.fixture
def wesl_resources(wesl_device):
    buffer = wesl_device.create_buffer_with_data(
        data=pack("<3f", 1, 2, 3),
        usage=wgpu.BufferUsage.STORAGE,
    )
    try:
        yield {0: [{"binding": 0, "resource": {"buffer": buffer}}]}
    finally:
        buffer.destroy()
```

Save the test shader as `shaders/buffers/values.test.wesl`:

```wesl
@group(0) @binding(0) var<storage, read> values: array<f32>;

@test
fn middle_value() {
    wgsl_test::expectNear(values[1], 2.0);
}
```

The runner uses automatic layouts by default.
Supply the bindings used by the selected test, including imported functions.
Unused extra bindings and missing resources produce WebGPU validation errors.
The runner selects the first unused binding in group 0 from the supplied entries.
It adds its result buffer there and supplies empty groups between occupied groups.
It copies the group lists before adding its binding.

To set explicit layouts, override `wesl_layouts` or pass `layouts` to `run_test()`.
Map each group number to a list of wgpu-py layout entries.
Supply a layout entry for every application binding.
The runner adds its result buffer to group 0. It avoids bindings from both mappings
and copies the layout lists before adding its entry.

The runner does not support dynamic buffer offsets.
Buffer layouts must use `has_dynamic_offset=False`, which is the default.
Set a fixed `offset` in the resource's buffer binding when needed.

For example, use these entries for a float32 texture and a nearest sampler in
group 2:

```python
@pytest.fixture
def wesl_layouts():
    return {
        2: [
            {
                "binding": 0,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "texture": {"sample_type": "unfilterable-float"},
            },
            {
                "binding": 1,
                "visibility": wgpu.ShaderStage.COMPUTE,
                "sampler": {"type": "non-filtering"},
            },
        ]
    }
```

These layouts allow nearest sampling of `r32float`, `rg32float`, and `rgba32float`
without the `float32-filterable` device feature. Automatic layouts require that
feature when a shader uses these textures with a sampler.

Fixtures own application resources and teardown. The runner reads and destroys
only its result buffer, including on failure. Read application outputs through the
device queue. NumPy is optional for fixtures and readback.

Arrays must match the shader's binary layout and the texture's format.
Specify NumPy dtypes explicitly when using NumPy. Represent struct offsets,
array strides, and padding explicitly. wgpu-py does not infer them from WGSL types.

The `wesl_constants` fixture sets override values for collected WESL tests.
Python calls to `run_test()` pass resources and constants explicitly.

### Fragment tests

Use `wesl_device` to create a render pipeline from compiled WGSL.
The test sets attachments, formats, and readback layout.
The [fragment example](../tests/examples/testing/test_fragment.py) renders a texture
with a sampler and a uniform buffer. The
[pipeline example](../tests/examples/testing/test_pipeline.py) shares a texture
between compute and rendering.

### Image snapshots

Use the optional [pytest-regressions](https://pytest-regressions.readthedocs.io/en/latest/api.html#ndarrays-regression)
plugin to compare arrays with stored baselines. Add it to your Pixi environment:

```bash
pixi add numpy pytest-regressions
```

Request its `ndarrays_regression` fixture in a Python test.
Pass the pixels read from the render target:

```python
ndarrays_regression.check(
    {"pixels": pixels},
    default_tolerance={"rtol": 1e-6, "atol": 1e-7},
)
```

The fixture stores float32 `.npz` baselines beside the test, including values outside
`[0, 1]`. Pytest IDs distinguish parameter variants.
Choose tolerances for the shader and adapters. The first run creates missing baselines
and fails for review. Keep approved baselines in version control.

Use `--force-regen` with a selected test to update a mismatched baseline.
The update fails that test; run it again to verify the new baseline.
See the [snapshot example](../tests/examples/testing/test_snapshot.py) and its
[update commands](../tests/examples/testing/README.md).

Comparisons report differences by array index. Native `@snapshot` is unsupported.

## Fixtures and pytest behavior

The plugin provides these fixtures:

- `wesl_device`: One device per pytest session or xdist worker
- `wesl_compiler`: A `Compiler` using the shared compilation fixtures
- `wesl_resources`: Empty mapping of groups to bind-group entries
- `wesl_layouts`: `None` for automatic layouts, or a mapping of groups to layout
  entries
- `wesl_modules`: Empty mapping of additional WESL modules
- `wesl_dependencies`: Explicit mapping of package names to shader directories.
  Defaults to an empty mapping
- `wesl_filenames`: Empty mapping of module names to source filenames
- `wesl_features`: Default `Features`, shared by both options fixtures
- `wesl_options`: `CompileOptions` for `wesl_compiler`, using `wesl_features`
- `wesl_test_options`: `TestOptions` for native WESL tests, using
  `wesl_features`
- `wesl_constants`: Empty mapping of WGSL overrides
- `wesl_root_directory`: Explicit `wesl_root`, manifest root, or test file's parent

Override fixtures in `conftest.py`. Parametrized fixtures produce separate shader
test cases with normal pytest IDs. Use `pytest_collection_modifyitems` to attach
skip, xfail, or project markers. Collected WESL tests carry `wesl` and `gpu` markers.

Python compilation and native shader tests use the same `wesl_dependencies` mapping.
Manifest dependency entries configure editors. They do not register Python imports.

The `gpu` marker includes hardware and software adapters.
A software adapter runs shaders on the CPU.
Use `-m 'not gpu'` to select tests that need no WebGPU runtime.

Use normal pytest selection and reports. Install pytest-xdist to use `-n`.

Use `--tb=line` for concise shader failures.
JUnit reports retain the shader location and failure message in this mode.
Pytest can repeat plain-text failure messages in this mode.
Use `--tb=no` to hide details.
Use `--tb=native` or `--full-trace` to inspect Python execution.

`wesl_constants` uses override names from the test module. For declarations with
`@id`, use the numeric ID as a string.

For example, put this fixture in `conftest.py` to test two WESL feature configurations:

```python
import pytest
import wesl


@pytest.fixture(params=[False, True], ids=["scalar", "vector"])
def wesl_features(request):
    return {"vector": request.param}
```

`wesl_features` accepts a mapping or a `Features` instance.
Mappings use `Feature.Disable` for unspecified flags.
The default options fixtures convert mappings to `Features` instances.
Use `Features` to select another default policy.

Override `wesl_device` to select an adapter, request features or limits, or use
an application's device. The fixture that creates a device owns its teardown.
`wesl.testing.run_test()` works outside pytest. Its signature is:

```python
def run_test(
    device: wgpu.GPUDevice,
    modules: Mapping[str, str],
    test_name: str,
    *,
    root: str = "package::main",
    options: wesl.TestOptions | None = None,
    filenames: Mapping[str, str | PathLike[str]] | None = None,
    root_directory: str | PathLike[str] | None = None,
    dependencies: Mapping[str, str | PathLike[str]] | None = None,
    resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    layouts: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    constants: Mapping[str, float] | None = None,
) -> None: ...
```

`modules` maps module names to WESL source strings.
`test_name` names a test function in the `root` module.
`root`, `filenames`, `root_directory`, and `dependencies` use the
[compilation conventions](api.md#compile-strings-and-files).
Pass `compiler.dependencies` to reuse its explicit directory mapping.
Pass `compiler.root_directory` separately when the test imports project files.

`resources` maps bind-group numbers to entry lists, as described
in [Resources for WESL tests](#resources-for-wesl-tests).
`layouts` supplies explicit layout entries for those groups. `None` uses automatic
layouts. An empty mapping specifies a layout with only the runner's result buffer.
`constants` maps override names or numeric ID strings to pipeline values.

The function runs one named `@test`, returns `None` on success, and reads no fixtures.
The caller owns the device and application resources.

Each `run_test()` call compiles the test and creates a compute pipeline.
For repeated execution, `prepare_test()` accepts the same arguments and returns
a callable:

```python
from wesl.testing import prepare_test

test = prepare_test(device, modules, "selected", resources=resources)
test()
test(resources=replacement_resources)
```

Preparation compiles once. Calls create and destroy a fresh result buffer.
Omit `resources` to reuse prepared resources; replacements must match the bindings
and layout. The caller keeps the device and resources alive and owns their teardown.
Prepare again to change sources, options, layouts, or constants.
Pytest prepares each shader test invocation separately.

The [convolution example](../examples/convolution/README.md) prepares its compute
pipelines and assertion callable once, then verifies multiple inputs.

The function raises `ShaderAssertionError` on assertion failure and
`ShaderTestDisabledError` when conditions disable the test.

`ShaderAssertionError` inherits from `AssertionError` and exposes these attributes:

- `diagnostic`: A [`wesl.Diagnostic`](api.md#diagnostics) for the first failing
  assertion.
- `filename`: The display path relative to the root directory, or the module
  name if no filename exists.
- `actual`: The actual value from the first failure: a Python `bool`, `int`,
  `float`, or tuple of floats.
- `expected`: The expected value from the first failure, with the same type as
  `actual`.
- `checks`: The total number of assertions executed, including passing
  assertions.
- `failures`: The total number of failed assertions.
- `invocation`: The local invocation index for a cooperative failure. Scalar tests
  report `None`.

`run_test()` accepts `wesl.TestOptions` through its `options` argument.
Passing `CompileOptions` raises `TypeError`.

| Test option | Behavior |
| --- | --- |
| `features=Features()` | Select conditional declarations and statements. |
| `strip=True` | Remove the declarations unused by the selected test. |
| `visibility=False` | Load external shaders without visibility restrictions. |
| `lower=False` | Lowering is unsupported. Set `True` to raise `NotImplementedError`. |
| `validate=True` | Run WESL validation before GPU validation. |

The runner owns import resolution, conditional translation, wrapper retention,
declaration naming, and source maps for assertion locations.
These settings are not fields of `TestOptions`.
Python compilation uses `CompileOptions` and honors its output settings.

When overriding either options fixture, pass `wesl_features` to keep the shared
feature configuration. For example:

```python
@pytest.fixture
def wesl_test_options(wesl_features):
    return wesl.TestOptions(strip=False, features=wesl_features)
```

Native tests use the shared source fixtures directly.
Overriding `wesl_compiler` or `wesl_options` affects only Python compilation.

Plugin import and collection do not import NumPy or wgpu-py.
Linux CI executes shaders on the CPU with Mesa lavapipe.

Missing adapters fail by default. Use `--wesl-gpu=optional` to
skip when the adapter or wgpu-py is unavailable. Shader compilation, device
creation, and execution errors still fail. A software adapter is valid.

The plugin registers through the `pytest11` entry point. If you disable automatic
plugin loading, load it with `-p wesl.pytest_plugin`.
Use `-p no:wesl` to disable automatic registration.

## Shader editing

Configure wgsl-analyzer to use the nearest `wesl.toml`.
The repository manifest sets `root = "."` and declares bundled `wgsl_test`.

For another development project with a sibling wesl-py checkout, use:

```toml
edition = "2026_pre"
root = "shaders"

[dependencies]
wgsl_test = { path = "../wesl-py/python/wesl/shaders/wgsl_test" }
```

Save this as your project's `wesl.toml` and set `root` to your shader directory.
The dependency points to source files and does not depend on a Python environment.
The [upstream manifest format](https://wesl-lang.dev/spec/WeslToml#dependencies-entry)
supports relative paths to directories that contain `wesl.toml`.
Its package discovery supports npm and Cargo.

To use the shaders from a Python installation instead, run this from the directory
that contains your project's `wesl.toml`:

```bash
pixi run python -c "
import os
from importlib.resources import files

print(os.path.relpath(files('wesl') / 'shaders/wgsl_test'))
"
```

Copy the returned path into the dependency entry.
Update it if you move or replace the environment.
This manifest configures the editor. Python compilation registers `wgsl_test` automatically.
