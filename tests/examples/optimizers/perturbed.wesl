@group(0) @binding(0) var<storage, read> parameters: array<f32>;
var<private> perturbed_index: u32;
var<private> perturbation: f32;

public fn parameter(index: u32) -> f32 {
    return parameters[index] + select(0.0, perturbation, index == perturbed_index);
}
