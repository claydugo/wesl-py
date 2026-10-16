override width: u32;
override height: u32;
override step: i32;
@group(0) @binding(0) var<storage, read> source: array<vec2<i32>>;
@group(0) @binding(1) var<storage, read_write> output: array<vec2<i32>>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    if (any(position.xy >= vec2<u32>(width, height))) { return; }
    let pixel = vec2<i32>(position.xy);
    var nearest = vec2<i32>(-1);
    var minimum_distance = 3.402823e38;
    for (var offset_y = -1; offset_y <= 1; offset_y++) {
        for (var offset_x = -1; offset_x <= 1; offset_x++) {
            let neighbor = pixel + vec2<i32>(offset_x, offset_y) * step;
            if (any(neighbor < vec2<i32>(0)) || any(neighbor >= vec2<i32>(i32(width), i32(height)))) { continue; }
            let candidate = source[u32(neighbor.y) * width + u32(neighbor.x)];
            if (candidate.x < 0) { continue; }
            let displacement = vec2<f32>(candidate - pixel);
            let distance_squared = dot(displacement, displacement);
            if (distance_squared < minimum_distance) {
                nearest = candidate;
                minimum_distance = distance_squared;
            }
        }
    }
    output[position.y * width + position.x] = nearest;
}
