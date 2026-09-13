# wesl-py

Python bindings for the [Rust WESL compiler](https://github.com/webgpu-tools/wesl-rs).

WESL extends WGSL with imports and conditional compilation. Compile modular
shaders from Python and pass the generated WGSL to wgpu-py. Compilation and
validation run without a GPU.

## Installation

Requires Python 3.12 or later. No public release is available yet.
Build from a checkout on Linux:

```bash
pixi install --locked
pixi run python -c "import wesl; print(wesl.__version__)"
```

The distribution name is `wesl-py`. Import it as `wesl`.
See [CONTRIBUTING.md](CONTRIBUTING.md#support) for platform support and source builds.

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
result = wesl.compile(modules, features={"enabled": True}, keep=["answer"])
wesl.validate(result.wgsl)
print(result.wgsl)
```

The feature flag selects the implementation of `value()`.
The compiler strips unused declarations by default. `keep=["answer"]`
retains `answer` even though it is not a shader entry point.
Use `device.create_shader_module(code=result.wgsl)` to load it in wgpu-py.

Use `compile_source()` for a string or `compile_file()` for a file.
`check_syntax()` checks WESL syntax. `validate()` checks WGSL semantics with Naga.
Validation does not check the features or limits of a GPU device.

See the [API reference](API.md) for compilation options and diagnostics.

## Examples

- [Compute](examples/compute.py) compiles two shader variants and runs them with wgpu-py.
- [Heightfield](examples/heightfield/README.md) shares shader modules for edges, normals, and lighting.
- [Image processing](examples/README.md) demonstrates multiscale fluorescence enhancement and adaptive local contrast.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and targeted checks.

## License

This project's code uses the [MIT license](LICENSE).
See [NOTICE](licenses/NOTICE) and [THIRDPARTY.yml](licenses/THIRDPARTY.yml) for dependency licenses and notices.
