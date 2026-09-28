struct Moments {
    means: vec2<f32>,
    weight: f32,
    products: vec3<f32>,
}

public fn correlation(products: vec3<f32>) -> vec2<f32> {
    let variance = max(products.xy, vec2<f32>(0.0));
    if (any(variance <= vec2<f32>(1e-6))) { return vec2<f32>(0.0); }
    return vec2<f32>(clamp(products.z / sqrt(variance.x * variance.y), -1.0, 1.0), 1.0);
}
