import package::examples::imaging::statistics::correlation;
import package::tests::examples::random::random;
import wgsl_test::{expectNearVec2, expectWithinVec2};

@test @workgroup_size(64)
fn correlation_properties(@builtin(local_invocation_index) lane: u32) {
    expectNearVec2(correlation(vec3f(0.25, 1.0, 0.25)), vec2f(0.5, 1.0));
    let first = 0.05 + 2.0 * random(lane * 3u);
    let second = 0.05 + 2.0 * random(lane * 3u + 1u);
    let coefficient = 2.0 * random(lane * 3u + 2u) - 1.0;
    let products = vec3f(first * first, second * second, coefficient * first * second);
    expectWithinVec2(correlation(products), vec2f(coefficient, 1.0), 0.0001, 0.000001);
    expectWithinVec2(correlation(products * vec3f(1.0, 1.0, -1.0)), vec2f(-coefficient, 1.0), 0.0001, 0.000001);
    expectWithinVec2(correlation(products * vec3f(9.0, 0.25, 1.5)), vec2f(coefficient, 1.0), 0.0001, 0.000001);
    expectNearVec2(correlation(vec3f(products.xy, 1.01 * first * second)), vec2f(1.0, 1.0));
    expectNearVec2(correlation(vec3f(products.x, 0.0000005, products.z)), vec2f(0.0));
    expectNearVec2(correlation(vec3f(-products.x, products.y, 0.0)), vec2f(0.0));
}
