import examples::imaging::statistics::correlation;
import examples::imaging::coordinates::polar_position;
import wgsl_test::expectNear;

@test
fn correlation_sign_and_validity() {
    expectNear(correlation(vec3<f32>(0.25, 0.25, 0.25)).x, 1.0);
    expectNear(correlation(vec3<f32>(0.25, 0.25, -0.25)).x, -1.0);
    expectNear(correlation(vec3<f32>(0.0)).y, 0.0);
}

@test
fn polar_center_and_clockwise_quarter_turn() {
    let center = vec2<f32>(10.0, 20.0);
    let origin = polar_position(vec2<u32>(0u, 0u), vec2<u32>(4u, 3u), center, 2.0);
    expectNear(origin.x, 10.0);
    expectNear(origin.y, 20.0);
    let quarter = polar_position(vec2<u32>(1u, 2u), vec2<u32>(4u, 3u), center, 2.0);
    expectNear(quarter.x, 10.0);
    expectNear(quarter.y, 22.0);
}
