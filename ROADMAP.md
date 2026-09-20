# Roadmap

## Compiler upgrade

- [x] Upgrade `wesl` and `wgsl-parse` to 0.5.0. Follow the new frontend API. Move `mangler` and `sourcemap` into `CompileOptions`, adopt `mangle_main` and `keep_main`, and remove `lazy`. Verify the known import and lowering defects before changing the release pin. [Upstream API](https://github.com/webgpu-tools/wesl-rs/blob/63a3627ba31258565df177f3f553beed8ff45338/crates/wesl/src/frontend.rs)
- [x] Verify source locations for errors in imported modules before the upgrade. WESL 0.5.0 can attach the root source to a diagnostic from an imported module. Keep `test_imported_undefined_symbol_has_byte_span` as a regression test. Mark the test as an expected failure until upstream restores module context.

WESL 0.5.0 still loses constant types and forward references during lowering.
It also resolves imports when `imports=False`.
The upgrade does not resolve these limitations.
Imports between modules in a named library also require public visibility in 0.5.0.
The binding uses the upstream frontend without a custom compiler driver.
Shader tests append a compute entry point after upstream conditional translation selects the active test.

## API additions

The API follows the binding scope in [API.md](API.md).
The following additions remain deferred:

- Feature-reference analysis and strict declaration selection.
- Reflection for entry points, overrides, resources, and buffer layouts.
- Override specialization and typed constant generation.
- A pygfx material example and downstream OWL migration.
- Exact mappings for expressions and statements in generated WGSL.
- File-dependency metadata beyond diagnostic filenames.

Revisit these additions when a consumer needs them. Reflection needs bounded
memory use for shared types and verified handling of explicit alignment.
Type spelling and override defaults must preserve their source meaning.
Constant generation must verify each declaration name before emission.
Keep cache policy and GPU execution in applications.

## API reductions

The [shader testing proposal](TESTING_PROPOSAL.md) defines the proposed API
and the tradeoffs for review.

- [ ] Remove `Compiler`. It duplicates the compilation functions. Keep `compile`, `compile_source`, and `compile_file`. Update the pytest fixtures that store compiler settings.
- [ ] Reduce shader testing to WESL `@test` functions and upstream `wgsl-test` assertions. Keep pytest reporting and support devices supplied by the caller. Review the general compute and fragment runners separately.
- [ ] Keep a small compilation example and a compute example in the release checks. Review the interactive applications separately. Keep optional example dependencies in the `examples` extra.

## Dawn support

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
- [ ] Add a focused Dawn check in CI after the Pixi setup works. Compile and dispatch the example, then compare its result with the CPU reference. Document which shader and pipeline checks Dawn performs.
- [ ] Use the example to assess whether a public Dawn adapter is useful. Define ownership of caller-supplied instances, devices, and buffers before adding an API. Create devices explicitly. The ONNX bridge must reuse the same Dawn implementation and device.

## Integration with ONNX Runtime

Build the integration in a separate repository. wesl-py supplies WGSL.
The bridge owns the Dawn device, buffers, inference, and synchronization.

- [ ] Reuse the Dawn example to establish the bridge's shader execution path. Verify that the selected ORT build accepts its device and buffer handles.
- [ ] Add focused regression tests for compiler defects that the integration exposes. Report parser and compiler defects upstream. Verify any required WGSL extensions across WESL, Naga, Dawn, and the target device before using them.
- [ ] Document validation boundaries. wesl-py runs upstream compiler checks. The bridge checks shader and pipeline creation on its Dawn device.
- [ ] Record the tested wesl-py, Dawn, and ONNX Runtime versions in the bridge repository. Verify the packaged interfaces for external devices and GPU buffers. The initial investigation checks current upstream source, not a tested release combination.
- [ ] Verify the external prerequisites in the bridge repository: one compatible Dawn implementation, ORT's `webgpuInstance` and `webgpuDevice` options, GPU buffer I/O binding, buffer lifetimes, and queue submission order. wgpu-native handles are not Dawn handles. Connecting existing wgpu-py resources requires a Dawn backend or native resource sharing. [ORT device options](https://onnxruntime.ai/docs/execution-providers/WebGPU-ExecutionProvider.html#webgpu-context-options), [ORT buffer allocation](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/core/providers/webgpu/allocator.cc)
- [ ] Verify a complete pipeline in the bridge repository. A WESL kernel writes an input buffer. A small ONNX model consumes it. A second WESL kernel consumes the output. Compare the final result with a CPU reference and verify that intermediate tensors stay on the GPU. Start with fixed shapes and graph capture disabled.
