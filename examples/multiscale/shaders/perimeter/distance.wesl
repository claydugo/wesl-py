override width: u32;
override height: u32;
override minimum_signal: f32 = 0.06;
@group(0) @binding(0) var<storage, read> seeds: array<vec2<i32>>;
@group(0) @binding(1) var<storage, read_write> output: array<vec2<f32>>;
@group(0) @binding(2) var<storage, read> channels: array<f32>;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    if (any(position.xy >= vec2<u32>(width, height))) { return; }
    let index = position.y * width + position.x;
    let field_size = width * height;
    output[index] = vec2<f32>(0.0);
    if (seeds[index].x < 0 || channels[field_size + index] + channels[2u * field_size + index] < minimum_signal) { return; }
    output[index] = vec2<f32>(distance(vec2<f32>(position.xy), vec2<f32>(seeds[index])), 1.0);
}
