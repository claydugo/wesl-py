import super::super::levels::adjust;
import wgsl_test::expectNear;

@group(0) @binding(0) var<storage, read> values: array<f32>;
@group(0) @binding(1) var<storage, read> expected: array<f32>;
override gain: f32 = 1.0;

@test
fn exposure_matches_reference() {
    for (var index = 0u; index < arrayLength(&values); index++) {
        expectNear(adjust(values[index]) * gain, expected[index]);
    }
}
