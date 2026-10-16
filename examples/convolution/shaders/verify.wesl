enable f16;

@group(0) @binding(0) var<storage, read> actual: array<f16>;
@group(0) @binding(1) var<storage, read> expected: array<f16>;

@test
fn matches_reference() {
    wgsl_test::expectEq(arrayLength(&actual), arrayLength(&expected));
    for (var index = 0u; index < arrayLength(&actual); index++) {
        wgsl_test::expectWithin(f32(actual[index]), f32(expected[index]), 0.002, 0.0005);
    }
}
