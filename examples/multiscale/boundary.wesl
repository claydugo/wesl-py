fn clamp_position(position: vec2<i32>, dimensions: vec2<u32>) -> vec2<u32> {
    return vec2<u32>(clamp(position, vec2<i32>(0), vec2<i32>(dimensions) - 1));
}
