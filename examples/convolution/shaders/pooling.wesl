enable f16;

@id(0) override input_height: u32;
@id(1) override input_width: u32;
@id(2) override channels: u32;
@id(3) override kernel_size: u32;
@id(4) override stride: u32;
@id(5) override padding: u32;

@group(0) @binding(0) var<storage, read_write> output: array<f16>;
@group(0) @binding(1) var<storage, read> input: array<f16>;

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) global: vec3u) {
    let output_width = (input_width + 2u * padding - kernel_size) / stride + 1u;
    let output_height = (input_height + 2u * padding - kernel_size) / stride + 1u;
    let channel = global.x / (output_width * output_height);
    if (channel >= channels) {
        return;
    }
    let output_y = global.x / output_width % output_height;
    let output_x = global.x % output_width;
    var maximum = f16(bitcast<f32>(0xff800000u));
    for (var kernel_y = 0u; kernel_y < kernel_size; kernel_y++) {
        for (var kernel_x = 0u; kernel_x < kernel_size; kernel_x++) {
            let input_y = i32(output_y * stride + kernel_y) - i32(padding);
            let input_x = i32(output_x * stride + kernel_x) - i32(padding);
            if (input_y >= 0 && input_x >= 0 && input_y < i32(input_height) && input_x < i32(input_width)) {
                maximum = max(maximum, input[(channel * input_height + u32(input_y)) * input_width + u32(input_x)]);
            }
        }
    }
    output[global.x] = maximum;
}
