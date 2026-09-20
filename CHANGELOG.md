# Release notes

## 0.1.0 (unreleased)

- Collect WESL `@test` functions with pytest. Run compute and fragment tests from Python with NumPy resources through the optional `testing` extra.
- Compile WESL modules, strings, and files into an immutable `CompileResult` with generated WGSL and loaded source records.
- Check WESL syntax with `check_syntax()` and report structured diagnostics with source locations.
- Configure upstream compiler behavior with `CompileOptions`, `Features`, `Feature`, and `ManglerKind`. Compiler settings support pickle and process workers.
- Load modules from directories and Python package resources with `load_modules()`.
- Preserve dependency-qualified package names, the upstream order of modules, symlinks, and parent components in file paths.
- Expose the binding version, upstream compiler version, and optional build revision.
- Use published WESL and wgsl-parse 0.5.0 crates without local patches. See [API.md](API.md) for known limitations of `imports=False` and `lower=True`.
- Require public declarations for imports from named packages. Unknown or disabled names in `keep` raise `CompileError`.
- Use the upstream frontend for compilation and shader tests. WESL 0.5.0 can lose module context in validation errors.
- Provide SDF rendering, multiscale image processing, RMSNorm, and stream compaction examples. The target GPU runtime validates generated shaders and pipelines.
- Build wheels with a stable ABI for CPython 3.12 and later and free-threaded CPython 3.15 and later. See [CONTRIBUTING.md](CONTRIBUTING.md#support) for release targets and verification status.
