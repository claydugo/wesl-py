@group(0) @binding(0) var<storage, read> parameters: array<f32>;

public fn parameter(index: u32) -> f32 {
    return parameters[index];
}
