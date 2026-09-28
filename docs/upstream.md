# Upstream integration limits

Initially reviewed on 2026-09-26 against the then-pinned `wesl`, `wgsl-parse`, `wgsl-types`,
and `wesl-quote` 0.4.4 crates, plus PyO3 0.29.2.
Upstream status uses [wesl-rs main at 0303ecc](https://github.com/webgpu-tools/wesl-rs/tree/0303eccfafd534cc76c91eddd4b4f5c4413a1733)
and [PyO3 main at 3260c48](https://github.com/PyO3/pyo3/tree/3260c4835f33d3c05d39715c2b729dfdb5e31e35).
Upstream checks inspect source and issue status.
The original runtime checks use the 0.4.4 versions. The Rust examples for those
checks retain their original API. The binding now pins the audited WESL commit.
Migration checks on 2026-09-28 confirm the additional failures below.

## Next actions

Prioritize the lost initializer and zero alignment.
The table distinguishes current binding behavior from the upstream failure.

| Item | Current binding behavior | Next action |
| --- | --- | --- |
| [Compiler adapter](#compiler-driver-integration) | A local driver supports transformations and works around three frontend defects | Request a transformation hook and fix visibility, disabled imports, and qualified references upstream |
| [Lost for initializer](#lowering-drops-side-effects-in-a-for-initializer) | Ordinary compilation with lowering changes behavior; shader tests have a partial workaround | Preserve the initializer and its scope upstream |
| [Zero alignment](#buffer-sizing-assumes-positive-member-alignment) | Local checks reject zero alignment in custom result layouts | Reject zero before layout arithmetic upstream |
| [Cyclic types](#type-evaluation-assumes-acyclic-declarations) | Local checks reject the documented alias and structure cycles | Add the low-level crash cases to issue #157 |
| [Diagnostic line boundaries](#diagnostic-rendering-uses-different-line-boundaries) | Compiler errors retain incorrect rendered locations | Normalize rendering and remap spans upstream |
| [PyO3 getter annotations](#pyo3-rejects-signature-overrides-on-getters) | The stub script supplies missing return types | Follow PR #5738 and adopt the fix when released |
| [Named layout constants](#standalone-type-evaluation-cannot-resolve-named-layout-constants) | Custom layouts with named attributes fail type evaluation | Request evaluation of a selected type and its dependencies |
| [Exact assertion values](#the-bundled-assertion-protocol-loses-integer-precision) | Local fields preserve exact operands | Add an upstream host regression test before changing the protocol |
| [Invalid diagnostic spans](#diagnostic-rendering-accepts-invalid-utf-8-spans) | Assertion rendering rejects invalid ranges | Consider a small upstream hardening patch |

Record the upstream issue or pull request and the fix revision in each section.
When updating a dependency, rerun the relevant reproducer against upstream without
the local workaround. Remove a workaround only after the pinned dependency includes
the fix and the associated binding tests pass.

The [wrapper parameter collision](#local-wrapper-parameters-can-collide) has a
local fix. The [dependency constraints](#dependency-constraints) describe the
visitor migration and compiler hooks.

The WESL Rust examples require neither Python nor a GPU.
Use `wesl = { version = ">=0.4.4,<0.5", default-features = false,
features = ["eval"] }` in `[dependencies]`.
Each example is a separate `src/main.rs`, except the PyO3 example.

## Lowering drops side effects in a for initializer

Source: [eval/lower.rs](https://docs.rs/crate/wesl/0.4.4/source/src/eval/lower.rs).
The same removal remains in the audited main source.

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
    let expression: Expression = "main()".parse().unwrap();
    let before = wesl::exec(
        &expression, &module, Default::default(), Default::default(),
    ).0.unwrap();
    wesl::lower(&mut module).unwrap();
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
[test_assertions_in_control_flow](../tests/test_testing.py) covers initializers
in test functions with both settings.

Submit a fix that preserves the initializer and its scope.
Cover a call initializer, a declaration with a side effect, and no initializer.
Remove the local initializer transformation after adopting that fix and verifying
assertion instrumentation with the control-flow tests.
Also verify ordinary compilation and overridden assertion modules without the
transformation. Both must preserve the initializer's side effects.

## Buffer sizing assumes positive member alignment

Source: [wgsl-types memory utilities](https://docs.rs/crate/wgsl-types/0.4.4/source/src/mem.rs).
The unchecked rounding remains in the audited main source.

```rust
use wesl::{
    eval::{Context, ty_eval_ty},
    syntax::{Ident, TranslationUnit, TypeExpression},
};

fn main() {
    let module: TranslationUnit =
        "struct Result { @align(0) value: u32 }".parse().unwrap();
    wesl::validate_wesl(&module).unwrap();
    let expression = TypeExpression::new(Ident::new("Result".into()));
    let result = ty_eval_ty(&expression, &mut Context::new(&module)).unwrap();
    let _ = result.size_of();
}
```

Observed: validation and type evaluation succeed, then rounding divides by zero.
`@align(0)` is invalid WGSL. The
[validator](https://docs.rs/crate/wesl/0.4.4/source/src/validate/mod.rs)
documents limited checks and does not validate layout attributes.
The failure is unchecked layout arithmetic on a type returned by the evaluator.

[compile_test](../src/testing.rs) calls `Type::size_of` for the result buffer.
The bundled result structure has valid alignment. A custom result member with
`@align(0)` previously raised PyO3's `PanicException` with validation enabled and
either lowering setting. The binding now inspects the upstream evaluated type
and raises `CompileError` before sizing or lowering. This check includes nested
structures and arrays. Upstream still owns layout calculation and buffer decoding.

Reject zero before rounding, including nested structures and arrays.
Verify rejection through type evaluation and result buffer sizing.
A general checked layout API needs a separate contract for overflow and other
invalid attributes.

## Type evaluation assumes acyclic declarations

Sources: [eval/ty.rs](https://docs.rs/crate/wesl/0.4.4/source/src/eval/ty.rs),
[eval/mod.rs](https://docs.rs/crate/wesl/0.4.4/source/src/eval/mod.rs),
and [validate/mod.rs](https://docs.rs/crate/wesl/0.4.4/source/src/validate/mod.rs).
The recursive resolution remains in the audited main source.

```rust
use wesl::{
    eval::{Context, ty_eval_ty},
    syntax::{Ident, TranslationUnit, TypeExpression},
};

fn main() {
    let module: TranslationUnit = "alias Value = Value;".parse().unwrap();
    let expression = TypeExpression::new(Ident::new("Value".into()));
    let _ = ty_eval_ty(&expression, &mut Context::new(&module));
}
```

Run this reproducer in a separate process with a timeout.
Observed: stack overflow aborts the process.
Replacing the source with `struct Value { child: Value }` also aborts.
Alias resolution recurses in `SyntaxUtil::resolve_alias`.
Structure evaluation recurses through member types.
Mutually recursive aliases and structures reach the same unguarded paths.

This is a low-level evaluation defect on invalid input.
It does not show that normal compilation with validation enabled accepts cycles.
The dependency check in [compile_test](../src/testing.rs) guards these cases before
`ty_eval_ty`, including when callers select `validate=False`.
[test_shader_assertion_type_cycles_without_validation](../tests/test_diagnostics.py)
covers direct and mutual aliases, an array alias, and a recursive structure.

[Issue #157](https://github.com/webgpu-tools/wesl-rs/issues/157)
already reports a related cyclic-type crash through a different declaration.
Add these cases to that discussion. An evaluator guard must cover both alias
resolution and structure evaluation.
Remove the local check only after upstream evaluation rejects these cycles
without requiring full validation.

## Diagnostic rendering accepts invalid UTF-8 spans

Source: [error.rs](https://docs.rs/crate/wesl/0.4.4/source/src/error.rs).
The end-only range check remains in the audited main source.

```rust
fn main() {
    let diagnostic = wesl::Diagnostic::from(wesl::ValidateError::Cycle(
        "value".into(), "value".into(),
    ))
    .with_source("é".into())
    .with_span((0..1).into());
    println!("{}", diagnostic.render_plain());
}
```

Observed: `annotate-snippets` 0.12.16 panics because byte 1 is inside `é`.
The renderer checks only the span's end against the source length.
[render_diagnostic](../src/lib.rs) checks the complete range for assertion
diagnostics. [test_failure_with_invalid_source_span](../tests/test_testing.py)
verifies the fallback.
This is a hardening opportunity for caller-supplied metadata.
The reproducer does not show that the parser generates invalid spans.

Extend the existing fallback for out-of-bounds spans to reversed ranges and
invalid UTF-8 boundaries. Retain the local range guard while local normalization
requires valid boundaries. Remove it after upstream handles both requirements.

## Diagnostic rendering uses different line boundaries

Source: [error.rs](https://docs.rs/crate/wesl/0.4.4/source/src/error.rs).
The audited main renderer still passes the source directly to `annotate-snippets`.

```rust
use wesl::syntax::TranslationUnit;

fn main() {
    let source = "fn main() {\rlet value = missing;\r}";
    let module: TranslationUnit = source.parse().unwrap();
    let diagnostic = wesl::validate_wesl(&module).unwrap_err();
    println!("{}", diagnostic.with_source(source.into()).render_plain());
}
```

Observed: the renderer places `missing` on line 1, column 25.
WGSL coordinates are line 2, column 13.
LF and CRLF controls render correctly.
CR, vertical tab, form feed, NEL, U+2028, and U+2029 reproduce the mismatch.
These are [WGSL line breaks](https://www.w3.org/TR/WGSL/#line-break).

The binding normalizes assertion sources in [render_diagnostic](../src/lib.rs).
[test_failure_with_unicode_line_breaks](../tests/test_testing.py) covers all eight
line-break sequences and multibyte text before the span.
Compiler errors use upstream rendering and retain this mismatch.

Normalize a rendering copy and remap its byte spans, or add suitable renderer
support.
Preserve declaration notes and the original source and byte spans exposed to
Python. Cover compiler errors with multibyte text before the span.
Remove the local normalization after upstream rendering passes the same cases.

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
Reviews accept the direction and subsequently request formatting and CI fixes.
Follow that PR. Once a release includes it, annotate the native getters and remove
these three corrections after verifying the generated stubs.

## Standalone type evaluation cannot resolve named layout constants

Sources: [eval/mod.rs](https://docs.rs/crate/wesl/0.4.4/source/src/eval/mod.rs)
and [eval/eval.rs](https://docs.rs/crate/wesl/0.4.4/source/src/eval/eval.rs).
The fresh context still starts in function scope on audited main.
The `Context::kind` field is private; `ScopeKind` itself is public.

```rust
use wesl::{
    eval::{Context, ty_eval_ty},
    syntax::{Ident, TranslationUnit, TypeExpression},
};

fn main() {
    let module: TranslationUnit = "
        const alignment = 64;
        struct Result { @align(alignment) value: u32 }
    ".parse().unwrap();
    let expression = TypeExpression::new(Ident::new("Result".into()));
    let result = ty_eval_ty(&expression, &mut Context::new(&module));
    assert!(result.is_ok(), "{result:?}");
}
```

Observed: `UnknownDecl("alignment")`.
Literal `@align(64)` works.
Executing the module first populates the context and makes this example succeed.
Thus ordinary module evaluation supports named constants.
The limitation is evaluating a selected type in a fresh context.

Whole-module execution also evaluates unrelated declarations and module assertions.
[compile_test](../src/testing.rs) evaluates the result type in a fresh context
before lowering. Named layout constants fail with both `lower=False` and
`lower=True`. The bundled result structure uses literals and works.

Request an API contract for evaluating a selected type and its dependencies.
It must handle cycles and avoid evaluating unrelated declarations.
An unrelated failing `const_assert` can test that boundary, even though it makes
the whole module invalid. This is a request for partial evaluation.
The API shape remains open; changing the default context scope is unverified.

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
Add a regression case to [TestWesl.test.ts](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/src/test/TestWesl.test.ts)
through its existing `runWesl` harness. Require both exact integers and the first
pair of operands after several failures.
The upstream host reproduction remains unverified.
Preserving operand types requires agreement on the shader and host representation.

The binding preserves `recordFailure` and appends `actual_bits` and
`expected_bits` in [compile_test](../src/testing.rs).
[test_failure_in_imported_helper](../tests/test_testing.py) verifies exact integers
and retention of the first failure.
Replace these fields only after adopting an upstream protocol that preserves
the supported operand types. Source locations and execution metadata still need
local instrumentation.
The [testing guide](testing.md#assertions) defines the result layout contract.

## Local wrapper parameters can collide

The wrapper in [compile_test](../src/testing.rs) previously used a fixed
`wesl_test_location` parameter and prepended the assertion's parameters.

Rename `condition` to `wesl_test_location` in an overridden bundled assertion module,
then call `wgsl_test::expect(false)` with `TestOptions(lower=False)`.
Before the fix, the generated wrapper has parameters named `wesl_test_location`
with both `bool` and `u32` types. GPU shader parsing rejects the duplicate name.
The bundled assertions do not use this parameter name.

The binding now chooses an unused parameter name and uses its identifier
throughout the wrapper. Regression tests cover colliding overrides with both
lowering settings.
This is a binding defect. [wesl-quote](https://docs.rs/crate/wesl-quote/0.4.4/source/README.md)
does not promise fresh names against the insertion scope.

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

The standard frontend keeps `CompilationPass` private. Request a public way to
wrap its module loading step. That would let the binding retain its transformations
without duplicating the frontend's option handling.
The transformation must run after the source mapper records the original source
and before conditional translation, identifier retargeting, and validation.
Expose the existing default driver and its constructor, or add this hook to the
standard frontend. Entry selection, pass ordering, and result assembly should
remain upstream responsibilities. Removing the adapter depends on this API and
the fixes below.

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

For disabled imports, use the same main source with `missing` in place of
`library`. Also set `imports: false`. Compilation tries to resolve `missing`.

For the qualified reference, the main source is:

```wesl
fn value() -> u32 { return package::helper::value(); }
```

Set `package::helper` to `fn value() -> u32 { return 7u; }`.
Compilation reports a cycle in `value`.

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
| Qualified references | `test_resource_loader_compiles_package_roots` in [test_sources.py](../tests/test_sources.py) and `test_cooperative_qualified_workgroup_size` in [test_testing.py](../tests/test_testing.py) |

Remove the full adapter only after adopting the transformation hook and all three
fixes. Verify option parity with [tests/upstream.rs](../tests/upstream.rs).
Retain coverage for scoped dependencies, shared package state, transformed result
modules, and original source locations when moving to the upstream frontend.

### Plain else traversal

The 0.4.4 [visitors](https://docs.rs/crate/wesl/0.4.4/source/src/visit.rs) omit
plain `else` bodies for both statements and expressions, including mutable visits.
[PR #307](https://github.com/webgpu-tools/wesl-rs/pull/307), merged on 2026-09-26,
fixes [issue #306](https://github.com/webgpu-tools/wesl-rs/issues/306).

The binding now uses `wesl::pass::Visit` from the fixed revision in
[compile_test](../src/testing.rs). The manual statement traversal is removed.
[test_assertions_in_control_flow](../tests/test_testing.py) verifies nested `else`
assertions with both lowering settings.

### Quoted visibility modifiers

`quote_declaration!(public fn exported() {})` fails to compile at the pinned
revision. The quote parser reads `public` as an identifier. The ordinary WESL
parser accepts the same declaration. Report the missing visibility tokens in
the quote parser upstream.

The test transformation sets `Function.visibility` to `Visibility::Public`
for its generated collector. This uses the upstream syntax API.

### SourceMapper resolver order

In 0.4.4, [SourceMapper](https://docs.rs/crate/wesl/0.4.4/source/src/sourcemap.rs)
forwards `resolve_source` but uses the default `resolve_module` implementation.
It reparses the source and bypasses transformations in an inner resolver.
[Issue #143](https://github.com/webgpu-tools/wesl-rs/issues/143) records this defect;
[PR #144](https://github.com/webgpu-tools/wesl-rs/pull/144) is closed without merging.

The 0.4.4 binding places transforming resolvers outside `SourceMapper` and uses
the same mapper for mangling. Audited main [removes `resolve_module` from `Resolver`](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/resolver.rs)
and removes `Preprocessor`. The binding now applies transformations through
`CompilerDriver::load_module`, after source recording and before conditional
translation. [test_result_instrumentation](../tests/test_testing.py) verifies
transformed result modules. [test_failure_in_imported_helper](../tests/test_testing.py)
verifies original source tracking.
