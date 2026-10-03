# Upstream issue ranking

Checked 2026-10-02 UTC. The original audit uses [wesl-rs
`0303ecc`](https://github.com/webgpu-tools/wesl-rs/tree/0303eccfafd534cc76c91eddd4b4f5c4413a1733),
[wesl-js
`37db232`](https://github.com/webgpu-tools/wesl-js/tree/37db2325b40cdb8aa504582cbc01cb4d41109a36),
and PyO3 0.29.2. The original audit records wesl-rs main at
[`4783a43`](https://github.com/webgpu-tools/wesl-rs/commit/4783a436efda2c8caec1bc20ec940800c5f5dd6d),
one maintenance commit after the pin. The audited wesl-js main equals the pin.
I inspected current source and issue and PR lists. The lexer and conditional
patches pass focused regressions on that revision. The seven selected cases now
have refreshed evidence in their assessments.
Other findings retain the original audit results. Merge likelihood is an
inference from scope, contract, and
existing maintainer work. It is not a promise.

## Review packages

These seven cases are local drafts. No GitHub submission is authorized.
Each report contains standalone reproduction commands.
Each assessment records the upstream base, validation, and remaining limits.
Review the report and patch before deciding whether to submit either.
Diff counts include production code and regression tests.
All six patches use existing files. Each of the four trimmed regressions fails
before its fix and passes afterward in an isolated Rust source copy.
The five Rust patches apply to our current `9c715d9` dependency pin.
The NaN case verifies published wgsl-test on a GPU.
Its added test in the upstream source tree has not run.

| Order | Case | Report | Patch | Diff (+/−) | Validation and limits |
| --- | --- | --- | --- | --- | --- |
| 1 | Qualified references report false cycles | [Issue](/home/clay/issue_tracking/20260929134130_wesl-rs_qualified_reference/issue.md) | [Fix](/home/clay/issue_tracking/20260929134130_wesl-rs_qualified_reference/fix.patch) | +20 / −9 | [Assessment](/home/clay/issue_tracking/20260929134130_wesl-rs_qualified_reference/assessment.md) |
| 2 | Disabled visibility is ignored | [Issue](/home/clay/issue_tracking/20260929134128_wesl-rs_disabled_visibility/issue.md) | [Fix](/home/clay/issue_tracking/20260929134128_wesl-rs_disabled_visibility/fix.patch) | +23 / −1 | [Assessment](/home/clay/issue_tracking/20260929134128_wesl-rs_disabled_visibility/assessment.md) |
| 3 | Same-package visibility fails | [Issue](/home/clay/issue_tracking/20260929020241_wesl-rs_package_visibility/issue.md) | [Fix](/home/clay/issue_tracking/20260929020241_wesl-rs_package_visibility/fix.patch) | +21 / −0 | [Assessment](/home/clay/issue_tracking/20260929020241_wesl-rs_package_visibility/assessment.md) |
| 4 | pygfx noise parentheses | No new report | [Existing PR](https://github.com/pygfx/pygfx/pull/1329/files) | Existing PR | [Assessment](/home/clay/issue_tracking/20260928150000_pygfx_noise_precedence/assessment.md) |
| 5 | NaN tolerance assertions | [Issue](/home/clay/issue_tracking/20261002184232_wgsl-test_nan_tolerance/issue.md) | [Fix](/home/clay/issue_tracking/20261002184232_wgsl-test_nan_tolerance/fix.patch) | +21 / −4 | [Assessment](/home/clay/issue_tracking/20261002184232_wgsl-test_nan_tolerance/assessment.md) |
| 6 | Module output order varies | [Addition to #292](/home/clay/issue_tracking/20260930150925_wesl-rs_nondeterministic_module_order/issue.md) | [Fix](/home/clay/issue_tracking/20260930150925_wesl-rs_nondeterministic_module_order/fix.patch) | +29 / −3 | [Assessment](/home/clay/issue_tracking/20260930150925_wesl-rs_nondeterministic_module_order/assessment.md) |
| 7 | Lowering drops a for initializer | [Issue](/home/clay/issue_tracking/20260929134256_wesl-rs_for_initializer/issue.md) | [Fix](/home/clay/issue_tracking/20260929134256_wesl-rs_for_initializer/fix.patch) | +37 / −1 | [Assessment](/home/clay/issue_tracking/20260929134256_wesl-rs_for_initializer/assessment.md) |

Items 1 and 2 can remove adapter adjustments after upstream adoption.
Item 3 enables a package-visible import that remains an expected failure.
Item 4 records the separate pygfx integration project.
Its prior recipe patch is absent from the current parent checkout.
[PR #1329](https://github.com/pygfx/pygfx/pull/1329) already contains its exact
fix.
Item 5 can replace the local assertion predicates.
Item 6 addresses one source of nondeterminism in existing issue #292.
Item 7 applies when lowering is enabled.

## Priority assessment

Rank prioritizes valid shader workflows and removal of local workarounds.
Malformed-input fixes rank below those cases. No listed case is a demonstrated
active blocker when an existing local workaround handles it.
Ease describes the scope of the fix, not a time estimate.
Merge likelihood is relative. Risk describes possible changes to valid behavior.

| Rank | Candidate and destination | Ease | Merge likelihood | Impact | Risk | Evidence and action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | [Qualified reference becomes a local cycle](/home/clay/issue_tracking/20260929134130_wesl-rs_qualified_reference/assessment.md), new wesl-rs issue and PR | Small | High | valid shader imports | Moderate | Retargeting matches the final name without checking the qualified path. A valid external call to a same-named function reports a cycle. The tested patch excludes qualified paths from local retargeting. |
| 2 | [Disabled visibility is ignored](/home/clay/issue_tracking/20260929134128_wesl-rs_disabled_visibility/assessment.md), new wesl-rs issue and PR | Small | High | option parity | Low | First lookup checks visibility despite `visibility=false`. The tested one-condition patch honors the public option. [PR #301](https://github.com/webgpu-tools/wesl-rs/pull/301) introduced the option; [issue #300](https://github.com/webgpu-tools/wesl-rs/issues/300) does not report this branch. |
| 3 | [Same-package named visibility](/home/clay/issue_tracking/20260929020241_wesl-rs_package_visibility/assessment.md), new wesl-rs issue and PR | Small | Moderate | valid shader imports | Moderate | Usage analysis requires `public` for all canonical package paths, including calls within the same named package. The tested patch compares package identity. Keep cross-package and private controls. |
| 4 | [pygfx noise precedence](/home/clay/issue_tracking/20260928150000_pygfx_noise_precedence/assessment.md), follow [PR #1329](https://github.com/pygfx/pygfx/pull/1329) | Small | Moderate | separate parent integration | Low | Open PR #1329 already contains the exact two-line fix. Current main still has the recorded source. Do not prepare a duplicate PR. The prior integration used a recipe patch; that recipe is absent from its current checkout. Merge depends on acceptance of strict WGSL grammar despite Naga accepting the original. Contribution guidance requires human communication and AI disclosure. No parser relaxation is justified. |
| 5 | [NaN tolerance assertions](https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders/lib.wesl#L30-L75), new wesl-js issue and PR | Small | Moderate | assertion correctness | Moderate | `diff > tolerance` is false for NaN, so `expectWithin*` passes unordered values. Four predicate changes in the binding reject them. Define infinity behavior before extending non-finite handling; no matching issue or PR appeared in the current tracker search. |
| 6 | [Non-deterministic module order](https://github.com/webgpu-tools/wesl-rs/issues/292), add evidence and PR there | Moderate | High | reproducible output | Moderate | Identical inputs produce two WGSL outputs because import traversal reads a hash map. A tested sorting patch makes this measured path stable. Issue #292 already covers reproducibility; do not open a second issue. |
| 7 | [False `for` initializer is lost](/home/clay/issue_tracking/20260929134256_wesl-rs_for_initializer/assessment.md), new wesl-rs issue and PR | Small | High | optional lowering | Moderate | `lower=true` drops an initializer that WGSL executes before the false condition. A focused patch and tests pass. Check scope preservation and one-pass lowering; repeated lowering has a separate known limit. |
| 8 | [Parser EOF span](/home/clay/issue_tracking/20260929141346_wesl-rs_unicode_eof/assessment.md), new wesl-rs issue and PR | Small | High | malformed-input diagnostics | Low | `fn f() {\u{2028}` returns byte span `8..9`, which splits a UTF-8 character and panics during rendering. The tested empty-span patch stops the panic. A full fix must place EOF after trailing blankspace before removing the binding rewrite. |
| 9 | [Invalid bitcast panics](/home/clay/issue_tracking/20260929141537_wesl-rs_invalid_bitcast_alignment/assessment.md), new wesl-rs issue and PR | Small | High | malformed-input safety | Low | An invalid operand with `@align(0)` reaches division by zero during normal compilation. A validated patch rejects the operand before size calculation. [Issue #191](https://github.com/webgpu-tools/wesl-rs/issues/191) covers size compatibility, not this panic. |
| 10 | [Optional conditional nodes](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/pass/condcomp.rs#L286), [PR #309](https://github.com/webgpu-tools/wesl-rs/pull/309), merged and adopted | Small | High | high | Moderate | The condition removes enabled `break if` and `continuing` nodes. The previous dependency pin retains the inverted predicate. The merged fix covers both forms and both truth values. The pin now includes the fix at `9c715d9`, and the shared test exceptions are removed. [PR 237](https://github.com/webgpu-tools/wesl-rs/pull/237) concerns block flattening, a different behavior. |
| 11 | [Discarded lexer errors](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wgsl-parse/src/lexer.rs#L756-L782), [PR #310](https://github.com/webgpu-tools/wesl-rs/pull/310), open | Small | High | malformed-input rejection | Moderate | The token filter drops `Err` with trivia. `💥` parses as empty source; `$` disappears from an expression. Submitted with focused regressions. The binding needs no duplicate lexer. Adopt the fix after merge and run the compact lexer regression. |
| 12 | [Unterminated block comments](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wgsl-parse/src/lexer.rs#L214), [PR #310](https://github.com/webgpu-tools/wesl-rs/pull/310), open | Small | High | malformed-input rejection | Low | The scanner reaches EOF with positive depth and accepts the source. The scanner fix depends on propagating lexer errors, so both defects share one PR. Focused regressions cover unfinished and valid nested comments. |
| 13 | [Diagnostic line breaks](/home/clay/issue_tracking/20260929134131_wesl-rs_diagnostic_line_breaks/assessment.md), new wesl-rs issue | Moderate | Moderate | medium | Moderate | The renderer splits on LF. CR, VT, FF, NEL, U+2028, and U+2029 receive wrong WGSL coordinates. Source normalization needs exact byte-span remapping. The report is ready; no validated patch exists. |
| 14 | [Exact integer assertion reports](/home/clay/issue_tracking/20260929134131_wgsl-test_integer_reports/assessment.md), new wesl-js issue | Large | Moderate | medium | Moderate | `expectEq(u32,u32)` decides correctly, then stores operands as `f32`. A failing `4294967295u` versus `4294967294u` can print equal values. The shader layout and TypeScript decoder need a shared typed protocol. First-failure retention already works. |
| 15 | [Grouped import namespace](https://github.com/webgpu-tools/wesl-rs/blob/0303eccfafd534cc76c91eddd4b4f5c4413a1733/crates/wesl/src/pass/import.rs#L52-L69), new wesl-rs issue after a direct reproducer | Small | Moderate | medium | Moderate | Pathless collection flattening constructs a package path; ordinary imports call `join_path`. The binding's separate namespace rewrite then duplicates its own package name for grouped self imports. The local fix uses `join_path`; report upstream only for a direct grouped dependency namespace failure. This is not yet a proven standalone upstream failure. |
| 16 | [Quoted visibility modifiers](/home/clay/issue_tracking/20260929134131_wesl-rs_quoted_visibility/assessment.md), new wesl-rs issue | Moderate | Moderate | low | High | Token quotes reject `public` and `private` prefixes that string quotes parse. A simple keyword mapping regresses valid identifiers named `private`; the first patch was withdrawn. Resolve contextual parsing before a PR. |
| 17 | [Disabled imports option](/home/clay/issue_tracking/20260929134129_wesl-rs_disabled_imports/assessment.md), new wesl-rs issue | Moderate | Low | medium | High | The frontend ignores its documented `imports=false` field and resolves missing modules. A fix must coordinate traversal, path erasure, and validation, or upstream can remove the option. Report the contract conflict before selecting policy. |
| 18 | [Signed 64-bit minimum literal](/home/clay/projects/wesl-py/docs/api.md:311), new wesl-rs issue after a portable reproducer | Moderate | Moderate | low | Moderate | The binding accepts `-2**63`, but a referenced generated `-9223372036854775808` fails parsing. The mismatch may belong to formatting or binding source generation. Do not assume the parser must accept the positive magnitude before unary negation. Verify the [WGSL integer contract](https://www.w3.org/TR/WGSL/#integer-literals) and build a standalone case before filing. No upstream patch is ready. |
| 19 | [Retarget pass scaling](/home/clay/issue_tracking/20260930150925_wesl-rs_retarget_scaling/assessment.md), new wesl-rs issue and PR | Small | Moderate | low to medium | Moderate | At 2,000 independent declarations the pass takes 16.6 ms; a tested map lookup patch takes 0.38 ms. Verify nearest-scope semantics. The synthetic benchmark does not show production latency. |
| 20 | [Cycle validation scaling](/home/clay/issue_tracking/20260930150925_wesl-rs_cycle_validation_scaling/assessment.md), new wesl-rs issue and PR | Small | Moderate | low to medium | Moderate | The pass takes 18.2 ms at 2,000 declarations; a tested index patch takes 0.84 ms. [Issue 157](https://github.com/webgpu-tools/wesl-rs/issues/157) covers a crash with actual cycles, not this scaling path. |
| 21 | [Usage analysis scaling](/home/clay/issue_tracking/20260930150925_wesl-rs_usage_analysis_scaling/assessment.md), new wesl-rs issue | Large | Moderate | medium | High | The pass takes 48.3 ms at 2,000 declarations with repeated requests. No safe small patch exists because public syntax and pointer-based identifiers can change after indexing. Discuss invalidation before implementing a cache. |

Tracked work: [PyO3 PR #5738](https://github.com/PyO3/pyo3/pull/5738) remains
open, unmerged, and marked dirty. Ease is moderate. Merge likelihood is moderate
because a focused implementation exists, but it still needs review and conflict
resolution. Risk is low to moderate. Follow that PR rather than duplicate it.
Getter support alone does not replace the binding's exception and tuple stub
metadata.

The following are integration features or deliberate limits, so they should not
become defect reports: Python `Traversable` loading and `.wesl` precedence;
root-only Python manifest loading; selective layout constant evaluation; the
`validate=false` cycle guard ([upstream issue
157](https://github.com/webgpu-tools/wesl-rs/issues/157) already tracks the
related crash); the zero-alignment guard for low-level type queries; source
locations, assertion counts, cooperative test collection, and shared assertion
registration; the custom driver needed for module transformations; the disabled
default for lowering; renderer cleanup without a teardown contract; and the
ImGui version cap pending PyPI backend compatibility. The six shared fixture
block-flattening substitutions follow [PR
237](https://github.com/webgpu-tools/wesl-rs/pull/237) and are not six defects.
The grouped self-import fix now uses upstream path joining in the binding.
A separate upstream failure still needs a standalone reproduction.
The documentation claim that named
layout constants fail is stale: selective evaluation supports them.

Submission requirements: [wesl-rs
CONTRIBUTING.md](https://github.com/webgpu-tools/wesl-rs/blob/main/CONTRIBUTING.md)
says to open an issue for a bug report and states that it has no developer
guide. Current wesl-rs and wesl-js trees have no issue or PR template. Submit
the standalone report, pinned reproduction, observed result, expected result,
and focused patch or test when ready. Add the module-order reproducer to issue
292. PyO3 has [issue
templates](https://github.com/PyO3/pyo3/tree/main/.github/ISSUE_TEMPLATE) and a
[PR
template](https://github.com/PyO3/pyo3/blob/main/.github/pull_request_template.md)
that asks for tests, docs, and a newsfragment for changed functions. It also
says not to submit unsolicited AI-generated PRs. The existing getter PR needs
review, not another submission. PRs #309 and #310 are published. The other
listed reports and patches remain local.

The best next patches for this binding are qualified-reference retargeting,
disabled visibility, and same-package visibility. The first two remove local
adapter adjustments. The third enables a valid import case that remains an
expected failure. Each has a standalone reproducer and a tested focused patch.
The pygfx patch serves a separate parent project. Recheck patches on the latest
upstream revision before considering submission. No more GitHub changes are
authorized in this session.

PR 309 is merged and adopted at `9c715d9`. Its test exceptions are removed.
PR 310 is open with the compact revision. It affects malformed input and does
not block a demonstrated valid-shader workflow. Other reports and patches
remain local. Leave the imports option and typed assertion protocol for design
discussion.
