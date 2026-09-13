import package::heightfield::field::sample;

fn gradient(position: vec2<i32>, dimensions: vec2<u32>) -> vec2<f32> {
    return vec2<f32>(
        sample(position + vec2<i32>(1, 0), dimensions) - sample(position - vec2<i32>(1, 0), dimensions),
        sample(position + vec2<i32>(0, 1), dimensions) - sample(position - vec2<i32>(0, 1), dimensions),
    ) * vec2<f32>(dimensions - 1u) * 0.25;
}

fn normal(position: vec2<i32>, dimensions: vec2<u32>) -> vec3<f32> {
    return normalize(vec3<f32>(-gradient(position, dimensions), 1.0));
}
