# wesl-py

Python bindings for the [Rust WESL compiler](https://github.com/webgpu-tools/wesl-rs).

WESL extends WGSL with imports and conditional compilation. Compile modular
shaders from Python and pass the generated WGSL to wgpu-py. Compilation runs without a GPU.

## Installation

Requires Python 3.12 or later. No public release is available yet.
Build from a checkout on Linux:

```bash
pixi install --locked
pixi run python -c "import wesl; print(wesl.__version__)"
```

The distribution name is `wesl-py`. Import it as `wesl`.
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

## Shader tests

Collect WESL `@test` functions with pytest, or test compute and fragment shaders
from Python with NumPy inputs and assertions. See [TESTING.md](TESTING.md).

```bash
pixi run -e testing python -m pytest tests/shaders -v
```

## Examples

- [SDF playground](examples/sdf/README.md) shares geometry between rendering and particle collisions.
- [Multiscale fluorescence](examples/multiscale/README.md) shares convolution across image axes, scales, and implementations.

Both examples open interactive windows:

```bash
pixi run -e examples python -m examples.sdf
pixi run -e examples python -m examples.multiscale
```

## Contributing

See [CONTRIBUTING.md](https://github.com/claydugo/wesl-py/blob/main/CONTRIBUTING.md) for development setup and targeted checks.

## License

This project's code uses the [MIT license](https://github.com/claydugo/wesl-py/blob/main/LICENSE).
See [NOTICE](https://github.com/claydugo/wesl-py/blob/main/licenses/NOTICE) and [THIRDPARTY.yml](https://github.com/claydugo/wesl-py/blob/main/licenses/THIRDPARTY.yml) for dependency licenses and notices.
