import package::examples::sdf::scene::distance_to_scene;
import package::examples::sdf::surface::normal;
import package::tests::examples::random::random;
import wgsl_test::{expect, expectNear, expectNearVec3, expectWithinVec3};

@test @workgroup_size(64)
fn sphere_tracing_contract(@builtin(local_invocation_index) lane: u32) {
    let seed = lane * 8u;
    let point = vec3f(random(seed), random(seed + 1u), random(seed + 2u)) * 5.0 - 2.5;
    let step = normalize(vec3f(random(seed + 3u), random(seed + 4u), random(seed + 5u)) - 0.5)
        * random(seed + 6u);
    let change = abs(distance_to_scene(point + step) - distance_to_scene(point));
    expect(change <= length(step) * 1.0001 + 0.000001);

    let angle = 6.28318530718 * random(seed + 7u);
    let floor = vec3f(3.0 * cos(angle), -1.25, 3.0 * sin(angle));
    expectNear(distance_to_scene(floor), 0.0);
    expectNearVec3(normal(floor), vec3f(0.0, 1.0, 0.0));

    let height = 0.6 + 0.2 * random(seed + 2u);
    let outward = vec3f(sqrt(1.0 - height * height) * cos(angle), height, sqrt(1.0 - height * height) * sin(angle));
    let crown = vec3f(0.0, 1.25, 0.0) + 0.85 * outward;
    expectNear(distance_to_scene(crown), 0.0);
    expectWithinVec3(normal(crown), outward, 0.0, 0.0002);

    let axis = vec3f(0.0, 0.45, 0.0);
    @if(cutout) expectNear(distance_to_scene(axis), 0.48);
    @else expect(distance_to_scene(axis) < 0.0);
}
