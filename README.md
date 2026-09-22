# wesl-py

Python bindings for the [Rust WESL compiler](https://github.com/webgpu-tools/wesl-rs).

WESL extends WGSL with imports and conditional compilation. Organize reusable
shader code into modules and compile it to ordinary WGSL from Python.
Compilation runs without a GPU.

Use pytest to [run shader tests](#shader-tests) on a WebGPU adapter.
Write assertions in WESL and see failures at the original shader file and line.

## Installation

Requires Python 3.12 or later. No public release is available yet.
Add a checkout as a dependency in your project's `pixi.toml`:

```toml
[pypi-dependencies]
wesl-py = { path = "/path/to/wesl-py" }
```

Install it from your project directory:

```bash
pixi install
pixi run python -c "import wesl; print(wesl.__version__)"
```

The distribution name is `wesl-py`. Import it as `wesl`.
Source installation requires Rust and a native linker.
See [CONTRIBUTING.md](https://github.com/claydugo/wesl-py/blob/main/CONTRIBUTING.md#support) for platform support and source builds.

## Usage

Put a reusable exposure function in `shaders/exposure.wesl`:

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

Compile the shader with output clamping enabled:

```python
import wesl

result = wesl.compile_file(
    "shaders/main.wesl",
    options=wesl.CompileOptions(
        features=wesl.Features(flags={"clamp_output": True}),
    ),
)
print(result.wgsl)
```

This prints ordinary WGSL:

```wgsl
@fragment
fn main(@location(0) color: vec4f) -> @location(0) vec4f {
    return vec4f(package_exposure__1apply_exposure(color.rgb, 1.0), color.a);
}

fn package_exposure__1apply_exposure(color: vec3f, stops: f32) -> vec3f {
    let adjusted = color * exp2(stops);
    return clamp(adjusted, vec3f(0.0), vec3f(1.0));
}
```

`compile_file()` resolves imports from the root file's directory.
The compiler includes the imported function and removes inactive code.
Set `clamp_output` to `False` to preserve values outside `[0, 1]`.

Use `compile_source()` for a string or `compile()` for a mapping of module names to sources.
`check_syntax()` checks WESL syntax.

See the [API reference](https://github.com/claydugo/wesl-py/blob/main/API.md) for compilation options and diagnostics.

## Library imports

Register a directory to import an external shader library.
For a Lygia checkout at `../lygia`:

```python
import wesl

compiler = wesl.Compiler(dependencies={"lygia": "../lygia"})
result = compiler.compile_source("""
    import lygia::color::palette::heatmap::heatmap;
    @fragment fn main() -> @location(0) vec4f {
        return vec4f(heatmap(0.5), 1.0);
    }
""")
```

The fragment shader outputs the heatmap color for `0.5`.
The compiler reads imported files from that directory.
You manage the library sources. See the [Lygia example](https://github.com/claydugo/wesl-py/blob/main/examples/lygia/README.md)
for image processing and tests.

## Use the generated WGSL

Pass `result.wgsl` to your renderer or compute framework.
For example, with an existing wgpu-py device:

```python
shader_module = device.create_shader_module(code=result.wgsl)
```

Compilation runs upstream WESL checks.
The target GPU runtime validates the generated shader and pipeline.

## Shader tests

`wesl-py` includes the pytest plugin and `wgsl_test` assertion shaders.
With pytest in the environment, it automatically collects `@test` functions from
`*.test.wesl` files. Pytest requires no `conftest.py` or manual plugin registration.

Use the `testing` extra to install pytest and wgpu-py for execution.
Set the dependency entry in your project's `pixi.toml` to:

```toml
[pypi-dependencies]
wesl-py = { path = "/path/to/wesl-py", extras = ["testing"] }
```

Save this as `shaders/math.test.wesl`:

```wesl
import wgsl_test::expectEq;

@test
fn addition() {
    expectEq(3u + 4u, 7u);
}
```

Run it from your project directory:

```bash
pixi run python -m pytest shaders --collect-only -q
pixi run python -m pytest shaders -q
```

Change `7u` to `8u` to see a failure at the assertion:

```text
/path/to/project/shaders/math.test.wesl:5:5: expectEq failed
        expectEq(3u + 4u, 8u);
        ^
actual:   (7.0, 0.0, 0.0, 0.0)
expected: (8.0, 0.0, 0.0, 0.0)
assertions: 1, failures: 1
```

Collection needs no GPU. Execution requires a hardware or software WebGPU adapter.
The bundled assertions need no JavaScript, download, or registration step.
If you disable automatic pytest plugin loading, use `-p wesl.pytest_plugin`.
You can also test compute and fragment shaders from Python with NumPy inputs
and assertions. See [TESTING.md](https://github.com/claydugo/wesl-py/blob/main/TESTING.md).

## Examples

Run these examples from the wesl-py checkout on Linux x86-64.

- [SDF playground](https://github.com/claydugo/wesl-py/blob/main/examples/sdf/README.md) shares geometry between rendering and particle collisions.
- [Multiscale fluorescence](https://github.com/claydugo/wesl-py/blob/main/examples/multiscale/README.md) shares convolution across image axes, scales, and implementations.
- [Lygia color mapping](https://github.com/claydugo/wesl-py/blob/main/examples/lygia/README.md) imports an external shader library to display a heatmap.

These examples open interactive windows:

```bash
pixi run -e examples python -m examples.sdf
pixi run -e examples python -m examples.multiscale
pixi run python tools/fetch_test_shaders.py
pixi run -e examples python -m examples.lygia --library .wesl/lygia
```

The [examples index](https://github.com/claydugo/wesl-py/blob/main/examples/README.md)
also includes RMSNorm and an advanced compaction example.
Both verify compute results without a window or downloaded data.

## Contributing

See [CONTRIBUTING.md](https://github.com/claydugo/wesl-py/blob/main/CONTRIBUTING.md) for development setup and targeted checks.

## License

This project's code uses the [MIT license](https://github.com/claydugo/wesl-py/blob/main/LICENSE).
The packaged wgsl-test shaders use the [upstream MIT license](https://github.com/claydugo/wesl-py/blob/main/licenses/WGSL-TEST-MIT).
See [NOTICE](https://github.com/claydugo/wesl-py/blob/main/licenses/NOTICE) for shader provenance.
