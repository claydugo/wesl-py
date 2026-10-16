import package::examples::sdf::primitives::{sphere, smooth_union};
import package::tests::examples::random::random;
import wgsl_test::{expect, expectNear, expectWithin};

@test @workgroup_size(64)
fn distance_bounds(@builtin(local_invocation_index) lane: u32) {
    expectNear(sphere(vec3f(0.0), 2.0), -2.0);
    expectNear(smooth_union(0.0, 0.0, 0.4), -0.1);
    let seed = lane * 8u;
    let point = vec3f(random(seed), random(seed + 1u), random(seed + 2u)) * 6.0 - 3.0;
    let other = vec3f(random(seed + 3u), random(seed + 4u), random(seed + 5u)) * 6.0 - 3.0;
    let radius = 0.25 + random(seed + 6u);
    expectWithin(sphere(normalize(point) * radius, radius), 0.0, 0.0, 0.000001);
    expect(abs(sphere(point, radius) - sphere(other, radius)) <= distance(point, other) + 0.000001);

    let first = sphere(point, radius);
    let second = sphere(other, radius);
    let width = 0.1 + random(seed + 7u);
    let blended = smooth_union(first, second, width);
    expectNear(blended, smooth_union(second, first, width));
    expect(blended <= min(first, second) + 0.000001);
    expect(blended >= min(first, second) - 0.25 * width - 0.000001);
    if abs(first - second) >= width {
        expectNear(blended, min(first, second));
    }
}
