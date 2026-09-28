# wesl-py

Python bindings for the [Rust WESL compiler](https://github.com/webgpu-tools/wesl-rs).
WESL adds imports and conditional compilation to WGSL.
Compile shaders from Python, or run WESL tests with pytest.
Compilation needs no GPU.

## Installation

Requires Python 3.12 or later and Rust 1.97.1 or later with a native linker.
Add a checkout to your project's `pixi.toml`:

```toml
[pypi-dependencies]
wesl-py = { path = "/path/to/wesl-py" }
```

Run `pixi install`. The distribution name is `wesl-py`; import it as `wesl`.
See [CONTRIBUTING.md](https://github.com/claydugo/wesl-py/blob/main/CONTRIBUTING.md)
to work in this repository.

## Compile a shader

Put a reusable function in `shaders/exposure.wesl`:

```wesl
fn apply_exposure(color: vec3f, stops: f32) -> vec3f {
    let adjusted = color * exp2(stops);
    @if(clamp_output) return clamp(adjusted, vec3f(0.0), vec3f(1.0));
    @if(!clamp_output) return adjusted;
}
```

Import it from `shaders/main.wesl`:

```wesl
import package::exposure::apply_exposure;

@fragment
fn main(@location(0) color: vec4f) -> @location(0) vec4f {
    return vec4f(apply_exposure(color.rgb, 1.0), color.a);
}
```

Compile with output clamping enabled:

```python
import wesl

result = wesl.compile_file(
    "shaders/main.wesl",
    features={"clamp_output": True},
)
print(result.wgsl)
```

Pass `result.wgsl` to your renderer. With an existing wgpu-py device, call
`device.create_shader_module(code=result.wgsl)`. The GPU runtime validates the WGSL.
Use `compile_source()` for a string or `compile()` for a mapping of modules.
See the [API reference](https://github.com/claydugo/wesl-py/blob/main/docs/api.md)
for options, library imports, and diagnostics.

For a project with multiple shader directories, add `wesl.toml` at the project root:

```toml
edition = "2026_pre"
root = "shaders"
```

Load the manifest with `Compiler.from_project()`:

```python
compiler = wesl.Compiler.from_project(".")
result = compiler.compile_file("main.wesl", features={"clamp_output": True})
```

Pytest discovers this manifest and uses the same import root.
Standalone `compile_file()` uses the shader file's parent directory by default.

## Test a shader

Add `extras = ["testing"]` to the dependency entry and run `pixi install`.
Save this as `shaders/math.test.wesl`:

```wesl
import wgsl_test::expectEq;

@test
fn addition() {
    expectEq(3u + 4u, 7u);
}
```

Run `pixi run python -m pytest shaders -q`.
The pytest plugin collects `@test` functions and reports failures at the shader
file and line.
The package includes assertion shaders. Execution requires a hardware or
software WebGPU adapter.
See the [shader testing guide](https://github.com/claydugo/wesl-py/blob/main/docs/testing.md)
for Python fixtures, compute tests, and image comparisons.

## Examples

- [Third-party imports](https://github.com/claydugo/wesl-py/blob/main/examples/imports.py):
  fetch a library module and compile a shader that uses it.
- [SDF playground](https://github.com/claydugo/wesl-py/blob/main/examples/sdf/README.md):
  share geometry between rendering and particle collisions.
- [Multiscale fluorescence](https://github.com/claydugo/wesl-py/blob/main/examples/multiscale/README.md):
  share convolution across image axes, scales, and implementations.
- [RMSNorm](https://github.com/claydugo/wesl-py/blob/main/examples/rmsnorm/README.md)
  and [compaction](https://github.com/claydugo/wesl-py/blob/main/examples/compaction/README.md):
  verify compute results without a window.

See the [examples index](https://github.com/claydugo/wesl-py/blob/main/examples/README.md)
for commands.

## License

MIT. See [LICENSE](https://github.com/claydugo/wesl-py/blob/main/LICENSE) for
third-party notices.
