fn linear_index(position: vec3<u32>, dimensions: vec2<u32>) -> u32 {
    return (position.z * dimensions.y + position.y) * dimensions.x + position.x;
}
