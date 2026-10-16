import wgsl_test::{expectEq, expectWithin};
enable f16;

override expected_count: u32;

@group(0) @binding(0) var<storage, read> actual: array<f16>;
@group(0) @binding(1) var<storage, read> expected: array<f16>;
@group(0) @binding(2) var<uniform> tolerance: vec2f;

@test
fn operator_matches_reference() {
    expectEq(arrayLength(&actual), arrayLength(&expected));
    for (var index = 0u; index < arrayLength(&actual); index++) {
        if index >= expected_count {
            expectWithin(f32(actual[index]), 123.0, 0.0, 0.0);
        } else {
            expectWithin(f32(actual[index]), f32(expected[index]), tolerance.x, tolerance.y);
        }
    }
}
