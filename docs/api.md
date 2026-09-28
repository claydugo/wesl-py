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

`compile(modules, *, root="package::main", options=None, features=None, constant_modules=None,
keep=..., keep_main=None, strip=None, filenames=None, root_directory=None,
dependencies=None)` returns a `CompileResult`.

Module keys and `root` use names such as `package::main` and
`package::settings`. Imports resolve through `modules` by default.
An explicit `root_directory` also enables file imports.
The function accepts mappings and preserves their contents.

`features`, `keep`, `keep_main`, and `strip` override the corresponding fields in
`options` for one call. They do not mutate the supplied options.
Omit `keep` to use the stored selection. Pass `keep=None` to select entry points.
Pass `keep=[]` to select no root declarations.
The other keyword overrides use `None` to retain the stored setting.

`CompileOptions` holds the upstream compiler options.
The shader runner accepts `TestOptions` instead.
See [shader test options](testing.md#fixtures-and-pytest-behavior).
It is a mutable dataclass with keyword arguments.
Omit `options` to use the defaults below.
Visibility checks default to `False` so existing external shaders remain usable.
Upstream defaults visibility checks to `True`.

`features` accepts a mapping such as `{"enabled": True}` or a `Features` instance.
Mappings use the default policy, `Feature.Disable`.
`CompileOptions.features` and `TestOptions.features` hold `Features` instances.
A call-level feature setting replaces the stored setting without merging flags.

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
[wesl-rs `CompileOptions`](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/frontend.rs).
`keep_main` and `mangle_main` refer to the root module.
They do not refer to a function named `main`.

- `strip=True`: Keep selected root declarations and their dependencies.
- `strip=False`: Preserve all declarations in each loaded module and resolve
  their dependencies.
- `keep=None`: Select entry points when stripping is enabled.
- `keep=["answer"]`: Select these original root names when stripping is enabled.
- `keep=[]`: Select no root declarations when stripping is enabled.
- `keep_main=True`: Select all active root declarations when stripping is
  enabled.

`strip=False` overrides `keep_main` and `keep`.
`keep_main=True` overrides `keep`.
The compiler rejects unknown names in `keep`. This includes declarations that
conditional translation removes.

A root with only unused helpers produces empty WGSL under the default options.
Use `compile_source(source, keep=["answer"])` to retain a helper and its dependencies.
Use `keep_main=True` to retain all active root declarations, or `strip=False`
to disable stripping.
The compiler loads modules when declarations depend on them. It does not scan
every file in a package.
The compiler uses upstream usage analysis to load dependencies.

Set `mangle_main=True` to rename root declarations as well as imported declarations.
Selections always use original names, independent of mangling.

The remaining `CompileOptions` fields use upstream names:

- `imports=True`: Resolve imports.
- `condcomp=True`: Evaluate conditional translation attributes.
- `visibility=False`: Ignore visibility restrictions. Set `True` to require
  declarations imported from external packages to be `public`.
- `lower=False`: Enable upstream lowering when set to `True`. This build evaluates
  constant expressions, inlines aliases, and removes unreachable code.
- `validate=True`: Run upstream compiler checks.
- `sourcemap=True`: Record source text and declaration names.
- `mangler=ManglerKind.Escape`: Select the declaration naming scheme.

The build enables upstream evaluation. It does not enable generics.
`CompileOptions` does not expose the inactive generics option.

The pinned compiler has these known limitations:

- `lower=True` can remove side effects from a `for` initializer when its condition
  is always false. Keep lowering disabled for affected shaders.
  See [the upstream reproducer](upstream.md#lowering-drops-side-effects-in-a-for-initializer).
- Large expressions can exhaust a small caller stack on Windows.
  See the [10,000-term expression failure](https://github.com/claydugo/wesl-py/actions/runs/35526430139/job/106119676932).

The binding pins upstream 0.5.0 plus the merged visibility and visitor fixes.
It does not modify dependency sources. The compiler adapter handles the remaining
[upstream integration gaps](upstream.md#compiler-driver-integration).
Disabling visibility follows the [upstream recommendation](https://github.com/webgpu-tools/wesl-rs/issues/300#issuecomment-5757180358).

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

Imports must precede directives and declarations in the assembled source.
When a template contains imports, place them before generated bindings.
Keep directives such as `enable f16;` between imports and declarations.

`compile_file(filename, ...)` reads the root file as UTF-8.
The file's parent directory is the default `root_directory`.
Pass `root_directory` to set a different import root.
Use `Compiler.from_project()` to load settings from `wesl.toml`.
The file path must be inside that directory. Its relative path determines
the root module name. For example, `nested/main.wesl` becomes
`package::nested::main`. A top-level `package.wesl` or `package.wgsl` becomes `package`.
The helper preserves symlinks. Imports resolve from the supplied directory,
including when the root file is a symlink to a file outside that directory.
File paths and root directories can contain `..`.

Invalid root file paths raise the corresponding Python file exception.
A file outside `root_directory` raises `ValueError`.

Both functions accept `options` and the keyword overrides from `compile()`.
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
Pass a mapping of package names to directory paths, or a `Dependencies` value
from `Compiler.from_project()`. Relative directory paths use the working directory.
Construct `Dependencies(directories)` to copy a directory mapping and fix its
relative paths at construction. Both forms use the same import scopes.
The binding routes imports through upstream `Router` and `FileResolver`.
It reads files on demand, with `.wesl` preferred over `.wgsl`.

The package root is `package.wesl`. For example, `library::value` refers to
`value` in that file, and `library::math::value` refers to `value` in `math.wesl`.
Register `alpha/common` when `alpha` imports `common`. A top-level `common` entry
does not supply that dependency. Use `package::` for imports within a library.
Entries in `modules` override files.

Each compilation reads the current sources. The binding does not download libraries.

For a WESL project, put the root and dependency paths in `wesl.toml`:

```toml
edition = "2026_pre"
root = "shaders"

[dependencies]
library = { path = "../library" }
```

The root and dependency paths are relative to the manifest that declares them.
The default root is `shaders`. Each path dependency must contain its own `wesl.toml`.
Its manifest supplies its root and dependencies. Transitive dependencies retain
their package scopes. Cyclic path dependencies raise `ValueError`.

Imports can use the package's declared dependencies and the bundled `wgsl_test`.
References to the same manifest share one package instance and its shader state.
A scoped override such as `alpha/common` replaces that dependency for `alpha`.
Other packages keep their declared dependency. Different scoped overrides create
separate package instances.
Directory overrides can supply their own children through entries such as
`alpha/common/settings`. The loader does not read manifests from overridden directories.

The loader supports the `2026_pre` edition and explicit path dependencies.
Package-manager dependencies and `dependencies = "auto"` raise `NotImplementedError`.

Manifest `include` and `exclude` patterns do not filter explicitly requested imports
or pytest collection.

`compile()`, `compile_source()`, and `compile_file()` do not discover manifests.
Use `Compiler.from_project()` to supply project settings.
Its `dependencies` is an immutable `Dependencies` value with resolved directories
and package aliases. Pass this value to another compiler or `run_test()` to retain
package scopes and shared state. It is not a mapping; `dict()` raises `TypeError`.
Supply directory overrides to `Compiler.from_project(..., dependencies=...)`
when constructing the graph.

Named libraries can also use `modules`:

```python
import wesl

result = wesl.compile_source(
    "import noise::lib::value; fn main() -> u32 { return value(); }",
    modules={"noise::lib": "fn value() -> u32 { return 7u; }"},
    options=wesl.CompileOptions(keep=["main"]),
)
```

Imports across package boundaries work without visibility modifiers when
`visibility=False`, the binding default.
For shaders you maintain, mark declarations exported to other packages as `public`
and enable `visibility=True`. Declarations used only within the package can keep
their default visibility. The repository examples and shader tests enable these
checks.
This applies to declarations. To re-export an imported name, mark the import
with `@publish`. Each conditional import needs the annotation:

```wesl
@if(packed_rgb)
@publish import package::packed::sample_im;
@else
@publish import package::standard::sample_im;
```

If this code is in `sampling.wesl` in the `image` library, consumers can use
`import image::sampling::sample_im;`.

Within a library, `package::` and relative imports refer to that library.
Virtual modules use the exact package paths that upstream's resolver receives.
If `noise::lib` imports `arithmetic::one`, supply that dependency under
`noise/arithmetic`. A module within that dependency uses a key such as
`noise/arithmetic::helpers`. The slash separates package dependencies.
WESL source still uses normal import syntax.
For example, `alpha/common` and `beta/common` identify separate dependencies.
Neither falls back to a virtual module named `common`.
These keys identify virtual modules. Virtual module mappings do not define a
package dependency graph or deduplicate package instances.
Use `dependencies` to register directories for named libraries.
With a project dependency graph, module overrides follow package aliases.
An override through either alias replaces the same module and preserves shared state.
This also applies to `constant_modules` and `filenames`.
Conflicting sources or filename labels for aliases of the same module raise `ValueError`.

## Supply constants

Pass `constant_modules` to supply scalar constants for one compilation:

```python
compiler = wesl.Compiler(root_directory="shaders")
result = compiler.compile_file(
    "main.wesl",
    constant_modules={
        "package::config": {"width": 64, "scale": 0.5, "enabled": True},
    },
)
```

The shader imports these constants from a virtual module:

```wesl
import package::config::{width, scale, enabled};

@compute @workgroup_size(width)
fn main() {
    let amount: f32 = select(0.0, scale, enabled);
}
```

`compile`, `compile_source`, `compile_file`, and both `Compiler` methods accept
`constant_modules`. The outer mapping uses the same module paths as `modules`,
including scoped dependencies. Each inner mapping pairs constant names with values.
Compilation preserves the supplied mappings and the stored compiler settings.
Omit the argument, or pass `None` or `{}`, to generate no modules.

The compiler emits one `public const` declaration for each value:

| Python value | Generated declaration |
| --- | --- |
| `64` | `public const width = 64;` |
| `0.5` | `public const scale = 0.5;` |
| `True` | `public const enabled = true;` |

Numeric declarations retain WGSL's abstract numeric types. The shader determines
the concrete type where it uses a constant. For example, the same integer constant
can initialize an `i32` or a `u32` when its value fits both types.
Float values retain a decimal point or exponent, including `1.0` and `-0.0`.

Values accept Python `bool`, `int`, and finite `float` instances.
They also accept `numbers.Integral` and `numbers.Real` instances.
Integers must fit the signed 64-bit range. Real values must convert to a finite
Python `float` without loss of precision. Common NumPy integer and floating scalars
meet these requirements. Their dtype does not determine the WGSL type.
Compilation does not import or require NumPy.

WESL generates the declarations and formats the literals. Declaration order is
unspecified. The pinned parser cannot parse its generated literal for `-2**63`.
Using that value raises `CompileError` when the compiler loads its module.

Strings, complex values, arrays, and other unsupported types raise `TypeError`.
Invalid identifiers, NaN, infinity, integers outside the supported range, and
lossy conversions raise `ValueError`. Errors identify the module and constant.
Normalization and identifier checks also apply to unused modules.
The GPU runtime still validates the concrete types and shader constraints.

Each generated module replaces the whole file at its path. Constants do not merge
with declarations from that file. A path present in both `modules` and
`constant_modules` raises `ValueError`. This includes the root source supplied to
`compile_source` or `compile_file`. Generated source appears in `CompileResult.sources`
when the module is used and source maps are enabled. `filenames` can label it.

These constants can supply constant expressions, such as `@binding` arguments.
Use WGSL `override` declarations for values supplied during pipeline creation.
Use `features` for `@if` conditions. Constant modules do not add numeric conditions
to `@if`. Use source modules for explicit types, vectors, arrays, or expressions.
Upstream lowering also applies to generated constants when `lower=True`.

## Reuse compilation settings

`Compiler` stores `options`, `modules`, `filenames`, `root_directory`, and `dependencies`.
These are optional keyword arguments. Each instance owns its default settings.
Supplied settings and mappings remain shared with the caller.
Set persistent compiler flags through `compiler.options`.
This example uses `shaders/main.wesl` from [above](#compile-strings-and-files):

```python
import wesl

compiler = wesl.Compiler(root_directory="shaders")
result = compiler.compile_file("main.wesl")
result = compiler.compile_source("@compute @workgroup_size(1) fn main() {}")
```

Load a manifest from a directory or its nearest ancestor with:

```python
compiler = wesl.Compiler.from_project(
    ".", options=wesl.CompileOptions(features=wesl.Features(flags={"enabled": True}))
)
result = compiler.compile_file("main.wesl")
```

This constructor raises `FileNotFoundError` if it finds no manifest.
It accepts the same settings as `Compiler`, with `dependencies` limited to a
mapping of directory overrides. Explicit settings override the manifest.
It stores the project settings for subsequent compilation.
The constructor resolves the root directory, relative overrides, and all manifests
once. Its `dependencies` holds the resulting `Dependencies` snapshot.
Construct a new compiler to pick up manifest changes.
Each compilation reads current shader contents from the stored directories.
`Compiler.compile_file()` uses these settings without searching for another manifest.

`compile_source(source, *, root="package::main", filename="<string>", ...)`
uses the stored settings. Both methods accept `features`, `keep`, `keep_main`, and
`strip` overrides for one call. They also accept `constant_modules` for that call.
`compile_file(filename, ...)` resolves relative paths from `root_directory`,
or the working directory when `root_directory` is `None`.
Each call compiles again. The object does not cache results.

## Compilation results

All compilation functions return an immutable `CompileResult`.
Use `result.wgsl` to pass the shader to wgpu-py.
`str(result)` also returns WGSL. Results support equality and pickle.

- `wgsl`: Compiled WGSL source.
- `modules`: Tuple of loaded module names in upstream order, with the root
  first.
- `entry_points`: Tuple of entry-point names in the emitted WGSL.
- `sources`: Dictionary from loaded module names to immutable `Source` records.

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
The top-level `package.wesl` or `package.wgsl` supplies the namespace's root module.
The loader skips `*.test.wesl` files. Pytest collects those files separately.
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

- `message`: Error message without the source excerpt.
- `module`: WESL module name, when available.
- `filename`: Display filename, when available.
- `source`: Source text associated with the error, when available.
- `span`: UTF-8 byte offsets `(start, end)` with an exclusive end.
- `line`, `column`: The start position, with one-based line and character
  numbers.
- `end_line`, `end_column`: The exclusive end position, with the same numbering.

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
`wesl.__version__` matches Python distribution metadata. This package uses the
WESL workspace crates at commit
[`0303eccfafd534cc76c91eddd4b4f5c4413a1733`](https://github.com/webgpu-tools/wesl-rs/tree/0303eccfafd534cc76c91eddd4b4f5c4413a1733).
This commit follows upstream 0.5.0 and includes
[PR #301](https://github.com/webgpu-tools/wesl-rs/pull/301) and
[PR #307](https://github.com/webgpu-tools/wesl-rs/pull/307).
Python wheels include the compiled Rust dependencies. Source builds require
Cargo and access to the pinned Git sources unless those sources are cached.
The source distribution includes `Cargo.lock`; builds use locked resolution.
Report parser defects to the [upstream issue tracker](https://github.com/webgpu-tools/wesl-rs/issues).
See [LICENSE](../LICENSE) for source provenance and third-party notices.

The binding enables imports, conditional translation, name mangling,
source diagnostics, and upstream validation by default. It enables evaluation
and disables generics at build time. Lowering is available through `CompileOptions`.
Upstream validation does not catch every WGSL error.
