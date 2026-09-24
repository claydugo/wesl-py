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
options = wesl.CompileOptions(
    features=wesl.Features(flags={"enabled": True}),
    keep=["answer"],
)
result = wesl.compile(modules, options=options)
print(result.wgsl)
```

`compile(modules, *, root="package::main", options=None, filenames=None,
root_directory=None, dependencies=None)` returns a `CompileResult`.

Module keys and `root` use names such as `package::main` and
`package::settings`. Imports resolve through `modules` by default.
An explicit `root_directory` also enables file imports.
The function accepts mappings and preserves their contents.

`CompileOptions` holds the upstream compiler options.
The shader runner accepts `TestOptions` instead.
See [shader test options](testing.md#fixtures-and-pytest-behavior).
It is a mutable dataclass with keyword arguments.
Omit `options` to use upstream defaults.

`Features()` holds the conditional translation settings in a mutable dataclass.
Its default policy is `Feature.Disable`. Its flag dictionary starts empty.
The four policies are `Feature.Enable`, `Feature.Disable`, `Feature.Keep`,
and `Feature.Error`. Each policy can apply to the default or an individual flag.
The `flags` mapping also accepts booleans, as upstream does.
Annotate a reusable flag dictionary as `dict[str, bool | wesl.Feature]`.

`Feature.Keep` preserves unresolved conditions for a later compilation.
`Feature.Error` rejects flags that the compiler evaluates with that policy.
Unused supplied flags do not cause an error.
Using `modules` from the first example:

```python
features = wesl.Features(default=wesl.Feature.Error, flags={"enabled": True})
result = wesl.compile(modules, options=wesl.CompileOptions(features=features))
```

Options retain the supplied feature settings and collections.
Each default instance owns a separate flag dictionary.
Assignments such as `options.features.flags["enabled"] = False` update the settings.
Compilation copies the settings into Rust before it releases the GIL.
The compile boundary checks field types.

`Feature` and `ManglerKind` are Python enums.
`CompileOptions`, `Features`, `Feature`, and `ManglerKind` support pickle.
Applications can pass these values to process workers.

The retention options follow
[wesl-rs `CompileOptions`](https://docs.rs/wesl/0.4.4/wesl/struct.CompileOptions.html).
`keep_main` and `mangle_main` map to upstream's `keep_root` and `mangle_root`.

| Option | Effect |
| --- | --- |
| `strip=True` | Keep selected root declarations and their dependencies. |
| `strip=False` | Preserve all declarations in each loaded module and resolve their dependencies. |
| `keep=None` | Select entry points when stripping is enabled. |
| `keep=["answer"]` | Select these original root names when stripping is enabled. |
| `keep=[]` | Select no root declarations when stripping is enabled. |
| `keep_main=True` | Select all active root declarations when stripping is enabled. |

`strip=False` overrides `keep_main` and `keep`.
`keep_main=True` overrides `keep`.
The compiler ignores unknown names in `keep`. This includes declarations that conditional
translation removes.

A root with only unused helpers produces empty WGSL under the default options.
The compiler loads modules when declarations depend on them. It does not scan every file in a package.
The binding enables upstream's lazy import resolution.

Set `mangle_main=True` to rename root declarations as well as imported declarations.
Selections always use original names, independent of mangling.

The remaining `CompileOptions` fields also use upstream names and defaults:

| Option | Effect |
| --- | --- |
| `imports=True` | Resolve imports. |
| `condcomp=True` | Evaluate conditional translation attributes. |
| `lower=False` | Enable upstream lowering when set to `True`. This build inlines aliases and constants. |
| `validate=True` | Run upstream compiler checks. |
| `sourcemap=True` | Record source text and declaration names. |
| `mangler=ManglerKind.Escape` | Select the declaration naming scheme. |

The build does not enable upstream generics or evaluation.
`CompileOptions` does not expose the inactive generics option.

The pinned wesl-rs 0.4.4 compiler has these known limitations:

- `imports=False` can strip root entry points. Use `strip=False` with this option.
- `lower=True` can lose explicit constant types or leave unresolved constant references.
  Keep `lower=False` for runtime shaders until upstream fixes these cases.
- Large expressions can exhaust a small caller stack on Windows.
  See the [10,000-term expression failure](https://github.com/claydugo/wesl-py/actions/runs/35526430139/job/106119676932).

The binding uses the published crates without local compiler patches.
It stays on 0.4.4 so existing shader libraries remain usable without visibility modifiers.
See the [upstream recommendation](https://github.com/webgpu-tools/wesl-rs/issues/300#issuecomment-5757180358).

`mangler` accepts `ManglerKind.Escape`, `ManglerKind.Hash`,
`ManglerKind.Unicode`, or `ManglerKind.None_`.
`None_` represents the Rust `None` variant and disables mangling.
The Unicode mangler keeps paths in names. A WGSL runtime can reject these names.
Set `CompileOptions(sourcemap=False)` to skip source-map recording.
Escape mangling and source-map recording are upstream defaults.

Invalid argument types raise `TypeError`. Invalid module names raise
`ValueError`. Missing modules and compiler failures raise `CompileError`.
Successful compilation still requires validation by the GPU device.

## Compile strings and files

Save this as `shaders/main.wesl`:

```wesl
@compute @workgroup_size(1) fn main() {}
```

Compile an inline source or that file:

```python
import wesl

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
The file path must be inside that directory. Its relative path determines
the root module name. For example, `nested/main.wesl` becomes
`package::nested::main`.
The helper preserves symlinks. Imports resolve from the supplied directory,
including when the root file is a symlink to a file outside that directory.
File paths and root directories can contain `..`.

Invalid root file paths raise the corresponding Python file exception.
A file outside `root_directory` raises `ValueError`.

Both functions accept `options` from `compile()`.
Files load only when the compiler resolves an import.
The resolver first checks the supplied `modules` mapping.
It then looks for a `.wesl` file, with `.wgsl` as a fallback.
Missing imported files raise `CompileError`.

The installed package includes `wgsl_test`, which needs no registration.
It provides the upstream assertion shaders for compilation and testing.

Register other library directories with `dependencies`:

```python
import wesl

compiler = wesl.Compiler(dependencies={"library": "path/to/library"})
result = compiler.compile_source(
    "import library::math::exposure; "
    "@fragment fn main() -> @location(0) vec4f { return vec4f(exposure(0.5)); }"
)
```

The [imports example](../examples/imports.py) fetches an upstream module and
compiles a shader that imports it.

`compile`, `compile_source`, and `compile_file` also accept `dependencies`.
Values are directory paths. Relative paths use the working directory.
The binding routes imports through upstream `Router` and `FileResolver`.
It reads files on demand, with `.wesl` preferred over `.wgsl`.

The package root is `package.wesl`. For example, `library::value` refers to
`value` in that file, and `library::math::value` refers to `value` in `math.wesl`.
Imports share registered directories by package name, including self-qualified imports.
An explicit dependency such as `alpha/common` takes precedence over `common`
when `alpha` imports it. Entries in `modules` override files.

Each compilation reads the current sources. The binding does not download libraries
or read `wesl.toml`.

Named libraries can also use `modules`:

```python
import wesl

result = wesl.compile_source(
    "import noise::lib::value; fn main() -> u32 { return value(); }",
    modules={"noise::lib": "fn value() -> u32 { return 7u; }"},
    options=wesl.CompileOptions(keep=["main"]),
)
```

Imports across package boundaries work without visibility modifiers in WESL 0.4.4.

Within a library, `package::` and relative imports refer to that library.
Virtual modules use the exact package paths that upstream's resolver receives.
If `noise::lib` imports `arithmetic::one`, supply that dependency under
`noise/arithmetic`. A module within that dependency uses a key such as
`noise/arithmetic::helpers`. The slash separates package dependencies.
WESL source still uses normal import syntax.
For example, `alpha/common` and `beta/common` identify separate dependencies.
Neither falls back to a virtual module named `common`.
These keys identify virtual modules. The binding does not construct an upstream
package dependency graph or deduplicate package instances.
Use `dependencies` to register directories for named libraries.

## Reuse compilation settings

`Compiler` stores `options`, `modules`, `filenames`, `root_directory`, and
`dependencies`.
These are optional keyword arguments. Each instance owns its default settings.
Supplied settings and mappings remain shared with the caller.
This example uses `shaders/main.wesl` from [above](#compile-strings-and-files):

```python
import wesl

compiler = wesl.Compiler(root_directory="shaders")
result = compiler.compile_file("main.wesl")
result = compiler.compile_source("@compute @workgroup_size(1) fn main() {}")
```

`compile_source(source, *, root="package::main", filename="<string>")`
uses the stored settings. `compile_file(filename)` resolves relative paths
from `root_directory`, or the working directory when no root is set.
Each call compiles again. The object does not cache results.

## Compilation results

All compilation functions return an immutable `CompileResult`.
Use `result.wgsl` to pass the shader to wgpu-py.
`str(result)` also returns WGSL. Results support equality and pickle.

| Attribute | Meaning |
| --- | --- |
| `wgsl` | Compiled WGSL source. |
| `modules` | Tuple of loaded module names in upstream order, with the root first. |
| `entry_points` | Tuple of entry-point names in the emitted WGSL. |
| `sources` | Dictionary from loaded module names to immutable `Source` records. |

Each access to `sources` returns a dictionary copy.
The source text comes from the upstream source map.
With `CompileOptions(sourcemap=False)`, `sources` is empty.
These records adapt the upstream result for Python. The binding emits WGSL once
and reads the existing syntax tree for names. It does not parse the output again.

`Source(text, filename=None)` retains exact UTF-8 source text and a display label.
`compile_file` uses the absolute filename as its label.
Applications track file dependencies and reload sources.
Source records support equality, hashing, and pickle.

## Package resources

Use `load_modules()` for local files and installed Python resources.
This example assumes your installed `shader_library.shaders` package contains
`blur.wesl` with a function named `apply` that takes no arguments:

```python
from importlib.resources import files

import wesl

loaded = wesl.load_modules(files("shader_library.shaders"), namespace="filters")
result = wesl.compile_source(
    "import filters::blur::apply; fn main() { apply(); }",
    modules=loaded.modules,
    filenames=loaded.filenames,
    options=wesl.CompileOptions(keep=["main"]),
)
```

`load_modules(directory, *, namespace)` accepts a directory path or a
`Traversable` resource collection. It returns `LoadedModules(modules, filenames)`.
Relative file paths become names within the explicit namespace.
The loader preserves UTF-8 text and line endings. It sorts the output mappings.
It prefers `.wesl` over `.wgsl` for the same relative stem.
It rejects different paths that produce the same module name.
Filesystem traversal accepts directory symlinks and rejects cycles.
Zipped resources use stable labels without extraction.
The helper does not cache resources or discover packages implicitly.

Applications own caches and reload timing. Invalidate cached results when compiler
inputs or the installed compiler change. Loaded dependencies describe one variant.
A watcher must also detect resolution changes, such as a new `.wesl` file replacing
a `.wgsl` fallback.

## Syntax checks

```python
import wesl

wesl.check_syntax("@compute @workgroup_size(1) fn main() {}", filename="main.wgsl")
```

`check_syntax(source, *, filename="<string>")` returns `None` on success.
It parses WESL without resolving imports or validating types.
The filename accepts a string or a path object as an error label.
The compiler does not open it.
Syntax errors raise `CompileError`.

## Validation

Compilation runs the checks provided by wesl-rs unless `options.validate` is false.
These checks do not establish
complete WGSL validity. For example, some type errors pass compilation.
Pass the output to the target runtime for shader and pipeline validation.
After pygfx transforms the output, validate the final shader through its GPU runtime.
The package does not expose a standalone semantic validator.

## Diagnostics

```python
import wesl

try:
    wesl.check_syntax("fn main(", filename="shaders/broken.wesl")
except wesl.CompileError as error:
    print(error)
    for diagnostic in error.diagnostics:
        print(diagnostic)
```

`CompileError.diagnostics` is a tuple. A manually constructed exception
starts with an empty tuple.
Error text contains no terminal color codes.
With `sourcemap=False`, validation errors can omit source text.
Syntax errors retain their module context.

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
unavailable.

All compilation functions accept `filenames`, a mapping from module
names to display filenames. Values accept strings or path objects.
File imports use their filesystem paths when reporting errors.

## Threads

The native module declares `gil_used = false`. Each native operation copies its
Python inputs, then detaches from Python while Rust parses or compiles.
Regular CPython releases the GIL during this work.
Concurrent calls can share inputs when callers do not modify those inputs.

## Build identity

`wesl.__version__` identifies the binding.
`wesl.__version__` matches Python distribution metadata. This package uses the published WESL and
`wgsl-parse` 0.4.4 crates without local patches.
Report parser defects to the [upstream issue tracker](https://github.com/webgpu-tools/wesl-rs/issues).
See [LICENSE](../LICENSE) for source provenance and third-party notices.

The binding enables imports, conditional translation, name mangling,
source diagnostics, and upstream validation by default. It disables evaluation
and generics at build time. Lowering is available through `CompileOptions`.
Upstream validation does not catch every WGSL error.
