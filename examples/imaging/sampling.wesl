import super::indexing::linear_index;

@group(0) @binding(0) var<storage, read> source: array<f32>;

fn clamp_position(position: vec2<i32>, dimensions: vec2<u32>) -> vec2<u32> {
    return vec2<u32>(clamp(position, vec2<i32>(0), vec2<i32>(dimensions) - 1));
}

fn sample_channel(position: vec2<i32>, channel: u32, dimensions: vec2<u32>) -> f32 {
    return source[linear_index(vec3<u32>(clamp_position(position, dimensions), channel), dimensions)];
}
