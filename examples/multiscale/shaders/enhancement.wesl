@group(0) @binding(0) var<storage, read> source: array<f32>;
@group(0) @binding(1) var<storage, read> fine: array<f32>;
@group(0) @binding(2) var<storage, read> coarse: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;
override strength: f32 = 2.0;

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) position: vec3<u32>) {
    let index = position.x;
    if (index >= arrayLength(&source)) {
        return;
    }
    if (index < arrayLength(&source) / 3u) {
        output[index] = source[index];
    } else {
        output[index] = clamp(source[index] + strength * (fine[index] - coarse[index]), 0.0, 1.0);
    }
}
