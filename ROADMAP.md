# Open work

Use [publish.md](publish.md) for release verification and publication.
This file tracks release blockers, settled decisions, maintenance, and deferred features.

## Before release

- WESL expression traversal can exhaust a small caller stack. The [Windows regression](https://github.com/claydugo/wesl-py/actions/runs/35526430139/job/106119676932) compiles a 10,000-term expression. Its test remains a required check. A failure blocks release under [publish.md](publish.md#release-verification). Keep the regression test after upstream fixes the defect.

## Deferred upstream limitations

Local fixes for these upstream issues are outside the current release work:

- The bundled [upstream assertions](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders/lib.wesl) can accept NaN, infinity, and infinite tolerances. Keep the finite-input contract in [TESTING.md](TESTING.md#assertions).
- Stay on WESL 0.4.4 until upstream supports existing shader libraries without visibility modifiers. Keep the regression tests for the compiler and [API documentation](API.md#diagnostics).

The compiler pin and shader runner reduction are complete.
The runner uses upstream `wgsl-test` assertions and accepts a caller's device.
Python examples use wgpu-py for general compute and fragment execution.

## Settled decisions

- Retain `Compiler`. It stores configuration for repeated calls and the `wesl_compiler` fixture.
- Keep the examples in the optional `examples` extra. The release checks verify compilation, compute results, and both viewers offscreen. The local tests verify window events.
- Use pygfx's shared device in `examples.multiscale.compute.enhance` and `examples.common.composite`. Both helpers obtain that device internally.

## Maintenance

- Review whether Pyrefly and Pyright add useful coverage beyond ty and native stubtest. They remain development dependencies until that decision.
- Keep the ImGui upper bound until a PyPI wgpu release supports ImGui 1.92.900. PyPI wgpu 0.32.0 still accesses the removed `cmd_lists_count` attribute. Conda's [backend patch](https://github.com/conda-forge/wgpu-py-feedstock/blob/main/recipe/0001-Use-len-draw_data.cmd_lists-in-imgui-backend.patch) makes the same versions pass, so verify PyPI artifacts before changing the bound.
- Keep the pytest reporting regressions. `pytest_plugin.py` modifies undocumented traceback fields to preserve shader locations in terminal, JUnit, and xdist reports. [Custom failure strings](https://docs.pytest.org/en/stable/example/nonpython.html) are public API, but a replacement must preserve those reports.
- Retain the local Rust statement traversal until the upstream visitor covers plain `else` branches. WESL 0.5.0 omits them in [its visitor](https://github.com/webgpu-tools/wesl-rs/blob/63a3627ba31258565df177f3f553beed8ff45338/crates/wesl/src/pass/visit.rs).
- Review GPU resource and ImGui context cleanup for repeated viewer use in one process. The SDF viewer has no explicit teardown. Closing its canvas leaves the particle buffer usable while the viewer remains referenced. The [wgpu renderer](https://github.com/pygfx/wgpu-py/blob/main/wgpu/utils/imgui/imgui_renderer.py) creates the ImGui context without a cleanup method. Keep this as maintenance work outside the release requirements.

## Deferred features

`CompileResult.entry_points` already lists emitted entry-point names.
`CompileResult.modules` and `sources` describe loaded modules and their source records.
These describe the selected compilation variant.

Revisit these when a consumer needs them:

- Feature-reference analysis and strict declaration selection.
- Reflection for entry-point stages, overrides, resources, and buffer layouts.
- Typed constant generation.
- A custom pygfx material example.
- Exact mappings for expressions and statements in generated WGSL.
- Dependency metadata for inactive imports and changes to file resolution.

Reflection must bound memory use and respect explicit alignment.
Type spelling and override defaults must preserve their source meaning.
Keep cache policy, GPU execution, and pipeline override values in applications.
The examples already specialize overrides through wgpu pipeline constants.
Implement phase correlation with FFTs in application repositories.
Integrate ONNX Runtime in application repositories.
