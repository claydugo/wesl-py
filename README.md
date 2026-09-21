# wesl-py

Python bindings for the [Rust WESL compiler](https://github.com/webgpu-tools/wesl-rs).

WESL extends WGSL with imports and conditional compilation. Compile modular
shaders from Python and pass the generated WGSL to wgpu-py. Compilation runs without a GPU.

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

```python
import wesl

modules = {
    "package::main": """
        import package::settings::value;
        fn answer() -> u32 { return value(); }
    """,
    "package::settings": """
        @if(enabled) fn value() -> u32 { return 7u; }
        @if(!enabled) fn value() -> u32 { return 3u; }
    """,
}
result = wesl.compile(
    modules,
    options=wesl.CompileOptions(
        features=wesl.Features(flags={"enabled": True}),
        keep=["answer"],
    ),
)
print(result.wgsl)
```

The feature flag selects the implementation of `value()`.
The compiler strips unused declarations by default. `CompileOptions(keep=["answer"])`
retains `answer` even though it is not a shader entry point.
Use `device.create_shader_module(code=result.wgsl)` to load it in wgpu-py.

Use `compile_source()` for a string or `compile_file()` for a file.
`check_syntax()` checks WESL syntax. Compilation runs upstream WESL checks.
The target GPU runtime validates the generated shader and pipeline.

See the [API reference](https://github.com/claydugo/wesl-py/blob/main/API.md) for compilation options and diagnostics.

## Library imports

Register a directory to import an external shader library.
For a Lygia checkout at `../lygia`:

```python
import wesl

compiler = wesl.Compiler(dependencies={"lygia": "../lygia"})
result = compiler.compile_source("""
    import lygia::color::palette::heatmap::heatmap;
    @compute @workgroup_size(1) fn main() {
        let color = heatmap(0.5);
    }
""")
```

The compiler reads imported files from that directory.
You manage the library sources. See the [Lygia example](https://github.com/claydugo/wesl-py/blob/main/examples/lygia/README.md)
for image processing and tests.

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

Collection needs no GPU. Execution requires a hardware or software WebGPU adapter.
The bundled assertions need no JavaScript, download, or registration step.
If you disable automatic pytest plugin loading, use `-p wesl.pytest_plugin`.
You can also test compute and fragment shaders from Python with NumPy inputs
and assertions. See [TESTING.md](https://github.com/claydugo/wesl-py/blob/main/TESTING.md).

## Examples

Run these examples from the wesl-py checkout.

- [SDF playground](https://github.com/claydugo/wesl-py/blob/main/examples/sdf/README.md) shares geometry between rendering and particle collisions.
- [Multiscale fluorescence](https://github.com/claydugo/wesl-py/blob/main/examples/multiscale/README.md) shares convolution across image axes, scales, and implementations.

Both examples open interactive windows:

```bash
pixi run -e examples python -m examples.sdf
pixi run -e examples python -m examples.multiscale
```

The [RMSNorm and compaction examples](https://github.com/claydugo/wesl-py/blob/main/examples/README.md#headless-compute)
run without a window or downloaded data.

## Contributing

See [CONTRIBUTING.md](https://github.com/claydugo/wesl-py/blob/main/CONTRIBUTING.md) for development setup and targeted checks.

## License

This project's code uses the [MIT license](https://github.com/claydugo/wesl-py/blob/main/LICENSE).
The packaged wgsl-test shaders use the [upstream MIT license](https://github.com/claydugo/wesl-py/blob/main/licenses/WGSL-TEST-MIT).
See [NOTICE](https://github.com/claydugo/wesl-py/blob/main/licenses/NOTICE) for shader provenance.
