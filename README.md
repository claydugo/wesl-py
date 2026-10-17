# wesl-py

Python bindings for the [Rust WESL compiler](https://github.com/webgpu-tools/wesl-rs).
WESL adds imports and conditional compilation to WGSL.
Run shader tests with pytest. Compilation needs no GPU.

## Installation

Requires Python 3.12 or later.

The distribution name is `wesl-py`; import it as `wesl`.

```bash
pip install wesl-py
```

To run shader tests, install the `testing` extra. It adds pytest and wgpu.

```bash
pip install "wesl-py[testing]"
```

## Compile a shader

Save as `shaders/exposure.wesl`:

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

Enable a shader feature at compile time:

```python
import wesl

result = wesl.compile_file(
    "shaders/main.wesl",
    features={"clamp_output": True},
)
print(result.wgsl)
```

Pass `result.wgsl` to your renderer, such as
`device.create_shader_module(code=result.wgsl)` in wgpu-py.
The GPU runtime validates the WGSL.
Use `compile_source()` for a string or `compile()` for a mapping of modules.
See the [API reference](https://github.com/claydugo/wesl-py/blob/main/docs/api.md)
for options, library imports, and diagnostics.

`compile_file()` resolves imports from the shader file's parent directory.
Use `Compiler.from_project()` for a `wesl.toml` project.

## Test a shader

Save this as `shaders/math.test.wesl`:

```wesl
import wgsl_test::expectEq;

@test
fn addition() {
    expectEq(3u + 4u, 7u);
}
```

Run pytest:

```bash
python -m pytest shaders -q
```

The plugin collects `@test` functions and reports failures at the shader file
and line. Assertion shaders are bundled.
Execution requires a hardware or software WebGPU adapter.
See the [shader testing guide](https://github.com/claydugo/wesl-py/blob/main/docs/testing.md)
for Python fixtures, compute tests, and image comparisons.

## License

MIT.
