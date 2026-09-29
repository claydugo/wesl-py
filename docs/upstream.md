# Upstream integration limits

Reviewed on 2026-09-29 against the pinned WESL commit
[`0303ecc`](https://github.com/webgpu-tools/wesl-rs/tree/0303eccfafd534cc76c91eddd4b4f5c4413a1733).
GitHub main still matches this revision at review time.
The review checks API preconditions, control cases, and existing reports.
The reproductions use upstream APIs without the binding's compiler adapter.

## Next actions

Ten defects warrant new reports: nine in wesl-rs and one in wgsl-test.
The getter annotation request already has a PyO3 pull request.
Prioritize the lost initializer because it changes execution of valid input.

These reports do not all block publication.
Both wesl-rs and this binding disable lowering by default.
The lowering defects affect callers that enable it.
See the [release checklist](../RELEASE_CHECKLIST.md) for publication requirements.

| Item | Current binding behavior | Upstream action |
| --- | --- | --- |
| [Lost for initializer](#lowering-drops-side-effects-in-a-for-initializer) | Lowering changes ordinary shader behavior; tests have a partial workaround | Preserve the initializer and its scope |
| [Invalid bitcast alignment](#lowering-panics-on-an-invalid-bitcast-with-zero-alignment) | Ordinary lowering raises `PanicException`; custom result checks reject zero alignment | Reject nonnumeric bitcast operands before computing their size |
| [Disabled visibility](#compiler-driver-integration) | The adapter honors the option | Apply the visibility option during usage analysis |
| [Disabled imports](#compiler-driver-integration) | The adapter honors the option | Restore the documented behavior of the imports option |
| [Qualified references](#compiler-driver-integration) | The adapter avoids a false cycle | Keep qualified references separate from local declarations |
| [Package visibility](#package-visibility-inside-named-packages) | One valid import case remains a strict expected failure | Permit package-visible imports within the same named package |
| [Quoted visibility](#quoted-visibility-modifiers) | Generated declarations set visibility through the syntax API | Accept visibility keywords in inline declaration quotes |
| [Diagnostic line boundaries](#diagnostic-rendering-uses-different-line-boundaries) | Compiler errors retain incorrect rendered locations | Count WGSL line breaks when rendering diagnostics |
| [Parser EOF spans](#parser-eof-spans-split-utf-8-characters) | The binding corrects EOF spans before rendering | Return an empty EOF span at the source end |
| [Exact assertion values](#the-bundled-assertion-protocol-loses-integer-precision) | Local fields preserve exact operands | Preserve integer operands in shader results and host decoding |

Record each upstream issue or pull request and the fix revision below.
When updating a dependency, rerun its reproducer without the local workaround.
Remove a workaround only after the pin includes the fix and its binding tests pass.

The Rust examples require neither Python nor a GPU. Use this dependency:

```toml
[dependencies.wesl]
git = "https://github.com/webgpu-tools/wesl-rs"
rev = "0303eccfafd534cc76c91eddd4b4f5c4413a1733"
default-features = false
features = ["eval"]
```

Each Rust example is a separate `src/main.rs`, except the PyO3 example.

## Lowering drops side effects in a for initializer

Source: [eval/lower.rs](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/eval/lower.rs).

When a `for` condition lowers to `false`, lowering replaces the entire statement
with `Statement::Void`.
WGSL executes the initializer before it checks the condition.
This is incorrect execution of valid input. See the [for statement specification](https://www.w3.org/TR/WGSL/#for-statement).

```rust
use wesl::syntax::{Expression, TranslationUnit};

fn main() {
    let mut module: TranslationUnit = "
        var<private> count: u32 = 0u;
        fn bump() { count += 1u; }
        fn main() -> u32 {
            for (bump(); false; ) {}
            return count;
        }
    ".parse().unwrap();
    wesl::pass::retarget_idents(&mut module);
    wesl::pass::validate_wesl(&module).unwrap();
    let expression: Expression = "main()".parse().unwrap();
    let before = wesl::exec(
        &expression, &module, Default::default(), Default::default(),
    ).0.unwrap();
    wesl::pass::lower(&mut module).unwrap();
    let after = wesl::exec(
        &expression, &module, Default::default(), Default::default(),
    ).0.unwrap();
    assert_eq!(before, after);
}
```

Observed: `before` contains `U32(1)` and `after` contains `U32(0)`.
Ordinary `wesl.compile` with `CompileOptions(lower=True)` also removes `bump()`.
Both `CompileOptions.lower` and `TestOptions.lower` default to `False`.
The compiler adapter does not correct this lowering defect.

In [compile_test](../src/testing.rs), instrumentation moves initializers into
enclosing blocks before lowering. It skips functions in `wgsl_test` and
`wgsl_test::TestResult`, so this workaround has limited coverage.
An overridden `expect` with a failing assertion in a false loop's initializer
fails with `lower=False` but passes with `lower=True`.
[test_assertions_in_control_flow](../tests/test_shader_assertions.py) covers initializers
in test functions with both settings.

Submit a fix that preserves the initializer and its scope.
Cover a call initializer, a declaration with a side effect, and no initializer.
Remove the local initializer transformation after adopting that fix and verifying
assertion instrumentation with the control-flow tests.
Also verify ordinary compilation and overridden assertion modules without the
transformation. Both must preserve the initializer's side effects.

## Lowering panics on an invalid bitcast with zero alignment

The standard compiler panics on this source with `lower=true`, `validate=true`,
and `keep_main=true`:

```wesl
struct Value { @align(0) member: u32 }
fn main() -> u32 { return bitcast<u32>(Value(0u)); }
```

Both the alignment and the bitcast operand are invalid WGSL.
Compilation must reject the source. Instead, [bitcast type evaluation](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wgsl-types/src/builtin/call_ty.rs)
computes the operand's size before rejecting its nonnumeric type.
Layout arithmetic then divides by zero.
This reproduces through `wesl::compile` with validation enabled.
It does not require a direct call to the low-level layout API.
Python `compile_source` with `CompileOptions(lower=True, validate=True)` and
`keep_main=True` raises `PanicException` instead of `CompileError`.

Reject nonnumeric bitcast operands before computing their size.
The binding's custom result checks still need to reject zero alignment.
This narrow bitcast fix does not establish general layout validation.

## Diagnostic rendering uses different line boundaries

Source: [error.rs](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/error.rs).
The renderer passes the source directly to `annotate-snippets`.

```rust
use wesl::syntax::TranslationUnit;

fn main() {
    let source = "fn main() {\rlet value = missing;\r}";
    let mut module: TranslationUnit = source.parse().unwrap();
    wesl::pass::retarget_idents(&mut module);
    let diagnostic = wesl::error::Diagnostic::from(
        wesl::pass::validate_wesl(&module).unwrap_err(),
    );
    println!("{}", diagnostic.with_source(source.into()).render_plain());
}
```

Observed: the renderer places `missing` on line 1, column 25.
WGSL coordinates are line 2, column 13.
LF and CRLF controls render correctly.
CR, vertical tab, form feed, NEL, U+2028, and U+2029 reproduce the mismatch.
These are [WGSL line breaks](https://www.w3.org/TR/WGSL/#line-break).

The binding normalizes assertion sources in [render_diagnostic](../src/lib.rs).
[test_failure_with_unicode_line_breaks](../tests/test_shader_errors.py) covers all eight
line-break sequences and multibyte text before the span.
Compiler errors use upstream rendering and retain this mismatch.

Normalize a rendering copy and remap its byte spans, or add suitable renderer
support.
Preserve declaration notes and the original source and byte spans exposed to
Python. Cover compiler errors with multibyte text before the span.
Remove the local normalization after upstream rendering passes the same cases.

## Parser EOF spans split UTF-8 characters

Parsing an incomplete function followed by U+2028 produces an invalid byte span:

```rust
use wesl::syntax::TranslationUnit;

fn main() {
    let source = "fn f() {\u{2028}";
    let error = source.parse::<TranslationUnit>().unwrap_err();
    let diagnostic = wesl::error::Diagnostic::from(error).with_source(source.into());
    println!("{}", diagnostic.render_plain());
}
```

The parser returns `8..9`. U+2028 occupies bytes `8..11`, so rendering panics.
NEL and U+2029 reproduce the failure. The caller supplies no span.
The source is incomplete, so the expected result is a syntax diagnostic.

The [parser error conversion](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wgsl-parse/src/error.rs#L91-L94)
adds one byte to the end of the last consumed token for an EOF error.
An empty span prevents the panic. Reporting the actual source end also requires
accounting for trailing blankspace.

The binding already rewrites EOF spans to the source end in
[Failure::from_diagnostic](../src/lib.rs).
`wesl.check_syntax` reports `CompileError` for this input without panicking.
Keep that rewrite until upstream supplies an empty span at the actual source end.

## PyO3 rejects signature overrides on getters

Sources: [signature handling](https://docs.rs/crate/pyo3-macros-backend/0.29.2/source/src/method.rs)
and [type annotations](https://pyo3.rs/v0.29.2/function/signature.html#type-annotations-in-the-signature).
The rejection remains in the audited PyO3 main source.

This separate crate uses `pyo3 = { version = ">=0.29.2,<0.30",
features = ["experimental-inspect"] }` and the following `src/lib.rs`:

```rust
use pyo3::{prelude::*, types::PyTuple};

#[pyclass]
struct Example;

#[pymethods]
impl Example {
    #[getter]
    #[pyo3(signature = () -> "tuple[str, ...]")]
    fn names<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, ["name"])
    }
}
```

Observed: `cargo check` rejects `signature` on `getter`.
PyO3 supports explicit return annotations on ordinary functions.
Returning an erased `PyTuple` or `PyAny` loses element or concrete-type information.
The [stub script](../scripts/generate_stubs.py) restores tuple types for
`CompileResult.modules`, `CompileResult.entry_points`, and `TestResult.values`.

[PR #5738](https://github.com/PyO3/pyo3/pull/5738) is open and implements getter
and setter signatures with tests.
This is a tracked feature request. It needs no new report.
Follow that PR. Once a release includes it, annotate the native getters and remove
these three corrections after verifying the generated stubs.

## The bundled assertion protocol loses integer precision

Source: [wgsl-test assertions](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders/lib.wesl).
This revision is also the audited wesl-js main.

`expectEq` compares the `u32` operands before it converts them to `f32`.
Its pass/fail decision remains exact.
`recordFailure` stores the converted values in `vec4f` fields, so failure reports
lose precision.
For example, neither operand in `expectEq(4294967295u, 4294967294u)` is exactly
representable as `f32`. The recorded values can coincide.
[WGSL conversion rules](https://www.w3.org/TR/WGSL/#floating-point-conversion)
permit either adjacent representable value, so identical results are not
guaranteed across implementations.

The upstream [host decoder](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/src/TestWesl.ts)
also reads these operands as floats.
The upstream `runWesl` harness reproduces the precision loss with wgsl-test 0.2.35,
Node 22.23.2, and webgpu 0.3.8. Its host source matches the audited revision.
It reports both large operands as `4294967296` while correctly reporting failure.
A second failed assertion increases `failCount` to two.
A control with small integers retains the first failed pair correctly.
First-failure retention needs no fix.
Add the exact-integer case to [TestWesl.test.ts](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/src/test/TestWesl.test.ts).
Preserving operand types requires agreement on the shader and host representation.

The binding preserves `recordFailure` and appends `actual_bits` and
`expected_bits` in [compile_test](../src/testing.rs).
[test_failure_in_imported_helper](../tests/test_shader_assertions.py) verifies exact integers
and retention of the first failure.
Replace these fields only after adopting an upstream protocol that preserves
the supported operand types. Source locations and execution metadata still need
local instrumentation.
The [testing guide](testing.md#assertions) defines the result layout contract.

## Dependency constraints

The binding pins WESL to retain required fixes. Recheck these constraints before
changing the dependency revision.

### Compiler driver integration

The pin uses upstream 0.5.0 at `0303eccfafd534cc76c91eddd4b4f5c4413a1733`.
[The adapter](../src/compiler.rs) implements upstream `CompilerDriver`.
It uses public upstream APIs.
It calls the upstream parsing, conditional translation, usage analysis, linking,
mangling, lowering, and validation passes. It records original sources before
applying the project and test transformations.

The public `CompilerDriver` API supports custom compilation passes.
The standard frontend keeps its default driver private.
A hook around module loading could reduce duplicated option handling, but the
current API supports the binding's transformations. It needs no defect report.

Test discovery parses declarations. Test selection uses the public
`pass::condcomp` directly. Neither requires the custom driver.
Compiling with imports disabled removes
qualified paths that the generated test entry point still needs.

Three small examples fail through upstream `wesl::compile` at this revision.
Use `CompileOptions { visibility: false, keep_main: true, ..Default::default() }`
and a `wesl::resolver::VirtualResolver` with `package::main` as the main module.

For disabled visibility, the main source is:

```wesl
import library::value;
fn main() -> u32 { return value(); }
```

Set the `library` source to `fn value() -> u32 { return 7u; }`.
Compilation requires public visibility despite the option.
Making the function public succeeds. A private function still fails when checks
are disabled. This contradicts the documented visibility option.

For disabled imports, use the same main source with `missing` in place of
`library`. Also set `imports: false`. Compilation tries to resolve `missing`.
The option documents removal of imports and qualified paths without resolving
their targets. Both explicit imports and inline paths reproduce the failure.

For the qualified reference, the main source is:

```wesl
fn value() -> u32 { return package::helper::value(); }
```

Set `package::helper` to `fn value() -> u32 { return 7u; }`.
Compilation reports a cycle in `value`.
Renaming the calling function or importing the helper under an alias succeeds.

Report these cases upstream:

- In `pass::usage_analysis`, apply `ignore_visibility` when first finding a
  declaration. The adapter passes private minimum visibility when checks are off.
- Restore `CompileOptions.imports` handling in the frontend. The adapter prevents
  external module traversal and linking when imports are off.
- In `pass::retarget_idents`, keep qualified references separate from local
  declarations. The adapter gives those references independent identifiers after
  upstream retargeting and before validation.

The existing project tests cover scoped imports and shared package state.
Visibility tests cover private and public external declarations with source maps
enabled and disabled. After adopting an upstream fix, remove its adapter adjustment
and run the corresponding regression tests:

| Adjustment | Regression tests |
| --- | --- |
| Disabled visibility | `test_external_visibility_is_optional` in [test_compile.py](../tests/test_compile.py) |
| Disabled imports | `test_import_resolution_can_be_disabled` and `test_disabled_imports_preserve_the_root_entry_point` in [test_compile.py](../tests/test_compile.py) |
| Qualified references | `test_resource_loader_compiles_package_roots` in [test_resources.py](../tests/test_resources.py) and `test_cooperative_qualified_workgroup_size` in [test_shader_workgroups.py](../tests/test_shader_workgroups.py) |

The adapter still supplies module transformations after these fixes.
Verify option parity with [tests/upstream.rs](../tests/upstream.rs) when changing it.

### Quoted visibility modifiers

`quote_declaration!(public fn exported() {})` fails to compile at the pinned
revision. The quote parser reads `public` as an identifier. The ordinary WESL
parser accepts the same declaration. The inline `private` form also fails.
Both modifiers work in the string form, such as
`quote_declaration!("public fn exported() {}")`.
Report the inconsistent visibility parsing between quote forms upstream.
The fix must preserve `private` as an identifier outside a visibility prefix,
as in `quote_declaration!(fn private() {})`.
The string parser also rejects this valid identifier at the pin.

The test transformation sets `Function.visibility` to `Visibility::Public`
for its generated collector. This uses the upstream syntax API.

### Package visibility inside named packages

At revision `0303eccfafd534cc76c91eddd4b4f5c4413a1733`,
[usage analysis](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/pass/usage_analysis.rs#L249-L252)
requires public visibility for an import whose canonical path names a package.
This also applies when the importing module belongs to that same package.
A public function in `library` therefore cannot call a helper with package
visibility through `package::helper::value`.
The failure also occurs through `wesl::compile` with `VirtualResolver`.
The [visibility specification](https://github.com/webgpu-tools/wesl-spec/blob/main/Visibility.md#referring-to-less-visible-declarations)
permits public functions to refer to less-visible declarations.

[test_named_package_local_imports_allow_package_visibility](../tests/test_sources.py)
keeps the default behavior and marks the checked case as a strict expected failure.
The test fails on an unexpected pass so an upstream fix requires removal of the
marker. The workaround disables visibility checks and also permits imports that
cross package boundaries.

## Local integration requirements

The binding queries custom result types in a fresh evaluation context.
Named layout constants therefore fail in the binding. Upstream supports them
when callers execute the module into the context before calling `ty_eval_ty`.
Transitive constants also work through this public API. Avoiding unrelated module
assertions would require partial evaluation; it is not an existing API guarantee.
This is a binding integration limit.

Cyclic types are invalid WGSL. The standard compiler rejects the tested cycles
with validation enabled. Compilation with `lower=true` and `validate=false` can
abort on them, as can direct low-level evaluation without validation.
[Issue #157](https://github.com/webgpu-tools/wesl-rs/issues/157) already tracks a
related crash. Keep the binding's cycle checks for `validate=False`.

The binding also rejects reversed, out-of-bounds, and invalid UTF-8 diagnostic
spans in assertion rendering. Keep this guard for caller-supplied metadata and
local normalization. The separate compiler error path needs the EOF correction
described above for invalid spans generated by the parser itself.
