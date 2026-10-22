import package::examples::imaging::gaussian::convolve_radius;
import package::examples::imaging::sampling::sample_channel;
import wgsl_test::{expect, expectNear};

const radius: i32 = constants::radius;

fn convolve(position: vec3u, dimensions: vec2u) -> f32 {
    return convolve_radius(position, dimensions, radius);
}

@test @workgroup_size(8, 8)
fn convolution_invariants(@builtin(local_invocation_id) position: vec3u) {
    let dimensions = vec2u(8u, 8u);
    @if(horizontal) let direction = vec2i(1, 0);
    @else let direction = vec2i(0, 1);
    let along = u32(dot(vec2i(position.xy), direction));
    let across = u32(dot(vec2i(position.xy), direction.yx));
    let along_field = select(2u, 1u, direction.x == 1);

    expectNear(convolve(vec3u(position.xy, 0u), dimensions), 0.75);
    expectNear(convolve(vec3u(position.xy, 3u - along_field), dimensions), f32(across));
    if along >= u32(radius) && along + u32(radius) < 8u {
        expectNear(convolve(vec3u(position.xy, along_field), dimensions), f32(along));
    }

    for (var field = 0u; field < 4u; field++) {
        var minimum = 1e30;
        var maximum = -1e30;
        for (var offset = -radius; offset <= radius; offset++) {
            let value = sample_channel(vec2i(position.xy) + direction * offset, field, dimensions);
            minimum = min(minimum, value);
            maximum = max(maximum, value);
        }
        let smoothed = convolve(vec3u(position.xy, field), dimensions);
        expect(smoothed >= minimum - 0.0001 && smoothed <= maximum + 0.0001);
    }
}
