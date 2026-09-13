fn color(iterations: f32) -> vec3<f32> {
    if (iterations < 0.0) {
        return vec3<f32>(0.015, 0.02, 0.04);
    }
    return 0.5 + 0.5 * cos(0.15 * iterations + vec3<f32>(0.0, 0.8, 1.8));
}
