# Development

The root Pixi workspace supports Linux.
Source builds require Rust 1.97.1 or later and a native linker.
The `ci` workspace also supports macOS arm64 and Windows x86-64.
Pixi installs the Rust toolchain, Python tools, and the editable extension.
Reinstall the extension after changing Rust source.

```bash
pixi install --locked
pixi reinstall wesl-py
pixi run lint
pixi run format-check
pixi run -e dev stubtest
pixi run -e testing ty check python/wesl tools/benchmark.py tools/profile_startup.py
pixi run rust-format-check
pixi run clippy
pixi run machete
pixi run deny
pixi run audit
pixi run licenses
```

The local `dev` environment provides mypy for stubtest.

Stubtest checks the compiled extension. Run `ty` in the `testing` environment
to check the Python API with its optional dependencies.

Cargo denies Clippy's `all` and `pedantic` groups and selected restriction
and nursery lints. `clippy.toml` sets the complexity limits. The Python
binding uses reasoned `expect` attributes for its argument count and length.

Pixi installs the dependency tools. Machete checks the binding manifest.
Cargo-deny checks dependencies against the license list in `deny.toml`.
Cargo-deny and Cargo-audit check the RustSec advisory database.
The workflow runs the Rust checks, Ruff, formatting, and ty on Linux.
The artifact tests run stubtest against installed wheels on each platform.

The project declares MIT in `LICENSE`, `Cargo.toml`, and `pyproject.toml`.
Dependencies retain their own licenses and notices in `licenses/`.
Maturin includes a CycloneDX SBOM in each wheel's `.dist-info/sboms/` directory.
The SBOM records Cargo dependencies and their declared licenses.
It does not replace the license files that accompany each artifact.

`pixi run licenses` checks the dependency licenses against `licenses/THIRDPARTY.yml`.
It also rejects empty license lists and empty license text.
After changing dependencies, regenerate the bundle and review its changes:

```bash
pixi run cargo bundle-licenses --format yaml --prefer MIT --previous licenses/THIRDPARTY.yml --output licenses/THIRDPARTY.yml
```

Fill the missing license texts before accepting the bundle.
The WESL 0.4.4 entries use the [upstream MIT text](https://github.com/webgpu-tools/wesl-rs/blob/666362633e5235fa56c6a351d0aea5a502fa42e3/LICENSE-MIT).
Their copyright notice comes from [NOTICE](licenses/NOTICE).

`licenses/RUST.html` contains the Rust 1.97.1 standard library notices.
It copies `share/doc/rust/COPYRIGHT-library.html` from that toolchain.
It also includes the `addr2line` 0.25.1, `adler2` 2.0.1, `miniz_oxide` 0.8.9,
and `object` 0.37.3 sections from `share/doc/rust/COPYRIGHT.html`.
These versions come from Rust's [library lockfile](https://github.com/rust-lang/rust/blob/1.97.1/library/Cargo.lock).
Refresh these notices when changing the Rust version used for release wheels.
Use Rust's [copyright documentation](https://github.com/rust-lang/rust/blob/1.97.1/COPYRIGHT) to locate the upstream notices.

Use `pixi run format` to apply Python formatting. Run the test files that
cover the change:

```bash
pixi run python -m pytest tests/test_compile.py -q
pixi run python -m pytest tests/test_check_syntax.py -q
pixi run python -m pytest tests/test_diagnostics.py -q
pixi run python -m pytest tests/test_sources.py -q
pixi run -e gpu python -m pytest tests/test_compute.py -q
pixi run -e testing python -m pytest tests/test_testing.py tests/test_pytest_plugin.py tests/shaders -q
pixi run -e testing-minimum python -m pytest tests/test_pytest_plugin.py -q
```

The pytest plugin delegates parametrization to pytest's collection hook.
It keeps each collected item and its plugin state.
It attaches WESL setup and reporting methods to the item.
Enabled tests call the item's original setup method.
It uses `_request` to check WESL conditions before GPU fixtures run.
The plugin tests cover this private access on the minimum and current pytest versions.

The `pytest_generate_tests` hook exposes each shader callable during collection.
The collector then removes it from the synthetic module.
This prevents shader names from becoming Python hooks during subsequent collection.

`pixi run benchmark` measures compilation of 65 in-memory modules.
`pixi run profile-startup` separates Python startup, import, and Pixi overhead.
Both commands report their units and measurement settings as JSON.

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

CI installs the extras from PyPI and runs their shaders with Mesa's software
Vulkan adapter. It verifies numerical results and renders both viewers
offscreen. Interactive use requires a window server and a supported graphics
adapter. The artifact workflow does not test window events.
Extras have no verified free-threaded support yet.

## Artifacts

```bash
pixi run maturin build --release --locked --out dist
pixi run --locked --manifest-path ci/pixi.toml maturin sdist --out dist
pixi run --locked --manifest-path ci/pixi.toml python tools/test_sdist.py dist/wesl_py-0.1.0.tar.gz
pixi run --locked --manifest-path ci/pixi.toml twine check --strict dist/*
```

On macOS arm64 or Windows x86-64, use the artifact workspace:

```bash
pixi install --locked --manifest-path ci/pixi.toml
pixi run --locked --manifest-path ci/pixi.toml maturin build --release --locked --out dist -i python
pixi run --locked --manifest-path ci/pixi.toml -e python315 maturin build --release --locked --out dist -i python
```

The workflow builds one sdist. Each wheel job downloads and extracts that
archive, then builds and tests its contents. The source test checks the
archive contents and installs the sdist into a temporary Pixi environment.
Pixi uses build isolation to install the requirements from `pyproject.toml`.
The test environment provides Python and Rust. It does not provide Maturin.

Use `tools/test_artifact.py` with a wheel filename to test that installation
outside the checkout. Its `--python` option selects Python 3.12 through 3.15.
Use `--python 3.15t` for the free-threaded interpreter.
The `--stubtest` option also runs mypy stubtest.
Use `--extra testing` to verify the pytest plugin and GPU test helpers.
Use `--extra examples` to install the dependencies and run the examples. `--compute` also
requires a software Vulkan adapter and runs `tests/test_compute.py`.

The script checks package versions, metadata, typing files, and license files.
It also verifies the SBOM format, project identity, and direct Cargo dependencies.
It compares dependency requirements and extras with `pyproject.toml`.
Its `--platform-tag` option requires the expected wheel tag. CI requires
`manylinux_2_28_x86_64`, `macosx_11_0_arm64`, or `win_amd64` for each platform.
The macOS build sets `MACOSX_DEPLOYMENT_TARGET=11.0`.

`tools/test_wheel_native.py` audits each wheel with auditwheel on Linux,
delocate on macOS, or delvewheel on Windows. It rejects unsupported Linux
symbol versions, external libraries, and absolute RPATHs.

The macOS audit checks arm64 and compatibility with macOS 11.
The Windows audit checks
x86-64 and the Python DLL for the wheel's ABI. Repair tools run on temporary
copies. The audit rejects changes to native files or the addition of files.
These checks do not replace testing on the minimum supported OS.

The workflow builds wheels for Linux, macOS, and Windows with Rust 1.97.1.
This matches the minimum in `Cargo.toml`.
The runners use Ubuntu 24.04, macOS 26, and Windows Server 2025.
The manylinux container and macOS deployment target set wheel compatibility
independently of the runner version.

Artifact builds use `ci/pixi.lock` and audit the Python ABI with `abi3audit`.
Local verification currently covers Linux.

Maturin builds each ABI family with a separate invocation.
Python 3.12 selects `abi3-py312`. Python 3.15 selects `abi3t-py315`.
Pass the matching wheel filename to the test script.
The `abi3t` wheel requires `--abi-tag cp315-abi3.abi3t`.
Use `--find-links dist` to test installer selection with both wheel families
present.

The script compares the installed tags and extension hash with
the expected wheel. It tests `abi3t` on regular and free-threaded Python 3.15.
It verifies that import leaves the GIL disabled on 3.15t.
The CPU test files include concurrent compilation and diagnostic checks.
Python 3.15 environments use conda-forge's `python_rc` label until final
interpreter builds are available.
See [Maturin's ABI guidance](https://www.maturin.rs/bindings.html#py_limited_apiabi3).

On Linux, a conda linker can add its environment path to the wheel.
Set the host linker inside the Pixi environment for a local wheel:

```bash
pixi run env CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=cc maturin build --release --locked --out dist
```

Local builds can produce a generic Linux tag. Use the workflow's manylinux
container for release wheels. Inspect the native dependencies before publishing.

The [conda recipe](recipe/recipe.yaml) builds from this checkout.
It uses the regular CPython ABI3 extension with a Python 3.12 minimum.
It does not provide a free-threaded extension. Replace the checkout source
with the published sdist URL and hash before submission to conda-forge:

```bash
rattler-build build --recipe recipe/recipe.yaml --output-dir target/conda
```

## Releases

`Cargo.toml` is the version source. Maturin supplies the Python package version.
Use tags of the form `v0.1.0`. The sdist test rejects a tag that does not match
the Cargo version. Installed wheel tests compare both with `wesl.__version__`.

Require the `checks`, `sdist`, all three `wheel` jobs, and `compute` to pass
before a package release. These include Python 3.15 and 3.15t coverage.
The [support table](#support) defines the initial targets.

The artifact workflow builds and tests packages. It does not upload to PyPI
or TestPyPI. Publishing automation, account setup, and remaining release checks
are in [TODO.md](TODO.md). Complete those tasks before publication.
The planned release procedure is:

1. Update the Cargo version and [release notes](CHANGELOG.md).
   Record WESL upgrades, WGSL output changes, and diagnostic changes.
   Refresh dependency notices when needed.
2. Run the required checks on the release revision. Review one sdist and
   six wheels, with both ABI families for each platform.
3. Rehearse publication and installation on TestPyPI with those artifacts.
4. Create the matching version tag and GitHub release. Upload the tested
   artifacts through Trusted Publishing without rebuilding.
5. Verify the PyPI file hashes and installation in a fresh Pixi environment.
   Compile a shader and check its syntax. Verify the GitHub release attachments.

For a partial upload, retain the original artifacts. Compare hashes of files
already on PyPI before uploading the missing files. For a broken release,
yank it with a reason and publish a corrected version. Never reuse its version.
See [PyPI's upload rules](https://docs.pypi.org/api/upload/) and
[yanking guidance](https://docs.pypi.org/project-management/yanking/).

Conda-forge submission follows the first PyPI release. Additional platforms,
free-threaded Python 3.13/3.14, and broader extras coverage can follow later.
