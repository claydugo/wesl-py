# API reference

Import the `wesl-py` distribution as `wesl`.

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

`compile(modules, *, root="package::main", options=None, features=None, constants=None,
keep=..., keep_main=None, strip=None, filenames=None, root_directory=None,
dependencies=None)` returns a `CompileResult`.

Module keys and `root` use paths such as `package::main`.
Imports resolve through `modules`; `root_directory` also enables file imports.
Compilation preserves supplied mappings.

`features`, `keep`, `keep_main`, and `strip` override the corresponding fields in
`options` for one call. They do not mutate the supplied options.
Omit `keep` to use the stored selection.
See retention rules below for `None` and `[]`.
The other keyword overrides use `None` to retain the stored setting.

`CompileOptions` is a mutable dataclass of upstream compiler options.
The shader runner uses `TestOptions`.
See [shader test options](testing.md#fixtures-and-pytest-behavior).
Both accept only keyword arguments. Omit `options` for the defaults below.
Visibility checks default to `False` so existing external shaders remain usable.

`features` accepts a mapping such as `{"enabled": True}` or a `Features` instance.
Mappings use the default policy, `Feature.Disable`.
`CompileOptions.features` and `TestOptions.features` hold `Features` instances.
A call-level feature setting replaces the stored setting without merging flags.

`Features()` defaults to an empty flag dictionary and `Feature.Disable`.
Policies are `Feature.Enable`, `Feature.Disable`, `Feature.Keep`, and `Feature.Error`.
Each applies to the default or an individual flag. Flags also accept booleans.
Annotate reusable flags as `dict[str, bool | wesl.Feature]`.

`Feature.Keep` preserves unresolved conditions for a later compilation.
`Feature.Error` rejects flags that the compiler evaluates with that policy.
Unused supplied flags do not cause an error.
Using `modules` from the first example, this call raises `CompileError` because
`enabled` has no value:

```python
features = wesl.Features(default=wesl.Feature.Error)
wesl.compile(modules, features=features, keep=["answer"])
```

`Feature` and `ManglerKind` are Python enums.
Both enums, `CompileOptions`, and `Features` support pickle for process workers.

The retention options follow
[wesl-rs `CompileOptions`](https://github.com/webgpu-tools/wesl-rs/blob/v0.6.0/crates/wesl/src/frontend.rs).
`keep_main` and `mangle_main` refer to the root module, not a function named `main`.

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
When `keep` applies, the compiler rejects unknown names. This includes
declarations that conditional translation removes.

A root with only unused helpers produces empty WGSL by default.
Modules load on demand; compilation does not scan the package.

Set `mangle_main=True` to rename root declarations as well as imported declarations.
Selections always use original names, independent of mangling.

The remaining `CompileOptions` fields use upstream names:

- `imports=True`: Resolve imports.
- `condcomp=True`: Evaluate conditional translation attributes.
- `visibility=False`: Ignore visibility restrictions. Set `True` to require
  declarations imported from external packages to be `public`.
- `lower=False`: Lowering is unsupported. Set `True` to raise `NotImplementedError`.
- `validate=True`: Run upstream compiler checks.
- `sourcemap=True`: Record source text and declaration names.
- `mangler=ManglerKind.Escape`: Select the declaration naming scheme.

The build enables upstream evaluation. It does not enable generics.

The compiler recurses on the caller's stack. A large expression can overflow
that stack and crash the process. The limit depends on the platform, the stack
size, and the build profile. A
[10,000-term sum](https://github.com/claydugo/wesl-py/actions/runs/35526430139/job/106119676932)
crashes on Windows.

Disabling visibility follows the [upstream recommendation](https://github.com/webgpu-tools/wesl-rs/issues/300#issuecomment-5757180358).

`mangler` accepts `ManglerKind.Escape`, `ManglerKind.Hash`,
`ManglerKind.Unicode`, or `ManglerKind.None_`.
`None_` represents the Rust `None` variant and disables mangling.
The Unicode mangler keeps paths in names. A WGSL runtime can reject these names.

Invalid argument types raise `TypeError`. Invalid module names raise
`ValueError`. Missing modules and compiler failures raise `CompileError`.

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

Imports must precede directives and declarations in the assembled source.
Keep directives such as `enable f16;` between imports and declarations.

`compile_file(filename, ...)` reads the root file as UTF-8.
The file's parent directory is the default `root_directory`.
Pass `root_directory` to set a different import root.
The file path must be inside that directory. Its relative path determines
the root module name. For example, `nested/main.wesl` becomes
`package::nested::main`. A top-level `package.wesl` or `package.wgsl` becomes `package`.
The helper preserves symlinks. Imports resolve from the supplied directory,
including when the root file is a symlink to a file outside that directory.
File paths and root directories can contain `..`.

Invalid root file paths raise the corresponding Python file exception.
A file outside `root_directory` raises `ValueError`.

Both functions accept `options` and the keyword overrides from `compile()`.
Imports check `modules`, then `.wesl` files, then `.wgsl` files.
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

All compilation functions accept `dependencies`, a mapping of package names to
shader directories. Relative paths use the working directory.

The package root is `package.wesl`. For example, `library::value` refers to
`value` in that file, and `library::math::value` refers to `value` in `math.wesl`.
Register `alpha/common` when `alpha` imports `common`. A top-level `common` entry
does not supply that dependency. Use `package::` for imports within a library.
Entries in `modules` override files.

Each compilation reads the current sources. The binding does not download libraries.

Use `wesl.toml` to set the project shader root:

```toml
edition = "2026_pre"
root = "shaders"
```

`Compiler.from_project()` finds the nearest ancestor manifest.
Upstream `WeslToml` parses the manifest and supplies the root.
The default root is `shaders`. Relative roots use the manifest directory.
The constructor loads the `path` entries of `[dependencies]`.
An explicit `dependencies` mapping replaces them.
The binding does not deduplicate package instances.

Manifest `include` and `exclude` patterns do not filter explicitly requested imports
or pytest collection.

`compile()`, `compile_source()`, and `compile_file()` do not discover manifests.

Named libraries can also use `modules`:

```python
import wesl

result = wesl.compile_source(
    "import noise::lib::value; fn main() -> u32 { return value(); }",
    modules={"noise::lib": "fn value() -> u32 { return 7u; }"},
    options=wesl.CompileOptions(keep=["main"]),
)
```

For shaders you maintain, mark declarations exported to other packages as `public`
and enable `visibility=True`. In a named library, wesl-rs also requires `public`
on declarations that other modules of the same library import.
The SDF, optimizer, and convolution examples enable these checks.
To re-export an imported name, mark the import `public`.
Each conditional import needs the modifier:

```wesl
@if(packed_rgb)
public import package::packed::sample_im;
@else
public import package::standard::sample_im;
```

If this code is in `sampling.wesl` in the `image` library, consumers can use
`import image::sampling::sample_im;`.

Within a library, `package::` and relative imports refer to that library.
Virtual modules use the exact package paths that upstream's resolver receives.
If `noise::lib` imports `arithmetic::one`, supply that dependency under
`noise/arithmetic`. A module within that dependency uses a key such as
`noise/arithmetic::helpers`. The slash separates package dependencies.
Virtual mappings do not define dependency graphs or deduplicate package instances.

## Supply constants

Pass `constants` to supply constants for one compilation, as the `constants`
parameter of wesl-js `link()` does:

```python
compiler = wesl.Compiler(root_directory="shaders")
result = compiler.compile_file(
    "main.wesl",
    constants={"width": 64, "scale": 0.5, "enabled": True},
)
```

The shader imports these constants from the virtual module `constants`:

```wesl
import constants::{width, scale, enabled};

@compute @workgroup_size(width)
fn main() {
    let amount: f32 = select(0.0, scale, enabled);
}
```

All compilation functions and methods accept `constants`.
The mapping pairs constant names with values.

The compiler emits one `public const` declaration for each value:

| Python value | Generated declaration |
| --- | --- |
| `64` | `public const width = 64;` |
| `0.5` | `public const scale = 0.5;` |
| `True` | `public const enabled = true;` |
| `"vec2f(0.5, 0.75)"` | `public const center = vec2f(0.5, 0.75);` |

Numbers retain WGSL's abstract numeric types; shader use determines concrete types.
Float literals retain a decimal point or exponent, including `1.0` and `-0.0`.

Values accept Python `bool`, `int`, and finite `float` instances.
They also accept `numbers.Integral` and `numbers.Real` instances.
Integers must fit the signed 64-bit range. Real values must convert to a finite
Python `float` without loss of precision. Common NumPy integer and floating scalars
meet these requirements. Their dtype does not determine the WGSL type.
Compilation does not import or require NumPy.
A `str` value is a WGSL expression, as in wesl-js. The compiler inserts it unchanged.

Declaration order is unspecified.
The pinned parser cannot parse its generated literal for `-2**63`.
Using that value raises `CompileError` when the compiler loads its module.

Complex values, arrays, and other unsupported types raise `TypeError`.
Invalid identifiers, invalid expressions, NaN, infinity, integers outside the
supported range, and lossy conversions raise `ValueError`.
Errors identify the constant.
Normalization and identifier checks also apply when no shader uses the module.

A `constants` key in `modules` together with `constants` raises `ValueError`.
Generated source appears in `CompileResult.sources` under `constants` when the
module is used and source maps are enabled. `filenames` can label it.

These constants can supply constant expressions, such as `@binding` arguments.
Use WGSL `override` declarations for values supplied during pipeline creation.
Use `features` for `@if` conditions. The `constants` module does not add
numeric conditions to `@if`. Use source modules for declarations other than
`const`.

## Reuse compilation settings

`Compiler` stores `options`, `modules`, `filenames`, `root_directory`, and `dependencies`.
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
It accepts the same settings as `Compiler`.
An explicit `root_directory` overrides the manifest root.
The constructor reads one manifest and fixes the root and dependency paths.

`compile(*, root="package::main", ...)` compiles a module path with the stored settings.
`compiler.compile(root="package::regions::extents")` compiles the module that
`var_reflection` and `classify_entry_points` name with the same path.
`compile_source(source, *, root="package::main", filename="<string>", ...)`
uses the stored settings.
`compile_file(filename, ...)` resolves relative paths from `root_directory`,
or the working directory when `root_directory` is `None`.

## Compilation results

All compilation functions return an immutable `CompileResult`.
`str(result)` also returns WGSL. Results support equality and pickle.

- `wgsl`: Compiled WGSL source.
- `modules`: Tuple of loaded module names in upstream order, with the root
  first.
- `entry_points`: Tuple of entry-point names in the emitted WGSL.
- `sources`: Dictionary from loaded module names to immutable `Source` records.

Each access to `sources` returns a dictionary copy.
The source text comes from the upstream source map.
With `CompileOptions(sourcemap=False)`, `sources` is empty.

`Source(text, filename=None)` retains exact UTF-8 source text and a display label.
`compile_file` uses the absolute filename as its label.
Source records support equality, hashing, and pickle.

## Reflection

`wesl.reflect` reads buffer layouts and entry points from WESL declarations.
Its functions follow the `wesl-reflect` package of wesl-js. After `import wesl`,
the module is available as `wesl.reflect`.
Each function takes a `Compiler` and a fully qualified path. It compiles the
module with the compiler's modules, filenames, root directory, dependencies, and
feature flags. Reflection does not add the `constants` module. To reflect a
shader that imports `constants::`, put a `constants` module in the compiler's
modules.
`var_reflection`, `build_struct_registry`, `numpy_dtype`, and `decode_buffer`
need NumPy to build dtypes. No function imports wgpu-py.

```python
from wesl.reflect import classify_entry_points, var_reflection

particles = var_reflection(compiler, "package::simulation::particles")
buffer_size = particle_count * particles.dtype.itemsize
workgroup_sizes = {
    entry_point.fn_name: entry_point.workgroup_size
    for entry_point in classify_entry_points(compiler, "package::simulation")
}
```

| Function | Result | wesl-js function |
| --- | --- | --- |
| `var_reflection(compiler, path)` | `VarReflection` | `varReflection` |
| `build_struct_registry(compiler, module)` | `dict` of struct names to dtypes | `buildStructRegistry` |
| `classify_entry_points(compiler, module)` | `list` of `EntryPoint` | `classifyEntryPoints` |
| `numpy_dtype(compiler, path)` | Structured NumPy dtype | `typeShape` |
| `decode_buffer(compiler, path, data, *, offset=0)` | NumPy arrays | `decodeBuffer` |

`VarReflection` is a frozen dataclass with these fields:

- `var_name`: The last component of `path`.
- `address_space`: The address space in the declaration, such as `"storage"`, or
  `None` when the declaration has none.
- `access_mode`: The access mode in the declaration, such as `"read_write"`.
  An omitted access mode gives `None`, as in wesl-js.
- `group` and `binding`: The evaluated `@group` and `@binding` arguments. The
  arguments can be constant expressions. A variable without them gives `None`.
- `dtype`: The NumPy dtype of the type, with the layout of `numpy_dtype`.
  For a runtime-sized array, this is the element type, padded to the array
  stride.
- `byte_size`: The size of the type in bytes. A runtime-sized array gives 0.

A structure that ends in a runtime-sized array gives `dtype=None` and
`byte_size=0`.
A type whose size depends on an override, or a type without a host-shareable
layout such as `bool`, gives `dtype=None` and `byte_size=0`.

`TypeShapeError` is a `ValueError` with a `var_name` attribute, as in wesl-js.
The functions raise it for a texture or a sampler, for a path that names no
module and item, and for a path whose item is neither a type nor a typed
module-scope variable.

`numpy_dtype()` and `decode_buffer()` accept a type path or a variable path.
For a type, `numpy_dtype()` gives the dtype of one element, and
`decode_buffer()` reads `data` as an array of that type, so the result has the
element count first. For a variable, `numpy_dtype()` gives `dtype` of
`var_reflection()`, and `decode_buffer()` decodes the variable's own type: a
`vec3f` variable gives shape `(3,)`, and a runtime-sized array takes its length
from `data`. `offset` skips that many bytes at the start of `data`.
In a dtype, an array of `vec3` values or a matrix with three rows keeps its
padding component, so a `mat3x3f` member has shape `(3, 4)`. `decode_buffer()`
removes that padding:

```python
results = decode_buffer(compiler, "package::simulation::results", readback, offset=16)
```

`build_struct_registry()` maps the name of each structure that the module
declares to its dtype. It leaves out imported structures. A structure without a
dtype maps to `None`.

`classify_entry_points()` returns an `EntryPoint(fn_name, stage, workgroup_size)`
named tuple for each `@compute`, `@vertex`, and `@fragment` function of the
module, in declaration order. `stage` is `"compute"`, `"vertex"`, or
`"fragment"`. `workgroup_size` is a tuple of three integers, with 1 for an
omitted dimension. The arguments can be constant expressions.
`workgroup_size` is `None` for a vertex or fragment function, and when the size
uses an override.

Errors in a reflected module name the module, for example
`= note: in package::regions::extents`.

## Package resources

Use `load_modules()` for installed Python resources.
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

`load_modules(directory, *, namespace)` accepts a `Traversable` resource collection.
This includes the `Path` objects returned by `importlib.resources.files()`.
It returns `LoadedModules(modules, filenames)`.
Relative file paths become names within the explicit namespace.
The top-level `package.wesl` or `package.wgsl` supplies the namespace's root module.
The loader skips `*.test.wesl` files. Pytest collects those files separately.
The loader preserves UTF-8 text and line endings. It sorts the output mappings.
It prefers `.wesl` over `.wgsl` for the same relative stem.
A resource that is not a directory raises `NotADirectoryError`.
Different paths that produce the same module name raise `ValueError`.
Filesystem traversal accepts directory symlinks. Cycles raise `ValueError`.
Zipped resources use stable labels without extraction.
The helper does not cache resources or discover packages implicitly.

## Validation

Compilation runs the checks provided by wesl-rs unless `options.validate` is false.
These checks do not establish
complete WGSL validity. For example, some type errors pass compilation.
Pass the output to the target runtime for shader and pipeline validation.
The package does not expose a standalone semantic validator.

## Diagnostics

```python
import wesl

try:
    wesl.compile_source("fn main(", filename="shaders/broken.wesl")
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
length in bytes.

A column advances by one for each Unicode character, including a tab.
Position attributes are `None` when the source or a valid offset is
unavailable.

All compilation functions accept `filenames`, a mapping from module
names to display filenames. Values accept strings or path objects.
File imports use their filesystem paths when reporting errors.

## Threads

Each native operation copies its Python inputs, then detaches from Python while
Rust parses or compiles.

## Build identity

`wesl.__version__` matches Python distribution metadata. The package uses the
WESL [0.6.0](https://github.com/webgpu-tools/wesl-rs/tree/v0.6.0) crates from crates.io.
Python wheels include the compiled Rust dependencies. Source builds require
Cargo and access to crates.io unless the crates are cached.
The source distribution includes `Cargo.lock`; builds use locked resolution.
Report parser defects to the [upstream issue tracker](https://github.com/webgpu-tools/wesl-rs/issues).
See [LICENSE](../LICENSE) for source provenance and third-party notices.
