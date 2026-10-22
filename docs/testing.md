# Shader tests

`wesl-py` provides a pytest plugin and bundles assertion shaders from the WESL project's
[wgsl-test](https://github.com/webgpu-tools/wesl-js/tree/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test).
Pytest loads the plugin automatically and collects `*.test.wesl` files.
The `testing` extra installs pytest and wgpu-py.
The base package can collect tests when pytest is installed.
Compilation and collection need no GPU. Execution requires a WebGPU adapter.
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
Workgroup dimensions can use constants from `wesl_constants` or overrides with a
default value.
The `wesl_device` fixture must enable any device features that the shader requires.
Use Python tests for multiple workgroups or fragment shaders.

Counts combine all invocations. Reports identify one failing invocation and its
first failure; GPU scheduling can change which invocation appears.
Early returns still record results. Passing invocations cannot overwrite a failure.

Declare scratch storage with `@buffer`, as in wgsl-test:

```wesl
@buffer var<storage, read_write> scratch: array<u32, 64>;
```

The runner creates a storage buffer of the declared size and fills it with zeros.
A runtime-sized array gets 4 bytes. The runner places each `@buffer` variable in
group 0 after the result binding, and skips the group 0 bindings of
`wesl_resources` and `wesl_layouts`. As in wgsl-test, only the test module declares
`@buffer` variables. A `@buffer` variable must be `var<storage>` and has no
`@group` or `@binding` attribute. Tests cannot fill a `@buffer` with
data; generate inputs in the shader, or use `wesl_resources`.

Imports resolve through the existing WESL compiler.
Each test uses the nearest ancestor `wesl.toml` for its shader root.
Register dependency directories through the `wesl_dependencies` fixture.
By default, the fixture maps each `path` entry of the manifest's `[dependencies]`
table to the `root` of the `wesl.toml` in that directory.
Use `Compiler.from_project()` to load the same root and dependencies outside pytest.
Without a manifest, the default package root is the test file's parent directory.
Set the root in [`wesl.toml`](api.md#compile-strings-and-files).

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
and public visibility modifiers.

WESL derives the result buffer layout from the compiled result type and decodes
the buffer. Custom result modules must retain the upstream field names and types.
Arbitrary custom layouts are unsupported. The binding evaluates named and
transitive layout constants. It rejects zero alignment and
cyclic result types. Pass a `wgsl_test` entry in `dependencies` to replace the
bundled package.

Shader tests reject scoped overrides such as `alpha/wgsl_test` in `dependencies`
or `modules`. Normal compilation accepts these overrides.

Other libraries use `dependencies` or the `wesl_dependencies` fixture.
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
- `expectEqI32(actual, expected)`: Exact `i32` equality
- `expectEqVec2u`, `expectEqVec3u`, `expectEqVec4u`: Exact equality of `u32`
  vectors
- `expectEqVec2i`, `expectEqVec3i`, `expectEqVec4i`: Exact equality of `i32`
  vectors
- `expectNear(actual, expected)`: `f32` comparison with relative tolerance
  `0.001` and absolute tolerance `0.000001`
- `expectWithin(actual, expected, relTol, absTol)`: `f32` comparison with
  explicit tolerances
- `expectUlp(actual, expected, maxUlp)`: At most `maxUlp` representable `f32`
  steps apart

The floating-point functions also have `Vec2`, `Vec3`, and `Vec4` suffixes.
For example, `expectNearVec3` accepts two `vec3f` values.
Each component must pass. A near comparison fails when
`abs(actual - expected) > max(absTol, relTol * max(abs(actual), abs(expected)))`
or when a component of either value is NaN.
Use finite operands and tolerances. An infinite operand makes the `expectNear`
tolerance infinite, so `expectNear(inf, 1.0)` and `expectNear(inf, inf)` pass.
A NaN tolerance makes every comparison pass, as in wgsl-test.
The NaN check reads the float bits. WGSL lets a compiler assume finite values, so
it can remove a comparison such as `x != x`. `expectUlp` has no NaN check.
GPU floating-point behavior still applies.

Failures underline the first failed assertion and show actual and expected values
with failure and assertion counts. Paths are relative to pytest's root directory.

Scalar values retain their types. Integers retain all 32 bits.
Vectors retain their dimensions, including zero components.
Boolean assertions report `false` and `true`.

Assertions continue after failure. Imported failures point to the helper's source.

## Python tests

Use `run_test_cpu` for shader calculations that need no GPU resources:

```python
from wesl.testing import run_test_cpu


def test_addition(wesl_compiler):
    run_test_cpu(
        wesl_compiler,
        "addition",
        source="""
            @test fn addition() {
                wgsl_test::expectEq(3u + 4u, 7u);
            }
        """,
    )
```

Run this test in the `test` environment. It needs neither wgpu-py nor an adapter.
`run_test_cpu` accepts the arguments of `run_test()` except `device`, `resources`,
and `layouts`.
The CPU runner supports imports, feature flags, private variables, and overrides
with a default value. Each call starts with fresh shader state.

CPU tests cannot use user buffers, textures, samplers, workgroup variables,
builtin parameters, or an explicit `@workgroup_size`.
The upstream interpreter is experimental and supports only some WGSL operations.

The `wesl_compiler` fixture collects `wesl_features`, `wesl_modules`,
`wesl_dependencies`, `wesl_filenames`, `wesl_root_directory`, and `wesl_constants`.
Native WESL tests compile through it. Every function of `wesl.testing` takes it
as the `compiler` argument, so a Python test finds the project's shaders and
dependencies without more arguments. The fixture does not request a GPU.
`wesl_options` configures its `compile_source` and `compile_file` methods.
`wesl_test_options` configures native tests.

Call `wesl_compiler.compile_source(source)` for an inline shader.
Call `wesl_compiler.compile_file("blur.wesl")` for a shader file.
Relative file paths start at `wesl_root_directory`.
Absolute paths must stay inside that directory.

Compile with `wesl.compile`, `compile_source`, or `compile_file` when a test
needs separate configuration. Pass `CompileResult.wgsl` to wgpu-py.
For buffer computations, wgpu-py provides `compute_with_buffers`.
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

`wesl.testing.run_compute()` follows wgsl-test's `testCompute()`. It compiles the
modules, runs the `main` entry point, and returns the contents of each
`read_write` `@buffer` variable of the root module by name:

```python
import numpy as np
from wesl.testing import run_compute


def test_squares(wesl_device, wesl_compiler):
    results = run_compute(
        wesl_device,
        wesl_compiler,
        """
            @buffer var<storage, read> values: array<u32>;
            @buffer var<storage, read_write> squares: array<u32, 8>;
            @compute @workgroup_size(4)
            fn main(@builtin(global_invocation_id) index: vec3u) {
                squares[index.x] = values[index.x] * values[index.x];
            }
        """,
        buffers={"values": np.arange(8, dtype=np.uint32)},
        dispatch_workgroups=2,
    )
    np.testing.assert_array_equal(results["squares"], np.arange(8) ** 2)
```

The `source` argument is the root module. Omit it to compile `root` from the
compiler's modules or root directory. `root` is a module path such as
`package::algorithms::sum`, or, as in wesl-js `testCompute`, a file path such
as `algorithms/sum.wesl` relative to the root directory. For a file path, the
runner reads the file and names the module as the pytest plugin does, so
`sum.test.wesl` becomes `package::algorithms::sum_test`. A name without `::`
or a file extension stays a module or package name, such as `package`, a
dependency, or a `load_modules()` namespace. `run_test()` and `run_test_cpu()`
accept the same forms.

`buffers` fills `@buffer` variables by name before the dispatch. The runner
assigns each value to a NumPy view of the buffer, so NumPy broadcasts and casts
the value as in `view[...] = value`. A runtime-sized array takes its length from
the value. A name that no `@buffer` variable has raises `ValueError`.
A float value for an integer or bool buffer raises `TypeError`; convert it
first.
Other buffers start as the `f32` value `-999.0`, so unwritten elements are visible.

Each result has the shape and type of the WGSL declaration:

| WGSL type | Result |
| --- | --- |
| `f32`, `i32`, `u32`, `f16` | 0-dimensional NumPy array of that type |
| `array<T, N>` | Shape `(N, ...)` |
| `vec3f` | Shape `(3,)` |
| `mat3x3f` | Shape `(3, 3)`, indexed by column and then row |
| Structure | `dict` of member names to results |

The runner removes the padding of vectors and matrices at every level, also in
structure members. An array of structures decodes as a `dict` of arrays: each
member array has the array dimensions first. For example,
`array<Eigenvectors, 256>` with a member `vectors: array<vec3f, 3>` gives
`result["vectors"]` of shape `(256, 3, 3)`. A nested structure gives a nested
`dict`. `atomic<T>` decodes as `T`. A `bool` member or a structure with a
runtime-sized array raises `TypeError`.

A `buffers` value for a structure is a `dict`, or a NumPy structured array, with
a value for each member. A runtime-sized array takes its length from the value.
This also sizes an output: declare `@buffer var<storage, read_write> results:
array<f32>;` and pass `buffers={"results": np.zeros(256, np.float32)}`, so the
count lives in one place. Without a value, a runtime-sized array has the length
that fits in the 4-byte default buffer.

`wesl.reflect.decode_buffer()` decodes bytes from an application pipeline the
same way. `wesl.reflect.numpy_dtype()` gives the byte layout with its padding.
See [Reflection](api.md#reflection).

The runner binds every `@buffer` variable of the root module, including variables
that `main` does not use.
`dispatch_workgroups` is a count or an `(x, y, z)` tuple and defaults to 1.
The compiler's options select features. `constants` supplies the `constants::`
module. Overrides keep their default values, as in `testCompute()`.

### Parametrized tests

A WESL test has no parameters. To run one test function on several cases, use
`pytest.mark.parametrize` in a Python test, and send each case through the
`constants::` module. A constant can be a WGSL expression string. Put the
function in a module whose name does not end in `.test.wesl`, so that the plugin
does not also collect it without its constants. Save this as
`shaders/contour_cases.wesl`:

```wesl
import constants::{mask, expected};
import package::contour::corners;
import wgsl_test::expectEqVec2u;

@test fn corners_match() {
    expectEqVec2u(corners(mask), expected);
}
```

Then save this as `test_contour.py`:

```python
import pytest
from wesl.testing import run_test


@pytest.mark.parametrize(
    ("mask", "expected"),
    [
        pytest.param("array<u32, 4>(0u, 1u, 0u, 0u)", "vec2u(1u, 0u)", id="a_pixel"),
        pytest.param("array<u32, 4>(1u, 1u, 1u, 1u)", "vec2u(4u, 0u)", id="a_square"),
    ],
)
def test_contour(wesl_device, wesl_compiler, mask, expected):
    run_test(
        wesl_device,
        wesl_compiler,
        "corners_match",
        root="package::contour_cases",
        constants={"mask": mask, "expected": expected},
    )
```

Each case is one pytest item with the ID that `pytest.param` gives. A failure
names the WESL line and the values of the case.

See the [executable examples](../tests/examples/testing/README.md).

### Resources for WESL tests

`wesl_resources` maps group numbers to wgpu-py bind-group entries.
Resources can be buffer dictionaries (with optional `offset` and `size`), texture
views, or samplers. With automatic layouts, each test binds only the entries of
the resources that it uses, so one fixture can serve every test in a directory.
Save this as `shaders/buffers/conftest.py`:

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

To set explicit layouts, override `wesl_layouts` or pass `layouts` to `run_test()`.
Map each group number to a list of wgpu-py layout entries.
Supply a layout entry for every application binding.
The runner adds its result buffer to group 0. It avoids bindings from both mappings.
The runner does not modify the supplied lists.

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
only the buffers that it creates: its result buffer and one buffer for each
`@buffer` variable. It destroys them also on failure. Read application outputs
through the device queue. NumPy is optional for fixtures and readback.

Arrays must match the shader's binary layout and the texture's format.
Specify NumPy dtypes explicitly when using NumPy. Represent struct offsets,
array strides, and padding explicitly. wgpu-py does not infer them from WGSL types.

The `wesl_constants` fixture supplies the values of the `constants::` module for
collected WESL tests, as in wgsl-test.
The runner sets no override values. An override that the selected test uses must
have a default value. To vary a value between test cases, read it from the
`constants::` module. The rmsnorm, compaction, and imaging examples show the
pattern: the shader keeps its override and calls a public function that takes
the value as a parameter, and the test calls that function with a value from
`constants::`.
`wesl_constants` and the `constants` argument of `run_test()` cannot be used
together, because both supply the `constants` module. Pass the values in one
place.

### Fragment tests

Use `wesl_device` to create a render pipeline from compiled WGSL.
The test sets attachments, formats, and readback layout.
The [fragment example](../tests/examples/testing/test_fragment.py) renders a texture
with a sampler and a uniform buffer. The
[pipeline example](../tests/examples/testing/test_pipeline.py) shares a texture
between compute and rendering.

### Image snapshots

Use the optional [pytest-regressions](https://pytest-regressions.readthedocs.io/en/latest/api.html#ndarrays-regression)
plugin to compare arrays with stored baselines. The repository's `testing`
environment includes it. The `testing` extra does not.
In another Pixi project, run:

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

See the [snapshot example](../tests/examples/testing/test_snapshot.py) and its
[baseline workflow](../tests/examples/testing/README.md#stored-baselines).
Native `@snapshot` is unsupported.

## Fixtures and pytest behavior

The plugin provides these fixtures:

- `wesl_device`: One device per pytest session or xdist worker
- `wesl_compiler`: A `Compiler` using the shared compilation fixtures and
  `wesl_constants`. Native WESL tests compile through it
- `wesl_resources`: Empty mapping of groups to bind-group entries
- `wesl_layouts`: `None` for automatic layouts, or a mapping of groups to layout
  entries
- `wesl_modules`: Empty mapping of additional WESL modules
- `wesl_dependencies`: Explicit mapping of package names to shader directories.
  Defaults to the `path` dependencies of the nearest `wesl.toml`
- `wesl_filenames`: Empty mapping of module names to source filenames
- `wesl_features`: Default `Features`, shared by both options fixtures
- `wesl_options`: `CompileOptions` for `wesl_compiler`, using `wesl_features`
- `wesl_test_options`: `TestOptions` for native WESL tests, using
  `wesl_features`
- `wesl_constants`: Empty mapping of `constants::` module values
- `wesl_root_directory`: Explicit `wesl_root`, manifest root, or test file's parent

Override fixtures in `conftest.py`. Parametrized fixtures produce separate shader
test cases with normal pytest IDs. Use `pytest_collection_modifyitems` to attach
skip, xfail, or project markers. Collected WESL tests carry the `wesl` marker.
Use `-m 'not wesl'` to deselect them.

Use `--tb=line` for the shortest shader failure output.
JUnit reports retain the shader location and failure message in this mode.
Use `--tb=native` or `--full-trace` to inspect Python execution.

For example, put this fixture in `conftest.py` to test two WESL feature configurations:

```python
import pytest


@pytest.fixture(params=[False, True], ids=["scalar", "vector"])
def wesl_features(request):
    return {"vector": request.param}
```

`wesl_features` accepts a mapping or a `Features` instance.
Mappings use `Feature.Disable` for unspecified flags.
The default options fixtures convert mappings to `Features` instances.
Use `Features` to select another default policy.

Override `wesl_device` to select an adapter, request features or limits, or use
an application's device.
`wesl.testing.run_test()` works outside pytest. Its signature is:

```python
def run_test(
    device: wgpu.GPUDevice,
    compiler: wesl.Compiler,
    test_name: str,
    *,
    source: str | None = None,
    root: str = "package::main",
    options: wesl.TestOptions | None = None,
    resources: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    layouts: Mapping[int, Sequence[dict[str, Any]]] | None = None,
    constants: Mapping[str, SupportsFloat | str] | None = None,
) -> None: ...
```

`compiler` supplies the modules, filenames, root directory, and dependencies, as
in [compilation conventions](api.md#compile-strings-and-files). Its `options` have
no effect; `options` configures the test. Outside pytest, construct it as
`wesl.Compiler(modules={"package::main": source})` or with
`wesl.Compiler.from_project()`.
`source`, when given, is the WESL source of the `root` module.
`test_name` names a test function in the `root` module.

`resources` maps bind-group numbers to entry lists, as described
in [Resources for WESL tests](#resources-for-wesl-tests).
`layouts` supplies explicit layout entries for those groups. `None` uses automatic
layouts. An empty mapping specifies a layout with only the runner's result buffer.
`constants` maps names to the scalar values of the `constants::` module, as in
[Supply constants](api.md#supply-constants).

The function runs one named `@test` and reads no fixtures.
The caller owns the device and application resources.

Each `run_test()` call compiles the test, creates a compute pipeline, and
creates and destroys the runner's buffers.
The [convolution example](../examples/convolution/README.md) prepares its compute
pipelines once, then calls `run_test()` to verify each input.

The function raises `ShaderAssertionError` on assertion failure and
`ShaderTestDisabledError` when conditions disable the test.
It raises `RuntimeError` when the shader does not record completion.
When wgpu-py rejects the shader module or the pipeline, `run_test()` and
`run_compute()` raise the wgpu-py error. In the message text, each mangled
declaration name changes to `module::name`. The source excerpt keeps the
compiled names, so its line and column numbers and its carets match the
compiled WGSL.

`ShaderAssertionError` inherits from `AssertionError` and exposes these attributes:

- `diagnostic`: A [`wesl.Diagnostic`](api.md#diagnostics) for the first failing
  assertion.
- `filename`: The display path relative to `root_directory`, or the module
  name if no filename exists.
- `actual`: The actual value from the first failure: a Python `bool`, `int`,
  `float`, or tuple of them.
- `expected`: The expected value from the first failure, with the same type as
  `actual`.
- `value_type`: The WGSL type of the compared values, such as `u32` or `vec2i`.
- `checks`: The total number of assertions executed, including passing
  assertions.
- `failures`: The total number of failed assertions.
- `invocation`: The local invocation index for a cooperative failure. Scalar tests
  report `None`.

Passing `CompileOptions` as `options` raises `TypeError`.

| Test option | Behavior |
| --- | --- |
| `features=Features()` | Select conditional declarations and statements. |
| `strip=True` | Remove the declarations unused by the selected test. |
| `visibility=False` | Load external shaders without visibility restrictions. |
| `lower=False` | Lowering is unsupported. Set `True` to raise `NotImplementedError`. |
| `validate=True` | Run WESL validation before GPU validation. |

The runner owns import resolution, conditional translation, wrapper retention,
declaration naming, and source maps for assertion locations.
Python compilation uses `CompileOptions` and honors its output settings.

When overriding either options fixture, pass `wesl_features` to keep the shared
feature configuration. For example:

```python
@pytest.fixture
def wesl_test_options(wesl_features):
    return wesl.TestOptions(strip=False, features=wesl_features)
```

Plugin import and collection do not import NumPy or wgpu-py.

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
