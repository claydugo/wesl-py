# Release notes

## 0.1.0 (unreleased)

- Collect WESL `@test` functions with pytest. Run compute and fragment tests from Python with NumPy resources through the optional `testing` extra.
- Compile WESL modules, strings, and files into an immutable `CompileResult` with generated WGSL and loaded source records.
- Check WESL syntax with `check_syntax()` and report structured diagnostics with source locations.
- Configure upstream compiler behavior with `CompileOptions`, `Features`, `Feature`, and `ManglerKind`. Compiler settings support pickle and process workers.
- Load modules from directories and Python package resources with `load_modules()`.
- Resolve library directories with `dependencies` and upstream resolvers. Use `wesl_dependencies` to register directories for pytest.
- Include upstream wgsl-test assertions in installed packages and register them automatically. Add a Lygia image example and GPU tests.
- Preserve dependency-qualified package names, the upstream order of modules, symlinks, and parent components in file paths.
- Expose the binding version as `wesl.__version__`.
- Pin published WESL and wgsl-parse 0.4.4 crates to support existing shader libraries without visibility modifiers. See [API.md](API.md) for known limitations of `imports=False` and `lower=True`.
- Ignore unknown or disabled names in `keep`, as upstream does.
- Preserve module context and assertion locations in shader tests.
- Provide examples for SDF rendering, multiscale image processing, RMSNorm, stream compaction, and color mapping with Lygia. The target GPU runtime validates generated shaders and pipelines.
- Build wheels with a stable ABI for CPython 3.12 and later and free-threaded CPython 3.15 and later. See [CONTRIBUTING.md](CONTRIBUTING.md#support) for release targets and verification status.
