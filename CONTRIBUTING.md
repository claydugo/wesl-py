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
| `docs/` | API reference and shader testing guide |

See the [API reference](docs/api.md) for compiler behavior and
[shader testing guide](docs/testing.md) for the executor and pytest fixtures.

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
See the [testing examples](tests/examples/testing/README.md) for snapshot updates
and [window tests](#window-tests) for display requirements.

The WESL tests exercise the SDF example's production functions.
The Python tests verify the executor and its failure reports.
The assertion syntax follows the upstream
[wgsl-test API](https://github.com/webgpu-tools/wesl-js/blob/main/packages/wgsl-test/API.md).
Execution uses wgpu-py. It does not require Node.js or the JavaScript test runner.

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
  See [thread behavior](docs/api.md#threads).
- Rust dependencies: `pixi run check-dependencies` runs Machete against the binding
  manifest and Cargo-deny for licenses and RustSec advisories.

`pixi run test` runs all Rust tests and one pytest session over `tests/`, including
examples, shader tests, and snapshots. It selects the `testing` environment.
Use the targeted commands above while working on a change.
For prose-only changes, verify links and commands in the affected documentation.

### Window tests

GPU tests require a WebGPU adapter. Hardware and software adapters both work.
Linux CI selects Vulkan and uses Mesa's software adapter.
Window tests require a display and native cursor positioning.
On Linux, they require X11. Install Xvfb and xauth to run them in an isolated display:

```bash
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 PYGLFW_LIBRARY_VARIANT=x11 xvfb-run -a pixi run -e testing python -m pytest tests/examples/test_example_windows.py -q
```

Pytest skips these tests without a display or when GLFW uses Wayland.

## Edit shaders

Configure your editor to use the nearest `wesl.toml` as the wgsl-analyzer project root.
The manifests point to shader sources in the checkout.
See [shader editing](docs/testing.md#shader-editing) for setup in other projects.

## Open a pull request

Describe the problem, the resulting behavior, and the checks you run.
Keep the change focused. Include a regression test when fixing a behavior defect.
Update the relevant guide or example when changing the public API.

The [CI workflow](.github/workflows/artifacts.yml) runs development checks and
verifies built packages.
It tests Python 3.12 wheels on Linux, macOS, and Windows.
Linux also tests those wheels on Python 3.13, 3.14, and 3.15.
The free-threaded wheel runs on Linux with Python 3.15 and 3.15t.

## Maintenance

- Keep the ImGui upper bound while PyPI wgpu 0.32.0 uses the removed
  `cmd_lists_count` attribute. Conda's [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch)
  makes newer versions work. Verify the PyPI dependencies before changing the bound.
- Retain the Rust statement traversal until the upstream visitor covers plain
  `else` branches. WESL 0.5.0 omits them in [its visitor](https://github.com/webgpu-tools/wesl-rs/blob/63a3627ba31258565df177f3f553beed8ff45338/crates/wesl/src/pass/visit.rs).
- Review GPU resource and ImGui context cleanup for repeated viewer use.
  The SDF viewer has no explicit teardown. Its particle buffer remains usable
  after the canvas closes while the viewer remains referenced.
  The [wgpu renderer](https://github.com/pygfx/wgpu-py/blob/main/wgpu/utils/imgui/imgui_renderer.py)
  creates the ImGui context without a cleanup method.

### Pytest plugin

Directory fixtures select shader roots and keep example parameters local.
The root configuration uses importlib mode so test filenames can repeat.

The pytest plugin delegates parametrization to pytest's collection hook.
It keeps each collected item and its plugin state.
It attaches WESL reporting methods to the item.
Pytest controls fixture setup, including autouse fixtures.
The runner checks conditional tests after fixture setup.
The plugin tests cover the minimum and current pytest versions.

The `pytest_generate_tests` hook exposes each shader callable during collection.
The collector then removes it from the synthetic module.
This prevents shader names from becoming Python hooks during subsequent collection.

The plugin modifies undocumented pytest traceback fields to preserve shader locations
in terminal, JUnit, and xdist reports. Keep the regression tests for these reports.
Pytest supports [custom failure strings](https://docs.pytest.org/en/stable/example/nonpython.html),
but a replacement must preserve the locations in all three formats.
