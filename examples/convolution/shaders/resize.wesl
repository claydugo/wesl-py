enable f16;

@id(0) override input_height: u32;
@id(1) override input_width: u32;
@id(2) override channels: u32;
@id(3) override scale: u32;

@group(0) @binding(0) var<storage, read_write> output: array<f16>;
@group(0) @binding(1) var<storage, read> input: array<f16>;

@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) global: vec3u) {
    let output_width = input_width * scale;
    let output_height = input_height * scale;
    let channel = global.x / (output_width * output_height);
    if (channel < channels) {
        let input_y = global.x / output_width % output_height / scale;
        let input_x = global.x % output_width / scale;
        output[global.x] = input[(channel * input_height + input_y) * input_width + input_x];
    }
}
