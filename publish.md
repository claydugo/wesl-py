# Release guide

Publish to GitHub, then PyPI.
Submit the published sdist separately through [conda-forge/staged-recipes](https://conda-forge.org/docs/maintainer/adding_pkgs/#step-by-step-instructions).
See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and local checks.

The [artifact workflow](.github/workflows/artifacts.yml) builds and tests packages.
It does not upload to PyPI or TestPyPI.

## Release verification

`Cargo.toml` is the version source. Maturin supplies the Python package version.
Use tags of the form `v0.1.0`. The sdist test rejects a tag that does not match
the Cargo version. Installation tests compare `wesl.__version__` with the
installed package metadata.

Require `checks`, `sdist`, and every `wheel`, `test-wheel`, and `compute` job to
pass before a package release. These include both ABI families and Python 3.15t.
The [support table](#support) defines the initial targets.

- [ ] Update the Cargo version and [release notes](CHANGELOG.md). Record WESL upgrades, WGSL output changes, and diagnostic changes. Refresh dependency notices when needed.
- [ ] Run the artifact workflow on the release revision. Require all build jobs, wheel installation jobs, and compute jobs to pass. The Python regression tests cover the documented upstream compiler defects.
- [ ] Resolve the Windows expression regression. Its test must pass in every required wheel-test job.
- [ ] Review one sdist and six wheels. Verify both ABI families for each platform in the [support table](#support).
- [ ] Run smoke tests on the minimum supported OS runtimes without relying on conda's shared libraries.
- [ ] Review the README on TestPyPI. `twine check` verifies distribution metadata but does not check Markdown link targets.

## PyPI publication

- [ ] Add and review publication automation separately. Upload tested artifacts without rebuilding. Verify the required platform and ABI combinations. Compare existing file hashes before resuming a partial upload.
- [ ] Set up the PyPI and TestPyPI accounts with verified email addresses and two-factor authentication. Store the recovery codes. [PyPI account requirements](https://pypi.org/help/#twofa)
- [ ] Configure a pending Trusted Publisher for `wesl-py` on PyPI and a separate publisher on TestPyPI. Bind each to the GitHub repository and the chosen publishing workflow and environment. A pending publisher does not reserve the package name. [First publication with OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [ ] Rehearse on TestPyPI before the first PyPI release. Use Trusted Publishing with attestations. [PyPI publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/), [Automatic attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [ ] Create the matching version tag and GitHub release. Publish the verified artifacts without rebuilding. Attach the same files to the GitHub release. Compare published file hashes with the tested artifacts. Verify installation, compilation, and syntax checks in a fresh uv environment. Update the README installation instructions after publication.

For a partial upload, retain the original artifacts. Compare hashes of files
already on PyPI before uploading the missing files. For a broken release,
yank it with a reason and publish a corrected version. Never reuse its version.
See [PyPI's upload rules](https://docs.pypi.org/api/upload/) and
[yanking guidance](https://docs.pypi.org/project-management/yanking/).

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
The `gpu` environment includes NumPy to calculate expected results in Python.
The examples require NumPy 2.1 to satisfy pygfx 0.17.
The examples use rendercanvas 2.7.2 as the baseline for window tests.

The imgui-bundle upper bound excludes 1.92.900 because PyPI wgpu 0.32.0
still accesses its removed `cmd_lists_count` attribute.
Conda applies a [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch).
Verify PyPI wheels before raising the bound.
Development tools have minimum versions; `pixi.lock` records their exact versions.

## Dependency licenses

The project declares MIT in `LICENSE`, `Cargo.toml`, and `pyproject.toml`.
The packaged wgsl-test shaders have their MIT license and provenance in `licenses/`.
Binary releases also need notices for the Rust code they incorporate.
`licenses/RUST-DEPENDENCIES` contains the upstream license texts and notices.
Maturin includes this file in wheels and source distributions.

Run `pixi run python tools/update_licenses.py` after changing Cargo dependencies.
The script collects notices for all platforms, including build dependencies.
It retrieves missing WESL licenses from the revision recorded in each crate.
CI verifies the generated file before it builds the source distribution.

Maturin includes an SBOM in CycloneDX format in each wheel's `.dist-info/sboms/` directory.
The SBOM records Cargo dependencies and their declared licenses.
It does not replace the license files that accompany each artifact.

## Artifacts

The artifact environments support Linux x86-64, macOS arm64, and Windows x86-64.
Run these commands from the repository root:

```bash
pixi install --locked -e artifacts
pixi run --locked -e artifacts maturin build --release --locked --out dist -i python
pixi run --locked -e artifacts-py315 maturin build --release --locked --out dist -i python
pixi run --locked -e artifacts maturin sdist --out dist
pixi run --locked -e artifacts python tools/check_sdist.py dist/wesl_py-0.1.0.tar.gz
pixi run --locked -e artifacts twine check --strict dist/*
```

Use the current Cargo version in the source archive filename.

### CI verification

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
On macOS, CI repairs wheels with delocate. On Windows, CI uses delvewheel.
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
pixi run --locked -e artifacts env CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=cc maturin build --release --locked --out dist
```

Local builds can produce a generic Linux tag. Use the workflow's manylinux
container for release wheels. Inspect the native dependencies before publishing.
