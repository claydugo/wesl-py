# Shader tests

`wesl-py` includes a pytest plugin and the `wgsl_test` assertion shaders.
Pytest loads the plugin automatically and collects `*.test.wesl` files.
The optional `testing` extra installs pytest and wgpu-py for execution.
The base package can collect tests if your environment already provides pytest.
Compilation and collection need no GPU.

The executor does not import NumPy. The current PyPI dependency chain still
installs NumPy through wgpu-py's dependency on rendercanvas.

For your Pixi project, add the checkout with its extra:

```toml
[pypi-dependencies]
wesl-py = { path = "/path/to/wesl-py", extras = ["testing"] }
```

See [installation](README.md#installation) for requirements.
The first test requires no `conftest.py` or manual plugin registration.

## WESL tests

Put shader tests in `*.test.wesl` files.
This matches [upstream CLI discovery](https://wesl-lang.dev/docs/wgsl-test#cli).
Each `@test` function becomes a separate pytest item.
Save this as `shaders/math.test.wesl`:

```wesl
import wgsl_test::expectEq;

@test
fn addition() {
    expectEq(3u + 4u, 7u);
}
```

```bash
pixi run python -m pytest shaders/math.test.wesl::addition
pixi run python -m pytest shaders --collect-only
pixi run python -m pytest shaders -k addition --junitxml=results.xml
```

A test function has no parameters, return value, or shader stage attribute.
The runner calls it from one compute invocation. A function with no assertions
passes when execution completes. Use Python tests for parallel dispatch and
fragment shaders.

Imports resolve through the existing WESL compiler. The default package root is
pytest's root directory. Configure a different directory with:

```toml
[tool.pytest.ini_options]
wesl_root = "shaders"
```

Keep collected files inside this directory. Their paths determine their
`package::` module names. Dots in a test filename's stem become `_` characters.
Pytest also collects any `.wesl` file that you select explicitly.

`@if`, `@elif`, and `@else` select implementations with `wesl_options`.
Collection includes conditional tests. A disabled test reports a skip at execution.
Pytest sets up fixtures before the runner checks conditions.
Session GPU fixtures can initialize for disabled tests.
Multiple conditional definitions of one name produce one item.

### Assertions

Import assertions from `wgsl_test`. The installed package includes the two
[upstream assertion shaders](https://github.com/webgpu-tools/wesl-js/tree/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders)
and registers them automatically for compilation and testing.
Their contents remain unchanged. The distribution names upstream `lib.wesl` as `package.wesl`
to identify the package root for the resolver and wgsl-analyzer.
The runner instruments them for source locations, assertion counts, and completion tracking.
It does not modify the packaged files.

Install the `testing` extra to obtain pytest and wgpu-py.
Shader imports need no download, cache, or registration step.
Editor configuration is optional for running tests.
See [shader editing](CONTRIBUTING.md#shader-editing) for wgsl-analyzer setup.

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
    return {"lygia": Path("path/to/lygia")}
```

The Lygia example has a repository setup script that fetches its two required shaders.
Run it from the wesl-py checkout:

```bash
pixi run python tools/fetch_test_shaders.py
```

This script is only for the example. Installed users manage their own library sources.
See [library directories](API.md#compile-strings-and-files) for the registration API.

| Function | Comparison |
| --- | --- |
| `expect(condition)` | Boolean is true |
| `expectEq(actual, expected)` | Exact `u32` equality |
| `expectNear(actual, expected)` | `f32` comparison with relative tolerance `0.001` and absolute tolerance `0.000001` |
| `expectWithin(actual, expected, relative, absolute)` | `f32` comparison with explicit tolerances |
| `expectUlp(actual, expected, maximum)` | At most `maximum` representable `f32` steps apart |

The floating-point functions also have `Vec2`, `Vec3`, and `Vec4` suffixes.
For example, `expectNearVec3` accepts two `vec3f` values.
Each component must pass. Near comparisons use
`abs(actual - expected) <= max(absolute, relative * max(abs(actual), abs(expected)))`.
Use finite operands and tolerances. The upstream assertions can accept NaN and
infinity. GPU floating-point behavior still applies.

A failure reports the first failing assertion, its original file and source line,
actual and expected values, and the total failure count.

Upstream reports values as four `f32` components.
The Python exception exposes them as tuples.
Scalar values occupy the first component. Large integers can round in reports.
Boolean assertions report upstream's `-999` sentinel values.
Use `expect(actual == expected)` to compare signed integers.

Assertions continue after a failure.
Failures in imported helpers point to the helper's source.

## Python tests

The `wesl_compiler` fixture shares `wesl_options`, `wesl_modules`, `wesl_dependencies`,
`wesl_filenames`, and `wesl_root_directory` with native WESL tests.
It returns a `wesl.Compiler` and does not request a GPU.
Parametrizing these fixtures also parametrizes Python tests that use the compiler.

Call `wesl_compiler.compile_source(source)` for an inline shader.
Call `wesl_compiler.compile_file("blur.wesl")` for a shader file.
Relative file paths start at `wesl_root_directory`.
Absolute paths must stay inside that directory.

Outside pytest, construct `wesl.Compiler` with `options`, `modules`, `filenames`,
`root_directory`, and `dependencies` to reuse the same configuration across compilations.

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

See the [executable examples](tests/examples/testing/README.md) for shared feature flags,
compute dispatch, texture sampling, image comparisons, and compilation failures.

### Resources for WESL tests

The `wesl_resources` fixture maps each group number to a list of entries.
These entries use wgpu-py's bind-group format.
Each entry specifies a binding number and a resource.
Use a buffer binding dictionary, a texture view, or a sampler as the resource.
Buffer dictionaries support `offset` and `size`.
Save this fixture as `shaders/buffers/conftest.py`:

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

Supply the bindings used by the selected test, including imported functions.
Unused extra bindings and missing resources produce WebGPU validation errors.
The runner selects the first unused binding in group 0 from the supplied entries.
It adds its result buffer there and supplies empty groups between occupied groups.
It copies the group lists before adding its binding.

Fixtures own application resources. The runner leaves those resources and the
device open, and it reads only its result buffer. It destroys that buffer on
success or failure. Read application outputs through the device queue when needed.
NumPy is optional for fixtures and application readback.

Arrays must match the shader's binary layout and the texture's format.
Specify NumPy dtypes explicitly when using NumPy. Represent struct offsets,
array strides, and padding explicitly. wgpu-py does not infer them from WGSL types.

The `wesl_constants` fixture sets override values for collected WESL tests.
Python calls to `run_test()` pass resources and constants explicitly.

### Fragment tests

Create a render pipeline through `wesl_device` and pass the compiled WGSL to
`create_shader_module()`. Choose the vertex shader, attachments, texture formats,
and readback layout in the test.
The [fragment example](tests/examples/testing/test_fragment.py) renders a texture
with a sampler and a uniform buffer. The
[pipeline example](tests/examples/testing/test_pipeline.py) shares a texture between
compute and rendering.

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

The fixture stores float32 arrays in `.npz` files beside the test module.
It preserves values outside the range from zero to one.
Choose tolerances for the shader and the target adapters.
Parameter values produce separate baselines with names derived from pytest IDs.
The first run creates missing baselines and fails the tests so you can review
the values. Keep approved baselines in version control.

Use `--force-regen` with a selected test to update a mismatched baseline.
The update fails that test; run it again to verify the new baseline.
See the [snapshot example](tests/examples/testing/test_snapshot.py) and its
[update commands](tests/examples/testing/README.md).

This comparison reports numerical differences by array index.
For PNG baselines and visual differences, use the plugin's
[`image_regression` fixture](https://pytest-regressions.readthedocs.io/en/latest/api.html#image-regression)
with Pillow. Convert the output to the intended image format explicitly.
The plugin does not support native WESL `@snapshot` annotations.

## Fixtures and pytest behavior

These fixtures work with Python tests and collected WESL tests:

| Fixture | Default |
| --- | --- |
| `wesl_device` | One device per pytest session or xdist worker |
| `wesl_compiler` | A `Compiler` using the shared compilation fixtures |
| `wesl_resources` | Empty mapping of groups to bind-group entries |
| `wesl_modules` | Empty mapping of additional WESL modules |
| `wesl_dependencies` | Empty mapping of package names to directories |
| `wesl_filenames` | Empty mapping of module names to source filenames |
| `wesl_options` | Default `CompileOptions` |
| `wesl_constants` | Empty mapping of WGSL overrides |
| `wesl_root_directory` | Resolved `wesl_root` directory |

Override fixtures in `conftest.py`. Parametrized fixtures produce separate shader
test cases with normal pytest IDs. Use `pytest_collection_modifyitems` to attach
skip, xfail, or project markers. Collected WESL tests carry `wesl` and `gpu` markers.

The `gpu` marker includes hardware and software adapters.
A software adapter runs shaders on the CPU.
Use `-m 'not gpu'` to select tests that need no WebGPU runtime.

`-k`, node IDs, JUnit reports, and pytest-xdist work through pytest's normal hooks.
Add the pytest-xdist package separately to use `-n`.

Use `--tb=line` for concise shader failures.
JUnit reports retain the shader location and failure message in this mode.
Use `--tb=no` to hide details.
Use `--tb=native` or `--full-trace` to inspect Python execution.

`wesl_constants` uses override names from the test module. For declarations with
`@id`, use the numeric ID as a string.

For example, put this fixture in `conftest.py` to test two WESL feature configurations:

```python
import pytest
import wesl


@pytest.fixture(params=[False, True], ids=["scalar", "vector"])
def wesl_options(request):
    return wesl.CompileOptions(
        features=wesl.Features(flags={"vector": request.param}),
    )
```

Override `wesl_device` to select an adapter, request features or limits, or use an
application's device. The fixture that creates a device owns its teardown.
`wesl.testing.run_test(device, modules, test_name, ...)` works outside pytest.
It runs one named `@test` function and returns `None` on success.

The function raises `ShaderAssertionError` on assertion failure and
`ShaderTestDisabledError` when conditions disable the test.
Shader tests require imports and conditional translation.

Importing the plugin, collecting tests, and compiling shaders need no WebGPU adapter.
Importing the plugin and collecting tests do not import NumPy or wgpu-py.
Executing shader tests requires a WebGPU adapter.
Linux CI uses Mesa lavapipe to execute shaders on the CPU.

Missing adapters fail by default. Use `--wesl-gpu=optional` to
skip when the adapter or wgpu-py is unavailable. Shader compilation, device
creation, and execution errors still fail. A software adapter is valid.

The plugin registers through the `pytest11` entry point. If you disable automatic
plugin loading, load it with `-p wesl.pytest_plugin`.
Use `-p no:wesl` to disable automatic registration.

## Repository tests

Run these commands from the wesl-py checkout:

```bash
pixi run -e testing python -m pytest tests/shaders -v
pixi run -e testing python -m pytest tests/test_testing.py -q
```

The WESL tests exercise the SDF example's production functions.
The Python tests verify the executor and its failure reports.
Tests report results in the terminal. They do not write image files.

The WESL assertion syntax follows the upstream
[wgsl-test API](https://github.com/webgpu-tools/wesl-js/blob/main/packages/wgsl-test/API.md).
Execution uses wgpu-py. It does not require Node.js or the JavaScript test runner.
