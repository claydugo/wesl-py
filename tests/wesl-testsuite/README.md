# Shared WESL cases

The JSON files come from
[wesl-testsuite at `28596c9`](https://github.com/webgpu-tools/wesl-testsuite/tree/28596c90b1a27fb2a0777291c95b0c279db97bc6/src/test-cases-json).
The pinned wesl-rs revision uses this fixture revision.
The copies retain the upstream data and MIT license.

`tests/upstream.rs` runs 94 compilation cases and 33 import syntax cases through
the Python API. It compares all 94 compilation results with expected output
after the parser sorts declarations. Two cases record strict expected failures.
They fail the test if the compiler starts to produce the expected output.

The `@else with package function reference` case expects an empty block.
The compiler flattens that block. The test expects `fn main() {}` for this case.
The upstream harness also identifies this stale expectation.

Five more expected results retain conditional blocks that the compiler flattens:
`@if on compound statement`, `@else with compound statements`, `nested @if/@else`,
`@else with variable references`, and
`@else with variable references false condition`.
The test supplies explicit flattened output for each case.
It does not flatten arbitrary blocks when comparing results.

The `@if on break-if statement` and `@if on continuing statement` cases expose
defects in the pinned compiler. It removes enabled statements and retains disabled
statements with WESL attributes. The tests retain the correct expected output and
require a mismatch until upstream fixes each defect.
