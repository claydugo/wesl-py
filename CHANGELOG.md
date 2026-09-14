# Release notes

## Unreleased

- Compilation returns an immutable `CompileResult`. Read generated code from `.wgsl`.
- Remove the inferred declaration ownership from `CompileResult`.
- Rename `parse()` to `check_syntax()`.
- Preserve upstream retention options and selection behavior.
- Bind `CompileOptions`, `Features`, `Feature`, and `ManglerKind`.
- Use Python enums and mutable dataclasses for compiler settings.
- Replace the compiler keywords and `missing_features` with `options=CompileOptions(...)`.
- Expose upstream import, conditional translation, lazy resolution, lowering, and validation controls.
- Allow callers to disable source-map recording.
- Preserve dependency-qualified package names and upstream module order.
- Preserve symlinks when compiling files.
- Accept parent components in file paths and root directories.
- Preserve compiler options and feature policies through pickle and process workers.
- Add loaded source records from the upstream source map.
- Add `load_modules()` for directories and Python package resources.
- Expose the optional `build_revision` supplied at build time.
- Remove standalone Naga validation. The target runtime validates generated WGSL.

- Add Python bindings for WESL compilation, syntax checks, and diagnostics.
- Use the published WESL and wgsl-parse 0.4.4 crates without local patches.
- Document the upstream limitations of `imports=False` and `lower=True`.
- Build stable ABI wheels for CPython 3.12 and later and free-threaded CPython 3.15 and later.
