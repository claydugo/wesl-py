# Open work

Use [publish.md](publish.md) for release verification and publication.
This file tracks unresolved defects, design decisions, and deferred features.

## Deferred upstream limitations

Local fixes for these upstream issues are outside the current release work:

- WESL expression traversal can exhaust a small caller stack. The [Windows regression](https://github.com/claydugo/wesl-py/actions/runs/35526430139/job/106119676932) compiles a 10,000-term expression. Keep the test as an upstream regression probe.
- The bundled [upstream assertions](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders/lib.wesl) can accept NaN, infinity, and infinite tolerances. Keep the finite-input contract in [TESTING.md](TESTING.md#assertions).
- WESL 0.5.0 has known diagnostic, lowering, and import-option defects. Keep their existing regression tests and [API documentation](API.md#diagnostics).

The compiler upgrade and shader runner reduction are complete.
The runner uses upstream `wgsl-test` assertions and accepts a caller's device.
Python examples use wgpu-py for general compute and fragment execution.

## API decisions

- [ ] Decide whether to retain `Compiler` before the first release. It stores configuration for repeated calls and the `wesl_compiler` fixture. Removing it reduces the public API but requires another way to share that configuration.
- [ ] Decide whether interactive examples belong in the release checks. Compilation and headless compute examples provide smaller integration checks. Interactive examples currently remain in the optional `examples` extra.
- [ ] Make GPU device ownership explicit in `examples.multiscale.compute.enhance` and `examples.common.composite`. They accept a device but use pygfx's shared device for pipelines. A different device fails. Choose pygfx ownership or direct wgpu pipelines before changing the signatures.
- [ ] Review whether Pyrefly and Pyright add useful coverage beyond ty and native stubtest. They remain development dependencies until that decision.

## Maintenance

- Keep the ImGui upper bound until a PyPI wgpu release supports ImGui 1.92.900. PyPI wgpu 0.32.0 still accesses the removed `cmd_lists_count` attribute. Conda's [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch) makes the same versions pass, so verify PyPI artifacts before changing the bound.
- Keep the pytest reporting regressions. `pytest_plugin.py` modifies undocumented traceback fields to preserve shader locations in terminal, JUnit, and xdist reports. [Custom failure strings](https://docs.pytest.org/en/stable/example/nonpython.html) are public API, but a replacement must preserve those reports.
- Retain the local Rust statement traversal until the upstream visitor covers plain `else` branches. WESL 0.5.0 omits them in [its visitor](https://github.com/webgpu-tools/wesl-rs/blob/63a3627ba31258565df177f3f553beed8ff45338/crates/wesl/src/pass/visit.rs).
- Review ImGui context cleanup for repeated viewer use in one process. The SDF viewer releases its GPU resources after close, but its ImGui context remains allocated. The [wgpu renderer](https://github.com/pygfx/wgpu-py/blob/main/wgpu/utils/imgui/imgui_renderer.py) creates the context without a cleanup method. This is a maintenance item, not a release requirement.

## Deferred features

Revisit these when a consumer needs them:

- Feature-reference analysis and strict declaration selection.
- Reflection for entry points, overrides, resources, and buffer layouts.
- Override specialization and typed constant generation.
- A pygfx material example and downstream OWL migration.
- Exact mappings for expressions and statements in generated WGSL.
- File-dependency metadata beyond diagnostic filenames.
- An FFT phase-correlation example with generated images and a NumPy reference.
- ONNX Runtime integration in a separate repository, when GPU resources can be shared through a supported interface.

Reflection must bound memory use and respect explicit alignment.
Type spelling and override defaults must preserve their source meaning.
Keep cache policy and GPU execution in applications.
