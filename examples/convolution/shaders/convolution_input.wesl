enable f16;

@id(0) override input_height: u32;
@id(1) override input_width: u32;
@id(2) override input_channels: u32;
@id(3) override output_channels: u32;
@id(4) override kernel_size: u32;
@id(5) override stride: u32;
@id(6) override padding: u32;
@id(7) override activation: u32;
@id(8) override first_channels: u32;
@id(9) override second_channels: u32;
@id(10) override third_channels: u32;

@group(0) @binding(1) var<storage, read> first: array<f16>;
@group(0) @binding(2) var<storage, read> second: array<f16>;
@group(0) @binding(3) var<storage, read> third: array<f16>;
@group(0) @binding(4) var<storage, read> fourth: array<f16>;

fn load(position: u32, reduction: u32) -> f16 {
    let output_width = (input_width + 2u * padding - kernel_size) / stride + 1u;
    let output_height = (input_height + 2u * padding - kernel_size) / stride + 1u;
    let channel = reduction / (kernel_size * kernel_size);
    let kernel_y = reduction / kernel_size % kernel_size;
    let kernel_x = reduction % kernel_size;
    let input_y = i32(position / output_width * stride + kernel_y) - i32(padding);
    let input_x = i32(position % output_width * stride + kernel_x) - i32(padding);
    if (position >= output_width * output_height || channel >= input_channels) {
        return 0.0h;
    }
    return load_pixel(channel, input_y, input_x);
}

fn load_pixel(channel: u32, input_y: i32, input_x: i32) -> f16 {
    if (input_y < 0 || input_x < 0 || input_y >= i32(input_height) || input_x >= i32(input_width)) {
        return 0.0h;
    }
    let plane = input_height * input_width;
    let pixel = u32(input_y) * input_width + u32(input_x);
    if (channel < first_channels) {
        return first[channel * plane + pixel];
    }
    if (channel < first_channels + second_channels) {
        return second[(channel - first_channels) * plane + pixel];
    }
    if (channel < first_channels + second_channels + third_channels) {
        return third[(channel - first_channels - second_channels) * plane + pixel];
    }
    return fourth[(channel - first_channels - second_channels - third_channels) * plane + pixel];
}
