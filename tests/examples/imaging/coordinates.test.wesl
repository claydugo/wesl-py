import package::examples::imaging::coordinates::polar_position;
import package::examples::imaging::indexing::linear_index;
import package::examples::imaging::sampling::clamp_position;
import wgsl_test::{expect, expectEq, expectNear};

@test @workgroup_size(8, 4, 2)
fn pixel_mappings(
    @builtin(local_invocation_id) position: vec3u,
    @builtin(local_invocation_index) lane: u32,
) {
    let dimensions = vec2u(8u, 4u);
    expectEq(linear_index(position, dimensions), lane);

    let requested = vec2i(position.xy) * 3 - vec2i(9, 4) + vec2i(i32(position.z));
    let clamped = clamp_position(requested, dimensions);
    expect(all(clamped < dimensions));
    for (var y = 0u; y < dimensions.y; y++) {
        for (var x = 0u; x < dimensions.x; x++) {
            let candidate = vec2f(f32(x), f32(y));
            expect(distance(vec2f(requested), vec2f(clamped)) <= distance(vec2f(requested), candidate));
        }
    }

    let center = vec2f(3.5, 1.5);
    let radius = 2.0 * f32(position.y);
    let sample = polar_position(position.xy, dimensions, center, 6.0);
    let next = polar_position(position.xy + vec2u(1u, 0u), dimensions, center, 6.0);
    expectNear(distance(sample, center), radius);
    expectNear(distance(sample, next), 2.0 * radius * sin(3.14159265 / 8.0));
    if position.x == 0u {
        expectNear(sample.y, center.y);
        expect(sample.x >= center.x);
    }
}
