# API reference

## Compile modules

```python
import wesl

modules = {
    "package::main": """
        import package::settings::value;
        fn answer() -> u32 { return value(); }
    """,
    "package::settings": """
        @if(enabled) fn value() -> u32 { return 7u; }
        @if(!enabled) fn value() -> u32 { return 3u; }
    """,
}
result = wesl.compile(modules, features={"enabled": True}, keep=["answer"])
print(result.wgsl)
```

`compile(modules, *, root="package::main", features=None, strip=True,
keep_root=False, mangle_root=False, keep=None, missing_features="disable",
filenames=None, root_directory=None)` returns a `CompileResult`.

Module keys and `root` use names such as `package::main` and
`package::settings`. Imports resolve through `modules` by default.
An explicit `root_directory` also enables file imports.
The function accepts mappings and preserves their contents.

Feature values, `strip`, `keep_root`, and `mangle_root` must be booleans.
The compiler disables unspecified feature flags.
Set `missing_features="error"` to require an explicit value for each
feature flag encountered during compilation. Unused supplied flags do
not cause an error.

| Option | Effect |
| --- | --- |
| `strip=True` | Remove the unused declarations. Follow imports only when needed. |
| `keep_root=True` | Preserve all root declarations when stripping. |
| `mangle_root=True` | Rename root declarations as well as imported declarations. |
| `keep=["main"]` | Preserve the named root declarations and their dependencies. |

The default matches the Rust compiler. A module containing only unused
helper functions can compile to an empty string. Use `strip=False` or
`keep_root=True` to preserve those functions. Stripping also determines
which imported modules the compiler reads.

`keep` replaces the default selection of entry points.
`keep_root=True` and `strip=False` take precedence over `keep`.
An empty `keep` sequence selects no declarations.
The compiler ignores unknown names.

Invalid argument types raise `TypeError`. Invalid module names raise
`ValueError`. Missing modules and compiler failures raise `CompileError`.
Successful compilation still requires validation by the GPU device.

## Compile strings and files

```python
result = wesl.compile_source(
    "@compute @workgroup_size(1) fn main() {}",
    filename="generated.wesl",
)
result = wesl.compile_file("shaders/main.wesl", root_directory="shaders")
```

`compile_source(source, ...)` uses `package::main` as its default root.
Set `root` to use another module name. The optional `modules` mapping
provides imported sources. It must not contain the root module.
`filename` labels the root source and defaults to `<string>`.
The compiler does not open this label.

`compile_file(filename, ...)` reads the root file as UTF-8.
Its parent directory is the default `root_directory`.
The file must be inside that directory. Its relative path determines
the root module name. For example, `nested/main.wesl` becomes
`package::nested::main`.

Invalid root file paths raise the corresponding Python file exception.
A file outside `root_directory` raises `ValueError`.

Both functions accept the feature and stripping options of `compile()`.
Files load only when the compiler resolves an import.
The resolver first checks the supplied `modules` mapping.
It then looks for a `.wesl` file, with `.wgsl` as a fallback.
Missing imported files raise `CompileError`.

Named libraries also use `modules`:

```python
result = wesl.compile_source(
    "import noise::lib::value; fn main() -> u32 { return value(); }",
    modules={"noise::lib": "fn value() -> u32 { return 7u; }"},
    keep=["main"],
)
```

Within a library, `package::` and relative imports refer to that library.
Named libraries share one namespace across the supplied modules.
The resolver does not search the filesystem for named libraries.

## Compilation results

All compilation functions return an immutable `CompileResult`.
Use `result.wgsl` to pass the shader to wgpu-py.
`str(result)` also returns WGSL. Results support equality and pickle.

| Attribute | Meaning |
| --- | --- |
| `wgsl` | Compiled WGSL source. |
| `modules` | Sorted tuple of loaded module names, including the root. |
| `entry_points` | Tuple of entry-point names in the emitted WGSL. |
| `declarations` | Dictionary from emitted names to `(module, original_name)`. |

The declaration map contains the named declarations that remain after
stripping. Each access returns a copy of the dictionary.
The map identifies original names. It does not map output positions
to input positions.

## Syntax checks

```python
wesl.check_syntax(result.wgsl, filename="generated shader.wgsl")
```

`check_syntax(source, *, filename="<string>")` returns `None` on success.
It parses WESL without resolving imports or validating types.
The filename accepts a string or a path object as an error label.
The compiler does not open it.
Syntax errors raise `CompileError`.

## Semantic validation

```python
wesl.validate(result.wgsl, filename="generated shader.wgsl")
```

`validate(source, *, filename="<string>")` returns `None` on success.
It uses Naga 29.0.4 to parse WGSL and validate shader semantics.
It accepts WGSL output. Compile WESL imports and conditional attributes
first. Failures raise `CompileError` with source diagnostics.
The filename accepts a string or a path object as an error label.

Validation runs without a GPU. It enables all Naga capabilities and
does not check the features or limits of a particular device.
`compile()` does not run this separate validation step.

## Diagnostics

```python
try:
    wesl.check_syntax("fn main(", filename="shaders/broken.wesl")
except wesl.CompileError as error:
    print(error)
    for diagnostic in error.diagnostics:
        print(diagnostic)
```

`CompileError.diagnostics` is a tuple. A manually constructed exception
starts with an empty tuple. Error text contains no terminal color codes.

`Diagnostic(message, module=None, filename=None, source=None, span=None)`
is an immutable value. It supports equality, hashing, and pickle.
Compiler exceptions also preserve their diagnostics through pickle.

| Attribute | Meaning |
| --- | --- |
| `message` | Error message without the source excerpt. |
| `module` | WESL module name, when available. |
| `filename` | Display filename, when available. |
| `source` | Source text associated with the error, when available. |
| `span` | UTF-8 byte offsets `(start, end)` with an exclusive end. |
| `line`, `column` | The start position, with one-based line and character numbers. |
| `end_line`, `end_column` | The exclusive end position, with the same numbering. |

Missing metadata is `None`. EOF spans have equal offsets at the source
length in bytes. These offsets are not Python character indices.

A column advances by one for each Unicode character, including a tab.
Position attributes are `None` when the source or a valid offset is
unavailable. Some Naga validation errors have no source span.

All compilation functions accept `filenames`, a mapping from module
names to display filenames. Values accept strings or path objects.
File imports use their filesystem paths when reporting errors.

## Compiler version

`wesl.__version__` identifies the binding. `wesl.compiler_version`
identifies the Rust compiler. This package uses the published WESL and
`wgsl-parse` 0.4.4 crates without local patches.
Report parser defects to the [upstream issue tracker](https://github.com/webgpu-tools/wesl-rs/issues).
See [NOTICE](licenses/NOTICE) for source provenance.

The binding enables imports, conditional translation, name mangling,
source diagnostics, and upstream validation. It disables evaluation,
generics, and lowering. Upstream validation does not catch every WGSL error.
