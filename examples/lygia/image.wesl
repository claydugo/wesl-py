import super::colorize::colorize;

@group(0) @binding(0) var<storage, read> values: array<f32>;
@group(0) @binding(1) var<storage, read_write> colors: array<vec4f>;

override minimum: f32 = 0.0;
override maximum: f32 = 1.0;
override width: u32;

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) invocation: vec3u) {
    if invocation.x >= width || invocation.y >= arrayLength(&values) / width {
        return;
    }
    let index = invocation.y * width + invocation.x;
    colors[index] = colorize(values[index], minimum, maximum);
}
