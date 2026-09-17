# Shader tests

The optional `testing` extra provides pytest integration, NumPy, and wgpu-py.
The compiler works without these dependencies.

From this checkout:

```bash
pixi run -e testing python -m pytest tests/shaders -v
pixi run -e testing python -m pytest tests/test_testing.py -q
```

The first command runs WESL tests against the SDF example's production functions.
The second runs Python tests for compute and fragment shaders.
Tests report results in the terminal. They do not write image files.

For another Pixi project, add the checkout with its extra:

```toml
[pypi-dependencies]
wesl-py = { path = "/path/to/wesl-py", editable = true, extras = ["testing"] }
```

## WESL tests

Put shader tests in `test_*.wesl`, `*_test.wesl`, or `*.test.wesl` files.
Each `@test` function becomes a separate pytest item.

```wesl
import package::interpolation::remap;
import wgsl_test::expectNear;

@test
fn midpoint() {
    expectNear(remap(0.5, 0.0, 1.0, 10.0, 20.0), 15.0);
}
```

```bash
pixi run python -m pytest shaders/test_interpolation.wesl::midpoint
pixi run python -m pytest shaders --collect-only
pixi run python -m pytest shaders -k midpoint --junitxml=results.xml
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
wesl_files = ["test_*.wesl", "*_test.wesl", "*.test.wesl"]
```

Keep collected files inside this directory. Their paths determine their
`package::` module names. Dots in a test filename's stem become `_` characters.
Pytest also collects any `.wesl` file that you select explicitly.

`@if`, `@elif`, and `@else` select implementations with `wesl_options`.
Collection includes conditional tests. A disabled test reports a skip at execution.
The plugin checks conditions before it requests GPU fixtures.
Multiple conditional definitions of one name produce one item.

### Assertions

Import assertions from `wgsl_test`. The runner supplies this package,
including when an external shader library imports it.

| Function | Comparison |
| --- | --- |
| `expect(condition)` | Boolean is true |
| `expectEq(actual, expected)` | Exact `u32` equality |
| `expectEqI32(actual, expected)` | Exact `i32` equality |
| `expectNear(actual, expected)` | `f32` comparison with relative tolerance `0.001` and absolute tolerance `0.000001` |
| `expectWithin(actual, expected, relative, absolute)` | `f32` comparison with explicit tolerances |
| `expectUlp(actual, expected, maximum)` | At most `maximum` representable `f32` steps apart |

The floating-point functions also have `Vec2`, `Vec3`, and `Vec4` suffixes.
For example, `expectNearVec3` accepts two `vec3f` values.
Each component must pass. Near comparisons use
`abs(actual - expected) <= max(absolute, relative * max(abs(actual), abs(expected)))`.
Use finite inputs. GPU floating-point behavior still applies.

A failure reports the first failing assertion, its original file and source line,
actual and expected values, tolerances, and the total failure count.
Integer reports preserve all 32 bits. Assertions continue after a failure.
Failures in imported helpers point to the helper's source.

## Python tests

The `wesl_compiler` fixture shares `wesl_options`, `wesl_modules`,
`wesl_filenames`, and `wesl_root_directory` with native WESL tests.
It returns a `wesl.Compiler` and does not request a GPU.
Parametrizing these fixtures also parametrizes Python tests that use the compiler.

Call `wesl_compiler.compile_source(source)` for an inline shader.
Call `wesl_compiler.compile_file("blur.wesl")` for a shader file.
Relative file paths start at `wesl_root_directory`.
Absolute paths must stay inside that directory.

Outside pytest, construct `wesl.Compiler` with `options`, `modules`, `filenames`,
and `root_directory` to reuse the same configuration across compilations.

Compile with `wesl.compile`, `compile_source`, or `compile_file`.
Pass the result to the `wesl_runner` fixture. A WGSL string also works.
These module functions remain available when a test needs separate configuration.

```python
import numpy as np
from wesl.testing import Buffer


def test_double(wesl_compiler, wesl_runner):
    shader = wesl_compiler.compile_source("""
        @group(0) @binding(0) var<storage, read_write> values: array<f32>;
        @compute @workgroup_size(1)
        fn main(@builtin(global_invocation_id) invocation: vec3u) {
            values[invocation.x] *= 2.0;
        }
    """)
    values = np.array([1, 2, 3], dtype=np.float32)
    output = wesl_runner.compute(
        shader,
        resources={(0, 0): Buffer(data=values)},
        workgroups=3,
    )
    np.testing.assert_array_equal(output[0, 0], values * 2)
```

`workgroups` is a count or an `(x, y, z)` tuple. It counts workgroups, not shader
invocations. `entry_point` defaults to `main`. `constants` maps WGSL override
names to values. Use pytest parametrization for input and feature matrices.

Pass resources and constants to Python execution calls explicitly.
The `wesl_resources` and `wesl_constants` fixtures supply these arguments to
collected WESL tests.

See the [executable examples](examples/testing/README.md) for shared feature flags,
compute dispatch, texture sampling, image comparisons, and compilation failures.

### Resources

Resource keys are `(group, binding)` tuples. Supply bindings used by the selected
entry point. Unused extra bindings produce WebGPU validation errors.

| Resource | Behavior |
| --- | --- |
| `Buffer(data=array)` | Upload a storage buffer. Return an array with the same shape and dtype. |
| `Buffer(data=array, uniform=True)` | Upload a uniform buffer. |
| `Texture(data=array, format="rgba8unorm")` | Upload a texture. The last axis contains channels. |
| `Texture(..., storage=True)` | Enable storage texture access. |
| `GPUBuffer` or a buffer binding dictionary | Bind a caller-owned buffer, including an optional offset and size. |
| `GPUTexture` or `GPUTextureView` | Bind a caller-owned texture or view. |
| `GPUSampler` | Bind a sampler created through `wesl_device` or `wesl_runner.device`. |

Texture data has shape `(height, width, channels)` for 2D textures.
Use `(depth, height, width, channels)` for 3D textures or 2D arrays.
Set `dimension="3d"` for 3D textures. `view_dimension` configures the texture view.
1D textures use `(width, channels)` and `dimension="1d"`.

Arrays must match the shader's binary layout and the texture's format.
Specify NumPy dtypes explicitly. Represent struct offsets, array strides, and
padding explicitly. The runner does not infer these from WGSL types.

Each call uploads fresh copies of `Buffer` and `Texture` data.
It leaves the original arrays unchanged and destroys temporary GPU resources
after readback. Compute results include all wrapped buffers and textures.
Caller-owned resources remain alive and retain their contents between calls.
Read them through the device queue when needed.

### Fragment tests

```python
import numpy as np


def test_color(wesl_compiler, wesl_runner):
    shader = wesl_compiler.compile_source("""
        @fragment fn main() -> @location(0) vec4f {
            return vec4f(0.25, 0.5, 0.75, 1.0);
        }
    """)
    pixels = wesl_runner.fragment(shader, size=(3, 2))
    np.testing.assert_array_equal(pixels[0, 0], [0.25, 0.5, 0.75, 1.0])
```

The runner draws a triangle that covers the render target.
Fragment shaders can use `@builtin(position)` and resources.
The shader writes `@location(0) vec4f`. The result has shape
`(height, width, 4)` and dtype `float32`. Size defaults to `(1, 1)`.

The resource, entry point, and override arguments match `compute()`.
This helper supplies its own vertex shader and an `rgba32float` target.
Custom vertex inputs, depth targets, and multiple render targets are outside
this interface.

### Image snapshots

Use the optional [pytest-regressions](https://pytest-regressions.readthedocs.io/en/latest/api.html#ndarrays-regression)
plugin to compare arrays with stored baselines. Add it to your Pixi environment:

```bash
pixi add pytest-regressions
```

Request its `ndarrays_regression` fixture in a Python test:

```python
def test_color_snapshot(wesl_compiler, wesl_runner, ndarrays_regression):
    shader = wesl_compiler.compile_source("""
        @fragment fn main() -> @location(0) vec4f {
            return vec4f(0.25, 0.5, 0.75, 1.0);
        }
    """)
    pixels = wesl_runner.fragment(shader, size=(3, 2))
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
See the [snapshot example](examples/testing/test_snapshot.py) and its
[update commands](examples/testing/README.md).

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
| `wesl_runner` | A `ShaderRunner` using that device |
| `wesl_resources` | Empty resource mapping |
| `wesl_modules` | Empty mapping of additional WESL modules |
| `wesl_filenames` | Empty mapping of module names to source filenames |
| `wesl_options` | Default `CompileOptions` |
| `wesl_constants` | Empty mapping of WGSL overrides |
| `wesl_root_directory` | Resolved `wesl_root` directory |

Override fixtures in `conftest.py`. Parametrized fixtures produce separate shader
test cases with normal pytest IDs. Use `pytest_collection_modifyitems` to attach
skip, xfail, or project markers. Collected WESL tests carry the `wesl` marker.
`-k`, node IDs, JUnit reports, and pytest-xdist work through pytest's normal hooks.
Add the pytest-xdist package separately to use `-n`.

Use `--tb=line` for concise shader failures.
JUnit reports retain the shader location and failure message in this mode.
Use `--tb=no` to hide details.
Use `--tb=native` or `--full-trace` to inspect Python execution.

`wesl_constants` uses override names from the test module. For declarations with
`@id`, use the numeric ID as a string.

For example, test two WESL feature configurations:

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
`ShaderRunner(device)` also works outside pytest. Its `run_test()` method runs
one named `@test` function from a module mapping and returns `ShaderTestResult`.

The method raises `ShaderAssertionError` on assertion failure and
`ShaderTestDisabledError` when conditions disable the test.
Shader tests require imports and conditional translation.

Importing the plugin and collecting tests do not create a GPU device or import
NumPy or wgpu-py. Missing adapters fail by default. Use `--wesl-gpu=optional` to
skip when the adapter or wgpu-py is unavailable. Shader compilation, device
creation, and execution errors still fail. A software adapter is valid.

The plugin registers through the `pytest11` entry point. If you disable automatic
plugin loading, load it with `-p wesl.pytest_plugin`.
Use `-p no:wesl` to disable automatic registration.

The WESL assertion syntax follows the upstream
[wgsl-test API](https://github.com/webgpu-tools/wesl-js/blob/main/packages/wgsl-test/API.md).
Execution uses wgpu-py. It does not require Node.js or the JavaScript test runner.
