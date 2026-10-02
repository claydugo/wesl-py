import package::examples::imaging::statistics::correlation;
import wgsl_test::expectNear;

@test
fn correlation_sign_and_validity() {
    expectNear(correlation(vec3<f32>(0.25, 0.25, 0.25)).x, 1.0);
    expectNear(correlation(vec3<f32>(0.25, 0.25, -0.25)).x, -1.0);
    let partial = correlation(vec3<f32>(0.25, 1.0, 0.25));
    expectNear(partial.x, 0.5);
    expectNear(partial.y, 1.0);
    expectNear(correlation(vec3<f32>(0.0)).y, 0.0);
    expectNear(correlation(vec3<f32>(0.0, 1.0, 0.0)).y, 0.0);
    expectNear(correlation(vec3<f32>(1.0, 0.0, 0.0)).y, 0.0);
}
