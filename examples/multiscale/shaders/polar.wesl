import package::examples::imaging::sampling::sample_channel;
import package::examples::imaging::coordinates::polar_position;

override width: u32;
override height: u32;
override center_x: f32;
override center_y: f32;
override maximum_radius: f32;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    let dimensions = vec2<u32>(width, height);
    if (any(position.xy >= dimensions)) { return; }
    let sample = polar_position(position.xy, dimensions, vec2<f32>(center_x, center_y), maximum_radius);
    let inside = all(sample >= vec2<f32>(0.0)) && all(sample <= vec2<f32>(dimensions - 1u));
    let lower = vec2<i32>(floor(sample));
    let fraction = fract(sample);
    let index = position.y * width + position.x;
    for (var channel = 0u; channel < 3u; channel++) {
        var value = 0.0;
        if (inside) {
            value = mix(
                mix(sample_channel(lower, channel, dimensions),
                    sample_channel(lower + vec2<i32>(1, 0), channel, dimensions), fraction.x),
                mix(sample_channel(lower + vec2<i32>(0, 1), channel, dimensions),
                    sample_channel(lower + vec2<i32>(1, 1), channel, dimensions), fraction.x), fraction.y);
        }
        output[channel * width * height + index] = value;
    }
}
