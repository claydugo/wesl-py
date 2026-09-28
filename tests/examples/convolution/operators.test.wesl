import wgsl_test::{expectEq, expectWithin};
import package::examples::convolution::shaders::activation::activate;
enable f16;

@group(0) @binding(0) var<storage, read> actual: array<f16>;
@group(0) @binding(1) var<storage, read> expected: array<f16>;
@group(0) @binding(2) var<uniform> tolerance: vec2f;

@test
fn operator_matches_reference() {
    expectEq(arrayLength(&actual), arrayLength(&expected));
    for (var index = 0u; index < arrayLength(&actual); index++) {
        expectWithin(f32(actual[index]), f32(expected[index]), tolerance.x, tolerance.y);
    }
    for (var index = arrayLength(&actual) - 16u; index < arrayLength(&actual); index++) {
        expectWithin(f32(actual[index]), 123.0, 0.0, 0.0);
    }
    expectWithin(f32(activate(-2.0, 0.0h, 0u)), -2.0, 0.0, 0.0);
    expectWithin(f32(activate(-10.0, 0.0h, 1u)), -1.0, 0.0, 0.0);
    expectWithin(f32(activate(0.0, 0.0h, 2u)), 0.5, 0.0, 0.0);
}
