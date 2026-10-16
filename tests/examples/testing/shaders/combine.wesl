import super::levels::adjust;

@group(0) @binding(0) var<storage, read> values: array<f32>;
@group(0) @binding(1) var<storage, read> weights: array<f32>;
@group(0) @binding(2) var<storage, read_write> weighted: array<f32>;
@group(0) @binding(3) var<storage, read_write> adjusted: array<f32>;

@compute @workgroup_size(4)
fn main(@builtin(global_invocation_id) invocation: vec3u) {
    let index = invocation.x;
    if index >= arrayLength(&values) {
        return;
    }
    weighted[index] = values[index] * weights[index];
    adjusted[index] = adjust(weighted[index]);
}
