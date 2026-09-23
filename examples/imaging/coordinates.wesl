fn polar_position(pixel: vec2<u32>, dimensions: vec2<u32>, center: vec2<f32>, maximum_radius: f32) -> vec2<f32> {
    let angle = 6.28318530718 * f32(pixel.x) / f32(dimensions.x);
    let radius = maximum_radius * f32(pixel.y) / f32(max(dimensions.y - 1u, 1u));
    return center + radius * vec2<f32>(cos(angle), sin(angle));
}
