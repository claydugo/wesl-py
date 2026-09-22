# Contributing

Bug reports, documentation fixes, examples, and code contributions are welcome.
If you want to try wesl-py, start with the [README](README.md) and
[examples](examples/README.md).

## Report a problem or suggest a change

Open an [issue](https://github.com/claydugo/wesl-py/issues) with a small example,
what you expect, and what happens instead.
For a bug, include the error output, your Python and wesl-py versions, and your OS.
For a GPU failure, also include the adapter and backend.

Questions about unclear documentation are useful reports too.
For a larger change, an issue is a good place to discuss the approach first.

## Set up a checkout

Install [Pixi](https://pixi.sh).
The development environments support Linux x86-64.
Pixi provides Python, Rust, Maturin, and an editable installation of wesl-py.
Source builds require Rust 1.97.1 or later and a native linker.

Clone the repository and run a small test file to verify the setup:

```bash
git clone https://github.com/claydugo/wesl-py.git
cd wesl-py
pixi install --locked -e test
pixi run -e test python -m pytest tests/test_check_syntax.py -q
```

This test needs no GPU.
Run the commands below from the repository root.

On macOS arm64 and Windows x86-64, use the `artifacts` environment to build a wheel:

```bash
pixi run --locked -e artifacts maturin build --release --locked --out dist -i python
```

Python changes take effect in the editable installation.
After changing Rust, rebuild the extension in the environment you use:

```bash
pixi reinstall --locked -e test wesl-py
```

Replace `test` with `gpu`, `testing`, or `dev` when working in those environments.
The default environment also contains the editable extension.
The `freethreading` environment has a separate, non-editable installation.
Reinstall it after changing either Python or Rust code before testing Python 3.15t.

## Find the code

| Location | Contents |
| --- | --- |
| `python/wesl/` | Python API, type stubs, shader executor, and pytest plugin |
| `src/` | Rust bindings and shader instrumentation |
| `python/wesl/shaders/wgsl_test/` | Bundled upstream assertion shaders |
| `tests/` | Python, Rust, and shader tests |
| `examples/` | Graphics and compute examples, with tests in `tests/examples/` |
| `tools/` | Release checks, license notices, and shader downloads |

See the [API reference](API.md) for compiler behavior and
[shader testing guide](TESTING.md) for the executor and pytest fixtures.

## Verify your change

Run the tests that cover the behavior you change.
For a compiler change, for example:

```bash
pixi run -e test python -m pytest tests/test_compile.py -q
```

The `test` environment adds pytest without GPU dependencies.
Use `tests/test_check_syntax.py`, `tests/test_diagnostics.py`, or
`tests/test_sources.py` for syntax checks, diagnostics, or source loading.
The Rust regression test runs with
`pixi run -e test cargo test --locked --test upstream`.

GPU checks use additional environments:

| Area | Command |
| --- | --- |
| Generated WGSL | `pixi run -e gpu python -m pytest tests/test_compute.py -q` |
| Shader executor and pytest plugin | `pixi run -e testing python -m pytest tests/test_testing.py tests/test_pytest_plugin.py tests/shaders -q` |
| Minimum pytest version | `pixi run -e testing-minimum python -m pytest tests/test_pytest_plugin.py -q` |

The `gpu` environment adds NumPy and wgpu-py.
The `testing` environment also includes the example dependencies and pytest plugins.
These tests accept hardware and software WebGPU adapters.
Each [example](examples/README.md) documents its own test command.
For Lygia tests, first run `pixi run python tools/fetch_test_shaders.py`.
See [repository tests](TESTING.md#repository-tests) for snapshots and window tests.

For code changes, run the style and type checks:

```bash
pixi run lint
pixi run format-check
```

These tasks select the `dev` environment.
After a Rust change, run `pixi reinstall --locked -e dev wesl-py` first.
`lint` runs Ruff, Clippy, ty, Pyrefly, Pyright, and native stubtest.
The type checkers check the Python API. Stubtest checks the compiled extension.
`pixi run format` applies Ruff and rustfmt.

Ruff discovers Python files from the repository root.
Cargo denies Clippy's `all` and `pedantic` groups plus selected restriction and nursery lints.
See [Cargo.toml](Cargo.toml) and [clippy.toml](clippy.toml) for the rules and complexity limits.
The binding uses `expect` attributes with reasons for its argument count and length.

Run these additional checks when the change affects the corresponding area:

- Native threading: `pixi run test-freethreading` verifies import without the GIL,
  concurrent compilation, diagnostics, and shader instrumentation on Python 3.15t.
  See [thread behavior](API.md#threads).
- Rust dependencies: `pixi run check-dependencies` runs Machete against the binding
  manifest and Cargo-deny for licenses and RustSec advisories.
  Run `pixi run python tools/update_licenses.py` after changing Cargo dependencies.

`pixi run test` runs all Rust tests and one pytest session over `tests/`, including
examples, shader tests, and snapshots. It selects the `testing` environment.
Use the targeted commands above while working on a change.
For prose-only changes, verify links and commands in the affected documentation.

## Edit shaders

Configure your editor to use the nearest `wesl.toml` as the wgsl-analyzer project root.
The manifests point to shader sources in the checkout.
See [shader editing](TESTING.md#shader-editing) for setup in other projects.

## Open a pull request

Describe the problem, the resulting behavior, and the checks you run.
Keep the change focused. Include a regression test when fixing a behavior defect.
Update the relevant guide or example when changing the public API.

The [CI workflow](.github/workflows/artifacts.yml) runs development checks and
verifies built packages.
