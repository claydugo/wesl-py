@group(0) @binding(0) var<storage, read> heights: array<f32>;

fn sample(position: vec2<i32>, dimensions: vec2<u32>) -> f32 {
    let clamped = vec2<u32>(clamp(position, vec2<i32>(0), vec2<i32>(dimensions) - 1));
    return heights[clamped.y * dimensions.x + clamped.x];
}
