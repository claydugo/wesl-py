Research checked on 2026-09-13. Publish to GitHub, then PyPI, then conda-forge.
Keep Pixi for environments and Maturin for extension builds.

GitHub publication:

- [x] Use published, unmodified `wesl` and `wgsl-parse` crates. Remove `vendor/`, Cargo path overrides, parser patch metadata, and patch packaging rules.
- [x] Remove the obsolete patch drafts and the `probe-patch` task. Review tests and documentation that assume local parser fixes. Keep the upstream compiler version available for bug reports. Treat parser defects as upstream issues.
- [x] License this project's code under MIT. Add the copyright holder and year to the project license. Update `Cargo.toml` and the README. Remove the project's Apache license after preserving any required dependency notices. [MIT guidance](https://choosealicense.com/licenses/mit/)
- [x] Add repository and issue URLs to package metadata. Document the distribution name `wesl-py`, the import name `wesl`, and the upstream issue tracker.
- [x] Document checkout installation with Pixi and the release procedure. Keep `Cargo.toml` as the version source. Verify that release tags, package metadata, and `wesl.__version__` agree. Record WESL and Naga upgrades and changes to WGSL output or diagnostics in release notes.

CI preparation:

- [x] Define the first release's support matrix and required checks. Specify support for the base package and extras separately. Mark tasks that can follow the first release.
- [x] Track `ci/pixi.lock` for the existing Linux, macOS, and Windows targets. Use locked Pixi environments and `--locked` Cargo builds in CI. Verify the declared Rust minimum. [Pixi CI guidance](https://pixi.prefix.dev/latest/integration/ci/github_actions/)
- [x] Run Ruff, Python formatting checks, ty, stubtest, rustfmt, and Clippy in CI. Keep the dependency checks. Run the relevant Python test files against installed wheels outside the checkout.
- [x] Test the `abi3-py312` wheel on CPython 3.12, 3.13, and 3.14. Add Python 3.15 prerelease coverage now. Verify each supported Python minor version even when it shares a wheel. [Stable ABI testing](https://docs.python.org/3.15/c-api/stable.html#stable-abi-caveats)
- [x] Build `abi3-py312` and `abi3t-py315` wheels with separate Maturin invocations. Pass each wheel explicitly to the test script. Verify installer selection when both wheel families exist. Test the `abi3t` wheel on Python 3.15 and 3.15t. Assert that 3.15t supports free threading and that import leaves the GIL disabled. Run the concurrency tests. Support for earlier free-threaded interpreters requires separate version-specific wheels. [Maturin ABI builds](https://www.maturin.rs/bindings.html#py_limited_apiabi3), [PyO3 free threading](https://pyo3.rs/main/free-threading)
- [x] Add a Linux integration job for the compute tests with Mesa's software Vulkan adapter. Keep GPU dependencies in the GPU environment. [wgpu-py CI example](https://github.com/pygfx/wgpu-py/blob/main/.github/workflows/ci.yml)
- [x] Pin GitHub Actions to full commit SHAs and configure automated updates. Keep workflow permissions at `contents: read`. Grant publishing permissions only to the publishing job. [GitHub Actions guidance](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions)

PyPI release:

Artifact tests pass on Linux and macOS. Windows tests pass on Python 3.12
through 3.15 with the `abi3` wheel.

- [x] Generate `licenses/THIRDPARTY.yml` from the locked Rust dependencies with `cargo-bundle-licenses`. Verify the copyright notices and license texts. Resolve missing entries from the matching upstream sources. Add a CI check for changes to the bundle and reject empty license text. Include the release toolchain's runtime notices in `licenses/RUST.html`. Refresh them when upgrading Rust. [License bundle workflow](https://github.com/sstadick/cargo-bundle-licenses#usage)
- [x] Declare `project.license-files` and include the project license and dependency notices in wheels and the sdist. Verify `License-File` entries and the actual archive contents. An SBOM or cargo-deny check does not replace the license texts. [PyPA license files](https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/)
- [x] Keep MIT project metadata and Maturin's CycloneDX SBOM in each wheel. Retain dependency notices. Verify the SBOM format, project identity, and direct Cargo dependencies. [Pydantic Core convention](https://github.com/pydantic/pydantic-core/blob/main/pyproject.toml), [Core metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/#license-expression), [Maturin metadata implementation](https://github.com/PyO3/maturin/blob/v1.15.0/src/metadata.rs)
- [x] Build Linux x86-64 wheels in the existing manylinux container and enforce `manylinux_2_28` compatibility. Reject generic `linux` wheel tags and absolute Pixi RPATHs. Set the local linker overrides inside the Pixi environment and document the command. [Maturin distribution guidance](https://www.maturin.rs/distribution.html#build-wheels)
- [ ] Build and test macOS arm64 and Windows x86-64 wheels on their native runners. Set an explicit macOS deployment target. Document the initial platform coverage and source build requirements.
- [ ] Resolve the Windows Python 3.15 `abi3t` import failure. Conda-forge's regular 3.15.0rc2 build omits `python3t.dll`. Keep the failing check until the runtime supports this ABI. [PyO3 DLL requirements](https://pyo3.rs/v0.29.2/faq#im-trying-to-call-python-from-rust-but-i-get-status_dll_not_found-or-status_entrypoint_not_found)
- [x] Build the sdist from the release revision and build every release wheel from that same archive. Also install the sdist through Pixi with PEP 517 build isolation enabled to verify the declared build requirements. Include `Cargo.lock`, typing files, tests, and required notices. Exclude obsolete patch material and generated binaries. [Maturin source builds](https://www.maturin.rs/distribution.html#build-wheels), [Pixi build isolation](https://pixi.prefix.dev/latest/reference/pixi_manifest/#no-build-isolation)
- [x] Verify wheel tags, metadata, notices, `py.typed`, and `_native.pyi`. Compare dependency requirements and extras with `pyproject.toml`. Verify installation in a clean Pixi environment without Rust or GPU packages. Check the README rendering with `twine check` from Pixi.
- [x] Audit native dependencies with auditwheel, delocate, and delvewheel. Verify the Linux symbol baseline, macOS deployment target, Windows Python DLL, and absence of libraries that need bundling. Reject absolute RPATHs and repairs that change native files.
- [ ] Run smoke tests on the minimum supported OS runtimes without relying on conda's shared libraries.
- [x] Run `abi3audit` on the `cp312-abi3` wheels to verify that their Python symbols match the declared ABI minimum. Keep interpreter tests for runtime behavior. [ABI audit guidance](https://github.com/pypa/abi3audit)
- [ ] Run the configured extras checks on GitHub. Verify `dev` on Python 3.12 on all three platforms. Verify `compute`, `fractal`, and `examples` on Python 3.12 on Linux. Local Linux checks cover installation and imports. The compute tests use Mesa. Broader extras coverage can follow the first release.
- [ ] Set up the PyPI and TestPyPI accounts with verified email addresses and two-factor authentication. Store the recovery codes. [PyPI account requirements](https://pypi.org/help/#twofa)
- [ ] Configure a pending Trusted Publisher for `wesl-py` on PyPI and a separate publisher on TestPyPI. Bind each to the GitHub repository, release workflow, and publishing environment. A pending publisher does not reserve the package name. [First publication with OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [ ] Add a publishing job that depends on successful artifact tests. Trigger publication from a versioned release. Give only this job `id-token: write` and use a dedicated publishing environment. Download and publish the tested artifacts without rebuilding them. [PyPA release workflow](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [ ] Verify that the sdist and every expected platform and ABI wheel exist before the first upload. Prevent concurrent uploads for the same version. Document recovery from partial uploads using the original artifacts. Verify existing file hashes before resuming. PyPI stops accepting new files for a release after 14 days. [PyPI upload behavior](https://docs.pypi.org/api/upload/), [PyPI upload window](https://blog.pypi.org/posts/2026-07-22-releases-now-reject-new-files-after-14-days/)
- [ ] Use `pypa/gh-action-pypi-publish` with Trusted Publishing and its default attestations. Rehearse on TestPyPI before the first PyPI release. Attach the same tested files to the GitHub release and update the README installation instructions. [PyPI publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/), [Automatic attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [ ] Verify installation from PyPI after publication. Compare the published file hashes with the tested artifacts. Run an example that compiles and validates a shader in a fresh Pixi environment.
- [ ] Document how to yank a broken release and publish a corrected version. Record the reason for yanking. PyPI does not permit reuse of an uploaded filename, even after deletion. [Yanking](https://docs.pypi.org/project-management/yanking/), [Filename reuse](https://pypi.org/help/#file-name-reuse)

conda-forge submission:

- [ ] Update the v1 recipe to use the published PyPI sdist URL and SHA256. Set the initial build number to zero. Add recipe maintainers. [Submission requirements](https://conda-forge.org/docs/maintainer/adding_pkgs/)
- [ ] Replace the Python 3.12-only runtime pin with correct ABI constraints. For ABI3, use `build.python.version_independent` and a `python-abi3` host dependency. Decide whether the first conda release supports free threading. Verify installation on supported Python versions and rejection of incompatible interpreters. The compiled extension remains platform-specific. [conda-forge ABI3 guidance](https://conda-forge.org/docs/maintainer/knowledge_base/#packages-with-abi3-extensions), [Rattler ABI3 recipe](https://rattler-build.prefix.dev/latest/tutorials/python/#an-abi3-compatible-package)
- [ ] Build with conda-forge compilers and sysroots. Keep Maturin plus `python-installer` for the recipe build. Keep `--auditwheel skip` confined to conda packaging. Include the project license and `licenses/THIRDPARTY.yml` through `license_file`. [Compiler guidance](https://conda-forge.org/docs/maintainer/knowledge_base/#compilers), [Rust dependency licenses](https://conda-forge.org/docs/maintainer/adding_pkgs/#licenses-of-included-dependencies)
- [ ] Include the source-resolution and validation tests in the recipe tests. Verify the package with `rattler-build`, then submit the recipe to `conda-forge/staged-recipes`. Resolve the recipe checks before feedstock creation. [Staged recipe process](https://conda-forge.org/docs/maintainer/adding_pkgs/#step-by-step-instructions)

Configuration cleanup:

- [x] Validate per-file Ruff ignores. Remove the unused `PLR0913` exemption for `_native.pyi` and the unused `S603` exemption for `test_diagnostics.py` if they remain unnecessary.
- [x] Reassess Clippy configuration. Remove the individual denies already covered by `all` or `pedantic`. Keep additional lints and justified exceptions.

Dawn support:

Establish a tested Dawn path before the ONNX integration. Keep Dawn optional.

Rough estimate for one developer: 2 to 5 working days for a Linux example,
the Pixi setup, documentation, and focused checks in CI. This assumes compatible
Dawn binaries and Python bindings. Allow 1 to 2 weeks in total if the bindings
or packaging require changes. Estimate a public adapter, support for other
platforms, and the ONNX bridge separately after the example works.

The tinygrad checkout at `f24806b1d068d5e0b3624bccfe5317862ce767a7` provides
the implementation references below.

- [ ] Evaluate `dawn-python` (`pydawn`) for the example. Tinygrad calls `libwebgpu_dawn` through generated ctypes bindings. Evaluate a Python adapter before writing a native extension. [Tinygrad bindings](https://github.com/tinygrad/tinygrad/blob/f24806b1d068d5e0b3624bccfe5317862ce767a7/tinygrad/runtime/autogen/webgpu.py), [pydawn](https://github.com/wpmed92/pydawn)
- [ ] Add a dedicated Pixi environment for Dawn examples and checks. Pin compatible bindings and the Dawn binary. Verify the header version and callback signatures together. Tinygrad's setup uses pydawn binaries, but that does not establish compatibility with ORT's Dawn build. [Tinygrad setup](https://github.com/tinygrad/tinygrad/blob/f24806b1d068d5e0b3624bccfe5317862ce767a7/.github/actions/setup-tinygrad/action.yml)
- [ ] Add a minimal Dawn compute example that consumes `CompileResult.wgsl`. Cover imports, conditional compilation, pipeline overrides, storage buffers, and workgroup memory with FP32 kernels. Verify the output against a CPU reference. Identify concrete compiler blockers before extending the wesl-py API.
- [ ] Capture Dawn errors during shader and pipeline creation. Retain callback objects until completion and copy diagnostic strings before callbacks return. Include the emitted WGSL and entry point in failure reports. Tinygrad's synchronous wrappers and error scopes provide a reference. [Tinygrad runtime](https://github.com/tinygrad/tinygrad/blob/f24806b1d068d5e0b3624bccfe5317862ce767a7/tinygrad/runtime/ops_webgpu.py)
- [ ] Query device features and limits in the example. Keep FP32 as the baseline. Exercise `enable f16` only when the device supports `shader-f16`. Verify buffer alignment, staging readback, and resource release. Keep kernel bindings explicit; tinygrad's binding layout serves its own WGSL renderer.
- [ ] Add a focused Dawn check in CI after the Pixi setup works. Compile and dispatch the example, then compare its result with the CPU reference. Document that Naga validation and Dawn execution are separate checks. Keep `wesl.validate()` as the existing Naga check.
- [ ] Use the example to assess whether a public Dawn adapter is useful. Define ownership of caller-supplied instances, devices, and buffers before adding an API. Create devices explicitly. The ONNX bridge must reuse the same Dawn implementation and device.

Integration with ONNX Runtime:

Build the integration in a separate repository. wesl-py supplies WGSL.
The bridge owns the Dawn device, buffers, inference, and synchronization.

- [ ] Reuse the Dawn example to establish the bridge's shader execution path. Verify that the selected ORT build accepts its device and buffer handles.
- [ ] Add focused regression tests for compiler defects that the integration exposes. Report parser and compiler defects upstream. Verify any required WGSL extensions across WESL, Naga, Dawn, and the target device before using them.
- [ ] Document validation boundaries. `wesl.validate()` uses Naga and does not verify Dawn compatibility or device capabilities. The bridge must also check shader and pipeline creation on its Dawn device.
- [ ] Record the tested wesl-py, Dawn, and ONNX Runtime versions in the bridge repository. Verify the packaged interfaces for external devices and GPU buffers. The initial investigation checks current upstream source, not a tested release combination.
- [ ] Verify the external prerequisites in the bridge repository: one compatible Dawn implementation, ORT's `webgpuInstance` and `webgpuDevice` options, GPU buffer I/O binding, buffer lifetimes, and queue submission order. wgpu-native handles are not Dawn handles. Connecting existing wgpu-py resources requires a Dawn backend or native resource sharing. [ORT device options](https://onnxruntime.ai/docs/execution-providers/WebGPU-ExecutionProvider.html#webgpu-context-options), [ORT buffer allocation](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/core/providers/webgpu/allocator.cc)
- [ ] Verify a complete pipeline in the bridge repository. A WESL kernel writes an input buffer. A small ONNX model consumes it. A second WESL kernel consumes the output. Compare the final result with a CPU reference and verify that intermediate tensors stay on the GPU. Start with fixed shapes and graph capture disabled.
