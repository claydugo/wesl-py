# Upstream integration limits

Reviewed on 2026-09-26 against the pinned `wesl`, `wgsl-parse`, `wgsl-types`,
and `wesl-quote` 0.4.4 crates, plus PyO3 0.29.2.
The binding uses WESL's evaluated result type for buffer sizing and decoding.
Upstream status uses [wesl-rs main at 0303ecc](https://github.com/webgpu-tools/wesl-rs/tree/0303eccfafd534cc76c91eddd4b4f5c4413a1733)
and [PyO3 main at 3260c48](https://github.com/PyO3/pyo3/tree/3260c4835f33d3c05d39715c2b729dfdb5e31e35).
Upstream checks inspect source.
Runtime results below apply to the pinned versions.

## Priority and submission order

P1 covers incorrect execution and process failures.
P2 covers diagnostics, constrained API use, and existing PR follow-up.
P3 covers proposals that need agreement on design.
Within each priority, prefer a small fix with a precise regression test.
Merge likelihood estimates acceptance of the stated scope, not review speed.
It is a judgment unless a linked review provides direct evidence.

A strong reproducer isolates the responsible package with a precise failure.
The WESL Rust examples require neither Python nor a GPU.
A partial reproducer still needs a host harness or an agreed API contract.
The Rust examples below use `wesl = { version = "=0.4.4",
default-features = false, features = ["eval"] }` in `[dependencies]`.
Each is a separate `src/main.rs`.

| Order | Priority | Item | Impact | Reproducer quality | Merge likelihood |
| --- | --- | --- | --- | --- | --- |
| 1 | P1 | [Lost for initializer](#lowering-drops-side-effects-in-a-for-initializer) | Valid code changes behavior | Strong: result changes from 1 to 0 | High: narrow semantic fix |
| 2 | P1 | [Zero alignment](#buffer-sizing-assumes-positive-member-alignment) | Invalid custom layouts can panic during sizing | Strong: validation, evaluation, then panic | High for zero rejection; medium for a new layout API |
| 3 | P1 | [Cyclic types](#type-evaluation-assumes-acyclic-declarations) | Low-level evaluation aborts the process | Strong: isolated alias and structure cases | Medium: known issue; guard design remains open |
| 4 | P2 | [Invalid diagnostic spans](#diagnostic-rendering-accepts-invalid-utf-8-spans) | Constructed diagnostics panic | Strong: one invalid UTF-8 boundary | Medium to high: small guard; define fallback behavior |
| 5 | P2 | [Diagnostic line boundaries](#diagnostic-rendering-uses-different-line-boundaries) | Incorrect locations for valid WGSL separators | Strong: CR input and LF control | Medium: requires span remapping or renderer support |
| 6 | P2 | [PyO3 getter annotations](#pyo3-getters-lose-precise-type-information) | Generated stubs need correction | Strong: verified compile error; existing PR tests | High for existing PR, subject to review and CI |
| 7 | P2 | [Named layout constants](#standalone-type-evaluation-cannot-resolve-named-layout-constants) | Fresh contexts cannot evaluate some valid types | Strong failure; proposed API needs design | Medium: limited evaluation needs a clear contract |
| 8 | P2 | [Exact assertion values](#the-bundled-assertion-protocol-lacks-exact-values-and-locations) | Failure reports lose integer precision | Partial: exact operands; host decoder test still needed | Medium: shader and host protocol must agree |
| 9 | P3 | [Assertion metadata](#the-bundled-assertion-protocol-lacks-exact-values-and-locations) | Less detail about assertion execution | Partial: feature requirements | Low to medium: broader instrumentation design |

The following failures belong to this binding.
An upstream API could help, but these reproducers do not establish upstream bugs.
They run with the bundled modules overridden and `TestOptions(lower=False)`.
All three cases are verified locally, including both `recordFailure` mutations.
WESL layout decoding resolves the result declaration mismatch.
Preserving upstream `recordFailure` resolves the statement-rewriting failures.

| Priority | Local item | Impact | Reproducer quality | Merge likelihood |
| --- | --- | --- | --- | --- |
| Resolved | [Result declarations disagree](#result-layouts-have-two-declarations) | A passing test reported failure | Strong locally: swap two fields | Existing WESL APIs resolve this |
| Resolved | [recordFailure rewriting](#local-rewriting-assumes-the-shape-of-recordfailure) | Wrong failure count or GPU validation error | Strong locally: change only statement nesting | Preserving upstream behavior resolves this |
| P2 | [Wrapper parameter collision](#quoted-identifiers-do-not-avoid-collisions) | A valid assertion override fails compilation | Strong locally: rename one parameter | Low as a quoting bug; freshness is a feature request |

The [else visitor](#statement-and-expression-visitors-skip-plain-else-bodies)
fix is already merged.
The [SourceMapper and Preprocessor](#sourcemapper-does-not-forward-module-transformations)
requests target APIs that main removes.
Keep both as records of pinned-version constraints.

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
The original `for (wgsl_test::expect(false); false; ) {}` also loses its assertion.
The standalone counter removes the test-library dependency from the report.
Shader instrumentation moves the initializer into an enclosing block before
upstream lowering.

Submit a fix that preserves the initializer and its scope.
Cover a call initializer, a declaration with a side effect, and no initializer.
A new lowering API is unnecessary for this defect.

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
`@align(0)` is invalid WGSL. This is failure to reject invalid input.
An `Option` return does not by itself promise a panic-free API.
The concrete defect is that accepted input reaches unchecked arithmetic.

The binding calls `Type::size_of` for the result buffer.
The bundled result structure has valid alignment.
Invalid custom layouts such as `@align(0)` are unsupported and can raise
PyO3's `PanicException` during test compilation.
The binding does not add a layout validator around the upstream implementation.
Reject zero before rounding, including nested structures and arrays.
Treat a general checked layout API as a separate proposal.
It needs decisions about overflow, invalid sizes, and other invalid alignments.

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
The binding checks type dependencies before `ty_eval_ty`, including when callers
select `validate=False`.
The upstream cycle checker is private.
Calling `validate_wesl` instead enables other checks that the caller disables.

[Issue #157](https://github.com/webgpu-tools/wesl-rs/issues/157)
already reports a related cyclic-type crash through a different declaration.
Add this evidence to that discussion before creating another report.
A guard in evaluation addresses the crash directly.
Exposing the cycle checker is a different API proposal.
Callers must still invoke it correctly.

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
The binding checks the complete UTF-8 range for externally constructed diagnostics.
This reproducer does not show that the parser generates invalid spans.

Handle invalid ranges before rendering, with a defined fallback diagnostic.
Test reversed ranges and invalid boundaries at both ends.
Keep this separate from line normalization: its trigger and fix are independent.

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

The binding already normalizes source text when it renders assertion failures.
Compiler errors use upstream rendering and retain this mismatch.
The experimental normalization helper and compiler workaround are removed.
An upstream fix must retain declaration notes and handle multibyte identifiers
before the span.
The source and byte spans exposed to Python must stay unchanged.

Normalize a rendering copy and remap its byte spans, or add suitable renderer
support.
Replacing multibyte separators without remapping spans is insufficient.
The added mapping work makes this less likely to merge quickly than the loop fix.

## PyO3 getters lose precise type information

Sources: [signature handling](https://docs.rs/crate/pyo3-macros-backend/0.29.2/source/src/method.rs)
and [type annotations](https://pyo3.rs/v0.29.2/function/signature.html#type-annotations-in-the-signature).
The rejection remains in the audited PyO3 main source.

This separate crate uses `pyo3 = { version = "=0.29.2",
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
This is not a claim that all getters lose their types.
The stub script restores tuple types for `CompileResult` and `TestResult`.

[PR #5738](https://github.com/PyO3/pyo3/pull/5738) already implements getter and
setter signatures with tests.
Reviews accept the direction and subsequently request formatting and CI fixes.
Follow up on that PR before proposing a replacement.
Getter annotations let these types live beside the native methods.
Typed return wrappers are another option, with additional binding code.

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
That changes shader-test behavior with lowering or validation disabled.
The binding evaluates the result type in a fresh context before lowering.
The bundled result structure works in this context.
Named constants in custom layout attributes remain unsupported, including when
lowering is enabled.
The binding does not execute the module to work around this limit.

Propose a public context for evaluation at module scope, with a defined dependency
boundary and cycle handling.
A regression test must resolve literal and named attributes while leaving an
unrelated failing `const_assert` unevaluated.
Do not treat changing the default context scope as an established fix.

## The bundled assertion protocol lacks exact values and locations

Source: [wgsl-test assertions](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders/lib.wesl).
This revision is also the audited wesl-js main.

`expectEq` compares the `u32` operands before it converts them to `f32`.
Its pass/fail decision remains exact.
`recordFailure` stores the converted values in `vec4f` fields, so failure reports
lose precision.
For example, `expectEq(4294967295u, 4294967294u)` fails but records the same `f32`
value for both operands.

Exact operand storage is a concrete reporting improvement.
A minimal upstream test must inspect the decoded record, preserve those two
integers, and verify that several failures retain the first pair of values.
The operand example and conversion path are established; a standalone test of
the upstream host decoder is still needed.
Changing the fields also requires updating that decoder.

The protocol has a failure count, but no total assertion count, assertion location,
or explicit completion flag.
These are separate feature requests.
Adding fields alone does not establish where or how to populate them.
Keep metadata design separate from precision preservation.

## Local rewriting assumes the shape of recordFailure

The previous implementation changes the result fields to `vec4u` and removes
top-level `if` statements from `recordFailure` before wrappers store exact bits.
This assumes the shape of the bundled function.

Two small changes to an overridden `wgsl_test` module expose the assumption:

- Put the existing `if (testResult.failCount == 0u) { ... }` inside a compound block.
  The float assignments survive. `expectEq(1u, 2u)` produces a GPU validation error
  when it assigns `vec4f` to `vec4u`.
- Put `testResult.failCount += 1u` inside `if (true) { ... }`.
  The increment disappears. One failing assertion reports zero failures and one
  executed check.

Both inputs preserve the upstream function's behavior before local rewriting.
These are binding transformation defects, not defects in the upstream assertions.
An upstream protocol with typed values and execution metadata could remove the
need to rewrite `recordFailure`, but it is not a prerequisite for local correctness.

The binding now preserves `recordFailure` and its original fields.
Wrappers store exact values in appended `actual_bits` and `expected_bits` fields.
The regression tests cover both mutations with lowering enabled and disabled.

## Result layouts have two declarations

The previous WGSL result structure and Rust `TestResult` describe the same protocol.
`encase` derives layout rules from that Rust declaration.
It does not read the WGSL declaration.

In an overridden `wgsl_test::TestResult` module, swap the declarations of `passed`
and `failCount`, then run `@test fn selected() { wgsl_test::expect(true); }`.
Observed: the passing assertion produces `ShaderAssertionError` with zero failures
and one executed check.
Adding layout attributes can also make the declarations disagree.
This is a binding integration limit, not a defect in `encase`.
The bundled structure has the expected layout.

The binding now uses `ty_eval_ty`, `Type::size_of`, and `Instance::from_buffer`.
The compiled WGSL type determines the layout.
`StructInstance::member` finds decoded values by name.
Rust stores those values without a buffer layout declaration.
The encase dependency is removed.

The supported protocol retains the upstream field names and types.
Instrumentation appends exact operand bits and execution metadata.
Field order and valid literal layout attributes can change without a matching
Rust declaration.
Regression tests cover reordered fields, explicit alignment and size, conditional
declarations, and lowering enabled and disabled.
Arbitrary custom layouts are not a supported contract.
The named-constant and invalid-alignment limits above still apply.

A shared schema with a generated host representation is a larger design proposal.
It does not, by itself, support arbitrary user overrides.
Existing WESL APIs remove the duplicate layout without that proposal.

## Quoted identifiers do not avoid collisions

Source: [wesl-quote](https://docs.rs/crate/wesl-quote/0.4.4/source/README.md).

Rename `condition` to `wesl_test_location` in an overridden bundled assertion module,
then call `wgsl_test::expect(false)`.
Observed: the generated wrapper has parameters named `wesl_test_location` with
both `bool` and `u32` types. GPU shader parsing rejects the duplicate name.
The bundled assertions do not use this parameter name.
The binding still uses the fixed wrapper parameter name.

The macros construct syntax nodes and support interpolation.
They do not promise fresh names against the scope into which nodes are inserted.
The binding copies the assertion parameters after it constructs the wrapper.
This establishes a local name collision, not a broken macro contract.
`retarget_idents` resolves existing names; it does not allocate unused names.

A public API for allocating identifiers against a function scope could replace a
local name search.
That is a convenience proposal with limited evidence of general demand.
The collision itself has a small local solution and does not require macro hygiene.

## Statement and expression visitors skip plain else bodies

Source: [visit.rs](https://docs.rs/crate/wesl/0.4.4/source/src/visit.rs).
Status: [issue #306](https://github.com/webgpu-tools/wesl-rs/issues/306)
is closed by
[PR #307](https://github.com/webgpu-tools/wesl-rs/pull/307), merged on 2026-09-26.

In 0.4.4, `Visit<StatementNode>` and `Visit<ExpressionNode>` omit `else_clause`
from their `Statement::If` arms.
The generated mutable visitors have the same omission.

```wgsl
if false { return 1; }
else if false { return 2; }
else { return 3; }
```

The statement visitor returns two return statements instead of three.
The expression visitor returns `false, 1, false, 2` instead of
`false, 1, false, 2, 3`.
The original count of two literals overlooks the two boolean literals.
The merged regression test covers immutable and mutable visitors.
Nested plain `else` bodies also need traversal when using recursive visitors.

This is a strong reproducer and a fix that maintainers already accept.
Track dependency adoption rather than submit another patch.
The binding retains explicit statement traversal while pinned to 0.4.4.
`Visit` is private in that release; the linked external reproducer uses the newer
`wesl::pass::Visit` API.

## SourceMapper does not forward module transformations

Source: [sourcemap.rs](https://docs.rs/crate/wesl/0.4.4/source/src/sourcemap.rs).

In 0.4.4, `SourceMapper` forwards `resolve_source`, but not `resolve_module`.
The default `Resolver::resolve_module` reparses the source and bypasses underlying
module transformations.

A small reproducer wraps a `VirtualResolver` containing an empty module in a
`Preprocessor` that appends a compute entry point.
Direct `resolve_module` returns the generated entry point.
Wrapping that preprocessor in `SourceMapper` returns an empty module.
Both outcomes are verified on 0.4.4.

The binding places its transforming resolvers outside `SourceMapper` and passes
the same mapper as the compiler's mangler.
This preserves source tracking and AST transformations.
Forwarding `resolve_module` alone would bypass source recording.
Resolving the source again introduces another resolver call and requires a contract
for source consistency.

[Issue #143](https://github.com/webgpu-tools/wesl-rs/issues/143)
already reports this exact defect.
[PR #144](https://github.com/webgpu-tools/wesl-rs/pull/144) proposes resolving twice
and is closed without merging.
The discussion explicitly questions the added complexity.
Audited main [removes `resolve_module` from `Resolver`](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/resolver.rs).
This is a pinned-version constraint and a migration concern, not a current patch
candidate for that trait.

The old `Preprocessor` callback receives a `TranslationUnit` without its path.
Test transformations must distinguish the root module from `wgsl_test::TestResult`.
Adding `ModulePath` to that callback is a separate convenience request.
Main also removes `Preprocessor`, so assess the replacement compiler hooks during
migration before proposing that API change.

## APIs used by the binding

Shader tests use `SourceMapper` to record sources and declaration names.
This replaces manual source reloading and declaration-map reconstruction.
They use `ty_eval_ty` to resolve assertion types and the result structure.
`Type::size_of` computes the result buffer size.
`Instance::from_buffer` decodes bytes using that type.
`StructInstance::member` supplies decoded fields to the Python binding.
`wesl-quote` constructs syntax nodes for test instrumentation.

The integration preserves upstream assertion behavior and extends its result fields.
Diagnostic rendering remains unchanged.
The findings identify upstream patch candidates and local integration risks.
They do not justify adding another implementation to this binding.
