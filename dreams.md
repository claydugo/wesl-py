# WESL dreams for this project

Reviewed on 2026-10-02 against [wesl-spec at `7bc9cdb`][spec] and
[wesl-rs at `9c715d9`][compiler]. The current `8bb029a` dependency pin leaves the
linked wesl-rs files unchanged. Three subagents review all 16
Markdown pages and relevant design discussions. The project baseline is
`3a08f105f23f122a59e82d1a83746318487a4a9e`.

The strongest opportunities are generic numerical kernels, configurable
algorithm libraries, static code generation, and debugging original shader
sources. Each opportunity below identifies its source in the specification
repository. Most appear in proposals or future sections. Their maturity varies.
The project applications and effort estimates are assessments.

Existing defects and conformance work belong in
[the upstream assessment](upstream-assessment.md). They do not define this
roadmap.

## Most valuable capabilities

| Priority | Dream | What it enables here | Source maturity |
| --- | --- | --- | --- |
| 1 | Declare function and algorithm parameters | Express operation contracts in shader code and automate specialization of reusable libraries | Future direction and concrete use cases |
| 2 | Declare type parameters on numerical kernels | Replace manual type-provider modules and namespace registration with explicit generic arguments | Competing generics designs |
| 3 | Instantiate configurable modules through import arguments | Let the compiler manage configurations and their identity | Written module-parameter proposal |
| 4 | Generate static shader code with translation-time loops | Express stencils and reduction schedules once, then emit specialized statements | Extension sketch |
| 5 | Map GPU diagnostics back to original WESL | Locate errors in imported helpers after linking and transformation | Explicit tooling ambition |
| 6 | Let shader calculations control specialization | Derive layouts, constants, and algorithm choices in shader code | Existing evaluator foundation; proposed language integration |
| 7 | Reflect shader parameters into Python | Inspect configuration and drive experiments without a parallel schema | Future direction; depends on module parameters |

### Pass functions and algorithm implementations into libraries

A convolution library should accept a sampler. A compaction library should
accept a predicate. A reduction library should accept an operation and its
identity value. The library owns scheduling, memory access, and synchronization;
applications supply the behavior that varies.

Ordinary imports already support this architecture. The host can supply an
operation module through `modules`, including a replacement for the existing
compaction predicate. A focused probe compiles both scan and scatter with a
custom predicate. Formal function parameters would declare the contract in
shader code and let the compiler manage specialization. Reusable algorithm
libraries do not depend on that extension.

This comes directly from [pluggable functions, issue #133][functions], which
includes configurable Gaussian sampling, and
[binary-operation monoids, issue #137][monoids], which discusses reductions,
matching element types, subgroup variants, and host selection. The
[module-parameter proposal][parameters] also lists function parameters and
named implementations as future extensions.

The local uses are immediate:

- [Compaction](examples/compaction/shaders/scan.wesl) imports one concrete
  [predicate](examples/compaction/predicate.wesl). An application could provide
  arbitrary classification logic while retaining the scan and scatter kernels.
- [Gaussian filtering](examples/imaging/gaussian.wesl) imports fixed sampling
  helpers. Callers could choose clamped, periodic, mirrored, or specialized
  sampling without copying the filter algorithm.
- [Workgroup reduction](examples/imaging/reduction.wesl) fixes addition.
  A typed operation bundle could select sum, maximum, histogram merging, or
  application-specific statistics.

Start with an explicit function argument and a checked signature. Resolve the
selected function during compilation and emit ordinary WGSL calls. This does
not require runtime function pointers. Named implementations can later group
related operations and their element type.

Effort is large for function specialization and larger for general interfaces.
A general interface mechanism needs rules for matching implementations and
checking their types. A reduction-specific prototype can establish useful
requirements before that design expands.

### Parameterize numerical kernels by type

Write a reduction once for scalar or vector elements. Give convolution separate
parameters for storage and accumulation types. Reuse fixed-array helpers across
several sizes. This would turn the current compute examples into reusable
numerical building blocks.

Imported type aliases already provide a form of type configuration. A second
probe registers one shared algorithm source under two package namespaces, each
with its own `operations` dependency. One provider defines `Element = u32` and
addition; the other defines `Element = vec4f` and maximum. Both versions compile
into one linked shader. The missing capability is an explicit generic parameter
model with compiler-managed instantiation and constraints. The host currently
provides the namespaces and dependency mappings.

Type parameters appear in the [module proposal's future section][parameter-future].
[Generics issue #112][generics] tracks several competing designs.
[Const generics issue #180][const-generics] discusses parameters that affect
fixed array sizes. These sources establish the ambition, not a settled syntax.

The [reduction helper](examples/imaging/reduction.wesl) currently fixes
`vec4<f32>`. The
[activation helper](examples/convolution/shaders/activation.wesl) has separate
narrow and wide arithmetic paths. The
[convolution kernel](examples/convolution/shaders/convolution.wesl) similarly
contains separate product paths. These provide concrete cases for type
specialization. Numerical behavior still requires explicit testing across
precision choices.

The Rust checkout contains an experimental `@type` variant generator, but its
crate root does not include that experimental module. It is not an operational
compiler feature that Python can expose by enabling a flag. See the
[experimental implementation][generic-code] and [crate root][compiler-root].

A constrained first design can require explicit arguments and instantiate only
used variants. General inference, structural constraints, and interfaces make
this one of the largest items. Type parameters and function parameters should
share a coherent specialization model.

### Instantiate configurable modules

Import one library several times with different capacities, tile sizes, or
algorithm settings. Each import selects a configuration that can coexist with
the others in the same linked shader.

This is the central capability of [proposal #222][parameters]. It specifies
shader-declared constant parameters, defaults, import arguments, and root-module
control over host configuration. The page lists no implementations.

For this project, a reduction helper could have several workgroup capacities.
Horizontal and vertical Gaussian helpers could coexist without sharing one
compilation-wide `horizontal` flag. Convolution could declare its tile sizes
beside the arrays and algorithms that depend on them.

Python already supplies scalar constant modules and boolean feature flags.
The host can also mount the same library source under different namespaces
with different scoped dependencies. That supports multiple configurations in
one compilation. A single module path still selects one definition. The
proposal expresses specialization through import arguments and makes the
compiler responsible for instance identity, rather than requiring the host to
construct it through module paths.

This is substantial compiler work. Instance identity must include evaluated
arguments. Equivalent arguments must identify one instance. Different arguments
can require separate variable state while preserving compatible type identity.
The [design notes][parameter-design] explain these distinctions. The current
[local driver](src/compiler.rs) identifies parsed modules by path alone.

The most useful first scope is constant parameters with defaults and explicit
specialization. Keep type and function parameters as later extensions of that
model. Resource-bearing instances also need deliberate binding assignments;
instantiation does not allocate unique binding numbers automatically.

### Generate static shader code with translation-time loops

Express a stencil or reduction schedule once, then expand it into specialized
statements before the GPU compiler receives WGSL.

The [conditional translation extensions][conditional-extensions] explicitly
sketch translation-time loops with names such as `@for` and `@repeat`. They do
not specify a final syntax or complete semantics.

The [direct convolution kernel](examples/convolution/shaders/convolution.wesl)
manually writes nine `accumulate` calls for a 3 by 3 stencil. A static loop could
emit those calls with literal coordinates. Other candidates include the fixed
tile loop in convolution and the halving schedules in
[reduction](examples/imaging/reduction.wesl) and
[RMSNorm](examples/rmsnorm/shaders/normalize.wesl).

The current Rust lowering pass visits loops without expanding them. Accepting
an unknown attribute such as `@repeat` does not implement its behavior; probes
show such attributes remain in emitted WGSL.

This is the most approachable substantial language experiment in this report.
A first patch can expand bounded statement loops whose iteration sequence is
known at translation time. It needs correct local scopes, identifier identity,
iteration substitution, source provenance, and a bound on expansion. Declaration
generation and complex loop control can wait for a broader design.

The benefit is explicit control over emitted code and less manual expansion.
A speedup is not guaranteed. Code size and compilation cost need measurement.

### Map GPU diagnostics back to original WESL

A type or uniformity error in an imported filter should identify the original
file and expression. Linking, mangling, conditional removal, and test
instrumentation should not force the user to debug the combined WGSL string.

The [source-map section in Imports][source-maps] explicitly describes mapping
Naga and Tint errors back to WESL. It also describes an eventual chain through
SPIR-V that lets RenderDoc display original WESL sources.

The existing [Rust source map][sourcemap-code] records declaration names,
modules, and source text. It does not index generated WGSL offsets. The Python
[result conversion](src/lib.rs) retains sources and emitted WGSL but exposes no
location translation. Assertion-site reporting already uses original spans;
it does not solve arbitrary GPU compiler diagnostics.

A useful first patch adds tracked WGSL emission and maps declaration ranges to
original declarations. A following patch maps statements and expressions.
Generated nodes need explicit provenance. A backend-neutral lookup can then
serve a Python adapter for GPU diagnostics.

The first increment has medium scope; precise mapping across transformations
has large scope. RenderDoc integration extends beyond wesl-rs and needs backend
cooperation. It is the longer-term dream, not the acceptance criterion for the
first patch.

### Let shader calculations control specialization

Keep derived configuration beside the shader that uses it. A tile width could
size workgroup arrays and select an algorithm. A fixed filter could calculate
its coefficient array during translation. The host would supply fundamental
inputs without also reproducing each derived decision.

The [conditional extension sketch][conditional-extensions] shows a shader
function evaluated by `@if`. The [module proposal][parameters] specifies
constant-valued conditions, including numeric comparisons. Together they point
toward shader-owned compile-time computation and specialization.

For example, the
[multiscale host code](examples/multiscale/compute.py) calculates Gaussian
weights and uploads them. Fixed configurations could instead emit computed
coefficients as shader constants. Runtime-adjustable filters still benefit
from the existing buffer path. Shader arithmetic may differ from the current
NumPy calculation, so equivalence needs numerical verification.

wesl-rs already has an evaluator, constant-function analysis, and
[constant folding][lowering-code]. The missing integration is using that
machinery to govern translation and exposing an appropriate path in wesl-py.
The binding currently rejects `lower=True`. Adding an evaluator from scratch
would duplicate existing work.

Ordinary helper evaluation is a smaller milestone than conditions that depend
on imports or conditional declarations. The latter require evaluation and
module resolution to cooperate. A comparison operator alone does not implement
that model. Treat numeric conditions as part of the module-parameter design.

### Reflect shader parameters into Python

Expose a shader family's configurable parameters, types, and defaults. Python
could inspect the supported configuration and run parameter sweeps without
maintaining a second schema.

Parameter reflection appears in the [module proposal's future section][parameter-future].
Using it for tuning convolution tiles, reduction sizes, or filter variants is
an application proposed by this report. Reporting effective parameter values
would be a useful API extension. Neither effective-value reporting nor automatic
tuning is specified by that future section.

The current `CompileResult` exposes source, module, and entry-point information.
It has no parameter model. Reflection should consume the semantic parameter
representation created for module specialization. Its first API must distinguish
known defaults from values that need specialization to evaluate.

This can be a medium follow-up once module parameters exist. It is not an
independent small patch today. General GPU resource reflection is a separate
capability and is not implied by this proposal.

## Ease of useful upstream increments

This order compares initial useful implementations. It assumes agreement on
experimental semantics. It does not imply that an entire dream fits one patch.

| Order | Upstream increment | Estimated scope | Boundary |
| --- | --- | --- | --- |
| 1 | Expand bounded statement loops | Medium | A local AST transform with evaluated bounds; retain scope and provenance |
| 2 | Record generated declaration locations | Medium | First source-map milestone; statement and expression precision follows |
| 3 | Integrate constant evaluation with translation decisions | Medium to large | Existing evaluator helps; imported and conditional constants complicate ordering |
| 4 | Specialize modules with constant parameters | Large | Parser, instance identity, lazy evaluation, state, and type sharing |
| 5 | Specialize libraries with explicit function arguments | Large | Signature checking, cross-module function resolution, and specialization |
| 6 | Add usable type parameters and typed algorithm contracts | Very large | Generic representation, specialization, constraints, and compatible interfaces |

Items 4 and 5 are close. Their order depends on whether upstream chooses module
parameters as the shared specialization mechanism. Parameter reflection becomes
relatively small only after that semantic model exists.

For a first contribution, investigate bounded static loops against the manually
expanded convolution stencil. For a tooling contribution, start with tracked
WGSL emission. For the largest improvement in library design, pursue function
and type specialization using reduction and compaction as concrete cases.

## Secondary dreams

- **Conditional expressions:** the conditional extension sketch suggests
  choosing expressions during translation. An inactive expression could refer
  to an unavailable helper. Existing conditional declarations cover many uses,
  so this ranks below static loops. Grammar and AST work are still required.
- **Stable module facades:** [VisibilityDesign][visibility-design] sketches
  whole-module re-exports and canonical import paths. A library could expose
  `imaging::filters` while reorganizing its internal modules. Preferred-path
  metadata is a smaller first step than making internal paths inaccessible.
- **Opaque shader types:** the same page sketches member visibility. Libraries
  could control construction and mutation of accumulators or packed state.
  This needs type-aware access checks and a language design for the boundary.
- **Readable generated names:** [NameMangling][mangling] describes renaming only
  collisions. It could improve inspection of dumped WGSL. It is a smaller
  convenience feature than source debugging.

## Coverage of the specification repository

All 16 Markdown pages receive review. Linked issues provide additional design
context; their full history is outside this review. Routine package loading,
existing import behavior, and conformance defects remain outside the dreams.

| Page | Contribution to this report |
| --- | --- |
| [README.md][readme] | Establishes reusable shader libraries and generics as goals. |
| [Imports.md][imports] | Supplies the source-debugging ambition; also mentions namespaces and scoped imports. |
| [ImportsDesign.md][import-design] | Explains curated preludes and wildcard tradeoffs; useful library ergonomics, below the main dreams. |
| [ConditionalTranslation.md][conditional] | Supplies static loops, compile-time functions, and expression-condition sketches. |
| [ConditionalTranslationDesign.md][conditional-design] | Supports structured transformations and tools that understand shader syntax. |
| [Visibility.md][visibility] | Defines existing interface behavior; its implementation gaps belong in the conformance backlog. |
| [VisibilityDesign.md][visibility-design] | Supplies module facades, canonical paths, and opaque-type possibilities. |
| [NameMangling.md][mangling] | Supplies readable generated names and notes future specialization needs. |
| [Packaging.md][packaging] | Establishes the library ecosystem and shared package identity; no separate headline dream. |
| [WeslToml.md][manifest] | Defines project metadata; missing integration belongs in ordinary project work. |
| [Versioning.md][versioning] | Contains unsettled edition questions; does not define a compelling capability for these kernels. |
| [Designing.md][designing] | Favors practical extensions demonstrated by real projects. |
| [GLOSSARY.md][glossary] | Supplies terminology; no independent feature. |
| [222-ModuleParameters.md][parameters] | Supplies module specialization and future type, function, implementation, and reflection extensions. |
| [222-ModuleParametersDesign.md][parameter-design] | Explains instance sharing and why pipeline overrides do not replace module parameters. |
| [assets/logo/LICENSE.md][logo-license] | Attribution terms; no language or tooling feature. |

Source inspection distinguishes existing infrastructure from new capabilities.
Focused compilation probes verify the current boundaries for numeric conditions,
module syntax, constant-function output, and unexpanded custom loop attributes.
No proposed extension is implemented or benchmarked by this report.

[spec]: https://github.com/webgpu-tools/wesl-spec/tree/7bc9cdb666092d6dd16383090cb6170d494e06b6
[compiler]: https://github.com/webgpu-tools/wesl-rs/tree/9c715d94828680b45b866b875754c49658cc27bd
[functions]: https://github.com/webgpu-tools/wesl-spec/issues/133
[monoids]: https://github.com/webgpu-tools/wesl-spec/issues/137
[generics]: https://github.com/webgpu-tools/wesl-spec/issues/112
[const-generics]: https://github.com/webgpu-tools/wesl-spec/issues/180
[generic-code]: https://github.com/webgpu-tools/wesl-rs/blob/9c715d94828680b45b866b875754c49658cc27bd/crates/wesl/src/experimental/generics/mod.rs
[compiler-root]: https://github.com/webgpu-tools/wesl-rs/blob/9c715d94828680b45b866b875754c49658cc27bd/crates/wesl/src/lib.rs
[sourcemap-code]: https://github.com/webgpu-tools/wesl-rs/blob/9c715d94828680b45b866b875754c49658cc27bd/crates/wesl/src/sourcemap.rs
[lowering-code]: https://github.com/webgpu-tools/wesl-rs/blob/9c715d94828680b45b866b875754c49658cc27bd/crates/wesl/src/pass/lower.rs
[readme]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/README.md
[imports]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/Imports.md
[source-maps]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/Imports.md#source-maps
[import-design]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/ImportsDesign.md
[conditional]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/ConditionalTranslation.md
[conditional-extensions]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/ConditionalTranslation.md#possible-extensions
[conditional-design]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/ConditionalTranslationDesign.md
[visibility]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/Visibility.md
[visibility-design]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/VisibilityDesign.md
[mangling]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/NameMangling.md
[packaging]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/Packaging.md
[manifest]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/WeslToml.md
[versioning]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/Versioning.md
[designing]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/Designing.md
[glossary]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/GLOSSARY.md
[parameters]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/proposals/222-ModuleParameters.md
[parameter-future]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/proposals/222-ModuleParameters.md#future
[parameter-design]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/proposals/222-ModuleParametersDesign.md
[logo-license]: https://github.com/webgpu-tools/wesl-spec/blob/7bc9cdb666092d6dd16383090cb6170d494e06b6/assets/logo/LICENSE.md
