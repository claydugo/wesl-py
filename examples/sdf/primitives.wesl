public fn sphere(position: vec3<f32>, radius: f32) -> f32 {
    return length(position) - radius;
}

public fn smooth_union(first: f32, second: f32, width: f32) -> f32 {
    let fraction = clamp(0.5 + 0.5 * (second - first) / width, 0.0, 1.0);
    return mix(second, first, fraction) - width * fraction * (1.0 - fraction);
}
