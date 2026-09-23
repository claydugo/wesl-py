import package::imaging::sampling::sample_channel;

override width: u32;
override height: u32;
override minimum_signal: f32 = 0.06;
@group(0) @binding(1) var<storage, read_write> output: array<vec2<i32>>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    let dimensions = vec2<u32>(width, height);
    if (any(position.xy >= dimensions)) { return; }
    let pixel = vec2<i32>(position.xy);
    let index = position.y * width + position.x;
    output[index] = vec2<i32>(-1);
    let gfp = sample_channel(pixel, 1u, dimensions);
    let rfp = sample_channel(pixel, 2u, dimensions);
    if (gfp + rfp < minimum_signal) { return; }
    for (var axis = 0u; axis < 2u; axis++) {
        for (var direction = -1; direction <= 1; direction += 2) {
            var neighbor = pixel;
            neighbor[axis] += direction;
            let inside = all(neighbor >= vec2<i32>(0)) && all(neighbor < vec2<i32>(dimensions));
            let neighbor_gfp = sample_channel(neighbor, 1u, dimensions);
            let neighbor_rfp = sample_channel(neighbor, 2u, dimensions);
            let occupied = inside && neighbor_gfp + neighbor_rfp >= minimum_signal;
            if (!occupied) { output[index] = pixel; }
        }
    }
}
