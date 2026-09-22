# Development

The Pixi environments for development support Linux.
Source builds require Rust 1.97.1 or later and a native linker.
The artifact environments also support macOS arm64 and Windows x86-64.

Pixi's default environment provides Python, Rust, Maturin, and the editable
extension. The `test` environment adds pytest.
The `dev` environment adds the development tools and GPU dependencies.
The `testing` environment selects both the `testing` and `examples` extras.

Reinstall the extension after changing Rust source.

```bash
pixi install --locked
pixi reinstall wesl-py
pixi run lint
pixi run format-check
pixi run test-freethreading
pixi run check-dependencies
```

The local `dev` environment provides mypy for stubtest, plus ty, Pyrefly, and Pyright.
These tools are development dependencies in `pixi.toml`.

Stubtest checks the compiled extension. The type checkers check the Python API.
The `dev` environment includes
the optional GPU dependencies needed to resolve their types.

`pixi run lint` runs Ruff, Clippy, all three type checkers, and stubtest.
`pixi run format` applies Ruff and rustfmt. `pixi run format-check` checks both.
Ruff discovers Python files from the repository root.
Behavior tests live under `tests/`. The release tooling lives under `tools/`.
Application examples live under `examples/`.

Cargo denies Clippy's `all` and `pedantic` groups and selected restriction
and nursery lints. `clippy.toml` sets the complexity limits. The Python
binding uses reasoned `expect` attributes for its argument count and length.

`pixi run check-dependencies` runs Machete and Cargo-deny.
Machete checks the binding manifest.
Cargo-deny checks dependencies against the license list in `deny.toml`.
Cargo-deny also checks the RustSec advisory database.
The workflow runs the Rust checks, Ruff, formatting, and all three type checkers on Linux.
The workflow runs stubtest against the development installation on Linux.

The project declares MIT in `LICENSE`, `Cargo.toml`, and `pyproject.toml`.
The packaged wgsl-test shaders have their MIT license and provenance in `licenses/`.
Binary releases also need notices for the Rust code they incorporate.
`licenses/RUST-DEPENDENCIES` contains the upstream license texts and notices.
Maturin includes this file in wheels and source distributions.
Run `pixi run python tools/update_licenses.py` after changing Cargo dependencies.
The script collects notices for all platforms, including build dependencies.
It retrieves missing WESL licenses from the revision recorded in each crate.
CI verifies the generated file before it builds the source distribution.
Maturin includes a CycloneDX SBOM in each wheel's `.dist-info/sboms/` directory.
The SBOM records Cargo dependencies and their declared licenses.
It does not replace the license files that accompany each artifact.

For the Lygia example, first run `pixi run python tools/fetch_test_shaders.py`.

Run the test files that cover the change:

```bash
pixi run -e test python -m pytest tests/test_compile.py -q
pixi run -e test python -m pytest tests/test_check_syntax.py -q
pixi run -e test python -m pytest tests/test_diagnostics.py -q
pixi run -e test python -m pytest tests/test_sources.py -q
pixi run -e gpu python -m pytest tests/test_compute.py -q
pixi run -e testing python -m pytest tests/test_testing.py tests/test_pytest_plugin.py tests/shaders -q
pixi run -e testing-minimum python -m pytest tests/test_pytest_plugin.py -q
```

Use `pixi run test` when you need to run all repository tests and shader examples.
This task runs one pytest session that collects `tests/`.
Example tests, shader tests, and snapshots run in that session.
The Python tests exercise the native Rust extension and the shader entry wrapper.

The task selects the `testing` environment for Python tests.
That environment includes the example dependencies and pytest plugins.
Directory fixtures select shader roots and keep example parameters local.
The root configuration uses importlib mode so test filenames can repeat.

`tests/examples/` contains tests for the application examples and shader testing
examples. `tools/check_sdist.py` checks a source archive supplied as an argument.
CI runs installation smoke checks directly in the workflow.

GPU tests require a WebGPU adapter. Hardware and software adapters both work.
Linux CI selects Vulkan and uses Mesa's software adapter.
Window tests require a display and native cursor positioning.
On Linux, they require X11. Install Xvfb and xauth to run them in an isolated display:

```bash
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 PYGLFW_LIBRARY_VARIANT=x11 xvfb-run -a pixi run -e testing python -m pytest tests/examples/test_example_windows.py -q
```

Pytest skips these tests without a display or when GLFW uses Wayland.

The `freethreading` environment installs a separate copy of the extension on
Python 3.15t. `pixi run test-freethreading` verifies import
without the GIL and concurrent compilation, diagnostics, and shader instrumentation.
The native module declares `gil_used = false`. Each native operation copies its
Python inputs, then detaches from Python while Rust parses or compiles.
Regular CPython releases the GIL during this work.
Concurrent calls can share inputs when callers do not modify those inputs.

The pytest plugin delegates parametrization to pytest's collection hook.
It keeps each collected item and its plugin state.
It attaches WESL reporting methods to the item.
Pytest controls fixture setup, including autouse fixtures.
The runner checks conditional tests after fixture setup.
The plugin tests cover the minimum and current pytest versions.

The `pytest_generate_tests` hook exposes each shader callable during collection.
The collector then removes it from the synthetic module.
This prevents shader names from becoming Python hooks during subsequent collection.

## Shader editing

The checked-in `wesl.toml` files configure wgsl-analyzer for this repository.
Their relative dependency paths point to the shader sources in the checkout.
The `wgsl_test` imports need no editor setup beyond loading the correct manifest.
The Lygia imports require the example setup command above.
Configure your editor to use the nearest `wesl.toml` as the project root.

For another development project with a sibling wesl-py checkout, use:

```toml
edition = "2026_pre"
root = "shaders"

[dependencies]
wgsl_test = { path = "../wesl-py/python/wesl/shaders/wgsl_test" }
```

Save this as your project's `wesl.toml` and set `root` to your shader directory.
The dependency points to source files and does not depend on a Python environment.
The [upstream manifest format](https://wesl-lang.dev/spec/WeslToml#dependencies-entry)
supports relative paths to directories that contain `wesl.toml`.
Its package discovery supports npm and Cargo.

To use the shaders from a Python installation instead, run this from the directory
that contains your project's `wesl.toml`:

```bash
pixi run python -c "import os; from importlib.resources import files; print(os.path.relpath(files('wesl') / 'shaders/wgsl_test'))"
```

Copy the returned path into the dependency entry.
Update it if you move or replace the environment.
This manifest configures the editor. Python compilation registers `wgsl_test` automatically.

## Support

The first release targets CPython 3.12, 3.13, 3.14, 3.15, and 3.15t.
Python 3.15 coverage currently uses the release candidate.

| Platform | Wheel target |
| --- | --- |
| Linux x86-64 | glibc 2.28 or later |
| macOS arm64 | macOS 11 or later |
| Windows x86-64 | Windows 10 or Windows Server 2016 or later |

The Windows minimum follows the [Rust target requirements](https://github.com/rust-lang/rust/blob/1.97.1/src/doc/rustc/src/platform-support/windows-msvc.md).

Each platform has an `abi3` wheel for regular CPython 3.12 and later.
It also has an `abi3t` wheel for regular and free-threaded CPython 3.15 and later.
CI tests each listed Python version. Later versions require verification.
Free-threaded Python 3.13 and 3.14 are outside the first release's scope.

| Extra | Purpose | Verification target |
| --- | --- | --- |
| `examples` | Interactive graphics and compute examples | Python 3.12 on Linux x86-64 |
| `testing` | pytest integration for WESL, compute, and fragment tests | Python 3.12 on Linux x86-64 |

CI installs each extra from the built wheel in a separate uv environment.
It resolves dependencies from PyPI and runs shaders with Mesa's software
Vulkan adapter. It verifies numerical results and renders both viewers
offscreen. Interactive use requires a window server and a supported graphics
adapter. The artifact workflow does not test window events.
GPU extras have no verified free-threaded support yet.

Minimum versions define the supported dependency baseline.
The `testing` extra requires pytest and wgpu-py. The executor does not import NumPy.
The GPU test environment supplies NumPy for Python reference calculations.
The examples require NumPy 2.1 to satisfy pygfx 0.17.
The examples use rendercanvas 2.7.2 as the baseline for window tests.
The imgui-bundle upper bound excludes 1.92.900 because PyPI wgpu 0.32.0
still accesses its removed `cmd_lists_count` attribute.
Conda applies a [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch).
Verify PyPI wheels before raising the bound.
Development tools have minimum versions; `pixi.lock` records their exact versions.

## Artifacts

```bash
pixi run --locked -e artifacts maturin build --release --locked --out dist
pixi run --locked -e artifacts maturin sdist --out dist
pixi run --locked -e artifacts python tools/check_sdist.py dist/wesl_py-0.1.0.tar.gz
pixi run --locked -e artifacts twine check --strict dist/*
```

The artifact environments support Linux x86-64, macOS arm64, and Windows x86-64:

```bash
pixi install --locked -e artifacts
pixi run --locked -e artifacts maturin build --release --locked --out dist -i python
pixi run --locked -e artifacts-py315 maturin build --release --locked --out dist -i python
```

The workflow builds one sdist. Each wheel job downloads and extracts that
archive, then builds wheels from its contents. The source check verifies the
archive contents. CI installs that archive into a fresh uv environment on
Python 3.12 with the minimum Rust version from `Cargo.toml`.
uv installs the build requirements from `pyproject.toml` in isolation.
The installation test verifies that the package works without Maturin installed.

Development checks use the Pixi environments and the editable checkout.
The installation tests for releases use uv environments without an editable installation.
Each `test-wheel` job downloads and installs an exact repaired wheel.

The jobs test the `abi3` wheel on Python 3.12, 3.13, 3.14, and 3.15.
They test the `abi3t` wheel on Python 3.15 and 3.15t.
Both sets run on Linux x86-64, macOS arm64, and Windows x86-64.
They verify package resources and run the existing Python API tests.

The `compute` jobs install the `examples` and `testing` extras separately on
Python 3.12. They run GPU tests, examples, and pytest integration against the
Linux wheel. The `testing` job also runs the plugin tests with pytest 8.2.0.
uv checks installed dependencies without using the contributor lockfile.

Maturin audits and repairs Linux wheels in the manylinux container.
CI repairs macOS wheels with delocate and Windows wheels with delvewheel.
Delocate checks arm64 and targets macOS 11.
The macOS build sets `MACOSX_DEPLOYMENT_TARGET=11.0`.
These checks do not replace testing on the minimum supported OS.

The root `pixi.toml` defines the `artifacts` and `artifacts-py315` environments.
They share Rust and Maturin requirements with the development environments.
They exclude the editable installation and use the root `pixi.lock`.

`artifacts` uses Python 3.12. `artifacts-py315` uses regular Python 3.15.
The `freethreading` environment tests Python 3.15t on Linux.
The Linux wheel builds read Rust and Maturin versions from the locked environment.

The runners use Ubuntu 24.04, macOS 26, and Windows Server 2025.
The manylinux container and macOS deployment target set wheel compatibility
independently of the runner version.

Artifact builds run `abi3audit` on the `cp312-abi3` wheels.
The workflow verifies both ABI families through installation and API tests.
Local verification currently covers Linux.

Maturin builds each ABI family with a separate invocation.
Python 3.12 selects `abi3-py312`. Python 3.15 selects `abi3t-py315`.
The CPU test files include concurrent compilation and diagnostic checks.
Pixi's Python 3.15 environments use conda-forge's `python_rc` label until final
interpreter builds are available. The installation tests use uv's interpreters.
See [Maturin's ABI guidance](https://www.maturin.rs/bindings.html#py_limited_apiabi3).

On Linux, a conda linker can add its environment path to the wheel.
Set the host linker inside the Pixi environment for a local wheel:

```bash
pixi run env CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=cc maturin build --release --locked --out dist
```

Local builds can produce a generic Linux tag. Use the workflow's manylinux
container for release wheels. Inspect the native dependencies before publishing.

## Releases

`Cargo.toml` is the version source. Maturin supplies the Python package version.
Use tags of the form `v0.1.0`. The sdist test rejects a tag that does not match
the Cargo version. Installation tests compare `wesl.__version__` with the
installed package metadata.

Require `checks`, `sdist`, and every `wheel`, `test-wheel`, and `compute` job to
pass before a package release. These include both ABI families and Python 3.15t.
The [support table](#support) defines the initial targets.

The artifact workflow builds and tests packages. It does not upload to PyPI
or TestPyPI. Follow [publish.md](publish.md) for account setup, publication,
and recovery from failed releases.
