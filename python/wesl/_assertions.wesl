struct TestResult {
    completed: u32,
    checks: u32,
    failures: u32,
    site: u32,
    kind: u32,
    width: u32,
    tolerance: vec2u,
    actual: vec4u,
    expected: vec4u,
}

@group(0) @binding(WESL_TEST_BINDING)
var<storage, read_write> result: TestResult;
var<private> location: u32;

fn begin() {
    result.completed = 0u;
    result.checks = 0u;
    result.failures = 0u;
}

fn finish() {
    result.completed = 1u;
}

fn record(passed: bool, actual: vec4u, expected: vec4u, kind: u32, width: u32, tolerance: vec2u) {
    result.checks += 1u;
    if passed { return; }
    if result.failures == 0u {
        result.site = location;
        result.kind = kind;
        result.width = width;
        result.tolerance = tolerance;
        result.actual = actual;
        result.expected = expected;
    }
    result.failures += 1u;
}

fn near(actual: vec4f, expected: vec4f, relative: f32, absolute: f32) -> bool {
    let difference = abs(actual - expected);
    let tolerance = max(vec4f(absolute), relative * max(abs(actual), abs(expected)));
    return relative >= 0.0 && absolute >= 0.0 && all((actual == expected) | (difference <= tolerance));
}

fn ordered(value: vec4f) -> vec4u {
    let bits = bitcast<vec4u>(value);
    return select(bits + vec4u(0x80000000u), vec4u(0x80000000u) - (bits & vec4u(0x7fffffffu)), (bits & vec4u(0x80000000u)) != vec4u(0u));
}

fn expect(condition: bool) {
    record(condition, vec4u(u32(condition), 0u, 0u, 0u), vec4u(1u, 0u, 0u, 0u), 0u, 1u, vec2u(0u));
}

fn expectEq(actual: u32, expected: u32) {
    record(actual == expected, vec4u(actual, 0u, 0u, 0u), vec4u(expected, 0u, 0u, 0u), 1u, 1u, vec2u(0u));
}

fn expectEqI32(actual: i32, expected: i32) {
    record(actual == expected, vec4u(bitcast<u32>(actual), 0u, 0u, 0u), vec4u(bitcast<u32>(expected), 0u, 0u, 0u), 2u, 1u, vec2u(0u));
}

fn expectNear(actual: f32, expected: f32) {
    record(near(vec4f(actual, 0.0, 0.0, 0.0), vec4f(expected, 0.0, 0.0, 0.0), 0.001, 0.000001), bitcast<vec4u>(vec4f(actual, 0.0, 0.0, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0, 0.0, 0.0)), 3u, 1u, bitcast<vec2u>(vec2f(0.001, 0.000001)));
}

fn expectWithin(actual: f32, expected: f32, relative: f32, absolute: f32) {
    record(near(vec4f(actual, 0.0, 0.0, 0.0), vec4f(expected, 0.0, 0.0, 0.0), relative, absolute), bitcast<vec4u>(vec4f(actual, 0.0, 0.0, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0, 0.0, 0.0)), 3u, 1u, bitcast<vec2u>(vec2f(relative, absolute)));
}

fn expectUlp(actual: f32, expected: f32, maximum: u32) {
    let actual_order = ordered(vec4f(actual, 0.0, 0.0, 0.0));
    let expected_order = ordered(vec4f(expected, 0.0, 0.0, 0.0));
    let passed = all(max(actual_order, expected_order) - min(actual_order, expected_order) <= vec4u(maximum));
    record(passed, bitcast<vec4u>(vec4f(actual, 0.0, 0.0, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0, 0.0, 0.0)), 4u, 1u, vec2u(maximum, 0u));
}

fn expectNearVec2(actual: vec2f, expected: vec2f) {
    record(near(vec4f(actual, 0.0, 0.0), vec4f(expected, 0.0, 0.0), 0.001, 0.000001), bitcast<vec4u>(vec4f(actual, 0.0, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0, 0.0)), 3u, 2u, bitcast<vec2u>(vec2f(0.001, 0.000001)));
}

fn expectWithinVec2(actual: vec2f, expected: vec2f, relative: f32, absolute: f32) {
    record(near(vec4f(actual, 0.0, 0.0), vec4f(expected, 0.0, 0.0), relative, absolute), bitcast<vec4u>(vec4f(actual, 0.0, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0, 0.0)), 3u, 2u, bitcast<vec2u>(vec2f(relative, absolute)));
}

fn expectUlpVec2(actual: vec2f, expected: vec2f, maximum: u32) {
    let actual_order = ordered(vec4f(actual, 0.0, 0.0));
    let expected_order = ordered(vec4f(expected, 0.0, 0.0));
    let passed = all(max(actual_order, expected_order) - min(actual_order, expected_order) <= vec4u(maximum));
    record(passed, bitcast<vec4u>(vec4f(actual, 0.0, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0, 0.0)), 4u, 2u, vec2u(maximum, 0u));
}

fn expectNearVec3(actual: vec3f, expected: vec3f) {
    record(near(vec4f(actual, 0.0), vec4f(expected, 0.0), 0.001, 0.000001), bitcast<vec4u>(vec4f(actual, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0)), 3u, 3u, bitcast<vec2u>(vec2f(0.001, 0.000001)));
}

fn expectWithinVec3(actual: vec3f, expected: vec3f, relative: f32, absolute: f32) {
    record(near(vec4f(actual, 0.0), vec4f(expected, 0.0), relative, absolute), bitcast<vec4u>(vec4f(actual, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0)), 3u, 3u, bitcast<vec2u>(vec2f(relative, absolute)));
}

fn expectUlpVec3(actual: vec3f, expected: vec3f, maximum: u32) {
    let actual_order = ordered(vec4f(actual, 0.0));
    let expected_order = ordered(vec4f(expected, 0.0));
    let passed = all(max(actual_order, expected_order) - min(actual_order, expected_order) <= vec4u(maximum));
    record(passed, bitcast<vec4u>(vec4f(actual, 0.0)), bitcast<vec4u>(vec4f(expected, 0.0)), 4u, 3u, vec2u(maximum, 0u));
}

fn expectNearVec4(actual: vec4f, expected: vec4f) {
    record(near(actual, expected, 0.001, 0.000001), bitcast<vec4u>(actual), bitcast<vec4u>(expected), 3u, 4u, bitcast<vec2u>(vec2f(0.001, 0.000001)));
}

fn expectWithinVec4(actual: vec4f, expected: vec4f, relative: f32, absolute: f32) {
    record(near(actual, expected, relative, absolute), bitcast<vec4u>(actual), bitcast<vec4u>(expected), 3u, 4u, bitcast<vec2u>(vec2f(relative, absolute)));
}

fn expectUlpVec4(actual: vec4f, expected: vec4f, maximum: u32) {
    let actual_order = ordered(actual);
    let expected_order = ordered(expected);
    let passed = all(max(actual_order, expected_order) - min(actual_order, expected_order) <= vec4u(maximum));
    record(passed, bitcast<vec4u>(actual), bitcast<vec4u>(expected), 4u, 4u, vec2u(maximum, 0u));
}
